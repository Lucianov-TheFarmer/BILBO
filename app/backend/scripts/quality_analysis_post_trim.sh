#!/bin/bash

set -euo pipefail

sra_code="$1"
user_id="$2"
sra_code_base=$(echo "$sra_code" | sed -E 's/(_1|_2|_trimmed)?\.fastq$//')
sra_base=$(echo "$sra_code_base" | sed -E 's/(_[12])$//')
output_dir="/users/${user_id}/QC_PostTrim/${sra_base}"
log_file="/tmp/${sra_code}_quality_analysis_post_trim.log"

mkdir -p "$output_dir"
input_file="/users/${user_id}/trimmed/${sra_code}"

if [ ! -f "$input_file" ]; then
  echo "Input file not found: $input_file" > "$log_file"
  exit 2
fi

sample_basename=$(basename "$sra_code" .fastq)

if command -v timeout >/dev/null 2>&1; then
  timeout 30m fastqc -t 4 -o "$output_dir" "$input_file" > "$log_file" 2>&1
else
  fastqc -t 4 -o "$output_dir" "$input_file" > "$log_file" 2>&1
fi

exit_code=$?
expected_zip="$output_dir/${sample_basename}_fastqc.zip"

if [ "$exit_code" -eq 0 ] && [ -f "$expected_zip" ]; then
  echo "Post-trim quality analysis completed successfully." >> "$log_file"
else
  echo "Post-trim quality analysis failed or zip missing (exit_code=${exit_code})." >> "$log_file"
fi

exit "$exit_code"
