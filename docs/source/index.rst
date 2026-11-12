BILBO RNA-seq Workflow Documentation
====================================

**BILBO** (*Bioinformatics Integration for Large-scale Biological Operations*) is a containerized, graphical RNA-seq analysis platform that integrates data acquisition, quality control, trimming, reference preparation, STAR alignment, HTSeq-count quantification, edgeR differential expression analysis, clustering, visualization, and retrieval-augmented LLM interpretation.

This documentation is written for two complementary purposes. First, it provides practical guidance for users who run BILBO through the graphical interface. Second, it documents the methodological assumptions and parameter choices that influence quantification and differential expression results.

Scientific publication
----------------------

If you use BILBO in your research, please cite:

   da Silva, V. L. C., Alvarenga, J. V. R., Linhares-Neto, M. V., Noman, M., & Chalfun-Junior, A. (2026). BILBO: a self-hosted platform for large-scale RNA-Seq analysis with a functional annotation clustering framework. *Functional & Integrative Genomics*, **26**, 306. https://doi.org/10.1007/s10142-026-02091-9

`Read the article <https://doi.org/10.1007/s10142-026-02091-9>`_ · `Privacy policy <privacy.html>`_

.. warning::

   A graphical interface can reduce operational friction, but it does not remove the need for statistical and experimental judgment. Users should understand library layout, strandedness, annotation structure, biological replication, contrast design, duplicate handling, and quality-control diagnostics before interpreting differential expression results as biological evidence.

Current Implemented Pipeline
----------------------------

The current codebase implements the following major stages:

1. User authentication, sample management, status tracking, and asynchronous job execution.
2. FASTQ upload or SRA acquisition using SRA Toolkit ``fasterq-dump``.
3. Pre-trimming FastQC quality analysis.
4. Read trimming and filtering using Trimmomatic.
5. Reference genome download, annotation handling, and STAR genome indexing.
6. Paired-end STAR alignment followed by Picard sorting, read-group insertion, and duplicate removal.
7. Gene or feature quantification using ``htseq-count``.
8. edgeR preprocessing, normalization, dispersion estimation, contrast testing, and DEG table export.
9. Result visualizations, including barplots, Venn diagrams, and heatmaps.
10. Functional clustering of DEG-derived annotations.
11. Local retrieval-augmented interpretation using Ollama and curated literature retrieval.

Documentation Contents
----------------------

.. toctree::
   :maxdepth: 2
   :caption: User and Scientific Guide

   methodological_guidance
   architecture
   installation
   workflow
   parameters
   experimental_design
   quality_control
   differential_expression
   clustering_llm
   results
   troubleshooting
   interface_links
   privacy

.. toctree::
   :maxdepth: 1
   :caption: Reference

   glossary
   implementation_notes
