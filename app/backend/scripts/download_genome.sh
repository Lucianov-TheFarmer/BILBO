#!/bin/bash

# Log file for debugging
LOG_FILE="/app/backend/logs/download_genome.log"

# Ensure the log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Start logging
echo "Starting genome download script..." > "$LOG_FILE"

# Check if the accession is provided
if [ -z "$1" ]; then
    echo "Error: Accession must be provided." >> "$LOG_FILE"
    echo "Usage: $0 <accession>" >&2
    exit 1
fi

ACCESSION="$1"
SHARED_DIR="/users/ref_genomes"
GENOME_DIR="$SHARED_DIR/$ACCESSION"
TMUX_SESSION_NAME="genome_$ACCESSION"

# Ensure the shared directory exists
mkdir -p "$SHARED_DIR"

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "Error: tmux is not installed. Please install tmux and try again." >> "$LOG_FILE"
    exit 1
fi

# Check if the tmux session already exists
if tmux has-session -t "$TMUX_SESSION_NAME" 2>/dev/null; then
    echo "Error: tmux session $TMUX_SESSION_NAME already exists." >> "$LOG_FILE"
    exit 1
fi

# Start a new tmux session to download the genome
echo "Starting tmux session $TMUX_SESSION_NAME for genome download..." >> "$LOG_FILE"
tmux new-session -d -s "$TMUX_SESSION_NAME" "
    datasets download genome accession $ACCESSION --filename $ACCESSION.zip --include genome,gtf,gff3 &&
    mv $ACCESSION.zip $SHARED_DIR &&
    unzip -o $SHARED_DIR/$ACCESSION.zip -d $GENOME_DIR &&
    rm $SHARED_DIR/$ACCESSION.zip &&
    echo 'Unzipped genome files for $ACCESSION.' >> $LOG_FILE &&
    # Locate and rename .fna, .gtf, and .gff3 files
    FNA_FILE=\$(find $GENOME_DIR -type f -name '*.fna') &&
    GTF_FILE=\$(find $GENOME_DIR -type f -name '*.gtf') &&
    gff3_FILE=\$(find $GENOME_DIR -type f -name '*.gff3') &&
    if [ -f \"\$FNA_FILE\" ]; then
        mv \"\$FNA_FILE\" \"$GENOME_DIR/genomic.fa\" &&
        echo 'Renamed \$FNA_FILE to genomic.fa.' >> $LOG_FILE
    else
        echo 'Error: .fna file not found for $ACCESSION.' >> $LOG_FILE
    fi &&
    if [ -f \"\$GTF_FILE\" ]; then
        mv \"\$GTF_FILE\" \"$GENOME_DIR/genomic.gtf\" &&
        echo 'Renamed \$GTF_FILE to genomic.gtf.' >> $LOG_FILE
    else
        echo 'Error: .gtf file not found for $ACCESSION.' >> $LOG_FILE
    fi &&
    if [ -f \"\$gff3_FILE\" ]; then
        mv \"\$gff3_FILE\" \"$GENOME_DIR/genomic.gff3\" &&
        echo 'Renamed \$gff3_FILE to genomic.gff3.' >> $LOG_FILE
    else
        echo 'Error: .gff3 file not found for $ACCESSION.' >> $LOG_FILE
    fi &&
    # Remove unnecessary files
    rm -rf \"$GENOME_DIR/ncbi_dataset\" \"$GENOME_DIR/md5sum.txt\" \"$GENOME_DIR/README.md\" &&
    echo 'Removed unnecessary files for $ACCESSION.' >> $LOG_FILE &&
    echo 'Genoma de referência $ACCESSION baixado, descompactado, renomeado e limpo com sucesso.' >> $LOG_FILE
"

# Check if the tmux session was created successfully
if [ $? -eq 0 ]; then
    echo "Tmux session $TMUX_SESSION_NAME started successfully." >> "$LOG_FILE"
else
    echo "Error: Failed to start tmux session $TMUX_SESSION_NAME." >> "$LOG_FILE"
    exit 1
fi
