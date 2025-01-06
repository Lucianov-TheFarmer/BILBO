#!/bin/sh

# Esperar um pouco para garantir que o arquivo ngrok_url.txt foi criado
sleep 5

# Ler o JSON do arquivo ngrok_url.txt
NGROK_JSON=$(cat /app/backend/temp/ngrok_url.txt)

# Extrair a URL pública usando sed
NGROK_URL=$(echo "$NGROK_JSON" | sed -n 's/.*"public_url":"\([^"]*\)".*/\1/p')

# Verificar se a URL foi obtida corretamente
if [ -z "$NGROK_URL" ]; then
  echo "Erro: Não foi possível obter a URL do ngrok."
  exit 1
fi

# Printar a URL no terminal
echo "URL do ngrok: $NGROK_URL/frontend"