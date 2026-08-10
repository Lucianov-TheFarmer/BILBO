from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from ..pipeline_rag.run import run_rag
from .cluster_interpretation import run_cluster_interpretation
from .generate_rag_html import generate_report_bundle
from .prioritize_genes import run_prioritization


def _users_root() -> Path:
    configured = os.getenv("USERS_ROOT")
    if configured:
        return Path(configured).resolve()
    if Path("/users").is_dir():
        return Path("/users")
    return Path(__file__).resolve().parents[3] / "users"


def _ollama_api(path: str) -> str:
    return os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + path


def _read_csv_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    frame = pd.read_csv(path)
    return json.loads(frame.to_json(orient="records"))


def _write_report(
    output_path: Path,
    cluster_interpretations: list[dict[str, Any]],
    prioritized_genes: list[dict[str, Any]],
    rag_results: list[dict[str, Any]],
) -> None:
    lines = ["# BILBO — Cluster and literature interpretation", ""]
    lines.extend(
        [
            "## Cluster interpretations",
            "",
            (
                "Each cluster summary uses only the `function` and ontology-specific "
                "`go` fields, following the validated prototype."
            ),
            "",
        ]
    )
    if not cluster_interpretations:
        lines.append("No eligible semantic clusters were generated.")
    for item in cluster_interpretations:
        lines.extend(
            [
                f"### {item.get('ontology')} {item.get('direction')} cluster {item.get('cluster')}",
                "",
                str(item.get("interpretation", "")),
                "",
                f"Genes in cluster: {item.get('n_genes', 0)}",
                "",
            ]
        )

    selected = [
        gene
        for gene in prioritized_genes
        if str(gene.get("selected_for_search", "")).lower() == "true" or gene.get("selected_for_search") is True
    ]
    lines.extend(
        [
            "## Prioritized representative genes",
            "",
            ("Genes are selected when they represent clusters in at least two independent GO ontologies."),
            "",
        ]
    )
    if not selected:
        lines.append("No representative gene met the multi-ontology selection rule.")
    for gene in selected:
        lines.append(f"- {gene.get('gene_id')} — {gene.get('primary_name')} ({gene.get('represented_ontologies')})")
    lines.extend(["", "## Traceable literature interpretation", ""])

    if not rag_results:
        lines.append("No gene-specific RAG interpretation was produced.")
    for result in rag_results:
        lines.extend(
            [
                f"### {result.get('gene_id')} — {result.get('primary_name')}",
                "",
                str(result.get("interpretation", "")),
                "",
                "Retrieved evidence:",
                "",
            ]
        )
        for chunk in result.get("chunks", []):
            citation = chunk.get("citation_id", "")
            source = chunk.get("source", "")
            section = chunk.get("section", "")
            lines.append(f"- [{citation}] {source} — {section}")
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def run_llm(
    file_path: str | None = None,
    sheet_name: str | None = None,
    out_dir: str | None = None,
    user_id: int | str | None = None,
) -> dict[str, Any]:
    """Run the validated prototype stages after semantic clustering.

    ``file_path`` is retained for compatibility with the previous backend API and
    is intentionally ignored. The scientific inputs are the cluster CSVs and Wang
    matrices already produced for the selected user and contrast.
    """
    del file_path
    if user_id is None or not sheet_name:
        raise ValueError("user_id and sheet_name are required")

    users_root = _users_root()
    clustering_dir = users_root / str(user_id) / "clustering" / sheet_name
    if not clustering_dir.is_dir():
        raise FileNotFoundError(f"Clustering directory not found: {clustering_dir}")

    features_dir = clustering_dir / "features"
    clusters_dir = clustering_dir / "clusters"
    features_file = features_dir / "genes_filtered.csv"
    required = [features_file, clusters_dir]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Required clustering artifacts not found: {missing}")

    output_dir = Path(out_dir).resolve() if out_dir else users_root / str(user_id) / "llm" / sheet_name
    output_dir.mkdir(parents=True, exist_ok=True)

    cluster_interpretations_path = clusters_dir / "interpretations.csv"
    prioritized_path = clustering_dir / "outputs" / "prioritized_genes.csv"
    rag_output_path = output_dir / "rag_gene_evidence.json"
    combined_output_path = output_dir / "data.json"
    report_path = output_dir / "report.md"
    html_report_path = output_dir / "report.html"

    cluster_model = os.getenv("CLUSTER_INTERPRETATION_MODEL", "gemma4:e4b")
    rag_model = os.getenv("RAG_LLM_MODEL", "gemma4:e4b")
    embedding_model = os.getenv("RAG_EMBEDDING_MODEL", "bge-m3:latest")

    interpretation_info = run_cluster_interpretation(
        clusters_dir,
        cluster_interpretations_path,
        ollama_url=_ollama_api("/api/chat"),
        model=cluster_model,
        num_ctx=int(os.getenv("CLUSTER_INTERPRETATION_NUM_CTX", "32768")),
    )
    prioritized = run_prioritization(
        features_file,
        features_dir,
        clusters_dir,
        cluster_interpretations_path,
        prioritized_path,
    )

    if prioritized.empty or not prioritized["selected_for_search"].astype(bool).any():
        rag_results: list[dict[str, Any]] = []
        rag_output_path.write_text("[]\n", encoding="utf-8")
    else:
        rag_results = run_rag(
            input_file=prioritized_path,
            output_file=rag_output_path,
            interpretations_file=cluster_interpretations_path,
            qdrant_url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
            collection_name=os.getenv("QDRANT_COLLECTION", "banco_literatura_bio"),
            bm25_metadata_path=Path(os.getenv("BM25_METADATA_PATH", "/rag/bm25_metadata.json")),
            ollama_url=_ollama_api("/api/chat"),
            llm_model=rag_model,
            llm_num_ctx=int(os.getenv("RAG_LLM_NUM_CTX", "8192")),
            selected_only=True,
            n_results=int(os.getenv("RAG_N_RESULTS", "5")),
            candidate_results=int(os.getenv("RAG_CANDIDATE_RESULTS", "40")),
            max_chunks_per_source=int(os.getenv("RAG_MAX_CHUNKS_PER_SOURCE", "2")),
        )

    cluster_interpretations = _read_csv_records(cluster_interpretations_path)
    prioritized_records = json.loads(prioritized.to_json(orient="records")) if not prioritized.empty else []
    combined = {
        "method": "bilbo_prototype_cluster_interpretation_and_hybrid_rag",
        "sheet": sheet_name,
        "models": {
            "cluster_interpretation": cluster_model,
            "embedding": embedding_model,
            "rag_synthesis": rag_model,
        },
        "cluster_interpretations": cluster_interpretations,
        "prioritized_genes": prioritized_records,
        "rag_gene_evidence": rag_results,
    }
    generate_report_bundle(
        base_payload=combined,
        clustering_dir=clustering_dir,
        output_dir=output_dir,
        title=(
            "BILBO - Semantic clustering and "
            f"traceable RAG report - {sheet_name}"
        ),
    )

    return {
        "report": str(report_path),
        "html": str(html_report_path),
        "json": str(combined_output_path),
        "rag_json": str(rag_output_path),
        "cluster_interpretations": str(cluster_interpretations_path),
        "prioritized_genes": str(prioritized_path),
        "interpreted_clusters": interpretation_info["interpreted_clusters"],
        "selected_genes": int(prioritized["selected_for_search"].sum()) if not prioritized.empty else 0,
        "interpreted_genes": len(rag_results),
        "models": combined["models"],
    }
