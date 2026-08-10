Architecture
============

BILBO combines a graphical frontend, a FastAPI backend, a PostgreSQL database, a Redis/Celery asynchronous execution layer, external bioinformatics tools, R statistical scripts, and local LLM infrastructure.

Software Components
-------------------

.. list-table:: Main components
   :header-rows: 1
   :widths: 24 28 48

   * - Component
     - Implementation
     - Role
   * - Frontend
     - Flet
     - Provides the graphical interface for upload, sample selection, parameter entry, stage execution, and result viewing.
   * - Backend API
     - FastAPI and Uvicorn
     - Authenticates users, validates requests, records sample stages, creates jobs, and serves artifacts.
   * - Database
     - PostgreSQL
     - Stores users, sample-stage records, pipeline jobs, artifacts, and audit logs.
   * - Queue
     - Celery with Redis
     - Executes long-running alignment, quantification, DEG, clustering, LLM, and visualization jobs asynchronously.
   * - Bioinformatics runtime
     - Conda environment ``bioinfo``
     - Provides FastQC, Trimmomatic, STAR, Picard, HTSeq, Samtools, SRA Toolkit, R, edgeR, and supporting Python packages.
   * - LLM layer
     - Ollama and hybrid retrieval infrastructure
     - Performs local retrieval-augmented interpretation of clustered DEG outputs.

Container Layout
----------------

The Docker Compose configuration defines the following services:

* ``bioinfo``: API container exposing port ``8890``.
* ``worker``: Celery worker with concurrency set to ``1`` by default.
* ``redis``: message broker and result backend.
* ``db``: PostgreSQL 13.
* ``ollama``: local model server.
* ``pgadmin`` and ``ssh-server``: optional administrative services.

Data Layout
-----------

User data are stored under ``users/<user_id>/``. Major subdirectories include:

* ``samples/``: downloaded or uploaded FASTQ files.
* ``QC/``: pre-trimming FastQC outputs.
* ``trimmed/``: Trimmomatic outputs.
* ``QC_PostTrim/``: post-trimming FastQC outputs.
* ``alignment/``: STAR/Picard BAM outputs.
* ``quantification/``: HTSeq-count tables.
* ``preprocess/``: edgeR input files, including ``Targets.txt``.
* ``DEG/``: ``DEG.xlsx``, ``DEG_full.xlsx``, plots, Venn diagrams, and heatmaps.
* ``clustering/``: cluster maps, metrics, and structured ``clusters.json`` files.
* ``llm/``: RAG/LLM reports and JSON artifacts.

Asynchronous Jobs
-----------------

Long-running stages are represented as pipeline jobs with explicit status fields. The backend records job creation, execution, completion, failure, artifacts, and audit events. This design improves traceability and avoids blocking the graphical interface during computationally expensive operations.
