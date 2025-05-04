#!/bin/bash

sample_name=$1
user_id=$2
feature_type=$3
id_attribute=$4
alignment_dir="../users/${user_id}/alignment/${sample_name%.bam}"
ref_genome_dir="../users/ref_genomes/GCF_000005845.2"
output_dir="../users/${user_id}/quantification"
log_file="/tmp/${sample_name}_quantification.log"

# Criar o diretório de saída, se não existir
mkdir -p "$output_dir"

# Caminho do arquivo de entrada e saída
input_file="${alignment_dir}/${sample_name}"
output_file="${output_dir}/${sample_name%.bam}.txt"
gff_file="${ref_genome_dir}/genomic.gff"

# Emitir log de início
echo "Iniciando quantificação para a amostra $sample_name do usuário $user_id" >> "$log_file"

# Verificar se os arquivos de entrada existem
if [ ! -f "$input_file" ]; then
    echo "Erro: Arquivo de entrada $input_file não encontrado." >> "$log_file"
    exit 1
fi

if [ ! -f "$gff_file" ]; then
    echo "Erro: Arquivo GFF $gff_file não encontrado." >> "$log_file"
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
