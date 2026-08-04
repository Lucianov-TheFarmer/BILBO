#!/usr/bin/env bash

set -uo pipefail

sra_code="$1"
threads="$2"
phred="$3"
illumina_clip="$4"
sliding_window="$5"
max_info="$6"
leading="$7"
trailing="$8"
crop="$9"
headcrop="${10}"
minlen="${11}"
avgqual="${12}"
base_path="${13}"
trimmed_path="${14}"

log_file="/tmp/${sra_code}_trimmagem.log"
adapters_dir="/app/backend/scripts/adapters"

mkdir -p "$trimmed_path"
: > "$log_file"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$log_file"
}

strip_fastq_extension() {
    local x
    x="$(basename "$1")"
    x="${x%.gz}"
    x="${x%.fastq}"
    x="${x%.fq}"
    printf '%s\n' "$x"
}

# ------------------------------------------------------------
# Resolver executável do Trimmomatic
# ------------------------------------------------------------

if command -v trimmomatic >/dev/null 2>&1; then
    TRIMMOMATIC=(trimmomatic)
elif [ -x /opt/conda/envs/bioinfo/bin/trimmomatic ]; then
    TRIMMOMATIC=(/opt/conda/envs/bioinfo/bin/trimmomatic)
else
    TRIMMOMATIC_JAR="$(
        find /opt/conda /usr/local /usr/share \
            -type f \
            \( -name 'trimmomatic*.jar' -o -name 'trimmomatic.jar' \) \
            2>/dev/null | head -n 1
    )"

    if [ -n "${TRIMMOMATIC_JAR:-}" ] && command -v java >/dev/null 2>&1; then
        TRIMMOMATIC=(java -jar "$TRIMMOMATIC_JAR")
    else
        log "ERRO: Trimmomatic não encontrado."
        exit 127
    fi
fi


# ------------------------------------------------------------
# Procurar um par PE
# ------------------------------------------------------------

input_file_1=""
input_file_2=""
is_paired=false

sample_dir="$base_path/$sra_code"

PAIR_SUFFIXES=(
    "_1.fastq.gz|_2.fastq.gz"
    "_1.fq.gz|_2.fq.gz"
    "_1.fastq|_2.fastq"
    "_1.fq|_2.fq"
    "_R1.fastq.gz|_R2.fastq.gz"
    "_R1.fq.gz|_R2.fq.gz"
    "_R1.fastq|_R2.fastq"
    "_R1.fq|_R2.fq"
)

for pair in "${PAIR_SUFFIXES[@]}"; do
    left="${pair%%|*}"
    right="${pair##*|}"

    p1="$sample_dir/${sra_code}${left}"
    p2="$sample_dir/${sra_code}${right}"

    if [ -f "$p1" ] && [ -f "$p2" ]; then
        input_file_1="$p1"
        input_file_2="$p2"
        is_paired=true
        break
    fi
done


# ------------------------------------------------------------
# Caso não seja PE, localizar arquivo SE
# ------------------------------------------------------------

if [ "$is_paired" = false ]; then
    candidates=()

    if [[ "$sra_code" =~ \.(fastq|fq)(\.gz)?$ ]]; then
        candidates+=("$base_path/$sra_code")

        while IFS= read -r f; do
            [ -n "$f" ] && candidates+=("$f")
        done < <(
            find "$base_path" \
                -mindepth 1 \
                -maxdepth 2 \
                -type f \
                -name "$sra_code" \
                -print 2>/dev/null
        )
    else
        for ext in \
            ".fastq.gz" ".fq.gz" ".fastq" ".fq"
        do
            candidates+=(
                "$base_path/$sra_code/${sra_code}${ext}"
            )
        done
    fi

    for candidate in "${candidates[@]}"; do
        if [ -f "$candidate" ]; then
            input_file_1="$candidate"
            break
        fi
    done

    if [ -z "$input_file_1" ]; then
        log "ERRO: nenhum FASTQ encontrado para $sra_code"
        exit 2
    fi
fi


# ------------------------------------------------------------
# Autodetecção Phred, gzip-aware
# Examina milhares de reads, não apenas uma linha.
# FASTQ moderno é assumido como Phred33 quando a faixa é ambígua.

if [ "$phred" = "autodetect" ]; then
    phred="$(
        python - "$input_file_1" <<'PYCODE'
import gzip
import sys

path = sys.argv[1]
opener = gzip.open if path.endswith(".gz") else open

min_ascii = 127
max_ascii = 0
records = 0

try:
    with opener(path, "rt", encoding="ascii", errors="ignore") as fh:
        while records < 10000:
            header = fh.readline()
            if not header:
                break

            seq = fh.readline()
            plus = fh.readline()
            qual = fh.readline().rstrip("\r\n")

            if not qual:
                break

            vals = [ord(c) for c in qual]
            min_ascii = min(min_ascii, min(vals))
            max_ascii = max(max_ascii, max(vals))
            records += 1

    # Qualquer caractere abaixo de '@' (ASCII 64)
    # prova que o arquivo não pode ser Phred64.
    if min_ascii < 64:
        print("phred33")

    # Valores acima da faixa típica de Illumina Phred33,
    # sem nenhum caractere <64, sugerem Phred64 antigo.
    elif max_ascii > 74:
        print("phred64")

    # Faixa 64-74 é ambígua. Dados Illumina/SRA modernos
    # são predominantemente Phred33; esta é a escolha segura.
    else:
        print("phred33")

except Exception:
    print("phred33")
PYCODE
    )"

    log "Codificação Phred autodetectada: $phred"
fi

case "$phred" in
    phred33|phred64)
        ;;
    *)
        log "ERRO: codificação Phred inválida: $phred"
        exit 3
        ;;
esac


# ------------------------------------------------------------
# Adaptadores
# ------------------------------------------------------------

adapter_file="$(echo "$illumina_clip" | jq -r '.["Arquivo adaptadores"]')"
seed_mismatches="$(echo "$illumina_clip" | jq -r '.["Seed mismatches"]')"
threshold_palindrome="$(echo "$illumina_clip" | jq -r '.["Threshold palindromo"]')"
threshold_simple="$(echo "$illumina_clip" | jq -r '.["Threshold simples"]')"
min_adapter_length="$(echo "$illumina_clip" | jq -r '.["Comprimento minimo adaptador"]')"

if [[ "$adapter_file" != /* ]]; then
    adapter_file="$adapters_dir/$adapter_file"
fi

if [ ! -f "$adapter_file" ]; then
    log "ERRO: arquivo de adaptadores não encontrado: $adapter_file"
    exit 4
fi

window_size="$(echo "$sliding_window" | jq -r '.["Tamanho janela"]')"
window_quality="$(echo "$sliding_window" | jq -r '.["Qualidade minima"]')"


# ------------------------------------------------------------
# Saídas
#
# Trimmomatic PE exige quatro destinos.
# Os reads unpaired são enviados diretamente para /dev/null.
# ------------------------------------------------------------

if [ "$is_paired" = true ]; then

    sample_base="$sra_code"

    output_1="$trimmed_path/${sample_base}_1_trimmed.fastq.gz"
    output_2="$trimmed_path/${sample_base}_2_trimmed.fastq.gz"

    command=(
        "${TRIMMOMATIC[@]}"
        PE
        -threads "$threads"
        "-$phred"
        "$input_file_1"
        "$input_file_2"
        "$output_1"
        /dev/null
        "$output_2"
        /dev/null
        "ILLUMINACLIP:$adapter_file:$seed_mismatches:$threshold_palindrome:$threshold_simple:$min_adapter_length"
        "SLIDINGWINDOW:$window_size:$window_quality"
        "LEADING:$leading"
        "TRAILING:$trailing"
        "MINLEN:$minlen"
    )

else

    sample_base="$(strip_fastq_extension "$input_file_1")"
    output_1="$trimmed_path/${sample_base}_trimmed.fastq.gz"

    command=(
        "${TRIMMOMATIC[@]}"
        SE
        -threads "$threads"
        "-$phred"
        "$input_file_1"
        "$output_1"
        "ILLUMINACLIP:$adapter_file:$seed_mismatches:$threshold_palindrome:$threshold_simple:$min_adapter_length"
        "SLIDINGWINDOW:$window_size:$window_quality"
        "LEADING:$leading"
        "TRAILING:$trailing"
        "MINLEN:$minlen"
    )

fi


# Parâmetros opcionais
[ -n "$crop" ] && command+=("CROP:$crop")
[ -n "$headcrop" ] && command+=("HEADCROP:$headcrop")
[ -n "$avgqual" ] && command+=("AVGQUAL:$avgqual")


log "Input 1: $input_file_1"

if [ "$is_paired" = true ]; then
    log "Input 2: $input_file_2"
    log "Output 1: $output_1"
    log "Output 2: $output_2"
else
    log "Output: $output_1"
fi

log "Executando Trimmomatic."


if command -v timeout >/dev/null 2>&1; then
    RUN_CMD=(timeout 24h "${command[@]}")
else
    RUN_CMD=("${command[@]}")
fi

if "${RUN_CMD[@]}" >> "$log_file" 2>&1; then
    exit_code=0
else
    exit_code=$?
fi


if [ "$exit_code" -ne 0 ]; then
    log "ERRO: Trimmomatic terminou com código $exit_code."

    rm -f "$output_1"
    [ "$is_paired" = true ] && rm -f "$output_2"

    exit "$exit_code"
fi


# ------------------------------------------------------------
# Validar gzip produzido
# ------------------------------------------------------------

if [ ! -s "$output_1" ] || ! gzip -t "$output_1" 2>>"$log_file"; then
    log "ERRO: saída 1 inválida ou gzip corrompido."
    rm -f "$output_1"
    [ "$is_paired" = true ] && rm -f "$output_2"
    exit 5
fi

# Um gzip vazio tem tamanho pequeno mas ainda passa em gzip -t.
# Exigir pelo menos quatro linhas = uma read FASTQ completa.
lines_1=$(gzip -dc "$output_1" 2>>"$log_file" | head -n 4 | wc -l)

if [ "$lines_1" -lt 4 ]; then
    log "ERRO: Trimmomatic produziu saída vazia para read 1."
    rm -f "$output_1"
    [ "$is_paired" = true ] && rm -f "$output_2"
    exit 7
fi

if [ "$is_paired" = true ]; then
    if [ ! -s "$output_2" ] || ! gzip -t "$output_2" 2>>"$log_file"; then
        log "ERRO: saída 2 inválida ou gzip corrompido."
        rm -f "$output_1" "$output_2"
        exit 6
    fi

    lines_2=$(gzip -dc "$output_2" 2>>"$log_file" | head -n 4 | wc -l)

    if [ "$lines_2" -lt 4 ]; then
        log "ERRO: Trimmomatic produziu saída vazia para read 2."
        rm -f "$output_1" "$output_2"
        exit 8
    fi
fi

log "Trimmagem concluída com sucesso."
exit 0
