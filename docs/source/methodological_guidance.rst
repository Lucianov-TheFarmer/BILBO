Methodological Guidance
========================

Purpose
-------

BILBO provides a graphical and containerized environment for RNA-seq analysis, but statistically valid interpretation still depends on informed parameter choices. This page summarizes the assumptions behind high-impact settings and directs users to the detailed sections of the documentation.

Scope
-----

The guidance provided here is intended to help users understand:

* which settings are currently configurable through the interface;
* which settings are fixed in the current implementation;
* when common defaults are appropriate;
* when a default may be inappropriate for a specific RNA-seq experiment;
* how parameter choices can affect quantification, differential expression, clustering, and biological interpretation.

Key Methodological Considerations
---------------------------------

.. list-table:: High-impact settings in BILBO
   :header-rows: 1
   :widths: 22 22 18 38

   * - Pipeline area
     - Current behavior
     - Configurability
     - Scientific implication
   * - Trimming
     - Trimmomatic with default GUI values: adapter ``TruSeq3-PE.fa``, seed mismatches ``2``, palindrome threshold ``30``, simple threshold ``10``, minimum adapter length ``8``, sliding window ``4:15``, ``LEADING:3``, ``TRAILING:3``, ``MINLEN:36``.
     - Configurable in the trimming dialog.
     - Defaults are typical for many Illumina RNA-seq libraries but may be inappropriate for non-TruSeq adapters, short reads, degraded RNA, or libraries containing known technical sequences.
   * - STAR indexing
     - User supplies ``sjdbOverhang`` and threads; STAR index generation uses the downloaded reference FASTA and annotation where available.
     - Partly configurable.
     - ``sjdbOverhang`` should normally equal read length minus one. Inappropriate values can reduce splice-junction sensitivity.
   * - STAR alignment
     - Paired-end alignment using STAR, ``--outSAMstrandField intronMotif``, ``--outSAMtype BAM Unsorted``; optional STAR filters can be passed from the interface.
     - Partly configurable.
     - Multimapping, mismatch, intron, and junction filters affect alignment yield and downstream counts.
   * - Duplicate handling
     - Picard ``MarkDuplicates`` is run with ``REMOVE_DUPLICATES=true``.
     - Fixed in the current implementation.
     - Removing duplicates may be inappropriate for some bulk RNA-seq datasets because high coverage can reflect true expression rather than technical duplication.
   * - Quantification
     - ``htseq-count -a 10 -t <feature_type> -i <id_attribute> -f bam --stranded=no``.
     - Feature type and ID attribute are configurable; strandedness and minimum alignment quality are fixed.
     - ``--stranded=no`` is valid for unstranded libraries but inappropriate for forward- or reverse-stranded protocols.
   * - Feature/ID fallback
     - If the requested ID attribute is absent for the chosen feature, BILBO attempts a fallback among ``ID``, ``gene_id``, ``locus_tag``, ``Name``, ``Parent``, and ``transcript_id``.
     - Automatic behavior.
     - Useful for heterogeneous annotations, but users must inspect logs to ensure biological identifiers match the intended unit of inference.
   * - edgeR filtering
     - Genes/features are retained when row mean counts are at least ``10``; if all features would be removed, BILBO falls back to unfiltered counts.
     - Fixed in the current implementation.
     - This simple filter is transparent but less adaptive than design-aware CPM filtering.
   * - edgeR testing
     - TMM normalization, GLM dispersion estimation, ``glmFit``, ``glmLRT``; significant DEG tables use ``FDR <= 0.05`` and ``abs(logFC) >= 1``.
     - Thresholds fixed in current implementation.
     - Appropriate as a conservative pairwise default, but users must ensure adequate biological replication and valid contrasts.
   * - Contrasts
     - Contrasts are defined as group A versus group B from selected sample repetitions.
     - Configurable through the GUI.
     - Current design is most suitable for pairwise group comparisons. Multifactor, paired, blocked, time-course, or batch-adjusted analyses require caution and may need external modeling.

Recommended User Practice
-------------------------

Before accepting downstream biological conclusions, users should verify:

* library layout and strandedness;
* adapter and trimming choices;
* reference genome and annotation compatibility;
* STAR alignment metrics;
* HTSeq feature type and ID attribute;
* replicate assignment and contrast direction;
* edgeR diagnostic plots;
* whether duplicate removal is appropriate for the library type;
* whether clustering and LLM outputs are supported by the underlying annotation and literature evidence.
