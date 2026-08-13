#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ollama_models="${BILBO_OLLAMA_MODELS:-${project_root}/.runtime/ollama-models}"
ollama_url="http://127.0.0.1:11436"
ollama_log="${project_root}/benchmarks/rag_evaluation/work/ollama-safe.log"
output_dir="${1:-/workspace/benchmarks/rag_evaluation/work/improved_interpretations}"
gene_limit="${BILBO_SAFE_GENE_LIMIT:-}"
ollama_pid=""

cleanup() {
  if [[ -n "${ollama_pid}" ]] && kill -0 "${ollama_pid}" 2>/dev/null; then
    kill "${ollama_pid}" 2>/dev/null || true
    wait "${ollama_pid}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

cd "${project_root}"
mkdir -p "$(dirname "${ollama_log}")"

available_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
if [[ -z "${available_kib}" ]] || (( available_kib < 6291456 )); then
  echo "Execução recusada: são necessários pelo menos 6 GiB de RAM disponível; detectado $((available_kib / 1024)) MiB." >&2
  exit 1
fi

# Never keep the 11 GiB Compose Ollama beside the host GPU process.
if docker ps --format '{{.Names}}' | grep -Fxq 'ollama-container'; then
  docker stop --time 20 ollama-container >/dev/null
fi

docker compose up -d --no-deps qdrant

if ! curl -fsS --max-time 2 "${ollama_url}/api/tags" >/dev/null 2>&1; then
  if [[ ! -d "${ollama_models}" ]]; then
    echo "O diretório de modelos não existe: ${ollama_models}" >&2
    exit 1
  fi
  env \
    OLLAMA_HOST=127.0.0.1:11436 \
    OLLAMA_MODELS="${ollama_models}" \
    OLLAMA_MAX_LOADED_MODELS=1 \
    OLLAMA_NUM_PARALLEL=1 \
    OLLAMA_KEEP_ALIVE=20s \
    OLLAMA_FLASH_ATTENTION=1 \
    OLLAMA_KV_CACHE_TYPE=q8_0 \
    ollama serve >"${ollama_log}" 2>&1 &
  ollama_pid=$!

  for _ in $(seq 1 60); do
    if curl -fsS --max-time 2 "${ollama_url}/api/tags" >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "${ollama_pid}" 2>/dev/null; then
      echo "O Ollama encerrou durante a inicialização. Consulte ${ollama_log}" >&2
      exit 1
    fi
    sleep 1
  done
fi

models="$(curl -fsS "${ollama_url}/api/tags")"
if [[ "${models}" != *'gemma4:e4b'* ]] || [[ "${models}" != *'bge-m3:latest'* ]]; then
  echo "Os modelos gemma4:e4b e bge-m3:latest não estão disponíveis em ${ollama_models}." >&2
  exit 1
fi

extra_args=()
if [[ -n "${gene_limit}" ]]; then
  extra_args+=(--gene-limit "${gene_limit}")
fi

docker compose --profile rag-interpretations-safe run --rm --no-deps \
  rag-interpretations-safe \
  --genes /prototype/outputs/prioritized_genes.csv \
  --cluster-interpretations /prototype/clusters/interpretations.csv \
  --output-dir "${output_dir}" \
  --qdrant-url http://127.0.0.1:6333 \
  --ollama-url http://127.0.0.1:11436/api/chat \
  --model gemma4:e4b \
  --num-ctx 8192 \
  --num-predict 1536 \
  --top-k 4 \
  --candidate-k 30 \
  --max-chunks-per-source 2 \
  --llm-attempts 3 \
  "${extra_args[@]}"
