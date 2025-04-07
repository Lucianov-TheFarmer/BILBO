#!/bin/bash

sra_code=$1
user_id=$2
token=$3  # Adicionado para receber o token como argumento
output_dir="../users/${user_id}/QC_PostTrim/$sra_code"
log_file="/tmp/${sra_code}_quality_analysis_post_trim.log"

if ! command -v tmux &> /dev/null; then
    echo "tmux não está instalado. Instalando tmux..." >> $log_file
    apt-get update >> $log_file 2>&1
    apt-get install -y tmux >> $log_file 2>&1
fi

sra_code_base=${sra_code%_[12].fastq}

echo "Criando diretório para análise de qualidade pós-trimmagem: $output_dir" >> $log_file
mkdir -p $output_dir

echo "Iniciando sessão tmux para fastqc pós-trimmagem" >> $log_file
tmux new-session -d -s QC_PostTrim_$user_id "fastqc -o $output_dir ../users/$user_id/trimmed/$sra_code >> $log_file 2>&1; exit_code=\$?; if [ \$exit_code -eq 0 ]; then echo 'Análise de qualidade pós-trimmagem concluída com sucesso' >> $log_file; curl -X POST http://bioinfo-container:8000/quality_analysis_post_trim/update_status -H 'Content-Type: application/x-www-form-urlencoded' -H \"Authorization: Bearer $token\" -d \"sra_code=$sra_code_base&status=Completed\" >> $log_file 2>&1; else echo 'Análise de qualidade pós-trimmagem falhou com código de saída \$exit_code' >> $log_file; fi; tmux wait-for -S quality_analysis_post_trim_done"

echo "Aguardando finalização da sessão tmux" >> $log_file
tmux wait-for quality_analysis_post_trim_done

echo "Encerrando sessão tmux" >> $log_file
tmux kill-session -t QC_PostTrim_$user_id

echo "Conteúdo do arquivo de log:" >> $log_file
cat $log_file

exit $exit_code