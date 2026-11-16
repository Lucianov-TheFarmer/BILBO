# Camada de IA e RAG

O BILBO resume clusters semânticos a partir de anotações GO, seleciona genes representativos entre ontologias e produz uma interpretação com evidências rastreáveis. A recuperação usa embeddings `bge-m3:latest` e BM25 local no Qdrant, com fusão de rankings antes da síntese pelo modelo Ollama configurado no `.env`.

## Índice compartilhado de literatura

Na primeira inicialização, `init.py` inicia o serviço `rag-bootstrap`, que baixa do Zenodo um snapshot versionado do Qdrant e o arquivo BM25 correspondente. O arquivo é validado por checksums antes da restauração e o download é retomável. O estado da preparação fica em `rag_data/bootstrap_status.json`. Os modelos Ollama também são baixados automaticamente e compartilhados entre execuções.

Para iniciar apenas a preparação do índice em uma instalação existente:

```bash
docker compose --profile bootstrap up -d rag-bootstrap
docker compose logs -f rag-bootstrap
```

Quem possui um corpus Markdown próprio pode montar `../Bilbo/artigos` no serviço `rag-indexer` e reconstruir a coleção manualmente:

```bash
docker compose --profile rag-index run --rm rag-indexer
```

Essa operação recria a coleção configurada e não faz parte da inicialização normal. A anotação de entidades com scispaCy é opcional; configure `RAG_ANNOTATE_LITERATURE_ENTITIES=true` apenas em um ambiente que contenha o modelo `en_ner_bionlp13cg_md`.

Para exportar ou importar um índice completo, mantenha juntos o snapshot do Qdrant, `bm25_metadata.json` e o manifesto de checksums:

```bash
make rag-export EXPORT_NAME=literature-backup
make rag-import EXPORT_NAME=literature-backup
```

## Clusterização e RAG sem a interface

O modo independente usa as mesmas funções científicas do aplicativo. Coloque uma planilha `DEG.xlsx` em `ai_data/input` e, após preparar o índice, execute:

```bash
make ai-run DEG_FILE=DEG.xlsx SHEET="Tratamento_vs_Controle" RUN_ID=experimento-01
```

Os resultados aparecem em `ai_data/output/runs/experimento-01`. Para usar diretórios externos, defina `BILBO_AI_INPUT_DIR` e `BILBO_AI_OUTPUT_DIR` no ambiente antes do comando.

## Reprodutibilidade

O relatório registra os genes e contrastes utilizados, as evidências recuperadas, os identificadores das citações, as seções e os títulos disponíveis no índice. Um título genérico produzido pela conversão de PDF é marcado como indisponível; o DOI da fonte permanece clicável. Para corrigir títulos na origem, reconstrua o índice a partir dos artigos com o extrator atualizado.
