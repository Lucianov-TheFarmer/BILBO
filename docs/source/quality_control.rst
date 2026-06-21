Quality Control
===============

Quality control is not a decorative stage; it determines whether downstream results are trustworthy.

Pre-trimming FastQC
-------------------

Inspect pre-trimming FastQC reports for:

* Per-base sequence quality.
* Per-sequence quality scores.
* Adapter content.
* Overrepresented sequences.
* Per-base sequence content.
* Per-sequence GC content.
* Sequence length distribution.
* Duplicate sequence level.

Adapter content and low-quality 3' tails usually justify trimming. Strong GC shifts, severe overrepresented sequences, and unexpected sequence composition may indicate library contamination or protocol-specific biases.

Post-trimming FastQC
--------------------

Post-trimming FastQC should answer two questions:

1. Did trimming remove the intended artifacts?
2. Did trimming preserve enough high-quality sequence for reliable alignment?

Good post-trim reports usually show lower adapter content and improved end-of-read quality without excessive shortening. If many reads fall below ``MINLEN`` or become very short, alignment sensitivity and unique mapping can decline.

Alignment QC
------------

BILBO retains STAR final logs where available. Users should inspect:

* Uniquely mapped read percentage.
* Multimapping percentage.
* Reads unmapped due to too many mismatches.
* Reads unmapped because they are too short.
* Splice-junction metrics.
* Consistency across samples and groups.

Low alignment rate may result from wrong reference genome, contamination, incorrect strandedness assumptions downstream, overly aggressive trimming, poor annotation, mixed species, or sequencing quality problems.

Quantification QC
-----------------

HTSeq-count produces special rows beginning with ``__`` such as unassigned or ambiguous categories. BILBO removes these metadata rows before edgeR analysis, but users should still inspect them because they diagnose counting problems.

High ``__no_feature`` may indicate an annotation mismatch, wrong feature type, wrong strand setting, or reads mapping mainly outside annotated regions. High ``__ambiguous`` may indicate overlapping features or inappropriate ID selection.

edgeR Diagnostic Plots
----------------------

BILBO generates preprocessing plots including:

* Library-size barplot.
* Biological coefficient of variation plot.
* MDS plot.
* Sample clustering dendrogram.
* Raw, filtered, normalized, and fitted density plots.
* Log-transformed count histograms.
* Sample correlation heatmap.

These plots should be inspected before DEG interpretation. Samples that cluster by batch, lane, or unexpected outlier behavior should be investigated.

QC Decision Rules
-----------------

The following are practical warning signs:

* One group has systematically lower library size than another.
* Post-trim read length differs strongly by group.
* Alignment rates differ strongly by condition.
* One replicate is an extreme MDS or clustering outlier.
* HTSeq unassigned rows dominate the count file.
* The chosen feature/ID combination produces unexpectedly few counted genes.

When these occur, do not proceed mechanically. Recheck sample metadata, reference selection, annotation file, strandedness, and trimming choices.
