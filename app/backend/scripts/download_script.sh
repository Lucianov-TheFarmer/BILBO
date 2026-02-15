#!/bin/bash

set -euo pipefail

sra_code="$1"
user_id="$2"
output_dir="/users/${user_id}/samples/${sra_code}"
log_file="/app/backend/logs/${sra_code}_download.log"

mkdir -p /app/backend/logs
mkdir -p "$output_dir"

echo "[download] Starting download for ${sra_code} (user ${user_id})" > "$log_file"

if command -v timeout >/dev/null 2>&1; then
  timeout 6h fasterq-dump --progress "$sra_code" -O "$output_dir" >> "$log_file" 2>&1
else
  fasterq-dump --progress "$sra_code" -O "$output_dir" >> "$log_file" 2>&1
fi

exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  echo "[download] Completed successfully" >> "$log_file"
else
  echo "[download] Failed with exit code ${exit_code}" >> "$log_file"
fi

exit "$exit_code"
