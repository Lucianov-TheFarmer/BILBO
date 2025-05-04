#!/bin/bash

# Log file for debugging
LOG_FILE="/app/backend/logs/index_genome_star.log"

# Ensure the log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Start logging
echo "Starting genome indexing with STAR..." > "$LOG_FILE"

# Check if the genome directory, sjdbOverhang, and threads are provided
if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ]; then
    echo "Error: Genome directory, sjdbOverhang, and threads must be provided." >> "$LOG_FILE"
    echo "Usage: $0 <genome_directory> <sjdbOverhang> <threads>" >&2
    exit 1
fi

GENOME_DIR="$1"

# Convert GENOME_DIR to an absolute path
GENOME_DIR=$(realpath "$GENOME_DIR")

SJDB_OVERHANG="$2"
THREADS="$3"
INDEX_DIR="$GENOME_DIR/STAR_index"

# Ensure the genome directory exists
if [ ! -d "$GENOME_DIR" ]; then
    echo "Genome directory $GENOME_DIR does not exist. Creating it now..." >> "$LOG_FILE"
    mkdir -p "$GENOME_DIR"
fi

# Ensure the STAR index directory exists
mkdir -p "$INDEX_DIR"

# Run STAR to generate the genome index
echo "Running STAR to index the genome in $GENOME_DIR with sjdbOverhang=$SJDB_OVERHANG and threads=$THREADS..." >> "$LOG_FILE"
STAR --runThreadN "$THREADS" \
     --runMode genomeGenerate \
     --genomeDir "$INDEX_DIR" \
     --genomeFastaFiles "$GENOME_DIR/genomic.fa" \
     --sjdbGTFfile "$GENOME_DIR/genomic.gtf" \
     --sjdbOverhang "$SJDB_OVERHANG" >> "$LOG_FILE" 2>&1

# Check if STAR completed successfully
if [ $? -eq 0 ]; then
    echo "Genome indexing completed successfully for $GENOME_DIR." >> "$LOG_FILE"
else
    echo "Error: Genome indexing failed for $GENOME_DIR." >> "$LOG_FILE"
    exit 1
fi
