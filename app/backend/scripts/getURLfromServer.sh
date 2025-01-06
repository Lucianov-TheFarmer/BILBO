#!/bin/sh

# Esperar um pouco para garantir que o ngrok está iniciado
sleep 3

# Obter o JSON do túnel gerado pelo ngrok e salvar em ngrok_url.txt
curl -s http://localhost:4040/api/tunnels > /app/temp/ngrok_url.txt