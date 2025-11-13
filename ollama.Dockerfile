FROM ollama/ollama
RUN sh -c "ollama serve & \
    while ! ollama list >/dev/null 2>&1; do \
        echo 'A aguardar pelo servidor Ollama...'; \
        sleep 1; \
    done; \
    ollama pull deepseek-r1:8b"
