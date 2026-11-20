# BILBO: Bioinformatics Integration for Large-scale Biological Operations

[![Docker](https://img.shields.io/badge/Docker-Enabled-blue?logo=docker)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.9+-yellow?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Flet](https://img.shields.io/badge/Frontend-Flet-orange)](https://flet.dev/)

## Overview

BILBO is a containerized RNA-Seq platform that brings together read acquisition, differential expression analysis, semantic clustering, and LLM-assisted interpretation in one web interface. Analyses run through Celery workers, with sample and job records stored in PostgreSQL.

## Getting Started

### Prerequisites

Install Git, Python 3.9+, and Docker with the Compose plugin. The first run also needs enough disk space for the bioinformatics image, Ollama models, the literature index, and analysis data.

### One-line installation

On Linux or macOS:

```bash
git clone https://github.com/Lucianov-TheFarmer/BILBO.git && python3 BILBO/init.py
```

On Windows PowerShell:

```powershell
git clone https://github.com/Lucianov-TheFarmer/BILBO.git; if ($LASTEXITCODE -eq 0) { python BILBO/init.py }
```

The initializer creates a private `.env` from [`.env.example`](.env.example), generates local passwords, validates host ports, builds the images, and starts the services. Ollama models and the shared RAG index begin downloading in the background. **The first startup can take time.** From the `BILBO` directory, follow its progress with:

```bash
docker compose logs -f bioinfo ollama rag-bootstrap
```

When the service is ready, open [http://localhost:8890/frontend](http://localhost:8890/frontend). Google Cloud is not needed for installation; Drive import remains optional until the BILBO maintainers configure one shared OAuth project.

### Local configuration

Edit `BILBO/.env` before startup, or edit it later and run `python3 init.py --no-build` from the repository directory. Git ignores the private file. The initializer preserves existing settings and fills only empty secrets.

| Variable | Purpose | Default |
| --- | --- | --- |
| `BILBO_HOST_PORT` | Port used to open BILBO in the browser | `8890` |
| `BILBO_BIND_ADDRESS` | Host network interface | `127.0.0.1` |
| `BILBO_PUBLIC_BASE_URL` | Public origin when using a domain or HTTPS proxy | Empty; uses `http://localhost:BILBO_HOST_PORT` |
| `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`, `QDRANT_HOST_PORT`, `QDRANT_GRPC_HOST_PORT`, `OLLAMA_HOST_PORT` | External ports for supporting services | See `.env.example` |
| `SECRET_KEY`, `POSTGRES_PASSWORD` | Application secrets | Generated locally |
| `GOOGLE_DRIVE_*` | Credentials for the BILBO OAuth project | Empty; Drive import disabled |

Container **internal** ports stay fixed. Changing `BILBO_HOST_PORT` updates browser downloads, uploads, viewers, CORS, and the derived OAuth callback URL. If Drive import is enabled, register the new callback URI in Google Cloud. See the [Drive import guide](docs/google-drive-import.md).

By default, host ports are accessible only on the server itself. To open BILBO from another computer, use an SSH tunnel. Replace both instances of `8890` with `BILBO_HOST_PORT` and replace `user@server` with your login:

```bash
ssh -L 8890:127.0.0.1:8890 user@server
```

For direct network access, set `BILBO_BIND_ADDRESS=0.0.0.0` and configure an HTTPS origin in `BILBO_PUBLIC_BASE_URL`. The Google OAuth redirect URI must match that origin exactly.

Useful commands from the `BILBO` directory:

```bash
python3 init.py --check       # Validate .env and Compose without starting containers
python3 init.py --no-build    # Restart without rebuilding the image
docker compose ps
docker compose logs -f bioinfo worker
docker compose down
```

Each analysis job keeps a timestamped event history under `users/<user_id>/logs/jobs/<job_id>.progress.log`. The pipeline terminal shows current events and the reason reported by a failed command. FastQC also writes one log per file under `users/<user_id>/QC/<sample>/` or `QC_PostTrim/<sample>/`. See [troubleshooting](docs/source/troubleshooting.rst) for exit codes and diagnostics.

## Core Capabilities

BILBO supports sample acquisition through SRA, local upload, or Google Drive; reference genomes from NCBI, a URL, or local files; FastQC, Trimmomatic, STAR, read quantification, edgeR, scientific figures, GO-based semantic clustering, and RAG interpretation. The **Configure pipeline** dialog lets users select stages and parameters before starting an automatic run.

The quality dialogs and pipeline settings accept FastQC memory **per file** (MiB); trimming accepts a Trimmomatic Java heap limit (MiB). FastQC's `--threads` option controls how many files it processes concurrently, so BILBO manages that parallelism through its quality workers instead of presenting a per-file thread setting. During trimming, growing FASTQ output sizes are shown as activity indicators, not estimated completion percentages.

A public SEQC test subset (GSE47774) is described in [examples/test_data/README.md](examples/test_data/README.md). FASTQ files are retrieved from SRA rather than stored in this repository.

## Technical Architecture

1. **Interface:** Flet.
2. **API:** FastAPI and Uvicorn.
3. **Persistence:** PostgreSQL.
4. **Background work:** Celery and Redis.
5. **Analysis tools:** Python, R, and established RNA-Seq software in Docker containers.

For implementation and administration details, see:

- [AI and RAG layer, literature index, and standalone mode](docs/ai-and-rag.md)
- [Google Drive configuration](docs/google-drive-import.md)
- [Detailed installation guide](docs/source/installation.rst)

## Repository Organization

```text
BILBO/
├── app/
│   ├── backend/        # FastAPI, Celery, and scientific scripts
│   ├── frontend/       # Flet interface
│   └── assets/         # Icons and institutional logos
├── config/             # Conda environment
├── docker-compose.yml  # Services and host ports
├── .env.example        # Configuration template; no real credentials
└── init.py             # One-line installation entry point
```

## Authors

Developed by Vitor Luciano Costa da Silva and Joao Vitor Reis Alvarenga, with support from Manoel Viana Linhares-Neto, Muhammad Noman, and Antonio Chalfun-Junior, at the Plant Molecular Physiology Laboratory (LFMP/UFLA).

<div align="center" style="display: flex; gap: 20px; justify-content: center; background-color: white;">
  <img src="app/assets/src/UFLA.png" alt="UFLA logo" style="width: 150px; height: auto;">
  <img src="app/assets/src/LFMP.png" alt="LFMP logo" style="width: 150px; height: auto;">
</div>

<br>

<div align="right">
  <i>"Happiness is either shared or lost, because no one can be happy alone."</i><br>
  — Carlos Bernardo Gonzalez Pecotche
</div>
