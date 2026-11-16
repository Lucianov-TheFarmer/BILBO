#!/bin/bash

set -euo pipefail

sra_code="$1"
user_id="$2"

sample_stem="${sra_code%.gz}"
sample_stem="${sample_stem%.fastq}"
sample_stem="${sample_stem%.fq}"
sra_code_base="$(printf '%s' "$sample_stem" | sed -E 's/(_R?[12])$//')"
input_file="/users/${user_id}/samples/${sra_code_base}/${sra_code}"
output_dir="/users/${user_id}/QC/${sra_code_base}"
log_file="${output_dir}/${sra_code}_quality_analysis.log"

mkdir -p "$output_dir"

if [ ! -f "$input_file" ]; then
  echo "Input file not found: $input_file" > "$log_file"
  exit 2
fi

if command -v timeout >/dev/null 2>&1; then
  timeout 30m fastqc -o "$output_dir" "$input_file" > "$log_file" 2>&1
else
  fastqc -o "$output_dir" "$input_file" > "$log_file" 2>&1
fi

exit_code=$?
if [ "$exit_code" -eq 0 ]; then
  echo "Quality analysis completed successfully" >> "$log_file"
else
  echo "Quality analysis failed with exit code $exit_code" >> "$log_file"
fi

exit "$exit_code"
