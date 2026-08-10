End-to-End Workflow
===================

This page describes the operational workflow as implemented in the current BILBO codebase.

1. Project Setup and User Session
---------------------------------

Users authenticate in the graphical interface. All subsequent files, stage records, and artifacts are associated with the authenticated user.

2. Sample Acquisition
---------------------

BILBO supports two acquisition routes:

* **SRA download** using ``fasterq-dump --split-files --skip-technical``.
* **FASTQ upload** through the interface.

SRA downloads are stored in ``users/<user_id>/samples/<sra_accession>/``. Uploaded FASTQ files are assigned a basename inferred from common FASTQ suffixes such as ``_1``, ``_2``, ``_R1``, and ``_R2``.

3. Initial Quality Control
--------------------------

Pre-trimming quality control is performed with FastQC. Users should inspect sequence quality, adapter content, per-base composition, sequence duplication, overrepresented sequences, and GC distribution before trimming and alignment.

4. Trimming
-----------

Trimming is performed with Trimmomatic. BILBO detects paired-end samples by checking for matching ``_1.fastq`` and ``_2.fastq`` files. Paired-end outputs include paired trimmed reads and unpaired reads; the downstream alignment stage currently expects the paired trimmed files.

5. Post-trimming Quality Control
--------------------------------

FastQC is rerun on trimmed reads. Users should confirm that adapter contamination and low-quality tails were reduced without excessive read loss.

6. Reference Genome Search, Download, and STAR Indexing
-------------------------------------------------------

The interface supports genome search/download and STAR index generation. STAR indexing uses user-provided ``sjdbOverhang`` and thread count. If a GFF/GTF annotation is available, it is passed to STAR for splice-junction-aware indexing.

7. Alignment
------------

The current alignment stage expects paired-end trimmed reads:

* ``<sample>_1_trimmed.fastq``
* ``<sample>_2_trimmed.fastq``

STAR produces an unsorted BAM. Picard then sorts by query name, adds read groups, and removes duplicates using ``MarkDuplicates REMOVE_DUPLICATES=true``. The final BAM is stored as ``users/<user_id>/alignment/<sample>/<sample>.bam``.

8. Quantification
-----------------

Quantification is performed with ``htseq-count`` against the selected reference annotation. The user provides:

* ``Feature Type (-t)``, such as ``gene``, ``exon``, or ``CDS``.
* ``ID Attribute (-i)``, such as ``ID``, ``gene_id``, ``Parent``, or ``locus_tag``.

The current command uses fixed ``--stranded=no`` and ``-a 10``.

9. Contrast Definition and Preprocessing
----------------------------------------

Users define pairwise contrasts by selecting biological groups and their repetitions. BILBO writes ``Targets.txt`` with ``files``, ``group``, and ``description`` columns for edgeR.

10. Differential Expression Analysis
------------------------------------

edgeR reads HTSeq-count outputs, removes metadata rows beginning with ``__``, filters low-count features by row mean count, applies TMM normalization, estimates dispersions, fits a GLM, and performs likelihood-ratio testing for selected contrasts.

11. Results and Visualization
-----------------------------

BILBO exports:

* ``DEG.xlsx``: significant genes/features only.
* ``DEG_full.xlsx``: all tested genes/features.
* Preprocessing QC plots.
* Barplots, Venn diagrams, and heatmaps.

12. Clustering and LLM Interpretation
-------------------------------------

For each selected DEG sheet, one job executes the complete validated prototype flow: GO-Wang clustering, one restricted function/GO summary per cluster, semantic-medoid selection, multi-ontology representative prioritization, hybrid Qdrant retrieval, and cited gene-level RAG synthesis.

Stage Dependencies
------------------

.. list-table:: Stage dependency summary
   :header-rows: 1
   :widths: 24 38 38

   * - Stage
     - Requires
     - Produces
   * - Download/upload
     - SRA accession or FASTQ files
     - FASTQ files and stage-1 sample records
   * - FastQC
     - FASTQ files
     - HTML/ZIP quality reports
   * - Trimming
     - Raw FASTQ files
     - Trimmed FASTQ files
   * - STAR indexing
     - Reference FASTA, optional annotation, ``sjdbOverhang``
     - STAR index directory
   * - Alignment
     - Paired trimmed FASTQ files and STAR index
     - Final BAM file
   * - Quantification
     - BAM file and annotation
     - HTSeq-count table
   * - Preprocess/DEG
     - Count tables and valid contrasts
     - edgeR objects, plots, DEG workbooks
   * - Complete clustering/interpretation pipeline
     - DEG workbook with annotation columns
     - Cluster CSVs/images, cluster interpretations, prioritized genes, retrieved chunks, Markdown report, and structured JSON
