#!/bin/bash

set -euo pipefail

sra_code="$1"
user_id="$2"
# Normalize base names: remove .fastq and optional _trimmed/_1/_2 to get base
sra_code_base=$(echo "$sra_code" | sed -E 's/(_1|_2|_trimmed)?\.fastq$//')
# sra_base without _1/_2 (folder grouping like pre-trim QC)
sra_base=$(echo "$sra_code_base" | sed -E 's/(_[12])$//')
output_dir="../users/${user_id}/QC_PostTrim/${sra_base}"
log_file="/tmp/${sra_code}_quality_analysis_post_trim.log"

echo "Starting quality_analysis_post_trim for $sra_code (user $user_id)" > "$log_file"

mkdir -p "$output_dir"

# Input file is expected to be ../users/<user>/trimmed/<sra_code>
input_file="../users/${user_id}/trimmed/${sra_code}"
if [ ! -f "$input_file" ]; then
    echo "Input file not found: $input_file" >> "$log_file"
    exit 2
fi

# Determine sample basename (without path and .fastq)
sample_basename=$(basename "$sra_code" .fastq)

# Run fastqc with timeout to avoid hangs
if command -v timeout >/dev/null 2>&1; then
    RUN_CMD=(timeout 30m fastqc -t 4 -o "$output_dir" "$input_file")
else
    RUN_CMD=(fastqc -t 4 -o "$output_dir" "$input_file")
fi

"${RUN_CMD[@]}" >> "$log_file" 2>&1 || true
exit_code=$?

# Expected zip path produced by FastQC
expected_zip="$output_dir/${sample_basename}_fastqc.zip"

echo "FastQC exit_code=$exit_code" >> "$log_file"
echo "Expected zip: $expected_zip" >> "$log_file"
echo "Output dir listing:" >> "$log_file"
ls -la "$output_dir" >> "$log_file" 2>&1 || true

if [ $exit_code -eq 0 ] && [ -f "$expected_zip" ]; then
    echo "Post-trim quality analysis completed successfully and zip found." >> "$log_file"
    # Extract base sra code (remove _1/_2, _trimmed, and .fastq)
    sra_code_base=$(echo "$sra_code" | sed -E 's/(_1|_2|_trimmed)?\.fastq$//')
    curl -s -X POST http://bioinfo-container:8000/quality_analysis_post_trim/update_status -H 'Content-Type: application/x-www-form-urlencoded' -d "sra_code=$sra_code_base&new_status=Completed" >> "$log_file" 2>&1 || true
else
    echo "Post-trim quality analysis failed or zip missing (exit_code=$exit_code)." >> "$log_file"
    sra_code_base=$(echo "$sra_code" | sed -E 's/(_1|_2|_trimmed)?\.fastq$//')
    echo "Will report status Failed for $sra_code_base" >> "$log_file"
    curl -s -X POST http://bioinfo-container:8000/quality_analysis_post_trim/update_status -H 'Content-Type: application/x-www-form-urlencoded' -d "sra_code=$sra_code_base&new_status=Failed" >> "$log_file" 2>&1 || true
fi

echo "----- log output -----" >> "$log_file"
cat "$log_file" >> "$log_file" 2>&1 || true

exit $exit_code