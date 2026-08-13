# Benchmark results addressing reviewer comment 3

## Reviewer comment

> The hybrid retrieval (BM25 + dense embeddings) is not assessed with
> precision/recall or other information-retrieval metrics. No comparison with
> domain-specific embedding models (BioBERT, PubMedBERT) is provided, and the
> accuracy of the LLM-generated interpretations against expert curation is not
> reported.

## Complete response

We thank the reviewer for identifying the absence of quantitative retrieval
and expert-curation analyses. We added a pooled information-retrieval benchmark
using a frozen set of 13 gene queries, a corpus of 53,037 literature chunks,
and 479 unique query--passage pairs judged by one expert. Relevance was graded
as irrelevant (0), indirect/contextual (1), or direct (2). BM25, BGE-M3,
BM25+BGE-M3 hybrid retrieval, BioBERT, and PubMedBERT were evaluated under the
same queries, corpus, candidate depth, final depth, and post-processing
protocol. We report Precision@5, nDCG@10, reciprocal rank of the first direct
result, and pooled Recall@10, with query-level bootstrap 95% confidence
intervals in the machine-readable metrics file.

| Retrieval method | Precision@5 | nDCG@10 | Direct MRR | Pooled Recall@10 |
| --- | ---: | ---: | ---: | ---: |
| BM25 + BGE-M3 hybrid | **0.862** | 0.785 | **0.511** | 0.469 |
| BM25 | 0.815 | **0.796** | 0.510 | **0.488** |
| BGE-M3 | 0.708 | 0.576 | 0.221 | 0.370 |
| PubMedBERT | 0.369 | 0.266 | 0.169 | 0.167 |
| BioBERT | 0.262 | 0.164 | 0.077 | 0.088 |

The hybrid method obtained the highest Precision@5 and marginally the highest
direct-evidence MRR. BM25 obtained the highest nDCG@10 and pooled Recall@10.
Accordingly, the benchmark supports the narrower conclusion that hybrid fusion
improves early precision in this setting; it does not support a claim of
universal superiority across retrieval metrics.

BGE-M3 outperformed the evaluated BioBERT and PubMedBERT representations.
BioBERT and PubMedBERT were used as domain-pretrained, but not
retrieval-fine-tuned, baselines with attention-mask mean pooling, L2
normalization, 512-token truncation, and cosine similarity. Therefore, this
result applies to these checkpoints and this protocol and should not be
interpreted as evidence that BGE-M3 is generally superior to all biomedical
retrievers. Because relevance was assessed over a pooled set rather than over
all 53,037 chunks, the recall result is explicitly reported as pooled
Recall@10.

We also added claim-level expert curation of the final LLM-generated
interpretations. The evidence-controlled pipeline generated 11 atomic claims
for 6 of the 13 genes and abstained for the remaining 7 genes. The expert
assessed each generated claim and its cited evidence.

| Expert judgment | Claims | Proportion |
| --- | ---: | ---: |
| Supported | 8 | **72.7%** |
| Partially supported | 1 | 9.1% |
| Unsupported | 2 | 18.2% |
| Contradicted | 0 | 0.0% |

Strict claim accuracy, which counts only fully supported claims as correct, was
72.7%. The proportion supported or partially supported was 81.8%, and citation
correctness was 81.8%. Answer coverage was 46.2% (6/13 genes), while the
abstention rate was 53.8% (7/13 genes). Accuracy is reported together with
coverage to avoid inflating apparent performance through abstention.

These results answer all three elements of the comment: the hybrid retriever is
quantitatively assessed with standard information-retrieval metrics;
domain-specific BioBERT and PubMedBERT baselines are included; and the
LLM-generated claims are evaluated against expert curation. We characterize
the analysis as a pilot benchmark because it contains 13 queries, 11 accepted
claims, and one expert annotator. Inter-annotator agreement cannot yet be
estimated, and project-specific `Sh*` identifiers still lack validated stable
identifier and orthology mappings. These limitations constrain
generalizability but do not invalidate the reported benchmark results.

## Reproducibility artifacts

- `retrieval/rankings.csv`: method-specific ranked chunk IDs.
- `retrieval/relevance_judgments_expert_01.csv`: compact expert relevance
  judgments without article text.
- `retrieval/metrics.json`: aggregate metrics, per-query results, and bootstrap
  confidence intervals.
- `retrieval/run_manifest.json`: frozen retrieval protocol and model names.
- `interpretations/claims_expert_01.csv`: generated claims and expert labels.
- `interpretations/metrics.json`: claim accuracy, citation accuracy, coverage,
  and abstention.
- `interpretations/run_manifest.json`: frozen interpretation configuration.
- `report.md`: extended analysis, limitations, and manuscript-safe claims.

Embedding caches, source article excerpts, logs, intermediate runs, unrestricted
baselines, and smoke-test outputs remain excluded from version control.
