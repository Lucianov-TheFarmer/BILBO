Troubleshooting
===============

SRA Download Fails
------------------

Possible causes:

* Network interruption.
* Invalid accession.
* SRA Lite or missing quality columns.
* Temporary NCBI service issues.
* Insufficient disk space.

Check the download log under ``app/backend/logs/<accession>_download.log``.

FastQC Stops Before Finishing
----------------------------

FastQC ``FAILED`` means the program did not finish; it does not mean the reads failed a quality metric. The per-file logs are under ``users/<user_id>/QC/<sample>/`` for initial quality and ``users/<user_id>/QC_PostTrim/<sample>/`` after trimming. The final log line records the exit code. Code 124 means the configured time limit expired; code 137 means the process received SIGKILL, which can indicate a memory limit or external termination. Other errors may identify malformed FASTQ records or missing files.

The default per-file limit is ``BILBO_FASTQC_TIMEOUT=170m`` in ``.env``. A user can increase it for slow disks or large libraries and restart the quality worker with ``docker compose up -d --no-deps quality-worker``. This setting does not allocate more CPUs or memory. The worker log is available with ``docker compose logs --tail=200 quality-worker``. Per-job event histories are stored at ``users/<user_id>/logs/jobs/<job_id>.progress.log`` and appear in the pipeline terminal.

Trimming Produces Too Few Reads
-------------------------------

Possible causes:

* Wrong adapter file.
* Overly aggressive ``SLIDINGWINDOW``, ``MINLEN``, ``CROP``, or ``AVGQUAL``.
* Poor initial sequencing quality.
* Incorrect Phred encoding.

Compare pre- and post-trim FastQC reports and examine read-length distributions.
Trimmomatic's per-sample log is under ``users/<user_id>/logs/trimming/<sample>.log``.

STAR Indexing Fails
-------------------

Possible causes:

* Insufficient RAM.
* Missing or malformed FASTA.
* Missing or malformed annotation.
* Incorrect ``sjdbOverhang``.
* Insufficient disk space.

For large genomes, use a system with more memory or adjust STAR indexing strategy.

Alignment Fails
---------------

The current alignment stage expects paired-end trimmed files. If only single-end trimmed files are present, alignment will fail because the script searches for both ``<sample>_1_trimmed.fastq`` and ``<sample>_2_trimmed.fastq``.

Other causes include:

* Missing STAR index.
* Wrong sample basename.
* Corrupted FASTQ files.
* Incompatible STAR filter parameters.

Quantification Fails
--------------------

Possible causes:

* BAM file not found.
* Reference genome directory cannot be resolved.
* Annotation file absent from the selected reference directory.
* Requested feature type is absent.
* Requested ID attribute is absent and no fallback can be found.
* Strandedness mismatch causes unexpectedly low assignment, even if the command completes.

Open ``users/<user_id>/logs/quantification/<sample>.bam.log`` (or the log icon in the quantification table) and confirm the actual feature type and ID attribute used after fallback. The icon is available for failed jobs too.

DEG Analysis Produces No Significant Genes
------------------------------------------

This can be biologically valid, but also check:

* Group labels and contrast direction.
* Replicate assignment.
* Count matrix dimensions.
* Library sizes and normalization plots.
* Excessive duplicate removal.
* Wrong strandedness.
* Wrong annotation feature/ID choice.
* Overly stringent filtering or logFC threshold.

Clustering Fails
----------------

The clustering script requires enough rows with functional annotation text. If a DEG sheet has fewer than three valid rows or lacks required annotation columns, clustering cannot proceed.

LLM Interpretation Fails
------------------------

Possible causes:

* Ollama is unavailable.
* Requested model is not present or too large for available resources.
* RAG literature index bootstrap fails.
* ``clusters.json`` does not exist because clustering was not run.

Use smaller local models for limited machines and verify that the configured literature index is available before starting interpretation.
