#!/bin/bash

SRA_CODE=$1
USER_ID=$2
BASE_PATH="../users/${USER_ID}/samples/${SRA_CODE}"

# Verificar e excluir arquivos em subdiretórios
for SUFFIX in "_1.fastq" "_2.fastq"; do
    FILE_PATH="${BASE_PATH}/${SRA_CODE}${SUFFIX}"
    if [ -f "$FILE_PATH" ]; then
        rm "$FILE_PATH"
        echo "File $FILE_PATH deleted successfully."
    else
        echo "File $FILE_PATH not found."
    fi
done
