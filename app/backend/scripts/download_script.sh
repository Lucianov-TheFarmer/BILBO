#!/bin/bash

sra_code=$1
output_dir=$2

# Verifique se o tmux está instalado, caso contrário, instale-o
if ! command -v tmux &> /dev/null; then
    echo "tmux não está instalado. Instalando tmux..."
    apt-get update
    apt-get install -y tmux
fi

# Create a new tmux session and run fasterq-dump inside it
tmux new-session -d -s download_session "fasterq-dump $sra_code -p -x --split-files -O $output_dir -t $output_dir; exit_code=\$?; if [ \$exit_code -eq 0 ]; then echo 'Download completed successfully'; curl -X POST http://bioinfo-container:8000/samples/update_status -H 'Content-Type: application/x-www-form-urlencoded' -d 'sra_code=$sra_code&status=Completed'; fi; tmux wait-for -S download_done"

# Wait for the tmux session to finish
tmux wait-for download_done

# Clean up the tmux session
tmux kill-session -t download_session

# Exit with the correct status code
exit $exit_code