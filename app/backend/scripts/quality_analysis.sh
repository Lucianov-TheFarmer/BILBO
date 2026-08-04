#!/bin/bash

set -euo pipefail

sra_code="$1"
user_id="$2"

case "$sra_code" in
  *_1.fastq.gz) sra_code_base="${sra_code%_1.fastq.gz}" ;;
  *_2.fastq.gz) sra_code_base="${sra_code%_2.fastq.gz}" ;;
  *_1.fq.gz)    sra_code_base="${sra_code%_1.fq.gz}" ;;
  *_2.fq.gz)    sra_code_base="${sra_code%_2.fq.gz}" ;;
  *_1.fastq)    sra_code_base="${sra_code%_1.fastq}" ;;
  *_2.fastq)    sra_code_base="${sra_code%_2.fastq}" ;;
  *_1.fq)       sra_code_base="${sra_code%_1.fq}" ;;
  *_2.fq)       sra_code_base="${sra_code%_2.fq}" ;;
  *)            sra_code_base="$sra_code" ;;
esac
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
