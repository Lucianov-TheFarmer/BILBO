FROM ollama/ollama
<<<<<<< HEAD
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
# ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
EXPOSE 11434
=======
RUN sh -c "ollama serve & \
    while ! ollama list >/dev/null 2>&1; do \
        echo 'A aguardar pelo servidor Ollama...'; \
        sleep 1; \
    done; \
    ollama pull qwen3:0.6b"
>>>>>>> 27ba8b27e8c3f35446f35e4e950237c819c9521a
