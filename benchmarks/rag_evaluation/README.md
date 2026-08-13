# BILBO RAG expert evaluation

This benchmark addresses three separate questions:

1. Does hybrid BM25 + BGE-M3 retrieval outperform either component alone?
2. How does BGE-M3 compare with BioBERT and PubMedBERT representations on the same corpus and queries?
3. What proportion of LLM-generated biological claims is supported by the cited evidence under expert review?

It is an offline scientific benchmark. It is not executed during a user's RNA-seq analysis.

The frozen results and the complete response to reviewer comment 3 are available
in [`results/benchmark/`](results/benchmark/README.md).

## Fixed protocol

- Select 20–30 representative genes before inspecting benchmark results.
- Keep corpus, chunking, query construction, candidate depth, final depth, and source-diversification settings fixed.
- Compare `bm25`, `bge_m3`, `hybrid_bm25_bge_m3`, `biobert`, and `pubmedbert`.
- BioBERT and PubMedBERT use attention-mask mean pooling, L2 normalization, 512-token truncation, and cosine similarity. They are domain-pretrained language-model baselines, not retrieval-fine-tuned models.
- Pool the top 10 documents from every method, deduplicate by query and chunk, shuffle deterministically, and hide method/rank from annotators.
- Grade each query–chunk pair as `0` irrelevant, `1` indirect/contextual, or `2` direct gene/function/process evidence.
- Report Precision@5, nDCG@10, MRR for the first direct result, and pooled Recall@10 with query-level bootstrap 95% confidence intervals.
- Select the evaluated LLM outputs before expert inspection. Label each claim `supported`, `partially_supported`, `unsupported`, or `contradicted`.
- Strict claim accuracy counts only `supported` claims as correct.

The benchmark uses the production query construction, entity/name/context reranking, and per-source diversification. The retrieval model is the experimental variable.

## Environment

Qdrant and Ollama must contain the same collection and models used by BILBO:

```bash
make ai-up
```

Install the optional benchmark dependencies in an isolated environment:

```bash
python -m venv .venv-rag-eval
. .venv-rag-eval/bin/activate
pip install -r requirements/rag-benchmark.txt
```

BioBERT and PubMedBERT checkpoints are downloaded on first use. Record the resolved model revisions in the final supplementary material if the local model cache does not already pin them.

Alternatively, use the isolated Compose image. It extends the BILBO runtime
with Torch and Transformers without adding those dependencies to the production
services:

```bash
docker compose --profile rag-evaluation build rag-benchmark
docker compose --profile rag-evaluation run --rm rag-benchmark \
  --genes /prototype/outputs/prioritized_genes.csv \
  --output-dir /workspace/benchmarks/rag_evaluation/work \
  --query-limit 30 --top-k 10
```

The Hugging Face model cache is persisted in the
`rag_benchmark_models` volume. The prototype path in this example contains 13
multi-ontology representative genes; additional independent datasets are
needed if a larger prespecified query sample is desired.

### Safe sequential preparation before expert review

On machines with limited RAM, do not run biomedical embedding and Gemma
interpretation containers concurrently. The following orchestrator resumes the
incremental embedding cache, loads only one biomedical encoder at a time, frees
it, and starts LLM interpretation only after retrieval has finished:

```bash
docker compose --profile rag-evaluation run --rm \
  --entrypoint conda rag-benchmark \
  run --no-capture-output -n bioinfo python -m benchmarks.rag_evaluation.prepare_expert_review
```

The Compose service is limited to 5 GiB and four CPUs; Qdrant is limited to 2
GiB. Ollama loads at most one model and processes one request at a time. The
process creates `READY_FOR_EXPERT_REVIEW.json` only after all six automatic
artifacts exist. Until that marker appears, do not begin human annotation.

## 1. Freeze the query set

Use a versioned copy of `prioritized_genes.csv`. The `gene_id` column must be unique and `selected_for_search` must be true for evaluated rows. Do not change this file after looking at method results.

## 2. Generate the blinded retrieval pool

When Python runs on the host, use the exposed Qdrant and Ollama ports:

```bash
OLLAMA_HOST=http://127.0.0.1:11435 \
OLLAMA_EMBEDDING_URL=http://127.0.0.1:11435/api/embed \
python -m benchmarks.rag_evaluation.run_retrieval \
  --genes benchmarks/rag_evaluation/data/queries.csv \
  --output-dir benchmarks/rag_evaluation/work \
  --bm25-metadata rag_data/bm25_metadata.json \
  --qdrant-url http://127.0.0.1:6333 \
  --query-limit 30 \
  --top-k 10
```

Outputs:

- `rankings.csv`: method-specific ranks; keep this away from annotators.
- `relevance_annotations.csv`: blinded document pool sent to experts.
- `run_manifest.json`: models and fixed protocol parameters.
- `embedding_cache/`: local BioBERT/PubMedBERT corpus vectors.

For a smoke test without downloading biomedical models, add `--skip-biomedical-models`. Do not use that option for the paper's final comparison.
The optional `--corpus-limit` argument exists only to validate checkpoint loading
and code paths. Its manifest sets `reportable_run=false`; never report metrics
from a truncated-corpus run.

## 3. Expert retrieval annotation

Give only `relevance_annotations.csv` to the expert. Fill:

- `relevance_grade`: `0`, `1`, or `2`;
- `annotator_id`: pseudonymous stable identifier;
- `notes`: optional justification.

For two experts, give each one an independent copy. Measure agreement separately and resolve disagreements into one consensus file before calculating the primary retrieval metrics. This prevents duplicated judgments from being treated as separate documents.

## 4. Calculate retrieval metrics

```bash
python -m benchmarks.rag_evaluation.evaluate retrieval \
  --rankings benchmarks/rag_evaluation/work/rankings.csv \
  --annotations benchmarks/rag_evaluation/work/relevance_annotations_consensus.csv \
  --output benchmarks/rag_evaluation/work/retrieval_metrics.json \
  --k 10
```

Because relevance judgments come from pooled system outputs rather than exhaustive corpus assessment, report the recall result as **pooled Recall@10**.

## 5. Generate the interpretation sheet

Generate fresh outputs with the current BILBO hybrid implementation and create
the expert sheet from the same command:

```bash
docker compose --profile rag-evaluation run --rm \
  --entrypoint conda rag-benchmark \
  run --no-capture-output -n bioinfo python -m benchmarks.rag_evaluation.run_interpretations \
  --genes /prototype/outputs/prioritized_genes.csv \
  --cluster-interpretations /prototype/clusters/interpretations.csv \
  --output-dir /workspace/benchmarks/rag_evaluation/work/current_interpretations
```

If a frozen `rag_gene_evidence.json` already exists, only create its annotation
sheet with:

```bash
python -m benchmarks.rag_evaluation.annotations \
  --rag-json ai_data/output/runs/experiment-01/llm/CONTRAST/rag_gene_evidence.json \
  --output benchmarks/rag_evaluation/work/interpretation_annotations.csv
```

Each row contains one automatically segmented claim and all retrieved evidence. Experts fill:

- `annotator_id`;
- `claim_label`: `supported`, `partially_supported`, `unsupported`, or `contradicted`;
- `citations_correct`: `1` or `0`;
- `expert_correction` and `notes`, when useful.

Reviewers should correct claim segmentation before annotation if a sentence contains multiple independently verifiable biological claims.

Current RAG runs emit atomic `claims` directly. Each claim includes its citations,
evidence level, relationship to the query gene, supported species, and model
confidence. The deterministic validator rejects uncited claims, unknown citation
IDs, blocked entity collisions, unverified direct/same-gene attribution, and
unsupported strong language. If no claim survives, the gene is marked
`insufficient_evidence` and is not exported as an expert-review claim.

Entity policies for high-risk aliases are stored in
`app/backend/pipeline_rag/resources/gene_entity_policies.json`. These policies
are guardrails, not proof of orthology. In particular, a textual name match is
kept as `unknown` until a stable entity/orthology mapping is available.

Stable IDs and validated orthologs belong in
`app/backend/pipeline_rag/resources/gene_entity_resolution.json`. Entries with
`status=unresolved` must remain empty until species and sequence/identifier
evidence are available. Retrieval decomposes each gene into identity, molecular
function, biological process, localization, stress/expression, and phenotype
facets when those facets occur in the input query. Generated claims may include
up to three independent evidence focuses. Species-treatment combinations are
accepted only when they co-occur in the same cited sentence.

## 6. Calculate interpretation metrics

```bash
python -m benchmarks.rag_evaluation.evaluate interpretations \
  --annotations benchmarks/rag_evaluation/work/interpretation_annotations.csv \
  --rag-json benchmarks/rag_evaluation/work/current_interpretations/rag_gene_evidence.json \
  --output benchmarks/rag_evaluation/work/interpretation_metrics.json
```

The output reports strict claim accuracy, the four label distributions, citation accuracy, and pairwise Cohen's kappa when multiple annotators use the same file.
When `--rag-json` is supplied, it also reports answer coverage, abstention rate,
accepted claims, and deterministically rejected claims. Coverage must be
reported with accuracy so that abstention cannot create an artificial apparent
improvement.

## Reporting boundary

The scripts make the evaluation reproducible but do not replace expert curation. Do not report numerical performance until every selected item has been annotated and the frozen outputs, consensus judgments, model revisions, and manifest have been archived.
