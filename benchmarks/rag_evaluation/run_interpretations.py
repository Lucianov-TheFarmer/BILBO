from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from app.backend.pipeline_rag.run import run_rag

from .annotations import write_interpretation_template


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the current BILBO hybrid RAG and prepare expert claim annotations."
    )
    parser.add_argument("--genes", type=Path, required=True)
    parser.add_argument("--cluster-interpretations", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--bm25-metadata", type=Path, default=Path(os.getenv("BM25_METADATA_PATH", "/rag/bm25_metadata.json")))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://qdrant:6333"))
    parser.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "banco_literatura_bio"))
    parser.add_argument("--ollama-url", default=os.getenv("OLLAMA_HOST", "http://ollama:11434").rstrip("/") + "/api/chat")
    parser.add_argument("--model", default=os.getenv("RAG_LLM_MODEL", "gemma4:e4b"))
    parser.add_argument("--num-ctx", type=int, default=int(os.getenv("RAG_LLM_NUM_CTX", "8192")))
    parser.add_argument("--num-predict", type=int, default=int(os.getenv("RAG_LLM_NUM_PREDICT", "1536")))
    parser.add_argument("--gene-limit", type=int, default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--candidate-k", type=int, default=40)
    parser.add_argument("--max-chunks-per-source", type=int, default=2)
    parser.add_argument("--llm-attempts", type=int, default=3)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.chmod(0o777)
    rag_json = args.output_dir / "rag_gene_evidence.json"
    results = run_rag(
        input_file=args.genes,
        output_file=rag_json,
        interpretations_file=args.cluster_interpretations,
        qdrant_url=args.qdrant_url,
        collection_name=args.collection,
        bm25_metadata_path=args.bm25_metadata,
        ollama_url=args.ollama_url,
        llm_model=args.model,
        llm_num_ctx=args.num_ctx,
        llm_num_predict=args.num_predict,
        selected_only=True,
        gene_limit=args.gene_limit,
        n_results=args.top_k,
        candidate_results=args.candidate_k,
        max_chunks_per_source=args.max_chunks_per_source,
        resume=True,
        llm_attempts=args.llm_attempts,
    )
    annotations_csv = args.output_dir / "interpretation_annotations.csv"
    claim_count = write_interpretation_template(rag_json, annotations_csv)
    manifest = {
        "genes_interpreted": len(results),
        "claims_for_expert_review": claim_count,
        "model": args.model,
        "num_ctx": args.num_ctx,
        "num_predict": args.num_predict,
        "top_k": args.top_k,
        "candidate_k": args.candidate_k,
        "max_chunks_per_source": args.max_chunks_per_source,
        "genes": str(args.genes),
        "cluster_interpretations": str(args.cluster_interpretations),
    }
    manifest_path = args.output_dir / "interpretation_run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for path in (rag_json, annotations_csv, manifest_path):
        path.chmod(0o666)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
