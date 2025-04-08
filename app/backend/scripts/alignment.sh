#!/bin/bash

sample=$1
output_dir=$2
log_file="/tmp/${sample}_alignment.log"

echo "Iniciando alinhamento para $sample" > $log_file

# Simulação de comando de alinhamento (substituir pelo real, ex.: STAR, HISAT2, etc.)
echo "Executando alinhamento para $sample..." >> $log_file
sleep 5  # Simula o tempo de execução
echo "Alinhamento concluído para $sample" >> $log_file

# Salvar o log no diretório de saída
cp $log_file "$output_dir/${sample}_alignment.log"
