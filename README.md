# 🧙‍♂️ BILBO: BIoinformatics and RNA-Seq LaB Online

[![Docker](https://img.shields.io/badge/Docker-Enabled-blue?logo=docker)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.9+-yellow?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Flet](https://img.shields.io/badge/Frontend-Flet-orange)](https://flet.dev/)

> **BILBO** é uma plataforma integrada e "dockerizada" projetada para simplificar o complexo pipeline de análise de RNA-Seq. Combinando ferramentas de bioinformática consagradas com uma interface moderna e assistência de IA, o BILBO transforma dados brutos em insights biológicos de forma intuitiva.

---

## 📋 Sobre o Projeto

A análise de transcriptômica (RNA-Seq) envolve o uso de diversas ferramentas de linha de comando, gerenciamento de dependências e scripts complexos em R e Python. O **BILBO** (Bioinformatics and RNA-Seq Lab Online) nasce para eliminar essa barreira, oferecendo um ambiente pronto para uso onde o foco do pesquisador permanece na **biologia**, não na configuração do servidor.

Seja você um estudante aprendendo bioinformática ou um pesquisador processando amostras reais, o BILBO oferece as ferramentas necessárias dentro de uma infraestrutura escalável e isolada.

---

## ✨ Funcionalidades Principais

O BILBO cobre todo o fluxo de trabalho de RNA-Seq:

* **🧬 Gestão de Genomas:** Busca automatizada e download de genomas e arquivos de anotação (GFF/GTF).
* **📥 Download de SRA:** Integração com o *SRA Toolkit* para baixar amostras diretamente do NCBI.
* **🛠️ Controle de Qualidade e Trimming:** * Análise de qualidade pré e pós-processamento (FastQC/MultiQC).
    * Limpeza de adaptadores e filtros de qualidade via *Trimmomatic*.
* **🎯 Alinhamento e Mapeamento:** Indexação de genomas e alinhamento de reads utilizando o *STAR* (Spliced Transcripts Alignment to a Reference).
* **📊 Expressão Diferencial (DEG):** * Quantificação de abundância com *featureCounts*.
    * Análises estatísticas robustas usando *EdgeR* em R.
* **🎨 Visualização de Dados:** Geração automática de Heatmaps, Diagramas de Venn e Gráficos de Barras para genes diferencialmente expressos.
* **🤖 Assistência via IA (RAG):** Integração com *Ollama* para permitir conversas inteligentes sobre os seus resultados de bioinformática.
* **🖥️ Interface Unificada:** Frontend amigável construído em *Flet*, permitindo operar ferramentas complexas sem digitar uma única linha de código Bash.

## 🛠️ Stack Tecnológica

O BILBO é construído sobre uma arquitetura robusta para garantir reprodutibilidade e desempenho:

* **Linguagens:** Python 3.9+ (Backend e Interface), R (Análises Estatísticas), Bash (Automação de Ferramentas).
* **Interface (GUI):** [Flet](https://flet.dev/) - Uma interface moderna e responsiva baseada em Flutter.
* **Backend & API:** [FastAPI](https://fastapi.tiangolo.com/) com Uvicorn.
* **Banco de Dados:** PostgreSQL (armazenamento de metadados de amostras e estágios do pipeline).
* **Containerização:** Docker & Docker Compose (Isolamento total do ambiente).
* **Orquestração de jobs:** Celery + Redis (execução assíncrona e rastreável por `job_id`).
* **Ferramentas de Bioinformática:**
    * `SRA Toolkit` (Download de dados)
    * `STAR` (Alinhamento de alta performance)
    * `Trimmomatic` (Limpeza de reads)
    * `EdgeR` (Análise de expressão diferencial)
    * `FastQC` / `MultiQC` (Relatórios de qualidade)

---

## 🚀 Como Começar

O BILBO foi projetado para ser "Plug and Play". Siga os passos abaixo para preparar seu laboratório virtual.

### Variáveis de ambiente obrigatórias
Para publicação/produção, configure:

* `SECRET_KEY` (obrigatória, sem valor padrão inseguro)
* `DATABASE_URL` (ou `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`)
* `CORS_ORIGINS` (lista separada por vírgula)
* `CELERY_BROKER_URL`
* `CELERY_RESULT_BACKEND`
* `LLM_PRIMARY_MODEL` (default `qwen3:14b`)
* `LLM_FALLBACK_MODELS` (default `qwen3:8b,qwen3:0.6b`)
* `ARTIFACT_RETENTION_DAYS`, `LOG_RETENTION_DAYS`, `AUDIT_RETENTION_DAYS`

### 1. Pré-requisitos
Certifique-se de ter instalado em sua máquina:
* [Docker](https://docs.docker.com/get-docker/)
* [Docker Compose](https://docs.docker.com/compose/install/)
* [Python 3](https://www.python.org/downloads/) (apenas para rodar o script de inicialização automática)

### 2. Instalação e Inicialização
Clone o repositório e utilize o script `init.py` que automatiza todo o processo de build e configuração de rede:

### 2. Instalação e Inicialização

O BILBO utiliza um script inteligente que prepara todo o ambiente para você. Siga os comandos abaixo:

```bash
# 1. Clone o repositório
git clone [https://github.com/seu-usuario/bilbo.git](https://github.com/seu-usuario/bilbo.git)

# 2. Entre na pasta do projeto
cd bilbo

# 3. Execute o inicializador automático
python init.py

# ou diretamente com Docker Compose
docker compose up -d bioinfo worker db redis ollama
```

### Troubleshooting rápido: erro de senha do Postgres

Se aparecer no log:

* `PostgreSQL Database directory appears to contain a database; Skipping initialization`
* `password authentication failed for user "postgres"`

o volume do banco foi criado com senha antiga. Para alinhar com o `.env` atual:

```bash
docker compose down
docker volume rm bilbo_postgres_data
docker compose up -d db
docker compose logs -f db
# aguarde: "database system is ready to accept connections"
docker compose up -d --build redis ollama bioinfo worker
```

Validação:

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

## organização dos arquivos
bilbo/
├── app/
│   ├── backend/       # API FastAPI, Banco de Dados e Scripts (R/Bash)
│   ├── frontend/      # Interface Flet e componentes de UI
│   └── assets/        # Identidade visual (ícones e logotipos)
├── config/            # Definições de ambiente (Conda/YML)
├── Dockerfile         # Receita da imagem principal (Ferramentas de Bioinfo)
├── docker-compose.yml # Orquestração multi-container
└── init.py            # Orquestrador de inicialização do sistema
```


## 🧬 Fluxo de Trabalho (Pipeline)

O BILBO organiza a análise de RNA-Seq em etapas lógicas, acessíveis pelo menu lateral da interface:

1.  **Upload & Samples:** Importe seus arquivos `.fastq` ou utilize o buscador integrado para baixar dados diretamente do SRA (NCBI).
2.  **Pre-processing:** Realize o controle de qualidade (FastQC) e a limpeza de adaptadores (Trimmomatic).
3.  **Alignment:** Mapeie suas sequências contra um genoma de referência utilizando o alinhador *STAR*.
4.  **Quantification:** Gere a matriz de contagem de genes com o *featureCounts*.
5.  **Differential Expression (DEG):** Execute a análise estatística com *EdgeR* para identificar genes super ou subexpressos.
6.  **Results & Plots:** Visualize Heatmaps, Volcano Plots e Diagramas de Venn prontos para publicação.

---

## 🤖 Assistência Inteligente (RAG + Ollama)

Um diferencial exclusivo do BILBO é a integração com o **Ollama**.
A plataforma utiliza uma técnica chamada **RAG (Retrieval-Augmented Generation)** para conectar os resultados da sua análise (como a lista de genes diferencialmente expressos) a um modelo de linguagem local.

* **Interpretação de Genes:** Pergunte à IA sobre a função biológica dos genes encontrados.
* **Insights Científicos:** Peça resumos sobre as vias metabólicas afetadas em seu experimento.
* **Privacidade:** Todo o processamento da IA ocorre localmente dentro do container, sem enviar seus dados para a nuvem.

### Política de modelo LLM

O backend prioriza `qwen3:14b` e aplica fallback automático para `qwen3:8b` e `qwen3:0.6b` quando necessário.

## 🧪 Qualidade e DevEx

Comandos utilitários:

```bash
make lint
make test
make run
make worker
```

## 🧭 API de Jobs

Endpoints principais:

* `POST /jobs/{stage}/enqueue`
* `GET /jobs/{job_id}`
* `GET /jobs?stage=&status=`
* `POST /jobs/{job_id}/cancel`
* `GET /jobs/{job_id}/artifacts`

As rotas longas do pipeline retornam `202` com `{job_id, status, message}`.

---

## 👨‍🔬 Autores

Desenvolvido por **[Vitor Luciano e João Vitor Reis Alvarenga]** no Laboratório de Fisiologia Molecular de Plantas (**LFMP/UFLA**).

> "Simplicidade é o último grau de sofisticação aplicado à Bioinformática."
