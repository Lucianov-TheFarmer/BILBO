# RAG evaluation results

## Retrieval

The benchmark comprised **[N] prespecified gene queries** and **[M] unique pooled query–chunk judgments**. Relevance was assessed blind to retrieval method as irrelevant (0), indirect/contextual (1), or direct evidence (2). Values are query-level means with bootstrap 95% confidence intervals.

| Method | Precision@5 | nDCG@10 | MRR (direct evidence) | pooled Recall@10 |
|---|---:|---:|---:|---:|
| BM25 | [ ] | [ ] | [ ] | [ ] |
| BGE-M3 | [ ] | [ ] | [ ] | [ ] |
| BioBERT | [ ] | [ ] | [ ] | [ ] |
| PubMedBERT | [ ] | [ ] | [ ] | [ ] |
| BM25 + BGE-M3 | [ ] | [ ] | [ ] | [ ] |

## Expert evaluation of generated interpretations

Experts evaluated **[N] outputs containing [C] independently verifiable claims** against the retrieved and cited passages.

| Outcome | Percentage |
|---|---:|
| Supported | [ ] |
| Partially supported | [ ] |
| Unsupported | [ ] |
| Contradicted | [ ] |
| Correct citations | [ ] |

Strict claim accuracy (supported claims / all evaluated claims) was **[ ]**. Inter-annotator agreement was **Cohen's κ = [ ]**.

## Limitations

Recall is pooled rather than exhaustive. BioBERT and PubMedBERT are domain-pretrained encoder baselines evaluated with a fixed pooling strategy; they were not fine-tuned on the BILBO corpus or relevance judgments. The expert sample supports evaluation of the selected queries and should not be interpreted as universal performance across organisms, corpora, or experimental contexts.
