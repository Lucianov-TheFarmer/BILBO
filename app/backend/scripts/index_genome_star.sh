#!/bin/bash

# Log file for debugging
LOG_FILE="/app/backend/logs/index_genome_star.log"

# Ensure the log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Start logging
echo "Starting genome indexing with STAR..." > "$LOG_FILE"
echo "Script executado a partir de: $(pwd)" >> "$LOG_FILE"

# Check if the genome directory, sjdbOverhang, and threads are provided
if [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ]; then
    echo "Error: Genome directory, sjdbOverhang, and threads must be provided." >> "$LOG_FILE"
    echo "Usage: $0 <genome_directory> <sjdbOverhang> <threads> [limitGenomeGenerateRAM_bytes] [outTmpDir]" >&2
    exit 1
fi

GENOME_DIR="$1"

SJDB_OVERHANG="$2"
THREADS="$3"
LIMIT_RAM="$4"   # optional: pass bytes, e.g. 50000000000 for ~50GB
TMP_DIR="$5"     # optional: temp dir for STAR intermediate files
INDEX_DIR="$GENOME_DIR/STAR_index"

# Ensure the genome directory exists
if [ ! -d "$GENOME_DIR" ]; then
    echo "Genome directory $GENOME_DIR does not exist. Creating it now..." >> "$LOG_FILE"
    mkdir -p "$GENOME_DIR"
fi

# Ensure the STAR index directory exists
mkdir -p "$INDEX_DIR"

# Paths to expected input files
GENOME_FASTA="$GENOME_DIR/genomic.fa"
GENOME_GTF="$GENOME_DIR/genomic.gtf"

if [ ! -f "$GENOME_FASTA" ]; then
    echo "Error: FASTA file $GENOME_FASTA not found." >> "$LOG_FILE"
    exit 1
fi

# Compute recommended genomeSAindexNbases based on genome length to reduce memory
GENOME_LEN=$(awk '/^>/ {next} {len+=length($0)} END{print len+0}' "$GENOME_FASTA")
if [ -z "$GENOME_LEN" ] || [ "$GENOME_LEN" -le 0 ]; then
    echo "Warning: Could not determine genome length, using default SAindexNbases=14" >> "$LOG_FILE"
    SAINDEX_NBASES=14
else
    SAINDEX_NBASES=$(awk -v L="$GENOME_LEN" 'BEGIN{n=int(log(L)/log(2)/2 -1); if(n>14) n=14; if(n<8) n=8; print n}')
fi
echo "Computed genome length=$GENOME_LEN; genomeSAindexNbases=$SAINDEX_NBASES" >> "$LOG_FILE"

# Run STAR to generate the genome index
echo "Running STAR to index the genome in $GENOME_DIR with sjdbOverhang=$SJDB_OVERHANG and threads=$THREADS..." >> "$LOG_FILE"

STAR_CMD=(STAR --runThreadN "$THREADS" \
     --runMode genomeGenerate \
     --genomeDir "$INDEX_DIR" \
     --genomeFastaFiles "$GENOME_FASTA" \
     --sjdbOverhang "$SJDB_OVERHANG" \
     --genomeSAindexNbases "$SAINDEX_NBASES")

# Only add GTF if it exists
if [ -f "$GENOME_GTF" ]; then
    STAR_CMD+=(--sjdbGTFfile "$GENOME_GTF")
else
    echo "GTF file $GENOME_GTF not found; proceeding without --sjdbGTFfile" >> "$LOG_FILE"
fi

# Optional memory limit to avoid full RAM consumption by STAR
if [ -n "$LIMIT_RAM" ]; then
    STAR_CMD+=(--limitGenomeGenerateRAM "$LIMIT_RAM")
    echo "Applying STAR RAM limit: $LIMIT_RAM bytes" >> "$LOG_FILE"
fi

# Optional tmp dir (useful to avoid tmpfs or memory-backed dirs)
if [ -n "$TMP_DIR" ]; then
    mkdir -p "$TMP_DIR"
    STAR_CMD+=(--outTmpDir "$TMP_DIR")
    echo "Using STAR temporary directory: $TMP_DIR" >> "$LOG_FILE"
fi

# Log and run
echo "STAR command: ${STAR_CMD[*]}" >> "$LOG_FILE"
"${STAR_CMD[@]}" >> "$LOG_FILE" 2>&1

# Check if STAR completed successfully
if [ $? -eq 0 ]; then
    echo "Genome indexing completed successfully for $GENOME_DIR." >> "$LOG_FILE"
else
    echo "Error: Genome indexing failed for $GENOME_DIR." >> "$LOG_FILE"
    exit 1
fi
