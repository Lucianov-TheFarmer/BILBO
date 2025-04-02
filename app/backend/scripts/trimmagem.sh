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
session_name="trimmagem_${sra_code}"

# Caminho absoluto para os adaptadores
adapters_dir="/app/backend/scripts/adapters"

# Verifique se o tmux está instalado, caso contrário, instale-o
if ! command -v tmux &> /dev/null; then
    echo "tmux não está instalado. Instalando tmux..." >> $log_file
    apt-get update >> $log_file 2>&1
    apt-get install -y tmux >> $log_file 2>&1
fi

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

# Use the absolute path for the adapter file
adapter_file="$adapters_dir/$adapter_file"

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

# Start tmux session and run the command
echo "Starting tmux session for trimmagem: $session_name" >> $log_file
tmux new-session -d -s "$session_name" "
    echo 'Executing: ${command[*]}' >> $log_file;
    ${command[*]} >> $log_file 2>&1;
    exit_code=\$?;
    if [ \$exit_code -eq 0 ]; then
        echo 'Trimmagem completed successfully' >> $log_file;
    else
        echo 'Trimmagem failed with exit code \$exit_code' >> $log_file;
    fi;
    tmux wait-for -S trimmagem_done
"

# Wait for the tmux session to finish
echo "Waiting for tmux session to finish" >> $log_file
tmux wait-for trimmagem_done

# Clean up the tmux session
echo "Cleaning up tmux session" >> $log_file
tmux kill-session -t "$session_name"

# Print the log file content for debugging
echo "Log file content:" >> $log_file
cat $log_file

# Ensure the correct exit code is returned
if grep -q "Trimmagem completed successfully" "$log_file"; then
    echo "Trimmagem completed successfully" >> $log_file
    exit 0
else
    echo "Trimmagem failed" >> $log_file
    exit 1
fi
