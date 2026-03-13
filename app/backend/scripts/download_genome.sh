#!/bin/bash

set -euo pipefail

# Check if the accession is provided
if [ -z "${1:-}" ]; then
    echo "Usage: $0 <accession>" >&2
    exit 1
fi

ACCESSION="$1"
LOG_FILE="/app/backend/logs/download_genome_${ACCESSION}.log"
SHARED_DIR="/users/ref_genomes"
GENOME_DIR="$SHARED_DIR/$ACCESSION"
MAX_ATTEMPTS="${DATASETS_MAX_ATTEMPTS:-3}"

# Ensure directories exist
mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$SHARED_DIR"

if ! command -v datasets >/dev/null 2>&1; then
    if [ -x "/opt/conda/envs/bioinfo/bin/datasets" ]; then
        PATH="/opt/conda/envs/bioinfo/bin:$PATH"
    elif [ -x "/opt/conda/bin/datasets" ]; then
        PATH="/opt/conda/bin:$PATH"
    else
        echo "Error: datasets command not found in PATH." > "$LOG_FILE"
        exit 1
    fi
fi

# Reset log file for this accession
echo "Starting genome download script for $ACCESSION..." > "$LOG_FILE"

# Download with retries to handle transient/corrupted archive responses.
download_valid_archive() {
    local attempt=1
    while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
        echo "Attempt ${attempt}/${MAX_ATTEMPTS}: downloading genome package for $ACCESSION..."
        rm -f "$ACCESSION.zip" "$SHARED_DIR/$ACCESSION.zip"

        if datasets download genome accession "$ACCESSION" --filename "$ACCESSION.zip" --include genome,gtf,gff3; then
            if [ -f "$ACCESSION.zip" ]; then
                mv "$ACCESSION.zip" "$SHARED_DIR/$ACCESSION.zip"
            fi

            if [ ! -f "$SHARED_DIR/$ACCESSION.zip" ]; then
                echo "Warning: archive file not found after download on attempt ${attempt}."
            elif unzip -tq "$SHARED_DIR/$ACCESSION.zip" >/dev/null; then
                echo "Archive validation passed on attempt ${attempt}."
                return 0
            else
                echo "Warning: invalid zip archive on attempt ${attempt}."
            fi
        else
            echo "Warning: datasets download command failed on attempt ${attempt}."
        fi

        rm -f "$ACCESSION.zip" "$SHARED_DIR/$ACCESSION.zip"
        attempt=$((attempt + 1))
        sleep 3
    done

    echo "Error: failed to download a valid archive for $ACCESSION after ${MAX_ATTEMPTS} attempts."
    return 1
}

{
    download_valid_archive

    rm -rf "$GENOME_DIR"
    mkdir -p "$GENOME_DIR"
    unzip -o "$SHARED_DIR/$ACCESSION.zip" -d "$GENOME_DIR"
    rm -f "$SHARED_DIR/$ACCESSION.zip"
    echo "Unzipped genome files for $ACCESSION."

    # Locate and rename .fna, .gtf, and .gff3 files
    FNA_FILE=$(find "$GENOME_DIR" -type f -name "*.fna" | head -n 1 || true)
    GTF_FILE=$(find "$GENOME_DIR" -type f -name "*.gtf" | head -n 1 || true)
    GFF3_FILE=$(find "$GENOME_DIR" -type f -name "*.gff3" | head -n 1 || true)

    if [ -z "$FNA_FILE" ]; then
        echo "Error: .fna file not found for $ACCESSION."
        exit 1
    fi

    mv "$FNA_FILE" "$GENOME_DIR/genomic.fa"
    echo "Renamed $FNA_FILE to genomic.fa."

    if [ -n "$GTF_FILE" ]; then
        mv "$GTF_FILE" "$GENOME_DIR/genomic.gtf"
        echo "Renamed $GTF_FILE to genomic.gtf."
    else
        echo "Warning: .gtf file not found for $ACCESSION."
    fi

    if [ -n "$GFF3_FILE" ]; then
        mv "$GFF3_FILE" "$GENOME_DIR/genomic.gff3"
        echo "Renamed $GFF3_FILE to genomic.gff3."
    else
        echo "Warning: .gff3 file not found for $ACCESSION."
    fi

    # Remove unnecessary extracted metadata files/folders
    rm -rf "$GENOME_DIR/ncbi_dataset" "$GENOME_DIR/md5sum.txt" "$GENOME_DIR/README.md"
    echo "Removed unnecessary files for $ACCESSION."

    if [ ! -f "$GENOME_DIR/genomic.fa" ]; then
        echo "Error: genomic.fa was not produced for $ACCESSION."
        exit 1
    fi

    echo "Genoma de referência $ACCESSION baixado, descompactado, renomeado e limpo com sucesso."
} >> "$LOG_FILE" 2>&1
