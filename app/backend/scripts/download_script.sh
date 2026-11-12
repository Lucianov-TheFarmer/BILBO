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

layout="$(curl -fsS --max-time 20 "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=${sra_code}&result=read_run&fields=library_layout&format=tsv" 2>/dev/null | awk -F '\t' 'NR == 2 {print $1}' || true)"
case "$layout" in SINGLE|PAIRED) ;; *) layout="UNKNOWN" ;; esac

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
echo "[download] Library layout: ${layout}" >> "$log_file"

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

    if [ "$layout" = "SINGLE" ] && [ -s "$output_dir/${sra_code}.fastq" ]; then
      mv "$output_dir/${sra_code}.fastq" "$output_dir/${sra_code}_1.fastq"
    fi
    if [ -s "$output_dir/${sra_code}_1.fastq" ] && [ ! -s "$output_dir/${sra_code}_2.fastq" ]; then
      spots="$(grep -E '^spots read[[:space:]]*:' "$log_file" | tail -1 | sed 's/.*:[[:space:]]*//; s/,//g' || true)"
      written="$(grep -E '^reads written[[:space:]]*:' "$log_file" | tail -1 | sed 's/.*:[[:space:]]*//; s/,//g' || true)"
      zero="$(grep -E '^reads 0-length[[:space:]]*:' "$log_file" | tail -1 | sed 's/.*:[[:space:]]*//; s/,//g' || true)"
      if [ "$layout" = "SINGLE" ] || { [ "$layout" = "UNKNOWN" ] && [ -n "$spots" ] && [ "$spots" = "$written" ] && [ "$spots" = "$zero" ]; }; then
        echo "[download] Completed single-end library" >> "$log_file"
        exit 0
      fi
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
