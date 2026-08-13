from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from app.backend.pipeline_rag.common import (
    DENSE_VECTOR_NAME,
    ENTITY_PAYLOAD_FIELDS,
    SPARSE_VECTOR_NAME,
    bm25_sparse_vector,
    embed_texts,
)
from app.backend.pipeline_rag.retrieval import (
    load_collection,
    load_prioritized_genes,
    rerank_chunks_by_name_and_context,
    retrieval_queries_for_gene,
    select_retrieved_chunks,
)

from .annotations import stable_id


DEFAULT_BIOMEDICAL_MODELS = {
    "biobert": "dmis-lab/biobert-base-cased-v1.2",
    "pubmedbert": "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext",
}


@dataclass
class Corpus:
    chunks: list[dict[str, Any]]
    positions: dict[str, int]


def point_to_chunk(point: Any) -> dict[str, Any]:
    payload = point.payload or {}
    text = str(payload.get("text", ""))
    chunk_id = str(payload.get("chunk_id") or stable_id(payload.get("fonte", ""), payload.get("section", ""), text))
    return {
        "chunk_id": chunk_id,
        "source": payload.get("fonte", ""),
        "article_title": payload.get("article_title", ""),
        "section": payload.get("section", ""),
        "text": text,
        **{field: payload.get(field, []) for field in ENTITY_PAYLOAD_FIELDS},
    }


def load_corpus(store: dict[str, Any], batch_size: int = 256) -> Corpus:
    chunks = []
    offset = None
    while True:
        points, offset = store["client"].scroll(
            collection_name=store["collection_name"],
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        chunks.extend(point_to_chunk(point) for point in points)
        if offset is None:
            break
    chunks.sort(key=lambda chunk: chunk["chunk_id"])
    return Corpus(chunks=chunks, positions={chunk["chunk_id"]: index for index, chunk in enumerate(chunks)})


def finalize_candidates(
    chunks: list[dict[str, Any]], queries: dict[str, Any], *, top_k: int, max_chunks_per_source: int
) -> list[dict[str, Any]]:
    ranked = []
    for rank, chunk in enumerate(chunks, start=1):
        ranked.append({**chunk, "hit_rank": rank})
    return select_retrieved_chunks(
        rerank_chunks_by_name_and_context(ranked, queries),
        n_results=top_k,
        max_chunks_per_source=max_chunks_per_source,
    )


def qdrant_candidates(
    store: dict[str, Any], queries: dict[str, Any], *, mode: str, candidate_k: int
) -> list[dict[str, Any]]:
    from qdrant_client import models

    dense_query = embed_texts([queries["embedding"] or queries["bm25"]])[0]
    sparse_indices, sparse_values = bm25_sparse_vector(queries["bm25"], store["bm25_model"])
    sparse = models.SparseVector(indices=sparse_indices, values=sparse_values)
    common = {
        "collection_name": store["collection_name"],
        "limit": candidate_k,
        "with_payload": True,
    }
    if mode == "bm25":
        if not sparse_indices:
            return []
        response = store["client"].query_points(query=sparse, using=SPARSE_VECTOR_NAME, **common)
    elif mode == "bge_m3":
        response = store["client"].query_points(query=dense_query, using=DENSE_VECTOR_NAME, **common)
    elif mode == "hybrid_bm25_bge_m3":
        if sparse_indices:
            response = store["client"].query_points(
                prefetch=[
                    models.Prefetch(query=sparse, using=SPARSE_VECTOR_NAME, limit=candidate_k),
                    models.Prefetch(query=dense_query, using=DENSE_VECTOR_NAME, limit=candidate_k),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                **common,
            )
        else:
            response = store["client"].query_points(query=dense_query, using=DENSE_VECTOR_NAME, **common)
    else:
        raise ValueError(f"Unsupported Qdrant mode: {mode}")
    return [point_to_chunk(point) for point in response.points]


def hf_embedder(model_name: str, *, batch_size: int = 8, max_length: int = 512) -> Callable[[list[str]], np.ndarray]:
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("BioBERT/PubMedBERT evaluation requires requirements/rag-benchmark.txt") from exc

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device).eval()

    def encode(texts: list[str]) -> np.ndarray:
        batches = []
        for start in range(0, len(texts), batch_size):
            encoded = tokenizer(
                texts[start : start + batch_size],
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            with torch.no_grad():
                hidden = model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            batches.append(pooled.cpu().numpy().astype("float32"))
        return np.concatenate(batches, axis=0)

    return encode


def cached_corpus_embeddings(
    corpus: Corpus, model_key: str, model_name: str, cache_dir: Path, *, batch_size: int
) -> tuple[np.ndarray, Callable[[list[str]], np.ndarray]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    embeddings_path = cache_dir / f"{model_key}_embeddings.npy"
    ids_path = cache_dir / f"{model_key}_chunk_ids.json"
    progress_path = cache_dir / f"{model_key}_progress.json"
    embed = hf_embedder(model_name, batch_size=batch_size)
    ids = [chunk["chunk_id"] for chunk in corpus.chunks]
    progress = {}
    if ids_path.exists() and progress_path.exists() and embeddings_path.exists():
        cached_ids = json.loads(ids_path.read_text(encoding="utf-8"))
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if cached_ids != ids or progress.get("model_name") != model_name:
            progress = {}

    if progress:
        embeddings = np.lib.format.open_memmap(embeddings_path, mode="r+")
        completed = int(progress.get("completed", 0))
        if completed == len(corpus.chunks):
            return embeddings, embed
    else:
        first = embed([corpus.chunks[0]["text"]])
        embeddings = np.lib.format.open_memmap(
            embeddings_path,
            mode="w+",
            dtype="float32",
            shape=(len(corpus.chunks), first.shape[1]),
        )
        embeddings[0] = first[0]
        completed = 1
        ids_path.write_text(json.dumps(ids), encoding="utf-8")

    checkpoint_size = max(batch_size * 16, batch_size)
    for start in range(completed, len(corpus.chunks), checkpoint_size):
        end = min(start + checkpoint_size, len(corpus.chunks))
        embeddings[start:end] = embed([chunk["text"] for chunk in corpus.chunks[start:end]])
        embeddings.flush()
        temporary = progress_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"model_name": model_name, "completed": end, "total": len(corpus.chunks)}),
            encoding="utf-8",
        )
        temporary.replace(progress_path)
        print(f"{model_key}: embedded {end}/{len(corpus.chunks)} chunks", flush=True)
    return embeddings, embed


def dense_candidates(
    corpus: Corpus,
    corpus_embeddings: np.ndarray,
    query: str,
    embed: Callable[[list[str]], np.ndarray],
    *,
    candidate_k: int,
) -> list[dict[str, Any]]:
    scores = corpus_embeddings @ embed([query])[0]
    count = min(candidate_k, len(scores))
    indices = np.argpartition(-scores, count - 1)[:count] if count < len(scores) else np.arange(len(scores))
    indices = indices[np.argsort(-scores[indices], kind="stable")]
    return [corpus.chunks[int(index)] for index in indices]


def write_outputs(
    output_dir: Path,
    rankings: list[dict[str, Any]],
    pool: dict[str, dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    ranking_fields = ["method", "query_id", "pool_id", "rank", "chunk_id"]
    with (output_dir / "rankings.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=ranking_fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in ranking_fields} for row in rankings)

    annotation_rows = list(pool.values())
    random.Random(metadata["seed"]).shuffle(annotation_rows)
    fields = [
        "pool_id", "query_id", "gene_id", "primary_name", "lexical_query", "semantic_query",
        "source", "article_title", "section", "chunk_text", "relevance_grade", "annotator_id", "notes",
    ]
    with (output_dir / "relevance_annotations.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in fields} for row in annotation_rows)
    manifest_path = output_dir / "run_manifest.json"
    manifest_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for path in (output_dir / "rankings.csv", output_dir / "relevance_annotations.csv", manifest_path):
        path.chmod(0o666)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate blinded expert pools for the BILBO retrieval benchmark.")
    parser.add_argument("--genes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bm25-metadata", type=Path, default=Path(os.getenv("BM25_METADATA_PATH", "/rag/bm25_metadata.json")))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://qdrant:6333"))
    parser.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "banco_literatura_bio"))
    parser.add_argument("--query-limit", type=int, default=30)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--candidate-k", type=int, default=40)
    parser.add_argument("--max-chunks-per-source", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--skip-biomedical-models", action="store_true")
    parser.add_argument(
        "--corpus-limit",
        type=int,
        default=None,
        help="Smoke-test only: truncate the corpus after loading. Never use for reported results.",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.chmod(0o777)

    store = load_collection(args.qdrant_url, args.collection, args.bm25_metadata)
    genes = load_prioritized_genes(args.genes, selected_only=True, limit=args.query_limit)
    if genes.empty:
        raise ValueError("No selected genes found")
    if genes["gene_id"].astype(str).duplicated().any():
        raise ValueError("gene_id must be unique in the benchmark query set")

    corpus = load_corpus(store)
    if not corpus.chunks:
        raise ValueError("The configured Qdrant collection is empty")
    full_corpus_size = len(corpus.chunks)
    if args.corpus_limit is not None:
        if args.corpus_limit < 1:
            raise ValueError("corpus-limit must be >= 1")
        limited_chunks = corpus.chunks[: args.corpus_limit]
        corpus = Corpus(
            chunks=limited_chunks,
            positions={chunk["chunk_id"]: index for index, chunk in enumerate(limited_chunks)},
        )
    rankings = []
    pool: dict[str, dict[str, Any]] = {}
    query_specs = [
        (gene, str(gene["gene_id"]), retrieval_queries_for_gene(gene, []))
        for _, gene in genes.iterrows()
    ]

    def record(method: str, gene: Any, query_id: str, queries: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
        final = finalize_candidates(
            candidates, queries, top_k=args.top_k, max_chunks_per_source=args.max_chunks_per_source
        )
        for rank, chunk in enumerate(final, start=1):
            pool_id = stable_id(query_id, chunk["chunk_id"])
            rankings.append(
                {"method": method, "query_id": query_id, "pool_id": pool_id, "rank": rank, "chunk_id": chunk["chunk_id"]}
            )
            pool.setdefault(
                pool_id,
                {
                    "pool_id": pool_id,
                    "query_id": query_id,
                    "gene_id": query_id,
                    "primary_name": gene.get("primary_name", ""),
                    "lexical_query": queries["bm25"],
                    "semantic_query": queries["embedding"],
                    "source": chunk.get("source", ""),
                    "article_title": chunk.get("article_title", ""),
                    "section": chunk.get("section", ""),
                    "chunk_text": chunk.get("text", ""),
                    "relevance_grade": "",
                    "annotator_id": "",
                    "notes": "",
                },
            )

    for gene, query_id, queries in query_specs:
        for mode in ("bm25", "bge_m3", "hybrid_bm25_bge_m3"):
            record(
                mode,
                gene,
                query_id,
                queries,
                qdrant_candidates(store, queries, mode=mode, candidate_k=args.candidate_k),
            )

    if not args.skip_biomedical_models:
        for key, model_name in DEFAULT_BIOMEDICAL_MODELS.items():
            embeddings, embed = cached_corpus_embeddings(
                corpus, key, model_name, args.output_dir / "embedding_cache", batch_size=args.batch_size
            )
            for gene, query_id, queries in query_specs:
                semantic_query = queries["embedding"] or queries["bm25"]
                record(
                    key,
                    gene,
                    query_id,
                    queries,
                    dense_candidates(
                        corpus, embeddings, semantic_query, embed, candidate_k=args.candidate_k
                    ),
                )
            del embeddings, embed
            gc.collect()

    write_outputs(
        args.output_dir,
        rankings,
        pool,
        {
            "seed": args.seed,
            "queries": len(genes),
            "corpus_chunks": len(corpus.chunks),
            "full_corpus_chunks": full_corpus_size,
            "smoke_test_corpus_limit": args.corpus_limit,
            "reportable_run": args.corpus_limit is None and not args.skip_biomedical_models,
            "top_k": args.top_k,
            "candidate_k": args.candidate_k,
            "methods": sorted({row["method"] for row in rankings}),
            "biomedical_models": {} if args.skip_biomedical_models else DEFAULT_BIOMEDICAL_MODELS,
            "biomedical_pooling": "attention-mask mean pooling followed by L2 normalization",
            "biomedical_max_tokens": 512,
            "production_postprocessing": "payload/name/context reranking and per-source diversification applied equally",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
