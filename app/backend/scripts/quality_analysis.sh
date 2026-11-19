#!/bin/bash

set -euo pipefail

sra_code="$1"
user_id="$2"
users_root="${BILBO_USERS_ROOT:-/users}"

sample_stem="${sra_code%.gz}"
sample_stem="${sample_stem%.fastq}"
sample_stem="${sample_stem%.fq}"
sra_code_base="$(printf '%s' "$sample_stem" | sed -E 's/(_R?[12])$//')"
input_file="${users_root}/${user_id}/samples/${sra_code_base}/${sra_code}"
output_dir="${users_root}/${user_id}/QC/${sra_code_base}"
log_file="${output_dir}/${sra_code}_quality_analysis.log"

mkdir -p "$output_dir"

if [ ! -f "$input_file" ]; then
  echo "Input file not found: $input_file" > "$log_file"
  exit 2
fi

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "FastQC started at ${started_at}; input=${sra_code}" > "$log_file"
set +e
fastqc -o "$output_dir" "$input_file" >> "$log_file" 2>&1
exit_code=$?
set -e

expected_zip="$output_dir/${sample_stem}_fastqc.zip"
expected_html="$output_dir/${sample_stem}_fastqc.html"
if [ "$exit_code" -eq 0 ] && { [ ! -s "$expected_zip" ] || [ ! -s "$expected_html" ]; }; then
  echo "FastQC exited successfully but its HTML or ZIP report is missing." >> "$log_file"
  exit_code=3
fi
case "$exit_code" in
  0) echo "FastQC completed successfully at $(date -u +%Y-%m-%dT%H:%M:%SZ)." >> "$log_file" ;;
  137) echo "FastQC was killed (exit code 137); check container memory and worker logs." >> "$log_file" ;;
  *) echo "FastQC failed with exit code ${exit_code} at $(date -u +%Y-%m-%dT%H:%M:%SZ)." >> "$log_file" ;;
esac

exit "$exit_code"
