#!/bin/bash

sra_code=$1
threads=$2
phred=$3
illumina_clip=$4
sliding_window=$5
max_info=$6
leading=$7
trailing=$8
crop=$9
headcrop=${10}
minlen=${11}
avgqual=${12}
base_path=${13}
trimmed_path=${14}


log_file="/tmp/${sra_code}_trimmagem.log"


# Caminho absoluto para os adaptadores
adapters_dir="/app/backend/scripts/adapters"

set -u
set -o pipefail


# Determine if the sample is PE or SE
input_file_1="$base_path/$sra_code/${sra_code}_1.fastq"
input_file_2="${input_file_1/_1.fastq/_2.fastq}"

if [[ -f "$input_file_1" ]]; then
    if [[ -f "$input_file_2" ]]; then
        is_paired=true
    else
        is_paired=false
    fi
else
    echo "Arquivo $input_file_1 não encontrado." >> $log_file
    exit 1
fi

# Determine Phred encoding if autodetect is selected
if [[ "$phred" == "autodetect" ]]; then
    first_line=$(head -n 40 "$input_file_1" | tail -n 1)
    if [[ "$first_line" =~ [!-I] ]]; then
        phred="phred33"
    else
        phred="phred64"
    fi
fi

# Create output directory
output_base="$trimmed_path/${sra_code/_1.fastq/}"
mkdir -p "$(dirname "$output_base")"

# Parse illumina_clip JSON
adapter_file=$(echo "$illumina_clip" | jq -r '.["Arquivo adaptadores"]')
seed_mismatches=$(echo "$illumina_clip" | jq -r '.["Seed mismatches"]')
threshold_palindrome=$(echo "$illumina_clip" | jq -r '.["Threshold palindromo"]')
threshold_simple=$(echo "$illumina_clip" | jq -r '.["Threshold simples"]')
min_adapter_length=$(echo "$illumina_clip" | jq -r '.["Comprimento minimo adaptador"]')

# Use the absolute path for the adapter file. If adapter_file is already an absolute path, keep it.
if [[ "$adapter_file" = /* ]]; then
    adapter_file="$adapter_file"
else
    adapter_file="$adapters_dir/$adapter_file"
fi

# Validate parsed values
if [[ -z "$adapter_file" || -z "$seed_mismatches" || -z "$threshold_palindrome" || -z "$threshold_simple" || -z "$min_adapter_length" ]]; then
    echo "Erro ao processar illumina_clip JSON." >> $log_file
    exit 1
fi

# Build the Trimmomatic command
if [[ "$is_paired" == true ]]; then
    command=(
        trimmomatic PE
        -threads "$threads"
        "-$phred"
        "$input_file_1" "$input_file_2"
        "${output_base}_1_trimmed.fastq" "${output_base}_1_unpaired.fastq"
        "${output_base}_2_trimmed.fastq" "${output_base}_2_unpaired.fastq"
        "ILLUMINACLIP:$adapter_file:$seed_mismatches:$threshold_palindrome:$threshold_simple:$min_adapter_length"
        "SLIDINGWINDOW:$(echo "$sliding_window" | jq -r '.["Tamanho janela"]'):$(echo "$sliding_window" | jq -r '.["Qualidade minima"]')"
        "LEADING:$leading"
        "TRAILING:$trailing"
        "MINLEN:$minlen"
    )
else
    command=(
        trimmomatic SE
        -threads "$threads"
        "-$phred"
        "$input_file_1"
        "${output_base}_trimmed.fastq"
        "ILLUMINACLIP:$adapter_file:$seed_mismatches:$threshold_palindrome:$threshold_simple:$min_adapter_length"
        "SLIDINGWINDOW:$(echo "$sliding_window" | jq -r '.["Tamanho janela"]'):$(echo "$sliding_window" | jq -r '.["Qualidade minima"]')"
        "LEADING:$leading"
        "TRAILING:$trailing"
        "MINLEN:$minlen"
    )
fi

# Add optional parameters
[[ -n "$crop" ]] && command+=("CROP:$crop")
[[ -n "$headcrop" ]] && command+=("HEADCROP:$headcrop")
[[ -n "$avgqual" ]] && command+=("AVGQUAL:$avgqual")

# Execute the command directly (avoid tmux). Use timeout if available to prevent hangs.
echo "Executing trimming command: ${command[*]}" >> "$log_file"
if command -v timeout >/dev/null 2>&1; then
    RUN_CMD=(timeout 60m "${command[0]}" "${command[@]:1}")
else
    RUN_CMD=("${command[@]}")
fi

"${RUN_CMD[@]}" >> "$log_file" 2>&1 || true
exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo "Trimmagem completed successfully" >> "$log_file"
else
    echo "Trimmagem failed with exit code $exit_code" >> "$log_file"
fi

# Print the log file content for debugging
echo "----- log output -----" >> "$log_file"
cat "$log_file" >> "$log_file" 2>&1 || true

exit $exit_code
