#!/bin/bash

BASENAME=$1
USER_ID=$2
ALIGNMENT_PATH=$3
GENOME_DIR=$4
THREADS=$5
TOKEN=$6  # Adicionado para receber o token como argumento
shift 6  # Shift para acessar parâmetros adicionais

# Construir a string de parâmetros adicionais
ADDITIONAL_PARAMS=""
for PARAM in "$@"; do
    ADDITIONAL_PARAMS+=" $PARAM"
done

# Criar subdiretório para os arquivos de alinhamento
ALIGNMENT_SUBDIR="${ALIGNMENT_PATH}/${BASENAME}"
mkdir -p "$ALIGNMENT_SUBDIR"

# Caminhos dos arquivos de entrada e saída
INPUT_1="../users/${USER_ID}/trimmed/${BASENAME}_1_trimmed.fastq"
INPUT_2="../users/${USER_ID}/trimmed/${BASENAME}_2_trimmed.fastq"
OUTPUT_PREFIX="${ALIGNMENT_SUBDIR}/${BASENAME}"
CUSTOM_LOG="${OUTPUT_PREFIX}_custom.log"

# Verifique se o tmux está instalado, caso contrário, instale-o
if ! command -v tmux &> /dev/null; then
    echo "tmux não está instalado. Instalando tmux..."
    apt-get update
    apt-get install -y tmux
fi

# Iniciar sessão tmux para o alinhamento completo
tmux new-session -d -s "alignment_${BASENAME}" "
    echo 'Executando alinhamento com STAR para $BASENAME...' >> $CUSTOM_LOG;
    STAR --runThreadN $THREADS \
        --genomeDir $GENOME_DIR \
        --readFilesIn $INPUT_1 $INPUT_2 \
        --outFileNamePrefix $OUTPUT_PREFIX \
        --outSAMstrandField intronMotif --outSAMtype BAM Unsorted \
        $ADDITIONAL_PARAMS >> $CUSTOM_LOG 2>&1;
    if [ \$? -ne 0 ]; then
        echo 'Erro no alinhamento com STAR para $BASENAME' >> $CUSTOM_LOG;
        tmux wait-for -S alignment_done_${BASENAME};
        exit 1;
    fi;

    echo 'Ordenando BAM com Picard para $BASENAME...' >> $CUSTOM_LOG;
    picard SortSam \
        I=${OUTPUT_PREFIX}Aligned.out.bam \
        O=${OUTPUT_PREFIX}Aligned.sorted.picard.query.bam \
        SORT_ORDER=queryname >> $CUSTOM_LOG 2>&1;
    if [ \$? -ne 0 ]; then
        echo 'Erro na ordenação com Picard para $BASENAME' >> $CUSTOM_LOG;
        tmux wait-for -S alignment_done_${BASENAME};
        exit 1;
    fi;

    echo 'Adicionando Read Groups com Picard para $BASENAME...' >> $CUSTOM_LOG;
    picard AddOrReplaceReadGroups \
        I=${OUTPUT_PREFIX}Aligned.sorted.picard.query.bam \
        O=${OUTPUT_PREFIX}Aligned.sorted.picard.query.rg.bam \
        RGID=$BASENAME \
        RGLB=lib1 \
        RGPL=ILLUMINA \
        RGPU=unit1 \
        RGSM=$BASENAME >> $CUSTOM_LOG 2>&1;
    if [ \$? -ne 0 ]; then
        echo 'Erro ao adicionar Read Groups com Picard para $BASENAME' >> $CUSTOM_LOG;
        tmux wait-for -S alignment_done_${BASENAME};
        exit 1;
    fi;

    echo 'Removendo duplicatas com Picard para $BASENAME...' >> $CUSTOM_LOG;
    picard MarkDuplicates \
        I=${OUTPUT_PREFIX}Aligned.sorted.picard.query.rg.bam \
        O=${OUTPUT_PREFIX}.bam \
        REMOVE_DUPLICATES=true \
        M=${OUTPUT_PREFIX}_markdup_metrics.txt >> $CUSTOM_LOG 2>&1;
    if [ \$? -ne 0 ]; then
        echo 'Erro na remoção de duplicatas com Picard para $BASENAME' >> $CUSTOM_LOG;
        tmux wait-for -S alignment_done_${BASENAME};
        exit 1;
    fi;

    # Obter tamanho do arquivo BAM final
    bam_size=\$(stat -c%s '${OUTPUT_PREFIX}.bam')
    bam_size_mb=\$(echo \"scale=2; \$bam_size / (1024 * 1024)\" | bc)

    # Atualizar status e tamanho no backend
    echo 'Atualizando status e tamanho no backend para $BASENAME...' >> $CUSTOM_LOG;
    curl -X POST http://bioinfo-container:8000/alignment/update_status \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        -H \"Authorization: Bearer $TOKEN\" \
        -d \"sra_code=${BASENAME}&status=Completed\" >> $CUSTOM_LOG 2>&1;
    if [ \$? -ne 0 ]; then
        echo 'Erro ao executar curl para $BASENAME' >> $CUSTOM_LOG;
    else
        echo 'Curl executado com sucesso para $BASENAME' >> $CUSTOM_LOG;
    fi;

    # # Enviar mensagem para o WebSocket
    # echo 'Enviando mensagem de conclusão para o WebSocket...' >> $CUSTOM_LOG;
    # curl -X POST http://bioinfo-container:8000/ws/ \
    #     -H 'Content-Type: application/x-www-form-urlencoded' \
    #     -d \"message=Alinhamento concluido para ${BASENAME}\" >> $CUSTOM_LOG 2>&1;
    # if [ \$? -ne 0 ]; then
    #     echo 'Erro ao enviar mensagem para o WebSocket para $BASENAME' >> $CUSTOM_LOG;
    # else
    #     echo 'Mensagem enviada com sucesso para o WebSocket para $BASENAME' >> $CUSTOM_LOG;
    # fi;

    # Limpeza de arquivos temporários
    echo 'Limpando arquivos temporários para $BASENAME...' >> $CUSTOM_LOG;
    find '$ALIGNMENT_SUBDIR' -type f ! -name '${BASENAME}.bam' ! -name '${BASENAME}Log.final.out' ! -name '${BASENAME}_custom.log' -delete;
    if [ \$? -eq 0 ]; then
        echo 'Arquivos temporários excluídos com sucesso para $BASENAME.' >> $CUSTOM_LOG;
    else
        echo 'Erro ao excluir arquivos temporários para $BASENAME.' >> $CUSTOM_LOG;
    fi;

    echo 'Alinhamento concluído para $BASENAME' >> $CUSTOM_LOG;
    tmux wait-for -S alignment_done_${BASENAME};
"

# Esperar a conclusão do tmux
tmux wait-for alignment_done_${BASENAME}

# Adicionar um atraso para garantir que o processo seja encerrado corretamente
sleep 2

# Excluir sessão tmux
tmux kill-session -t "alignment_${BASENAME}" 2>/dev/null || echo "Sessão tmux alignment_${BASENAME} já foi encerrada."

# Adicionar um atraso adicional para evitar conflitos com o próximo processo
sleep 2