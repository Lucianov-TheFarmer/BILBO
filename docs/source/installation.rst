Installation and Deployment
===========================

Prerequisites
-------------

BILBO is designed to run through Docker Compose. A typical deployment requires:

* Docker.
* Docker Compose.
* Sufficient disk space for FASTQ, BAM, reference genome, index, count, and result artifacts.
* Enough memory for STAR genome indexing and alignment. Large eukaryotic genomes can require substantial RAM.
* Network access for SRA downloads, genome downloads, first-use RAG database bootstrap, and optional model acquisition.

Starting the Platform
---------------------

From the project root:

.. code-block:: bash

   docker compose up -d bioinfo worker db redis ollama

The backend API is exposed on port ``8000`` by default. The Ollama container is exposed through ``OLLAMA_HOST_PORT`` with a default host-side port of ``11435``.

Environment Variables
---------------------

Important variables include:

.. list-table:: Environment variables
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Meaning
   * - ``SECRET_KEY``
     - Required for production authentication.
   * - ``DATABASE_URL`` or PostgreSQL fields
     - Database connection settings.
   * - ``CELERY_BROKER_URL``
     - Redis broker URL.
   * - ``CELERY_RESULT_BACKEND``
     - Redis result backend URL.
   * - ``LLM_PRIMARY_MODEL``
     - Primary Ollama model, default ``qwen3:14b``.
   * - ``LLM_FALLBACK_MODELS``
     - Comma-separated fallback models, default ``qwen3:8b,qwen3:0.6b``.
   * - ``BILBO_RAG_DB_URL``
     - Optional replacement URL for the RAG literature index archive, when the configured deployment uses automatic bootstrap.
   * - ``FASTERQ_MAX_ATTEMPTS``
     - Number of SRA download retry attempts; default ``3``.

Reference Genome Requirements
-----------------------------

BILBO expects downloaded reference directories under ``users/ref_genomes/<accession>/`` with genome FASTA and annotation files. Quantification searches for ``genomic.gff``, ``genomic.gff3``, or ``genomic.gtf``.

Read the Docs Build
-------------------

The documentation is configured through ``.readthedocs.yaml`` and can also be built locally:

.. code-block:: powershell

   cd docs
   pip install -r requirements.txt
   .\make.bat html

The generated HTML will be written to ``docs/build/html``.
