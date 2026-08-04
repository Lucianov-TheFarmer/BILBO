#!/usr/bin/env bash

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

GZ_1="/users/${USER_ID}/trimmed/${BASENAME}_1_trimmed.fastq.gz"
GZ_2="/users/${USER_ID}/trimmed/${BASENAME}_2_trimmed.fastq.gz"

PLAIN_1="/users/${USER_ID}/trimmed/${BASENAME}_1_trimmed.fastq"
PLAIN_2="/users/${USER_ID}/trimmed/${BASENAME}_2_trimmed.fastq"

READ_FILES_COMMAND=()

if [ -f "$GZ_1" ] && [ -f "$GZ_2" ]; then

    INPUT_1="$GZ_1"
    INPUT_2="$GZ_2"
    READ_FILES_COMMAND=(--readFilesCommand zcat)

elif [ -f "$PLAIN_1" ] && [ -f "$PLAIN_2" ]; then

    INPUT_1="$PLAIN_1"
    INPUT_2="$PLAIN_2"

else

    CUSTOM_LOG="${ALIGNMENT_SUBDIR}/${BASENAME}_custom.log"

    {
        echo "Input FASTQ pair not found."
        echo "Checked:"
        echo "  $GZ_1"
        echo "  $GZ_2"
        echo "  $PLAIN_1"
        echo "  $PLAIN_2"
    } > "$CUSTOM_LOG"

    exit 2
fi

OUTPUT_PREFIX="${ALIGNMENT_SUBDIR}/${BASENAME}"
CUSTOM_LOG="${OUTPUT_PREFIX}_custom.log"

{
    echo "[alignment] Sample: ${BASENAME}"
    echo "[alignment] Input 1: ${INPUT_1}"
    echo "[alignment] Input 2: ${INPUT_2}"

    if [ "${#READ_FILES_COMMAND[@]}" -gt 0 ]; then
        echo "[alignment] Compressed FASTQ detected; using zcat."
    fi

    echo "[alignment] Running STAR"

    STAR \
        --runThreadN "$THREADS" \
        --genomeDir "$GENOME_DIR" \
        --readFilesIn "$INPUT_1" "$INPUT_2" \
        "${READ_FILES_COMMAND[@]}" \
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

    find "$ALIGNMENT_SUBDIR" \
        -type f \
        ! -name "${BASENAME}.bam" \
        ! -name "${BASENAME}Log.final.out" \
        ! -name "${BASENAME}_custom.log" \
        -delete

    echo "[alignment] Completed"

} >> "$CUSTOM_LOG" 2>&1
