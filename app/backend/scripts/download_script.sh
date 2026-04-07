#!/bin/bash

set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <sra_code> <user_id>" >&2
  exit 1
fi

sra_code="$1"
user_id="$2"
output_dir="/users/${user_id}/samples/${sra_code}"
log_file="/app/backend/logs/${sra_code}_download.log"
temp_dir="${output_dir}/tmp"
max_download_attempts="${FASTERQ_MAX_ATTEMPTS:-3}"

mkdir -p /app/backend/logs
mkdir -p "$output_dir"
mkdir -p "$temp_dir"

resolve_bin() {
  local name="$1"
  shift

  if command -v "$name" >/dev/null 2>&1; then
    command -v "$name"
    return 0
  fi

  for candidate in "$@"; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

FASTERQ_BIN="$(resolve_bin fasterq-dump "/usr/local/sratoolkit/bin/fasterq-dump" "/opt/conda/envs/bioinfo/bin/fasterq-dump" "/opt/conda/bin/fasterq-dump")" || {
  echo "[download] Error: fasterq-dump command not found." > "$log_file"
  exit 1
}

run_fasterq_once() {
  if command -v timeout >/dev/null 2>&1; then
    timeout 6h "$FASTERQ_BIN" --progress --split-files --skip-technical -t "$temp_dir" -O "$output_dir" "$sra_code"
  else
    "$FASTERQ_BIN" --progress --split-files --skip-technical -t "$temp_dir" -O "$output_dir" "$sra_code"
  fi
}

echo "[download] Starting download for ${sra_code} (user ${user_id})" > "$log_file"
echo "[download] Using fasterq-dump binary: ${FASTERQ_BIN}" >> "$log_file"

last_exit_code=1
for attempt in $(seq 1 "$max_download_attempts"); do
  echo "[download] Attempt ${attempt}/${max_download_attempts}: direct fasterq-dump" >> "$log_file"

  rm -f "$output_dir/${sra_code}_1.fastq" "$output_dir/${sra_code}_2.fastq"
  rm -rf "$temp_dir"
  mkdir -p "$temp_dir"

  if run_fasterq_once >> "$log_file" 2>&1; then
    if [ -s "$output_dir/${sra_code}_1.fastq" ] && [ -s "$output_dir/${sra_code}_2.fastq" ]; then
      echo "[download] Completed successfully" >> "$log_file"
      exit 0
    fi

    echo "[download] Attempt ${attempt} produced incomplete FASTQ pair." >> "$log_file"
    ls -lah "$output_dir" >> "$log_file" 2>&1 || true
    last_exit_code=4
  else
    last_exit_code=$?
    echo "[download] Attempt ${attempt} failed with exit code ${last_exit_code}." >> "$log_file"
  fi

  sleep 3
done

echo "[download] Failed with exit code ${last_exit_code}" >> "$log_file"

if grep -q "missing the QUALITY-column" "$log_file"; then
  echo "[download] Hint: accession appears to be SRA Lite/no-quality for this path or with remote validation issue." >> "$log_file"
fi

exit "$last_exit_code"
