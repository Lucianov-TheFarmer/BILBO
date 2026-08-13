# Expert annotation guidelines

## Retrieval relevance

Judge only whether the displayed chunk answers the displayed gene/function query. Do not infer relevance from an article title alone and do not use outside knowledge to repair an unsupported chunk.

- **2 — direct evidence:** the passage explicitly discusses the queried gene or a credible alias, or directly establishes the queried molecular function, process, phenotype, or localization for that gene/protein.
- **1 — indirect/contextual evidence:** the passage is biologically related, for example at protein-family, pathway, process, or homolog level, but does not directly establish the query-specific relationship.
- **0 — irrelevant:** the passage does not materially help answer the query, contains only an ambiguous lexical collision, or is too generic to support even contextual interpretation.

When the gene symbol is ambiguous, require biological context consistent with the query. Record difficult cases in `notes`; do not inspect retrieval method or rank.

## Generated-claim assessment

Evaluate each claim against the displayed retrieved chunks, especially the chunks cited by the claim.

- **supported:** all material parts of the claim follow from the cited evidence without adding biological specificity.
- **partially_supported:** a core relationship is supported, but the claim adds an unsupported qualifier, mechanism, organism transfer, certainty, or scope.
- **unsupported:** the cited material does not establish the claim, although it does not explicitly refute it.
- **contradicted:** the cited material or accepted expert-curated reference directly conflicts with the claim.

Set `citations_correct=1` only when every cited chunk genuinely supports the associated claim and the claim does not depend on an uncited retrieved chunk. Use `expert_correction` to state the minimally corrected interpretation.

If automatic sentence segmentation combines two independently verifiable propositions, split the row before annotation and assign new unique claim IDs. If two experts annotate, they must receive identical frozen rows and work independently.
