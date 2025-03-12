#!/bin/bash

sra_code=$1
user_id=$2
output_dir="../users/${user_id}/QC/$sra_code"
log_file="/tmp/${sra_code}_quality_analysis.log"

# Verifique se o tmux está instalado, caso contrário, instale-o
if ! command -v tmux &> /dev/null; then
    echo "tmux não está instalado. Instalando tmux..."
    apt-get update
    apt-get install -y tmux
fi

# Create a new directory for the quality analysis
echo "Creating directory for quality analysis: $output_dir"
mkdir -p $output_dir

# Remove the extension from sra_code
sra_code_base=${sra_code%_[12].fastq}

# Create a new tmux session and run fastqc inside it
echo "Starting tmux session for fastqc"
tmux new-session -d -s QC_$user_id "fastqc -o $output_dir ../users/$user_id/samples/$sra_code_base/$sra_code > $log_file 2>&1; exit_code=\$?; if [ \$exit_code -eq 0 ]; then echo 'Quality analysis completed successfully' >> $log_file; curl -X POST http://bioinfo-container:8000/quality_analysis/update_status -H 'Content-Type: application/x-www-form-urlencoded' -d 'sra_code=$sra_code&status=Completed'; curl -X POST http://bioinfo-container:8000/quality_analysis/add_result -H 'Content-Type: application/x-www-form-urlencoded' -d 'sra_code=$sra_code&user_id=$user_id'; else echo 'Quality analysis failed with exit code \$exit_code' >> $log_file; fi; tmux wait-for -S quality_analysis_done"

# Wait for the tmux session to finish
echo "Waiting for tmux session to finish"
tmux wait-for quality_analysis_done

# Clean up the tmux session
echo "Cleaning up tmux session"
tmux kill-session -t QC_$user_id

# Print the log file content for debugging
echo "Log file content:"
cat $log_file

# Exit with the correct status code
echo "Exiting with status code $exit_code"
exit $exit_code
