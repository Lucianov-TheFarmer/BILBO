#!/bin/bash

SRA_CODE=$1
FILE_PATH="/samples/${SRA_CODE}"

if [ -f "$FILE_PATH" ]; then
    rm "$FILE_PATH"
    echo "File $FILE_PATH deleted successfully."
else
    echo "File $FILE_PATH not found."
fi
