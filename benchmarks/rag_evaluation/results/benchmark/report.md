# Final evaluation report for reviewer comment 3

## Reviewer comment

> The hybrid retrieval (BM25 + dense embeddings) is not assessed with precision/recall or other information-retrieval metrics. No comparison with domain-specific embedding models (BioBERT, PubMedBERT) is provided, and the accuracy of the LLM-generated interpretations against expert curation is not reported.

## Evaluation status

The requested analyses were implemented and executed on a frozen evaluation set of 13 gene queries and a corpus of 53,037 literature chunks. Retrieval and interpretation artifacts were preserved together with their run manifests. The current results are sufficient for a transparent pilot response to the reviewer, but should not be presented as definitive evidence of general performance.

## 1. Information-retrieval evaluation

An expert assessed 479 unique pooled query–chunk pairs using a three-level relevance scale:

- `2`: direct evidence;
- `1`: indirect or contextual evidence;
- `0`: irrelevant.

The pool contained 37 direct, 187 indirect and 255 irrelevant judgments. Five retrieval methods were evaluated under the same protocol.

| Method | Precision@5 | nDCG@10 | MRR direct | Pooled Recall@10 |
|---|---:|---:|---:|---:|
| Hybrid BM25 + BGE-M3 | **0.862** | 0.785 | **0.511** | 0.469 |
| BM25 | 0.815 | **0.796** | 0.510 | **0.488** |
| BGE-M3 | 0.708 | 0.576 | 0.221 | 0.370 |
| PubMedBERT | 0.369 | 0.266 | 0.169 | 0.167 |
| BioBERT | 0.262 | 0.164 | 0.077 | 0.088 |

The hybrid method achieved the highest early precision and marginally the highest direct-evidence MRR. BM25 achieved the highest nDCG@10 and pooled Recall@10. Therefore, the results do not support a claim that hybrid retrieval is universally superior; they support a narrower conclusion that fusion improved top-rank precision with a small loss of overall ranking quality and pooled coverage.

BioBERT and PubMedBERT were evaluated as mean-pooled, L2-normalized encoders without retrieval-specific contrastive fine-tuning. BGE-M3 is retrieval-oriented, making its stronger result plausible. The comparison is specific to these checkpoints, this plant-science corpus and this protocol.

Because relevance was assessed over the pooled outputs rather than exhaustively over all 53,037 chunks, Recall@10 must be described as **pooled Recall@10**.

## 2. Expert evaluation of LLM interpretations

The final pipeline used:

- atomic claims;
- mandatory claim-level citations;
- deterministic entity and citation validation;
- explicit separation of gene, ortholog, family and general evidence;
- species/experimental-condition checks;
- abstention when evidence was insufficient;
- up to three claims per gene;
- faceted retrieval for identity, function, process, localization, stress/expression and phenotype.

Expert 1 annotated every generated claim in the final frozen run.

| Interpretation outcome | Count | Proportion |
|---|---:|---:|
| Supported | 8 | **72.7%** |
| Partially supported | 1 | 9.1% |
| Unsupported | 2 | 18.2% |
| Contradicted | 0 | **0.0%** |

Additional results:

- strict claim accuracy: **72.7%**;
- supported or partially supported: **81.8%**;
- citation correctness: **81.8%**;
- answered genes: **6/13 (46.2%)**;
- abstained genes: **7/13 (53.8%)**;
- accepted claims: **11**;
- deterministically rejected candidate claims: **22**.

This result is acceptable as a pilot expert-curation result: most claims were at least partially supported, no claim was contradicted, and citation correctness exceeded 80%. It is not strong enough to claim general high accuracy because only 11 claims from six answered genes were evaluated and abstention was substantial.

## 3. Interpretation of the result

The final system deliberately prioritizes precision over coverage. The original unrestricted generator produced many more claims, but expert review identified unsupported specificity, cross-species transfer, alias collisions and uncited statements. The final pipeline suppresses such claims and abstains when the available literature cannot support a cautious statement.

Accuracy must therefore be reported together with coverage and abstention. Reporting 72.7% alone would overstate overall system capability because seven of the 13 genes received no accepted interpretation.

The principal remaining bottleneck is entity resolution. The project-specific `Sh*` identifiers currently lack query-species metadata, sequences and stable UniProt/TAIR/NCBI identifiers. Consequently, the pipeline correctly refuses to treat literature about similarly named Arabidopsis or other plant genes as direct evidence or validated orthology.

## 4. Threats to validity

1. Only 13 gene queries were evaluated.
2. Only 11 final claims were produced.
3. Results currently represent one expert annotator; inter-annotator agreement cannot yet be calculated.
4. Pooled relevance judgments do not exhaustively assess the full corpus.
5. The evaluated genes use project-specific IDs without validated stable-identifier or orthology mappings.
6. Claims from the same gene are not statistically independent.

For a stronger final manuscript, a second independent expert should annotate the same frozen retrieval pool and final claim sheet. Cohen's kappa and a consensus file should then be reported. The current single-expert analysis can still be reported if explicitly identified as a limitation.

## 5. Suggested response to the reviewer

> We thank the reviewer for identifying the absence of quantitative retrieval and expert-curation analyses. We added a pooled information-retrieval evaluation over 13 gene queries and 479 expert-judged query–passage pairs. We compared BM25, BGE-M3, BioBERT, PubMedBERT, and BM25+BGE-M3 hybrid retrieval using Precision@5, nDCG@10, direct-evidence MRR, and pooled Recall@10. The hybrid method achieved the highest Precision@5 (0.862) and direct-evidence MRR (0.511), whereas BM25 achieved the highest nDCG@10 (0.796) and pooled Recall@10 (0.488). BGE-M3 outperformed the evaluated BioBERT and PubMedBERT encoders under the same retrieval protocol. We therefore describe the hybrid approach as improving early precision rather than as uniformly superior. We also added claim-level expert curation of the final LLM outputs. Of 11 generated atomic claims, 72.7% were fully supported, 9.1% partially supported, 18.2% unsupported, and none contradicted; citation correctness was 81.8%. The evidence-controlled system answered 6 of 13 genes and abstained for 7 genes, which we now report alongside accuracy. We have revised the manuscript to characterize this as a pilot evaluation and to acknowledge the limited query and claim sample sizes and the current absence of validated orthology mappings for the project-specific gene identifiers.

## 6. Recommended manuscript claims

Appropriate:

- the hybrid method improved Precision@5 relative to the evaluated individual retrievers;
- BM25 remained strongest for nDCG@10 and pooled Recall@10;
- BGE-M3 outperformed the evaluated untuned BioBERT and PubMedBERT encoders;
- 72.7% of final atomic claims were fully supported under expert review;
- 81.8% of citations were judged correct;
- the system abstained for 53.8% of evaluated genes;
- the study constitutes a pilot expert evaluation.

Not supported:

- hybrid retrieval is universally superior;
- BGE-M3 is generally superior to biomedical encoders;
- the LLM has 72.7% accuracy for all genes or plant-science questions;
- abstained genes were interpreted correctly;
- similarly named genes from other species are validated orthologs of the `Sh*` genes.

## 7. Published final artifacts

Retrieval:

- `retrieval/rankings.csv`;
- `retrieval/relevance_judgments_expert_01.csv`;
- `retrieval/metrics.json`;
- `retrieval/run_manifest.json`.

Interpretation:

- `interpretations/claims_expert_01.csv`;
- `interpretations/metrics.json`;
- `interpretations/run_manifest.json`.

The published judgment tables intentionally omit retrieved article text. Local
embedding caches, source excerpts, logs, unrestricted baselines, intermediate
runs, and smoke-test outputs are excluded from version control. The compact
tables retain stable IDs, generated claims, expert labels, ranks, metrics, and
protocol manifests needed to audit the reported pilot results.
