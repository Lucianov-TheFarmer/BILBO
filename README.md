# BILBO: Bioinformatics Integration for Large-scale Biological Operations

[![Docker](https://img.shields.io/badge/Docker-Enabled-blue?logo=docker)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.9+-yellow?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Flet](https://img.shields.io/badge/Frontend-Flet-orange)](https://flet.dev/)

## Overview

BILBO is a containerized, end-to-end RNA-Seq analysis platform designed to improve reproducibility, reduce operational overhead, and accelerate biological interpretation. The system integrates established bioinformatics tools, asynchronous job orchestration, and retrieval-augmented language modeling in a single user-facing environment.

The core objective is to keep researchers focused on biological inference rather than infrastructure setup, dependency conflicts, and command-line pipeline management.

## Scientific Motivation

RNA-Seq workflows are typically fragmented across heterogeneous tools, scripting languages, and execution environments. This fragmentation introduces variability in execution and increases the cost of technical maintenance. BILBO addresses this challenge by providing:

1. A standardized computational environment (Docker-based).
2. A stage-oriented analytical workflow from raw reads to interpretation.
3. Traceable asynchronous execution with explicit job states.
4. Integrated RAG-assisted interpretation of cluster and DEG-derived results.

## Core Capabilities

BILBO covers the complete RNA-Seq processing and interpretation lifecycle:

1. Genome and annotation handling.
2. Automated SRA acquisition through SRA Toolkit.
3. Pre- and post-trimming quality control (FastQC-based steps).
4. Adapter trimming and quality filtering (Trimmomatic).
5. Reference indexing and read alignment (STAR).
6. Quantification and count matrix generation (HTSeq-count).
7. Differential expression analysis (EdgeR in R).
8. Scientific visual outputs (heatmaps, Venn diagrams, barplots, DEG artifacts).
9. Semantic clustering for downstream biological grouping.
10. LLM-assisted interpretation using local RAG infrastructure.

## Technical Architecture

### Languages and Runtime

1. Python 3.9+ (backend services and frontend logic).
2. R (statistical modeling and plotting workflows).
3. Bash (pipeline orchestration scripts for external tools).

### Application Stack

1. Frontend: Flet.
2. Backend API: FastAPI + Uvicorn.
3. Persistence: PostgreSQL (sample metadata, stage status, jobs, artifacts).
4. Task queue: Celery + Redis (asynchronous execution with job tracking).
5. Containerization: Docker + Docker Compose.

## AI and RAG Layer

BILBO follows the validated ``Bilbo/`` prototype: GO-Wang semantic clusters are first summarized from their own function/GO annotations, representatives are selected by recurrence across GO ontologies, and only then a traceable gene-level RAG is executed with Ollama and Qdrant.

### Shared literature index

The shared corpus uses ``bge-m3:latest`` dense vectors and local BM25 sparse vectors in Qdrant. Retrieval fuses both rankings with RRF and performs the prototype's name/context/entity reranking before synthesis with ``gemma4:e4b``.

The repository Compose configuration mounts the prototype corpus from
``../Bilbo/artigos`` read-only at ``/rag/articles``. Build the shared index once:

```bash
docker compose --profile rag-index run --rm rag-indexer
```

The operation recreates the configured collection and may take a long time. It
is an administrative operation and must not run during application startup.

Export the Qdrant collection together with the required BM25 metadata:

```bash
make rag-export EXPORT_NAME=literature-2026-08-06
```

This creates ``rag_data/exports/literature-2026-08-06`` containing the Qdrant
snapshot, ``bm25_metadata.json`` and a checksummed manifest. Restore it into a
Qdrant 1.15.x instance with a patch version equal to or newer than the source:

```bash
make rag-import EXPORT_NAME=literature-2026-08-06
```

Import uses Qdrant snapshot priority and validates file checksums and point
counts before installing the BM25 metadata. Keep the whole export directory;
the Qdrant snapshot alone is insufficient for BILBO's hybrid retrieval.

Entity annotation is optional in the standard image. Set ``RAG_ANNOTATE_LITERATURE_ENTITIES=true`` when the indexing environment contains scispaCy and ``en_ner_bionlp13cg_md``.

### Standalone Cluster + RAG mode

Clustering and literature interpretation can run without the API, frontend,
PostgreSQL, Redis, or Celery. Place an existing ``DEG.xlsx`` workbook in
``ai_data/input`` and ensure that the shared literature index has already been
built or imported. Then run:

```bash
make ai-run DEG_FILE=DEG.xlsx SHEET="Treatment_vs_Control" RUN_ID=experiment-01
```

Compose starts only the one-shot ``cluster-rag`` runner and its Qdrant and
Ollama dependencies. Results are written under
``ai_data/output/runs/experiment-01``. The runner calls the same clustering,
prioritization, retrieval, and interpretation functions used by the complete
application; it does not maintain a separate scientific implementation.

Use custom host directories without copying data into the repository:

```bash
BILBO_AI_INPUT_DIR=/data/inputs BILBO_AI_OUTPUT_DIR=/data/results \
  make ai-run DEG_FILE=DEG.xlsx SHEET="Treatment_vs_Control"
```

## Environment Variables

Configure the following variables for secure and predictable operation:

1. SECRET_KEY (required in production).
2. DATABASE_URL, or POSTGRES_HOST, POSTGRES_PORT, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB.
3. CORS_ORIGINS.
4. CELERY_BROKER_URL.
5. CELERY_RESULT_BACKEND.
6. CLUSTER_INTERPRETATION_MODEL (default: gemma4:e4b).
7. RAG_LLM_MODEL (default: gemma4:e4b).
8. RAG_EMBEDDING_MODEL (default: bge-m3:latest).
9. QDRANT_URL and QDRANT_COLLECTION.
10. BM25_METADATA_PATH.
11. ARTIFACT_RETENTION_DAYS, LOG_RETENTION_DAYS and AUDIT_RETENTION_DAYS.

## Getting Started

### Prerequisites

1. Docker.
2. Docker Compose.
3. Python 3 (only required for the optional initialization helper script).

### Installation and startup

```bash
# Clone repository
git clone https://github.com/Lucianov-TheFarmer/BILBO.git

# Enter project directory
cd BILBO

# Optional helper bootstrap
python init.py

# Or start the complete application stack
make full-up
```

Use ``make full-build`` instead when the application image must be rebuilt.
The complete mode starts the API/frontend container, Celery worker, PostgreSQL,
Redis, Qdrant, Ollama, SSH gateway, and pgAdmin. Administrative one-shot
services such as the RAG indexer remain opt-in through their Compose profiles.

Inspect or stop the complete stack with:

```bash
make full-status
make full-logs
make full-down
```

The complete and standalone modes share the same Ollama model volume, Qdrant
collection, and BM25 metadata. Consequently, an index built or imported for one
mode is immediately available to the other.

## Public test dataset

A versioned manifest for a four-run subset of the real, publicly accessible
SEQC dataset (GSE47774) is provided in `examples/test_data`. The subset contains
two paired-end replicates from group A and two from group B and uses Ensembl
GRCh38 release 112, as adopted in the BILBO benchmark.

The repository records the accessions, experimental groups, reference files,
and execution instructions. Raw sequencing files are retrieved directly from
SRA and are not duplicated in the repository.

See [`examples/test_data/README.md`](examples/test_data/README.md) for details.

## Repository Organization

```text
BILBO/
├── app/
│   ├── backend/       # FastAPI, Database and R/Bash/Python scripts
│   ├── frontend/      # Flet interface and UI procedures
│   └── assets/        # Icons and visual identity assets
├── config/            # Conda and runtime configuration
├── Dockerfile         # Main execution image
├── docker-compose.yml # Multi-container orchestration
└── init.py            # Optional startup bootstrap
```

## Job API

Long-running operations are asynchronous and return HTTP 202 with a job descriptor.

Main endpoints:

1. POST /jobs/{stage}/enqueue
2. GET /jobs/{job_id}
3. GET /jobs?stage=&status=
4. POST /jobs/{job_id}/cancel
5. GET /jobs/{job_id}/artifacts

## Reproducibility and Traceability

BILBO was designed to improve methodological consistency by combining:

1. Fixed execution environments.
2. Stage-level status persistence in the database.
3. Artifact tracking per job.
4. Auditable asynchronous job lifecycle.

## Authors

Developed by Vitor Luciano Costa da Silva and Joao Vitor Reis Alvarenga, with support from Manoel Viana Linhares-Neto, Muhammad Noman, and Antonio Chalfun-Junior, at the Plant Molecular Physiology Laboratory (LFMP/UFLA).

<div align="center" style="display: flex; gap: 20px; justify-content: center; background-color: white;">
  <img src="app/assets/src/UFLA.png" alt="Logo UFLA" style="width: 150px; height: auto;">
  <img src="app/assets/src/LFMP.png" alt="Logo LFMP" style="width: 150px; height: auto;">
</div>

<br>

<div align="right">
<i>"Happiness is either shared or lost, because no one can be happy alone."</i>
</div>

<div align="right">
    - Carlos Bernardo Gonzalez Pecotche
</div>
