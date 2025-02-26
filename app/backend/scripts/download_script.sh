#!/bin/bash

sra_code=$1
output_dir=$2
log_file="/tmp/${sra_code}_download.log"

# Verifique se o tmux está instalado, caso contrário, instale-o
if ! command -v tmux &> /dev/null; then
    echo "tmux não está instalado. Instalando tmux..."
    apt-get update
    apt-get install -y tmux
fi

# Create a new directory for the sample
echo "Creating directory for sample: $sra_code"
mkdir -p $sra_code

# Create a new tmux session and run fasterq-dump inside it
echo "Starting tmux session for fasterq-dump"
tmux new-session -d -s download_session "fasterq-dump --progress $sra_code -O $sra_code > $log_file 2>&1; exit_code=\$?; if [ \$exit_code -eq 0 ]; then echo 'Download completed successfully' >> $log_file; mv $sra_code/${sra_code}_*.fastq $output_dir; rm -rf ../../../samples/sra; rmdir $sra_code; curl -X POST http://bioinfo-container:8000/samples/update_status -H 'Content-Type: application/x-www-form-urlencoded' -d 'sra_code=$sra_code&status=Completed'; else echo 'Download failed with exit code \$exit_code' >> $log_file; fi; tmux wait-for -S download_done"

# Wait for the tmux session to finish
echo "Waiting for tmux session to finish"
tmux wait-for download_done

# Clean up the tmux session
echo "Cleaning up tmux session"
tmux kill-session -t download_session

# Print the log file content for debugging
echo "Log file content:"
cat $log_file

# Exit with the correct status code
echo "Exiting with status code $exit_code"
exit $exit_code