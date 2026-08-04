#!/bin/bash

set -euo pipefail

if [ "$#" -lt 4 ]; then
    echo "Usage: $0 <sample_name.bam> <user_id> <feature_type> <id_attribute> [genome_param]" >&2
    exit 1
fi

sample_name="$1"
user_id="$2"
feature_type="$3"
id_attribute="$4"
genome_param="${5:-}"

alignment_dir="/users/${user_id}/alignment/${sample_name%.bam}"
output_dir="/users/${user_id}/quantification"
log_file="/tmp/${sample_name}_quantification.log"
ref_parent="/users/ref_genomes"

mkdir -p "$output_dir"
: > "$log_file"

log() {
    echo "$1" >> "$log_file"
}

log_err() {
    echo "$1" | tee -a "$log_file" >&2
}

resolve_bin() {
    local name="$1"
    shift

    if command -v "$name" >/dev/null 2>&1; then
        command -v "$name"
        return 0
    fi

    for candidate in "$@"; do
        if [ -x "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done

    return 1
}

resolve_ref_genome_dir() {
    local param="$1"

    if [ -n "$param" ]; then
        if [ -d "$param" ]; then
            echo "$param"
            return 0
        fi

        if [ -d "/users/ref_genomes/$param" ]; then
            echo "/users/ref_genomes/$param"
            return 0
        fi
    fi

    if [ ! -d "$ref_parent" ]; then
        return 1
    fi

    mapfile -d '' candidates < <(find "$ref_parent" -maxdepth 2 -type f \
        \( -name "genomic.gff" -o -name "genomic.gff3" -o -name "genomic.gtf" \) \
        -printf "%h\0" | sort -zu)

    if [ "${#candidates[@]}" -eq 1 ]; then
        echo "${candidates[0]}"
        return 0
    fi

    return 1
}

resolve_annotation_file() {
    local dir="$1"
    for candidate in "genomic.gff" "genomic.gff3" "genomic.gtf"; do
        if [ -f "$dir/$candidate" ]; then
            echo "$dir/$candidate"
            return 0
        fi
    done
    return 1
}

attribute_exists_for_feature() {
    local gff="$1"
    local feature="$2"
    local attr="$3"

    awk -F '\t' -v ft="$feature" -v target="$attr" '
        $0 !~ /^#/ && $3 == ft {
            n = split($9, parts, ";")
            for (i = 1; i <= n; i++) {
                p = parts[i]
                gsub(/^[ \t]+|[ \t]+$/, "", p)
                key = p
                sub(/[= ].*$/, "", key)
                if (key == target) {
                    found = 1
                    exit
                }
            }
        }
        END { exit(found ? 0 : 1) }
    ' "$gff"
}

detect_fallback_attribute() {
    local gff="$1"
    local feature="$2"

    local keys
    keys="$(awk -F '\t' -v ft="$feature" '
        $0 !~ /^#/ && $3 == ft {
            n = split($9, parts, ";")
            for (i = 1; i <= n; i++) {
                p = parts[i]
                gsub(/^[ \t]+|[ \t]+$/, "", p)
                key = p
                sub(/[= ].*$/, "", key)
                if (key != "") print key
            }
            exit
        }
    ' "$gff" | awk '!seen[$0]++')"

    if [ -z "$keys" ]; then
        return 1
    fi

    local preferred
    for preferred in ID gene_id locus_tag Name Parent transcript_id; do
        if echo "$keys" | grep -Fxq "$preferred"; then
            echo "$preferred"
            return 0
        fi
    done

    echo "$keys" | head -n 1
}

input_file="${alignment_dir}/${sample_name}"
output_file="${output_dir}/${sample_name%.bam}.txt"

HTSEQ_BIN="$(resolve_bin htseq-count "/opt/conda/envs/bioinfo/bin/htseq-count" "/opt/conda/bin/htseq-count")" || {
    log_err "Error: htseq-count command not found."
    exit 1
}

log "Starting quantification for sample ${sample_name} (user ${user_id})"
log "Requested feature_type=${feature_type} id_attribute=${id_attribute} genome_param=${genome_param}"

if [ ! -f "$input_file" ]; then
    log_err "Error: input BAM not found: $input_file"
    exit 1
fi

ref_genome_dir="$(resolve_ref_genome_dir "$genome_param" || true)"
if [ -z "$ref_genome_dir" ]; then
    log_err "Error: could not resolve reference genome directory. Check selected_genome and /users/ref_genomes."
    exit 1
fi

annotation_file="$(resolve_annotation_file "$ref_genome_dir" || true)"
if [ -z "$annotation_file" ]; then
    log_err "Error: annotation file not found in $ref_genome_dir (expected genomic.gff, genomic.gff3 or genomic.gtf)."
    exit 1
fi

# HTSEQ_STRAND_NORMALIZATION
normalized_annotation="${annotation_file%.*}.htseq.${annotation_file##*.}"

if [ ! -f "$normalized_annotation" ] || [ "$annotation_file" -nt "$normalized_annotation" ]; then
    invalid_strands="$(
        awk -F '\t' '
            $0 !~ /^#/ && NF >= 9 &&
            $7 != "+" && $7 != "-" && $7 != "." {
                count++
            }
            END { print count + 0 }
        ' "$annotation_file"
    )"

    awk -F '\t' '
        BEGIN { OFS = "\t" }
        /^#/ {
            print
            next
        }
        NF >= 9 && $7 != "+" && $7 != "-" && $7 != "." {
            $7 = "."
        }
        {
            print
        }
    ' "$annotation_file" > "${normalized_annotation}.tmp"

    mv "${normalized_annotation}.tmp" "$normalized_annotation"
    log "Normalized ${invalid_strands} unsupported strand values for HTSeq."
fi

annotation_file="$normalized_annotation"

if ! attribute_exists_for_feature "$annotation_file" "$feature_type" "$id_attribute"; then
    fallback_attr="$(detect_fallback_attribute "$annotation_file" "$feature_type" || true)"
    if [ -n "$fallback_attr" ]; then
        log "Warning: attribute '$id_attribute' not found for feature '$feature_type'. Falling back to '$fallback_attr'."
        id_attribute="$fallback_attr"
    else
        log_err "Error: no valid attribute found for feature '$feature_type' in $annotation_file."
        exit 1
    fi
fi

log "Using reference directory: $ref_genome_dir"
log "Using annotation file: $annotation_file"
log "Using htseq-count binary: $HTSEQ_BIN"
log "Running: $HTSEQ_BIN -a 10 -t $feature_type -i $id_attribute -f bam --stranded=no $input_file $annotation_file"

if "$HTSEQ_BIN" -a 10 -t "$feature_type" -i "$id_attribute" -f bam --stranded=no "$input_file" "$annotation_file" > "$output_file" 2>> "$log_file"; then
    log "Quantification completed for $sample_name"
else
    log_err "Error: htseq-count failed for $sample_name. Showing last log lines:"
    tail -n 40 "$log_file" >&2 || true
    exit 1
fi
