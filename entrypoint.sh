done
#!/bin/sh
set -e

# Configuration
MAX_WAIT=60
PULL_RETRIES=3
PULL_DELAY=5

start_server() {
    cmds=(
        "ollama serve"
    )

    for cmd in "${cmds[@]}"; do
        echo "Trying: $cmd"
        sh -c "$cmd" &
        PID=$!
        sleep 2
        if kill -0 "$PID" >/dev/null 2>&1; then
            echo "Ollama started with: $cmd (pid $PID)"
            return 0
        else
            echo "Failed to start with: $cmd"
        fi
    done
    return 1
}

# Start Ollama server in background (try multiple argument variants)
if ! start_server; then
    echo "Failed to start Ollama server with known flags; running default 'ollama serve' fallback"
    ollama serve &
    PID=$!
fi

# Wait until server responds (with timeout)
START_TS=$(date +%s)
while ! ollama list >/dev/null 2>&1; do
    NOW_TS=$(date +%s)
    ELAPSED=$((NOW_TS - START_TS))
    if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        echo "Ollama server did not become ready within ${MAX_WAIT}s"
        break
    fi
    echo 'A aguardar pelo servidor Ollama...'
    sleep 1
done

# Pull model in background with limited retries to avoid infinite pulling
(
    i=0
    while [ "$i" -lt "$PULL_RETRIES" ]; do
        echo "Attempting to pull model (attempt $((i+1))/${PULL_RETRIES})"
        if ollama pull deepseek-r1:8b; then
            echo "Model pulled successfully"
            break
        else
            echo "Pull failed, retrying after ${PULL_DELAY}s"
            sleep "$PULL_DELAY"
        fi
        i=$((i+1))
    done
    if [ "$i" -ge "$PULL_RETRIES" ]; then
        echo "Model pull failed after ${PULL_RETRIES} attempts; continuing without model."
    fi
) &

# Wait for the server process to exit
wait "$PID"
