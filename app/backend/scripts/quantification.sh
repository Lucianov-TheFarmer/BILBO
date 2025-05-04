#!/bin/bash

sample_name=$1
user_id=$2
output_dir="../users/${user_id}/quantification"
log_file="/tmp/${sample_name}_quantification.log"

# Criar o diretório de saída, se não existir
mkdir -p "$output_dir"

# Caminho do arquivo de saída
output_file="${output_dir}/${sample_name%.bam}.txt"

# Emitir log de início
echo "Iniciando quantificação para a amostra $sample_name do usuário $user_id" >> "$log_file"

# Simular o processo de quantificação
sleep 5  # Placeholder para o processo real

# Gerar o arquivo de saída
echo "Resultados da quantificação para $sample_name" > "$output_file"

# Verificar se o arquivo foi gerado corretamente
if [ -f "$output_file" ]; then
    echo "Quantificação concluída para $sample_name" >> "$log_file"
else
    echo "Erro ao gerar o arquivo de quantificação para $sample_name" >> "$log_file"
    exit 1
fi
