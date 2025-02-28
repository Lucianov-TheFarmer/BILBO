#!/bin/bash

SRA_CODE=$1
USER_ID=$2
FILE_PATH="../users/${USER_ID}/samples/${SRA_CODE}"

if [ -f "$FILE_PATH" ]; then
    rm "$FILE_PATH"
    echo "File $FILE_PATH deleted successfully."
else
    echo "File $FILE_PATH not found."
fi
