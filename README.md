# BILBO — Bioinformatics Integration for Large-scale Biological Operations

BILBO reúne as etapas de RNA-Seq, da obtenção de reads à análise diferencial, clusterização semântica e interpretação com LLM, em uma interface web. As análises rodam em containers Docker com filas Celery e resultados persistidos no PostgreSQL.

## Instalação rápida

Requisitos: Git, Python 3.9+ e Docker com o plugin Compose em execução. Reserve espaço para a imagem de bioinformática, os modelos Ollama, o índice de literatura e os dados das análises.

Em Linux ou macOS, cole uma linha no terminal:

```bash
git clone https://github.com/Lucianov-TheFarmer/BILBO.git && python3 BILBO/init.py
```

No PowerShell:

```powershell
git clone https://github.com/Lucianov-TheFarmer/BILBO.git; if ($LASTEXITCODE -eq 0) { python BILBO/init.py }
```

O inicializador cria um `.env` privado a partir de [`.env.example`](.env.example), gera senhas locais, valida as portas, constrói as imagens e inicia os serviços. Os modelos Ollama e o índice RAG começam a baixar em segundo plano. **A primeira inicialização pode demorar**; acompanhe com `docker compose logs -f bioinfo ollama rag-bootstrap` dentro da pasta `BILBO`.

Quando o serviço estiver pronto, abra [http://localhost:8890/frontend](http://localhost:8890/frontend). A instalação não exige Google Cloud: o importador do Drive fica opcional até os mantenedores configurarem um único projeto OAuth do BILBO.

### Configuração local

Edite `BILBO/.env` antes de iniciar, ou altere-o depois e execute `python3 init.py --no-build` na pasta do projeto. O arquivo `.env` é ignorado pelo Git. O inicializador mantém os valores que você já configurou e só gera os segredos que estiverem vazios.

| Variável | Uso | Padrão |
| --- | --- | --- |
| `BILBO_HOST_PORT` | Porta para abrir o BILBO no navegador | `8890` |
| `BILBO_BIND_ADDRESS` | Interface de rede do hospedeiro | `127.0.0.1` |
| `BILBO_PUBLIC_BASE_URL` | Origem pública, se usar domínio ou proxy HTTPS | vazio; usa `http://localhost:BILBO_HOST_PORT` |
| `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`, `QDRANT_HOST_PORT`, `QDRANT_GRPC_HOST_PORT`, `OLLAMA_HOST_PORT` | Portas externas dos serviços auxiliares | ver `.env.example` |
| `SECRET_KEY`, `POSTGRES_PASSWORD` | Segredos gerados na primeira inicialização | gerados localmente |
| `GOOGLE_DRIVE_*` | Credenciais do projeto OAuth mantido pelo BILBO | vazias; integração desativada |

As portas **internas** dos containers permanecem fixas; altere apenas as portas externas no `.env`. Assim, uma alteração de `BILBO_HOST_PORT` atualiza os links de download, upload, visualização, CORS e o retorno OAuth. Se o Google Drive estiver ativado, cadastre a nova URI de retorno no projeto Google Cloud. Veja o [guia de importação do Drive](docs/google-drive-import.md).

Por padrão as portas são acessíveis só no próprio servidor. Para abrir o BILBO de outro computador por SSH, use um túnel; troque `8890` pelo valor de `BILBO_HOST_PORT` e `usuario@servidor` pelo seu acesso:

```bash
ssh -L 8890:127.0.0.1:8890 usuario@servidor
```

Para acesso direto pela rede, configure `BILBO_BIND_ADDRESS=0.0.0.0` e uma origem HTTPS em `BILBO_PUBLIC_BASE_URL`, com proteção de acesso adequada ao servidor. O endereço OAuth do Google deve corresponder exatamente à origem configurada.

Comandos úteis, executados dentro de `BILBO`:

```bash
python3 init.py --check       # valida .env e Compose sem iniciar containers
python3 init.py --no-build    # reinicia sem reconstruir a imagem
docker compose ps
docker compose logs -f bioinfo worker
docker compose down
```

## Etapas de análise

O BILBO oferece importação de amostras por SRA, upload ou Google Drive; genoma de referência por NCBI, URL ou upload; FastQC, Trimmomatic, STAR, quantificação, edgeR, figuras, clusterização por GO e interpretação RAG. O modal **Configurar pipeline** permite escolher etapas e parâmetros antes de iniciar uma execução automática.

O conjunto público de teste SEQC (GSE47774) está descrito em [examples/test_data/README.md](examples/test_data/README.md). Os FASTQ são obtidos do SRA e não ficam no repositório.

## Documentação técnica

- [Camada de IA e RAG, índice de literatura e modo independente](docs/ai-and-rag.md)
- [Configuração do Google Drive](docs/google-drive-import.md)
- [Instalação detalhada](docs/source/installation.rst)

## Organização

```text
app/backend/       FastAPI, Celery e scripts científicos
app/frontend/      interface Flet
config/            ambiente Conda
docker-compose.yml serviços e portas
init.py            instalação em um comando
.env.example       opções de configuração, sem credenciais reais
```

Desenvolvido por Vitor Luciano Costa da Silva e Joao Vitor Reis Alvarenga, com apoio de Manoel Viana Linhares-Neto, Muhammad Noman e Antonio Chalfun-Junior, no LFMP/UFLA.
