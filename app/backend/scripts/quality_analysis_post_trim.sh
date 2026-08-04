#!/usr/bin/env bash

set -euo pipefail

sra_code="$1"
user_id="$2"

sample_file="$(basename "$sra_code")"

sample_stem="$sample_file"
sample_stem="${sample_stem%.gz}"
sample_stem="${sample_stem%.fastq}"
sample_stem="${sample_stem%.fq}"

without_trimmed="${sample_stem%_trimmed}"
sra_base="$(echo "$without_trimmed" | sed -E 's/(_R?[12])$//')"

output_dir="/users/${user_id}/QC_PostTrim/${sra_base}"
input_file="/users/${user_id}/trimmed/${sra_code}"
log_file="/tmp/${sample_stem}_quality_analysis_post_trim.log"

mkdir -p "$output_dir"

if [ ! -f "$input_file" ]; then
    echo "Input file not found: $input_file" > "$log_file"
    exit 2
fi

if command -v timeout >/dev/null 2>&1; then
    timeout 170m fastqc \
        -t 4 \
        -o "$output_dir" \
        "$input_file" \
        > "$log_file" 2>&1
else
    fastqc \
        -t 4 \
        -o "$output_dir" \
        "$input_file" \
        > "$log_file" 2>&1
fi

exit_code=$?

expected_zip="$output_dir/${sample_stem}_fastqc.zip"
expected_html="$output_dir/${sample_stem}_fastqc.html"

if [ "$exit_code" -eq 0 ] \
   && [ -f "$expected_zip" ] \
   && [ -f "$expected_html" ]; then

    echo "Post-trim quality analysis completed successfully." >> "$log_file"
    exit 0
fi

echo \
    "Post-trim QC failed or expected outputs missing (exit_code=${exit_code})." \
    >> "$log_file"

exit "${exit_code:-1}"
