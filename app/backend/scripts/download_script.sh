#!/bin/bash

sra_code=$1
user_id=$2
output_dir="../users/${user_id}/samples/${sra_code}"
log_file="/app/backend/logs/${sra_code}_download.log"

# Garante que o diretório de logs exista
mkdir -p /app/backend/logs

echo "Script iniciado para $sra_code (user $user_id)" >> $log_file

# Verifique se o tmux está instalado, caso contrário, instale-o
if ! command -v tmux &> /dev/null; then
    echo "tmux não está instalado. Instalando tmux..." >> $log_file
    apt-get update
    apt-get install -y tmux
fi

# Create a new directory for the sample
echo "Criando diretório de saída: $output_dir" >> $log_file
mkdir -p "$output_dir"

# Create a new tmux session and run fasterq-dump inside it
echo "Iniciando sessão tmux para fasterq-dump" >> $log_file
tmux new-session -d -s download_${user_id}_${sra_code} "fasterq-dump --progress $sra_code -O $output_dir >> $log_file 2>&1; exit_code=\$?; if [ \$exit_code -eq 0 ]; then echo 'Download completed successfully' >> $log_file; curl -X POST http://bioinfo-container:8000/samples/update_status -H 'Content-Type: application/x-www-form-urlencoded' -d 'sra_code=$sra_code&status=Completed'; else echo 'Download failed with exit code \$exit_code' >> $log_file; fi; tmux wait-for -S download_done_${user_id}_${sra_code}"

# Wait for the tmux session to finish
echo "Aguardando término da sessão tmux" >> $log_file
tmux wait-for download_done_${user_id}_${sra_code}

# Clean up the tmux session
echo "Finalizando sessão tmux" >> $log_file
tmux kill-session -t download_${user_id}_${sra_code}

# Print the log file content for debugging
echo "Conteúdo do log:" >> $log_file
cat $log_file

# Exit with the correct status code
echo "Saindo com status code $exit_code" >> $log_file
exit $exit_code