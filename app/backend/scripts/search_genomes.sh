#!/bin/bash

# Log file for debugging
LOG_FILE="/app/backend/logs/search_genomes.log"

# Ensure the log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Start logging
echo "Starting genome search script..." > "$LOG_FILE"

# Check if the search type and value are provided
if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Error: Search type and value must be provided." >> "$LOG_FILE"
    echo "Usage: $0 <search_type> <search_value>" >&2
    exit 1
fi

SEARCH_TYPE="$1"
SEARCH_VALUE="$2"
echo "Search type: $SEARCH_TYPE, Search value: $SEARCH_VALUE" >> "$LOG_FILE"

# Determine the command based on the search type
if [ "$SEARCH_TYPE" == "taxon" ]; then
    COMMAND="datasets summary genome taxon \"$SEARCH_VALUE\" --as-json-lines"
elif [ "$SEARCH_TYPE" == "accession" ]; then
    COMMAND="datasets summary genome accession \"$SEARCH_VALUE\" --as-json-lines"
else
    echo "Error: Invalid search type. Must be 'taxon' or 'accession'." >> "$LOG_FILE"
    exit 1
fi

# Run the NCBI datasets command
OUTPUT=$(eval "$COMMAND" | dataformat tsv genome --elide-header --fields accession,assminfo.name,organism.name,assmstats.total-sequence-len,assminfo.biosample-submission-date 2>>"$LOG_FILE")

# Check if the command succeeded
if [ $? -ne 0 ]; then
    echo "Error: Failed to fetch genomes." >> "$LOG_FILE"
    exit 1
fi

# Output the result
echo -e "Assembly Accession\tAssembly Name\tOrganism Name\tAssembly Stats Total Sequence Length\tAssembly BioSample Submission date"
echo "$OUTPUT"

# Log success
echo "Genome search completed successfully." >> "$LOG_FILE"
