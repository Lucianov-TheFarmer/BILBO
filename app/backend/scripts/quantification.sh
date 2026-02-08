#!/bin/bash

sample_name=$1
user_id=$2
feature_type=$3
id_attribute=$4
alignment_dir="../users/${user_id}/alignment/${sample_name%.bam}"
# Optional 5th parameter: genome accession or absolute/relative path to ref_genome dir
genome_param="$5"

# log and output (defined early so detection errors can be logged)
output_dir="../users/${user_id}/quantification"
log_file="/tmp/${sample_name}_quantification.log"

# Determine reference genome directory
if [ -n "$genome_param" ]; then
    if [ -d "$genome_param" ]; then
        ref_genome_dir="$genome_param"
    else
        ref_genome_dir="../users/ref_genomes/${genome_param}"
    fi
else
    REF_PARENT="../users/ref_genomes"
    if [ -d "$REF_PARENT" ]; then
        # find candidate dirs containing genomic.gff or genomic.gtf
        candidates=()
        while IFS= read -r -d $'\0' dir; do
            candidates+=("$dir")
        done < <(find "$REF_PARENT" -maxdepth 2 -type f \( -name "genomic.gff" -o -name "genomic.gtf" \) -printf "%h\0" | sort -uz)

        if [ ${#candidates[@]} -eq 1 ]; then
            ref_genome_dir="${candidates[0]}"
        else
            echo "Erro: não foi possível determinar automaticamente o ref_genome. Passe o accession ou caminho como 5º parâmetro." >> "$log_file"
            exit 1
        fi
    else
        echo "Erro: diretório ../users/ref_genomes não existe." >> "$log_file"
        exit 1
    fi
fi

# Criar o diretório de saída, se não existir
mkdir -p "$output_dir"

# Caminho do arquivo de entrada e saída
input_file="${alignment_dir}/${sample_name}"
output_file="${output_dir}/${sample_name%.bam}.txt"
# Prefer genomic.gff, fallback to genomic.gtf
if [ -f "${ref_genome_dir}/genomic.gff" ]; then
    gff_file="${ref_genome_dir}/genomic.gff"
elif [ -f "${ref_genome_dir}/genomic.gtf" ]; then
    gff_file="${ref_genome_dir}/genomic.gtf"
else
    gff_file=""
fi

# Emitir log de início
echo "Iniciando quantificação para a amostra $sample_name do usuário $user_id" >> "$log_file"

# Verificar se os arquivos de entrada existem
if [ ! -f "$input_file" ]; then
    echo "Erro: Arquivo de entrada $input_file não encontrado." >> "$log_file"
    exit 1
fi

if [ -z "$gff_file" ] || [ ! -f "$gff_file" ]; then
    echo "Erro: Arquivo GFF/GTF não encontrado em ${ref_genome_dir}." >> "$log_file"
    exit 1
fi

# Executar htseq-count
htseq-count -a 10 -t "$feature_type" -i "$id_attribute" -f bam --stranded=no "$input_file" "$gff_file" > "$output_file" 2>> "$log_file"

# Verificar se o htseq-count foi executado com sucesso
if [ $? -eq 0 ]; then
    echo "Quantificação concluída para $sample_name" >> "$log_file"
else
    echo "Erro ao executar htseq-count para $sample_name. Verifique os parâmetros fornecidos." >> "$log_file"
    exit 1
fi
