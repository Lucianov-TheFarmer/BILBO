Results and Artifacts
=====================

BILBO stores analysis outputs under each user's workspace and records important artifacts in the backend database.

Main Output Files
-----------------

.. list-table:: Result artifacts
   :header-rows: 1
   :widths: 26 34 40

   * - Artifact
     - Location
     - Interpretation
   * - FastQC reports
     - ``QC/`` and ``QC_PostTrim/``
     - Quality reports before and after trimming.
   * - Trimmed FASTQ files
     - ``trimmed/``
     - Reads after Trimmomatic filtering.
   * - Final BAM files
     - ``alignment/<sample>/<sample>.bam``
     - STAR-aligned, Picard-processed alignments after duplicate removal.
   * - HTSeq-count files
     - ``quantification/<sample>.txt``
     - Feature-level counts plus HTSeq metadata rows.
   * - ``Targets.txt``
     - ``preprocess/Targets.txt``
     - edgeR sample design table.
   * - Preprocessing plots
     - ``preprocess/``
     - edgeR QC and normalization plots.
   * - ``DEG.xlsx``
     - ``DEG/``
     - Significant genes/features only.
   * - ``DEG_full.xlsx``
     - ``DEG/``
     - All tested genes/features.
   * - Barplot images
     - ``DEG/BARPLOT.MULTIPLO - <title>.png``
     - Summary plots across selected contrasts.
   * - Volcano plots
     - ``DEG/VOLCANO.ISOLADO - <contrast>.png``
     - Contrast-specific visualization of log-fold change against adjusted significance.
   * - MA plots
     - ``DEG/MA.ISOLADO - <contrast>.png``
     - Contrast-specific visualization of expression abundance against log-fold change.
   * - Venn diagrams
     - ``DEG/VENN.DIAGRAM - <title>.png``
     - Overlap of significant genes across 2-4 contrasts.
   * - Heatmaps
     - ``DEG/HEATMAP - <title>.png``
     - Contrast-level logFC heatmap using ``DEG_full.xlsx``.
   * - Cluster maps and metrics
     - ``clustering/<contrast>/``
     - Functional annotation cluster outputs and quality metrics.
   * - LLM reports
     - ``llm/<contrast>/``
     - Markdown and JSON RAG interpretation outputs.

Barplots
--------

Barplots summarize selected DEG contrasts. They are useful for presentation and exploratory comparison, but users should inspect the underlying DEG tables for exact statistics.

Volcano and MA Plots
--------------------

Volcano plots display the relationship between effect size and adjusted statistical support, typically using ``logFC`` and ``-log10(FDR)``. MA plots display log-fold change as a function of expression abundance, helping users identify intensity-dependent effects and possible biases. Both plot types should be interpreted alongside the full DEG table and edgeR diagnostic plots.

Venn Diagrams
-------------

Venn diagrams require two to four contrasts. They use thresholded significant gene sets from ``DEG.xlsx``. Because they depend on DEG thresholds, they can hide near-threshold genes and should not be used as the sole evidence for shared biology.

Heatmaps
--------

Heatmaps use ``DEG_full.xlsx`` and selected contrasts. They are useful for comparing logFC patterns, including genes that may not pass the significant threshold in every contrast.

Download and Audit
------------------

Download routes record audit events. This supports traceability by linking artifact access to user, stage, file, and job metadata.
