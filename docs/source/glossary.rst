Glossary
========

Biological replicate
  An independently collected biological sample representing the variability of the biological condition.

Technical replicate
  A repeated measurement of the same biological material. It measures technical variability but does not replace biological replication.

Stranded RNA-seq
  A library preparation in which read orientation preserves transcript strand information. Counting must use the correct strandedness setting.

Unstranded RNA-seq
  A library preparation in which read orientation does not preserve transcript strand information. BILBO's current ``--stranded=no`` setting assumes this case.

Duplicate read
  A read or read pair with coordinates suggesting it may arise from PCR duplication. In RNA-seq, duplicate interpretation is complex because high expression can create coordinate redundancy.

Feature type
  The annotation feature counted by HTSeq, such as ``gene``, ``exon``, or ``CDS``.

ID attribute
  The annotation attribute used to group reads into count rows, such as ``gene_id``, ``ID``, ``Parent``, or ``locus_tag``.

TMM normalization
  The trimmed mean of M-values normalization method used by edgeR to adjust for compositional differences between libraries.

FDR
  False discovery rate, a multiple-testing-adjusted measure of expected false discoveries among significant calls.

RAG
  Retrieval-augmented generation. BILBO retrieves context from a local vector database before asking an LLM to interpret clusters.
