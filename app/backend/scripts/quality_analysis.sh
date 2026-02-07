#!/bin/bash

set -euo pipefail

# usage: quality_analysis.sh <sra_filename> <user_id>
sra_code="$1"
user_id="$2"

# Determine basename and paths
sra_code_base=${sra_code%_[12].fastq}
input_file="../users/${user_id}/samples/${sra_code_base}/${sra_code}"
output_dir="../users/${user_id}/QC/${sra_code_base}"
log_file="${output_dir}/${sra_code}_quality_analysis.log"

echo "Quality analysis: input=$input_file output=$output_dir log=$log_file"

mkdir -p "$output_dir"

# Quick sanity checks
if [ ! -f "$input_file" ]; then
    echo "Input file not found: $input_file" >&2
    exit 2
fi

# Prefer timeout if available to avoid indefinite hangs
if command -v timeout >/dev/null 2>&1; then
    RUN_CMD=(timeout 30m fastqc -o "$output_dir" "$input_file")
else
    RUN_CMD=(fastqc -o "$output_dir" "$input_file")
fi

"${RUN_CMD[@]}" > "$log_file" 2>&1 || true
exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo "Quality analysis completed successfully" >> "$log_file"
    curl -s -X POST http://bioinfo-container:8000/quality_analysis/update_status -H 'Content-Type: application/x-www-form-urlencoded' -d "sra_code=${sra_code_base}&status=Completed" || true
else
    echo "Quality analysis failed with exit code $exit_code" >> "$log_file"
    curl -s -X POST http://bioinfo-container:8000/quality_analysis/update_status -H 'Content-Type: application/x-www-form-urlencoded' -d "sra_code=${sra_code_base}&status=Failed" || true
fi

echo "----- log output -----"
cat "$log_file" || true

echo "Exiting with status code $exit_code"
exit $exit_code
