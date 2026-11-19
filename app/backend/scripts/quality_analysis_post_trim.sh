#!/usr/bin/env bash

set -euo pipefail

sra_code="$1"
user_id="$2"
users_root="${BILBO_USERS_ROOT:-/users}"

sample_file="$(basename "$sra_code")"

sample_stem="$sample_file"
sample_stem="${sample_stem%.gz}"
sample_stem="${sample_stem%.fastq}"
sample_stem="${sample_stem%.fq}"

without_trimmed="${sample_stem%_trimmed}"
sra_base="$(echo "$without_trimmed" | sed -E 's/(_R?[12])$//')"

output_dir="${users_root}/${user_id}/QC_PostTrim/${sra_base}"
input_file="${users_root}/${user_id}/trimmed/${sra_code}"
log_file="${output_dir}/${sample_stem}_quality_analysis_post_trim.log"

mkdir -p "$output_dir"

if [ ! -f "$input_file" ]; then
    echo "Input file not found: $input_file" > "$log_file"
    exit 2
fi

set +e
fastqc -t 4 -o "$output_dir" "$input_file" > "$log_file" 2>&1

exit_code=$?
set -e

expected_zip="$output_dir/${sample_stem}_fastqc.zip"
expected_html="$output_dir/${sample_stem}_fastqc.html"

if [ "$exit_code" -eq 0 ] \
   && [ -f "$expected_zip" ] \
   && [ -f "$expected_html" ]; then

    echo "Post-trim quality analysis completed successfully." >> "$log_file"
    exit 0
fi

if [ "$exit_code" -eq 0 ]; then
    echo "Post-trim FastQC exited successfully but its HTML or ZIP report is missing." >> "$log_file"
    exit_code=3
elif [ "$exit_code" -eq 137 ]; then
    echo "Post-trim FastQC was killed (exit code 137); check container memory and worker logs." >> "$log_file"
else
    echo "Post-trim FastQC failed with exit code ${exit_code}." >> "$log_file"
fi

exit "$exit_code"
