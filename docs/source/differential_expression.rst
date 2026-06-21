Differential Expression Analysis
================================

Implemented Statistical Workflow
--------------------------------

BILBO uses edgeR for differential expression. The implemented scripts perform the following operations:

1. Read count files using ``readDGE`` and ``Targets.txt``.
2. Remove HTSeq-count metadata rows beginning with ``__``.
3. Filter low-expression features using row mean count ``>= 10``.
4. Create a ``DGEList`` with group assignments.
5. Build a no-intercept design matrix: ``model.matrix(~0+group, ...)``.
6. Apply TMM normalization with ``calcNormFactors``.
7. Estimate common, trended, and tagwise dispersion.
8. Fit a GLM using ``glmFit``.
9. Test selected contrasts using ``glmLRT``.
10. Export significant genes/features to ``DEG.xlsx``.
11. Export all tested genes/features to ``DEG_full.xlsx``.

Significance Criteria
---------------------

The significant DEG workbook uses:

* ``FDR <= 0.05``
* ``abs(logFC) >= 1``

This is a common conservative rule for identifying genes with both statistical support and minimum effect size. However, it is not universal. Some studies may justify a different log-fold-change threshold, independent filtering strategy, or statistical model.

Count Filtering
---------------

The current filter retains features with mean count at least ``10`` across samples. This is transparent and simple, but it is not design-aware. In edgeR, many workflows use CPM-based filtering that considers library size and group structure. Users should be cautious when sample library sizes are highly unequal, groups are unbalanced, or expression is expected in only a subset of conditions.

Normalization
-------------

BILBO uses TMM normalization through ``calcNormFactors``. TMM is appropriate for many bulk RNA-seq datasets because it adjusts for compositional differences between libraries. It assumes that most genes are not differentially expressed and that extreme expression shifts should not dominate scaling.

Dispersion Estimation
---------------------

edgeR models count data using negative binomial distributions. Dispersion estimates capture biological variability beyond Poisson sampling noise. Reliable dispersion estimation depends on biological replication. Without replication, differential expression p-values should not be considered reliable.

Contrast Direction
------------------

BILBO constructs contrast vectors with ``+1`` for the first group and ``-1`` for the second group. Therefore, a positive ``logFC`` indicates higher expression in the first group relative to the second group as represented in the selected contrast.

DEG Outputs
-----------

``DEG.xlsx``
  Contains only genes/features passing the implemented FDR and logFC thresholds for each selected contrast.

``DEG_full.xlsx``
  Contains all tested genes/features for each contrast. This file is used for heatmap generation and should be preferred when users need ranked statistics, not only thresholded hits.

Limitations
-----------

The current BILBO DEG implementation is best suited to simple pairwise comparisons. It does not currently expose:

* batch covariates;
* subject blocking;
* paired designs;
* interaction terms;
* continuous covariates;
* time-course models;
* user-adjustable filtering and DEG thresholds.

For such designs, users should export count tables and conduct a custom statistical analysis.
