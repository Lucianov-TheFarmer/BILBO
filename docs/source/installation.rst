Installation and Deployment
===========================

Prerequisites
-------------

BILBO is designed to run through Docker Compose. A typical deployment requires:

* Docker.
* Docker Compose.
* Sufficient disk space for FASTQ, BAM, reference genome, index, count, and result artifacts.
* Enough memory for STAR genome indexing and alignment. Large eukaryotic genomes can require substantial RAM.
* Network access for SRA/genome downloads and initial Ollama model acquisition.
* A shared Qdrant index and matching BM25 metadata generated from the literature corpus.

Starting the Platform
---------------------

From the project root:

.. code-block:: bash

   docker compose up -d bioinfo worker db redis qdrant ollama

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
   * - ``CLUSTER_INTERPRETATION_MODEL``
     - Prototype cluster-summary model, default ``gemma4:e4b``.
   * - ``RAG_LLM_MODEL``
     - Evidence synthesis model, default ``gemma4:e4b``.
   * - ``RAG_EMBEDDING_MODEL``
     - Dense retrieval model, default ``bge-m3:latest``.
   * - ``QDRANT_URL`` and ``QDRANT_COLLECTION``
     - Shared hybrid literature index location and collection.
   * - ``BM25_METADATA_PATH``
     - BM25 vocabulary and IDF metadata generated with the Qdrant collection.
   * - ``FASTERQ_MAX_ATTEMPTS``
     - Number of SRA download retry attempts; default ``3``.

Building the Shared Literature Index
------------------------------------

The Compose configuration mounts the prototype Markdown corpus from
``../Bilbo/artigos`` read-only at ``/rag/articles``. Run the administrative
indexer once:

.. code-block:: bash

   docker compose --profile rag-index run --rm rag-indexer

The command recreates the Qdrant collection and writes
``rag_data/bm25_metadata.json``. Do not run it as part of an individual user's
analysis. Entity annotation can be enabled with
``RAG_ANNOTATE_LITERATURE_ENTITIES=true`` in an indexing image containing
scispaCy and ``en_ner_bionlp13cg_md``.

Exporting and Importing the Literature Index
--------------------------------------------

Qdrant collection snapshots are the portable backup unit used by BILBO. The
export command also copies the BM25 vocabulary and writes a manifest containing
checksums and the expected point count:

.. code-block:: bash

   make rag-export EXPORT_NAME=literature-2026-08-06

The result is stored under ``rag_data/exports/literature-2026-08-06``. Copy the
complete directory to the destination installation, not only the ``.snapshot``
file, because hybrid retrieval also requires ``bm25_metadata.json``.

Restore the export with:

.. code-block:: bash

   make rag-import EXPORT_NAME=literature-2026-08-06

The destination must run Qdrant 1.15.x, with a patch version equal to or newer
than the source snapshot. Import verifies SHA-256 checksums, restores with
``priority=snapshot``, confirms the point count and then installs BM25 metadata.
If ``QDRANT_API_KEY`` is configured, both commands send it to the snapshot API.

These are administrative commands. Do not run indexing, export, or import as
part of FastAPI startup or an individual user's analysis.

Standalone Cluster and RAG Execution
-------------------------------------

An existing ``DEG.xlsx`` workbook can be processed without starting the API,
frontend, database, Redis, or Celery. Copy the workbook to ``ai_data/input``
and run:

.. code-block:: bash

   make ai-run DEG_FILE=DEG.xlsx SHEET="Treatment_vs_Control" RUN_ID=experiment-01

The one-shot runner starts only its Qdrant and Ollama dependencies and writes
the clustering, prioritization, retrieved evidence, and interpretation outputs
under ``ai_data/output/runs/experiment-01``. Set ``BILBO_AI_INPUT_DIR`` and
``BILBO_AI_OUTPUT_DIR`` to use directories outside the repository.

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
