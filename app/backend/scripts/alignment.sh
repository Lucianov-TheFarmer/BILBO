#!/bin/bash

set -euo pipefail

BASENAME="$1"
USER_ID="$2"
ALIGNMENT_PATH="$3"
GENOME_DIR="$4"
THREADS="$5"
shift 5 || true

ADDITIONAL_PARAMS=("$@")

ALIGNMENT_SUBDIR="${ALIGNMENT_PATH}/${BASENAME}"
mkdir -p "$ALIGNMENT_SUBDIR"

INPUT_1="/users/${USER_ID}/trimmed/${BASENAME}_1_trimmed.fastq"
INPUT_2="/users/${USER_ID}/trimmed/${BASENAME}_2_trimmed.fastq"
OUTPUT_PREFIX="${ALIGNMENT_SUBDIR}/${BASENAME}"
CUSTOM_LOG="${OUTPUT_PREFIX}_custom.log"

if [ ! -f "$INPUT_1" ] || [ ! -f "$INPUT_2" ]; then
  echo "Input files not found: $INPUT_1 $INPUT_2" > "$CUSTOM_LOG"
  exit 2
fi

{
  echo "[alignment] Running STAR for ${BASENAME}"
  STAR --runThreadN "$THREADS" \
    --genomeDir "$GENOME_DIR" \
    --readFilesIn "$INPUT_1" "$INPUT_2" \
    --outFileNamePrefix "$OUTPUT_PREFIX" \
    --outSAMstrandField intronMotif \
    --outSAMtype BAM Unsorted \
    "${ADDITIONAL_PARAMS[@]}"

  echo "[alignment] Sorting BAM with Picard"
  picard SortSam \
    I="${OUTPUT_PREFIX}Aligned.out.bam" \
    O="${OUTPUT_PREFIX}Aligned.sorted.picard.query.bam" \
    SORT_ORDER=queryname

  echo "[alignment] Adding read groups"
  picard AddOrReplaceReadGroups \
    I="${OUTPUT_PREFIX}Aligned.sorted.picard.query.bam" \
    O="${OUTPUT_PREFIX}Aligned.sorted.picard.query.rg.bam" \
    RGID="$BASENAME" \
    RGLB=lib1 \
    RGPL=ILLUMINA \
    RGPU=unit1 \
    RGSM="$BASENAME"

  echo "[alignment] Marking duplicates"
  picard MarkDuplicates \
    I="${OUTPUT_PREFIX}Aligned.sorted.picard.query.rg.bam" \
    O="${OUTPUT_PREFIX}.bam" \
    REMOVE_DUPLICATES=true \
    M="${OUTPUT_PREFIX}_markdup_metrics.txt"

  echo "[alignment] Cleanup intermediates"
  find "$ALIGNMENT_SUBDIR" -type f \
    ! -name "${BASENAME}.bam" \
    ! -name "${BASENAME}Log.final.out" \
    ! -name "${BASENAME}_custom.log" -delete

  echo "[alignment] Completed"
} >> "$CUSTOM_LOG" 2>&1
