Documentation Links in the Interface
====================================

Extensive documentation should be directly linked within the interface, especially for first-time users. This page defines where links should be placed in the GUI.

Recommended Link Placement
--------------------------

.. list-table:: Interface linking plan
   :header-rows: 1
   :widths: 26 36 38

   * - Interface area
     - Link target
     - Reason
   * - Trimming dialog
     - :doc:`parameters`
     - Explains adapter files, quality thresholds, read-length filters, and downstream impact.
   * - Genome indexing dialog
     - :doc:`parameters`
     - Explains ``sjdbOverhang`` and resource requirements.
   * - Alignment dialog
     - :doc:`parameters`
     - Explains STAR filters and duplicate removal.
   * - Quantification dialog
     - :doc:`parameters`
     - Explains HTSeq feature type, ID attribute, fallback behavior, and strandedness.
   * - Contrast dialog
     - :doc:`experimental_design`
     - Explains biological replication, pairwise contrasts, and unsupported designs.
   * - Preprocess/DEG stage
     - :doc:`differential_expression`
     - Explains edgeR filtering, normalization, dispersion, and significance thresholds.
   * - Results view
     - :doc:`results`
     - Explains workbooks, plots, Venn diagrams, and heatmaps.
   * - Clustering and LLM dialogs
     - :doc:`clustering_llm`
     - Explains exploratory clustering and limitations of LLM interpretation.
   * - Job/status views
     - :doc:`troubleshooting`
     - Helps diagnose failed or unexpected stages.
   * - About/help menu
     - :doc:`methodological_guidance`
     - Provides a concise summary of methodological assumptions and limitations.

Warning Text to Surface in the GUI
----------------------------------

Short warning messages should be displayed near high-impact parameters:

* **Duplicate removal**: "Current pipeline removes Picard-marked duplicates. This may be inappropriate for some bulk RNA-seq datasets."
* **Strandedness**: "Current quantification uses unstranded counting. Confirm that your library is unstranded before interpreting results."
* **Contrasts**: "This contrast interface is intended for pairwise group comparisons. Batch, paired, and multifactor designs require additional modeling."
* **LLM interpretation**: "LLM reports are hypothesis-generating and require expert validation."

First-time User Flow
--------------------

For first-time users, the interface should encourage the following path:

1. Read the workflow overview.
2. Inspect QC before choosing trimming parameters.
3. Confirm library strandedness before quantification.
4. Confirm biological replication and valid contrasts before DEG.
5. Inspect edgeR diagnostics before interpreting DEG tables.
6. Treat clustering and LLM reports as exploratory summaries.
