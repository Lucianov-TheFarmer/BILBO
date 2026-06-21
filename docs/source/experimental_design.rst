Experimental Design Guidance
============================

RNA-seq validity depends more on experimental design than on any graphical interface. BILBO can execute a standardized workflow, but users remain responsible for defining valid biological comparisons.

Minimum Design Principles
-------------------------

Biological Replication
~~~~~~~~~~~~~~~~~~~~~~

Differential expression analysis requires biological replicates. Technical replicates do not substitute for biological replication unless they are modeled or combined appropriately. As a practical default:

* Use at least three biological replicates per group when possible.
* Prefer balanced designs with similar numbers of samples per condition.
* Avoid interpreting DEG results from designs with no replication as statistically reliable.

Randomization and Batch
~~~~~~~~~~~~~~~~~~~~~~~

RNA extraction, library preparation, sequencing lane, sequencing date, genotype, tissue collection date, and operator can introduce batch effects. If batches are confounded with biological groups, no downstream software can fully separate technical from biological effects.

The current BILBO DEG workflow is most appropriate for simple pairwise group comparisons. It does not currently expose a full GUI design matrix for batch adjustment. If a study contains batch, paired structure, time-course structure, or multiple factors, users should either:

* design contrasts so that batch is balanced across groups; or
* export count tables and analyze them externally with a design formula appropriate to the study.

Library Strandedness
~~~~~~~~~~~~~~~~~~~~

Library strandedness must be known before quantification. The current fixed setting ``--stranded=no`` assumes an unstranded protocol. For stranded libraries, users should treat BILBO's current quantification as a documented limitation unless the code is modified or the interface is extended.

Common RNA-seq Designs
----------------------

Two-group Comparison
~~~~~~~~~~~~~~~~~~~~

Example: control versus treatment.

This is the best-supported design in the current BILBO interface. Users define one group on the left side of the contrast and one group on the right side. BILBO fits an edgeR GLM with group-specific coefficients and tests the selected contrast.

Recommended conditions:

* At least three biological replicates per group.
* Similar library preparation and sequencing depth across groups.
* Same strandedness and read layout across all samples.
* No group-batch confounding.

Multiple Pairwise Comparisons
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Example: control versus treatment A, control versus treatment B, treatment A versus treatment B.

BILBO can store and run multiple pairwise contrasts. Users should remember that each contrast is a separate statistical question. The exported FDR values are computed per contrast, not necessarily as a global correction over all possible study questions.

Factorial Designs
~~~~~~~~~~~~~~~~~

Example: genotype, treatment, and genotype-by-treatment interaction.

The current GUI contrast model does not expose interaction terms. A simple pairwise contrast may answer a limited question, but it does not test interaction. For factorial hypotheses, export count tables and fit an explicit model externally, for example with edgeR, DESeq2, or limma-voom.

Paired or Repeated-measures Designs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Example: before/after samples from the same subject or matched tissue pairs.

The current BILBO design does not expose subject blocking. Treating paired samples as independent can inflate false positives or reduce power. Use external modeling when pairing is central to the hypothesis.

Time-course Designs
~~~~~~~~~~~~~~~~~~~

Example: 0 h, 6 h, 24 h, and 48 h after treatment.

BILBO can compare pairs of time points, but it does not model trends, splines, or time-by-treatment interactions. Interpret pairwise results as snapshots, not as a full time-course model.

Single-cell or Pseudobulk Data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

BILBO is designed for bulk RNA-seq. Pseudobulk count matrices may be analyzed only if they are prepared as valid sample-level count tables and the design is compatible with the edgeR model. Cell-level single-cell workflows are outside the implemented scope.

Contrast Definition in BILBO
----------------------------

The contrast interface stores names in a structured form equivalent to:

.. code-block:: text

   GroupA(Sample1;Sample2;Sample3)*GroupB(Sample4;Sample5;Sample6)

The preprocessing route writes ``Targets.txt`` with one row per count file:

.. code-block:: text

   files	group	description
   ../quantification/Sample1.txt	GroupA	GroupA
   ../quantification/Sample2.txt	GroupA	GroupA
   ../quantification/Sample4.txt	GroupB	GroupB

BILBO checks that the same sample is not assigned to incompatible groups within or across selected contrasts.

Practical Checklist Before DEG
------------------------------

Before starting DEG analysis, confirm:

* All samples are from the intended organism/reference.
* All samples use compatible library layout and strandedness.
* FastQC reports do not show unresolved severe quality problems.
* Alignment rates are acceptable and similar across groups.
* Quantification logs show the intended feature and ID attributes.
* Biological replicates cluster primarily by biological condition or interpretable covariates.
* Contrasts reflect the study hypothesis.
* Batch effects are absent, balanced, or handled outside the current BILBO GUI.
