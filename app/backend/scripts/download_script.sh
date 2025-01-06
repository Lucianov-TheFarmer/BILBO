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
tmux new-session -d -s download_session "fasterq-dump $sra_code -p -x --split-files -O $output_dir -t $output_dir"

# Capture the tmux pane output in real-time and filter for "lookup"
while tmux has-session -t download_session 2>/dev/null; do
    tmux capture-pane -pt download_session -S -100 | grep "lookup"
    sleep 1
done

# Clean up the tmux session
tmux kill-session -t download_session