#!/bin/sh
set -eu

ollama serve &
server_pid=$!

attempt=0
until ollama list >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 60 ]; then
        echo "Ollama did not become ready within 60 seconds" >&2
        exit 1
    fi
    sleep 1
done

pull_model() {
    model="$1"
    [ -n "$model" ] || return 0
    ollama pull "$model" || echo "Warning: unable to pull Ollama model $model" >&2
}

(
    pull_model "${OLLAMA_CLUSTER_MODEL:-gemma4:e4b}"
    if [ "${OLLAMA_RAG_MODEL:-gemma4:e4b}" != "${OLLAMA_CLUSTER_MODEL:-gemma4:e4b}" ]; then
        pull_model "${OLLAMA_RAG_MODEL:-gemma4:e4b}"
    fi
    pull_model "${OLLAMA_EMBEDDING_MODEL:-bge-m3:latest}"
) &

wait "$server_pid"
