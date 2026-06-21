Implementation Notes
====================

This page records implementation details that affect scientific interpretation.

Code Locations
--------------

.. list-table:: Key implementation files
   :header-rows: 1
   :widths: 34 66

   * - File
     - Role
   * - ``app/backend/scripts/trimmagem.sh``
     - Builds and runs the Trimmomatic command.
   * - ``app/backend/routes/trimmagem.py``
     - Receives GUI trimming parameters and writes custom adapter files.
   * - ``app/backend/scripts/index_genome_star.sh``
     - Builds the STAR genome index.
   * - ``app/backend/scripts/alignment.sh``
     - Runs STAR and Picard processing.
   * - ``app/backend/scripts/quantification.sh``
     - Runs HTSeq-count and feature/attribute fallback logic.
   * - ``app/backend/routes/preprocess.py``
     - Writes ``Targets.txt`` from selected contrasts.
   * - ``app/backend/scripts/preprocess.R``
     - Generates edgeR preprocessing and QC plots.
   * - ``app/backend/scripts/DEG.R``
     - Runs edgeR differential expression and writes DEG workbooks.
   * - ``app/backend/scripts/clustering.py``
     - Performs functional annotation clustering and structured cluster export.
   * - ``app/backend/scripts/llm.py``
     - Performs RAG retrieval, evidence-constrained interpretation, and report export.
   * - ``app/backend/tasks/pipeline_tasks.py``
     - Orchestrates asynchronous pipeline jobs and artifact records.

Current Fixed Settings
----------------------

Some important settings are fixed in scripts rather than exposed through the interface:

* Picard duplicate removal: ``REMOVE_DUPLICATES=true``.
* HTSeq strandedness: ``--stranded=no``.
* HTSeq minimum alignment quality: ``-a 10``.
* edgeR low-expression filter: row mean count ``>= 10``.
* edgeR significant DEG export: ``FDR <= 0.05`` and ``abs(logFC) >= 1``.
* Celery worker concurrency: ``1`` in ``docker-compose.yml``.

Documentation Implication
-------------------------

Because these settings can affect results, they must be documented in any analysis performed with BILBO. Where a setting is unsuitable for a dataset, users should modify the implementation, wait for a configurable release, or export intermediate files for an external analysis.

Scientific Scope
----------------

BILBO is best understood as a reproducible, user-accessible platform for standardized bulk RNA-seq processing and interpretation. It is not a substitute for experimental design, sample metadata curation, or statistical modeling expertise.
