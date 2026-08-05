from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

from .common import (
    DENSE_VECTOR_NAME,
    EMBEDDING_MODEL,
    ENTITY_PAYLOAD_FIELDS,
    SPARSE_VECTOR_NAME,
)
from .retrieval import (
    BM25_METADATA,
    CANDIDATE_RESULTS,
    CLUSTER_INTERPRETATIONS_FILE,
    COLLECTION,
    GENE_LIMIT,
    INPUT_FILE,
    MAX_CHUNKS_PER_SOURCE,
    N_RESULTS,
    QDRANT_ENDPOINT,
    SELECTED_ONLY,
    add_citation_ids,
    aliases_for_gene,
    citation_id_for_index,
    cluster_interpretations_for_gene,
    evidence_signals,
    load_cluster_interpretations,
    load_collection,
    load_prioritized_genes,
    rerank_chunks_by_name_and_context,
    retrieval_queries_for_gene,
    search_chunks,
    select_retrieved_chunks,
)

__all__ = [
    "analyze_genes",
    "build_interpretation_prompt",
    "cluster_interpretations_for_gene",
    "evidence_signals",
    "load_cluster_interpretations",
    "load_prioritized_genes",
    "parse_interpretation_response",
    "rerank_chunks_by_name_and_context",
    "retrieval_queries_for_gene",
    "run_rag",
    "search_chunks",
    "select_retrieved_chunks",
    "strip_markdown",
]


OUTPUT_JSON = Path("outputs/rag_gene_evidence.json")
OLLAMA_CHAT_URL = os.environ.get(
    "OLLAMA_CHAT_URL",
    os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
)
LLM_MODEL = os.environ.get("RAG_LLM_MODEL", "gemma4:e4b")
LLM_NUM_CTX = int(os.environ.get("RAG_LLM_NUM_CTX", "8192"))


def build_interpretation_prompt(
    gene: pd.Series,
    chunks: list[dict[str, Any]],
    cluster_interpretations: list[dict[str, str]],
) -> str:
    evidence = [
        {
            "chunk_ref": chunk.get("citation_id") or citation_id_for_index(index),
            "chunk_id": chunk.get("chunk_id", ""),
            "source": chunk["source"],
            "article_title": chunk["article_title"],
            "section": chunk["section"],
            "retrieved_rank": chunk.get("retrieved_rank"),
            "final_rank": chunk.get("hit_rank"),
            "payload_match": chunk.get("payload_match", {}),
            "mentions": {field: chunk.get(field, []) for field in ENTITY_PAYLOAD_FIELDS if chunk.get(field)},
            "text": chunk["text"],
        }
        for index, chunk in enumerate(chunks, start=1)
    ]
    return (
        "You are a plant molecular biology specialist. "
        "Create a traceable literature interpretation for the gene below. "
        "Use only the retrieved chunks, the gene metadata, and the represented "
        "cluster interpretations provided in this prompt. Do not use outside "
        "biological knowledge to add unsupported details.\n\n"
        f"Gene ID: {gene.get('gene_id')}\n"
        f"Name: {gene.get('primary_name')}\n"
        "Known aliases from the current input table: "
        f"{json.dumps(aliases_for_gene(gene), ensure_ascii=False)}\n"
        f"Expression direction: {gene.get('direction', '')}\n"
        "Represented cluster interpretations:\n"
        f"{json.dumps(cluster_interpretations, ensure_ascii=False)}\n\n"
        "Retrieved chunks:\n"
        f"{json.dumps(evidence, ensure_ascii=False)}\n\n"
        "Return valid JSON only, with exactly these top-level keys: "
        "chunk_interpretations, cross_chunk_synthesis, interpretation.\n"
        "The JSON schema is:\n"
        "{"
        '"chunk_interpretations": ['
        "{"
        '"chunk_ref": "C1", '
        '"source": "source filename", '
        '"section": "section title", '
        '"matched_basis": ["payload or text match used"], '
        '"supported_observation": "one cautious sentence supported only by this chunk", '
        '"relevance_to_gene": "explain whether this chunk mentions the gene/alias, only a protein family/process, only context, or is not useful", '
        '"limitation": "what this chunk does not establish", '
        '"used_in_synthesis": true'
        "}"
        "], "
        '"cross_chunk_synthesis": "short synthesis using only chunk observations and chunk citations like [C1]", '
        '"interpretation": "final 2 to 4 sentence interpretation with chunk citations like [C1, C2]"'
        "}\n"
        "Include exactly one chunk_interpretations item for every retrieved chunk, "
        "even when the chunk is only generic context or not useful. In "
        "supported_observation, summarize only what the chunk itself states. "
        "In relevance_to_gene, distinguish direct gene or alias evidence from "
        "family-level, process-level, or contextual evidence using plain prose. "
        "Every biological claim in cross_chunk_synthesis and interpretation that "
        "comes from retrieved literature must cite one or more chunk_refs in "
        "square brackets. Do not cite a chunk unless its chunk_interpretation "
        "supports the claim. Gene name, aliases, and cluster interpretations may "
        "be used to frame the interpretation, but if a conclusion depends mainly "
        "on them rather than on retrieved chunks, say so explicitly. If the chunk "
        "list is empty or generic, state that the retrieved literature is "
        "insufficient for a gene-specific claim."
    )


def strip_markdown(text: str) -> str:
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            loaded = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return loaded if isinstance(loaded, dict) else None


def normalize_interpretation_result(result: Any) -> dict[str, Any]:
    if isinstance(result, str):
        return {
            "chunk_interpretations": [],
            "cross_chunk_synthesis": "",
            "interpretation": strip_markdown(result),
        }
    if not isinstance(result, dict):
        return {"chunk_interpretations": [], "cross_chunk_synthesis": "", "interpretation": ""}

    chunk_interpretations = result.get("chunk_interpretations", [])
    if not isinstance(chunk_interpretations, list):
        chunk_interpretations = []
    cross_chunk_synthesis = strip_markdown(str(result.get("cross_chunk_synthesis", "") or ""))
    interpretation = strip_markdown(
        str(result.get("interpretation") or result.get("final_interpretation") or cross_chunk_synthesis or "")
    )
    return {
        "chunk_interpretations": [item for item in chunk_interpretations if isinstance(item, dict)],
        "cross_chunk_synthesis": cross_chunk_synthesis,
        "interpretation": interpretation,
    }


def parse_interpretation_response(text: str) -> dict[str, Any]:
    parsed = extract_json_object(text)
    return normalize_interpretation_result(text if parsed is None else parsed)


def insufficient_interpretation() -> dict[str, Any]:
    message = "The retrieved literature is insufficient to support a gene-specific interpretation."
    return {
        "chunk_interpretations": [],
        "cross_chunk_synthesis": message,
        "interpretation": message,
    }


def interpret_gene(
    gene: pd.Series,
    chunks: list[dict[str, Any]],
    cluster_interpretations: list[dict[str, str]],
    *,
    ollama_url: str = OLLAMA_CHAT_URL,
    model: str = LLM_MODEL,
    num_ctx: int = LLM_NUM_CTX,
) -> dict[str, Any]:
    if not chunks:
        return insufficient_interpretation()

    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "user",
                "content": build_interpretation_prompt(
                    gene,
                    chunks,
                    cluster_interpretations,
                ),
            }
        ],
        "options": {"temperature": 0.0, "num_ctx": num_ctx},
    }
    request = urllib.request.Request(
        ollama_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        result = json.load(response)
    return parse_interpretation_response(result["message"]["content"])


def analyze_genes(
    genes: pd.DataFrame,
    collection: dict[str, Any],
    cluster_interpretations: dict[str, str] | None = None,
    n_results: int = N_RESULTS,
    candidate_results: int = CANDIDATE_RESULTS,
    max_chunks_per_source: int = MAX_CHUNKS_PER_SOURCE,
    interpreter=interpret_gene,
    llm_model: str = LLM_MODEL,
) -> list[dict[str, Any]]:
    cluster_interpretations = cluster_interpretations or {}
    results = []
    for _, gene in genes.iterrows():
        print(f"{gene['rank']}: {gene['gene_id']}")
        gene_cluster_interpretations = cluster_interpretations_for_gene(
            gene,
            cluster_interpretations,
        )
        queries = retrieval_queries_for_gene(gene, gene_cluster_interpretations)
        chunks = search_chunks(
            collection,
            queries,
            n_results=n_results,
            candidate_results=candidate_results,
            max_chunks_per_source=max_chunks_per_source,
        )
        chunks = add_citation_ids(chunks)
        interpretation_result = normalize_interpretation_result(interpreter(gene, chunks, gene_cluster_interpretations))
        results.append(
            {
                "rank": int(gene["rank"]),
                "gene_id": gene["gene_id"],
                "primary_name": gene["primary_name"],
                "queries": {
                    "bm25": queries["bm25"],
                    "embedding": queries["embedding"],
                    "aliases": list(queries["aliases"]),
                    "context_phrases": list(queries["context_phrases"]),
                },
                "embedding_model": EMBEDDING_MODEL,
                "llm_model": llm_model,
                "retrieval": {
                    "backend": "qdrant_bm25_name_dense_ontology_payload_rerank_rrf",
                    "dense_vector": DENSE_VECTOR_NAME,
                    "sparse_vector": SPARSE_VECTOR_NAME,
                    "n_results": n_results,
                    "candidate_results": candidate_results,
                    "max_chunks_per_source": max_chunks_per_source,
                },
                "cluster_interpretations": gene_cluster_interpretations,
                "evidence": evidence_signals(gene, queries, chunks),
                "chunks": chunks,
                "chunk_interpretations": interpretation_result["chunk_interpretations"],
                "cross_chunk_synthesis": interpretation_result["cross_chunk_synthesis"],
                "interpretation": interpretation_result["interpretation"],
            }
        )
    return results


def write_json(results: list[dict[str, Any]], output_file: Path = OUTPUT_JSON) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_rag(
    *,
    input_file: Path,
    output_file: Path,
    interpretations_file: Path,
    qdrant_url: str,
    collection_name: str,
    bm25_metadata_path: Path,
    ollama_url: str = OLLAMA_CHAT_URL,
    llm_model: str = LLM_MODEL,
    llm_num_ctx: int = LLM_NUM_CTX,
    selected_only: bool = True,
    gene_limit: int | None = None,
    n_results: int = N_RESULTS,
    candidate_results: int = CANDIDATE_RESULTS,
    max_chunks_per_source: int = MAX_CHUNKS_PER_SOURCE,
) -> list[dict[str, Any]]:
    genes = load_prioritized_genes(
        input_file=input_file,
        selected_only=selected_only,
        limit=gene_limit,
    )
    if genes.empty:
        write_json([], output_file)
        return []

    store = load_collection(qdrant_url, collection_name, bm25_metadata_path)
    interpretations = load_cluster_interpretations(interpretations_file)

    def configured_interpreter(gene, chunks, cluster_interpretations):
        return interpret_gene(
            gene,
            chunks,
            cluster_interpretations,
            ollama_url=ollama_url,
            model=llm_model,
            num_ctx=llm_num_ctx,
        )

    results = analyze_genes(
        genes,
        store,
        cluster_interpretations=interpretations,
        n_results=n_results,
        candidate_results=candidate_results,
        max_chunks_per_source=max_chunks_per_source,
        interpreter=configured_interpreter,
        llm_model=llm_model,
    )
    write_json(results, output_file)
    return results


def main() -> None:
    genes = load_prioritized_genes(
        input_file=INPUT_FILE,
        selected_only=SELECTED_ONLY,
        limit=GENE_LIMIT,
    )
    collection = load_collection(QDRANT_ENDPOINT, COLLECTION, BM25_METADATA)
    interpretations = load_cluster_interpretations(CLUSTER_INTERPRETATIONS_FILE)
    results = analyze_genes(
        genes,
        collection,
        cluster_interpretations=interpretations,
        n_results=N_RESULTS,
        candidate_results=CANDIDATE_RESULTS,
        max_chunks_per_source=MAX_CHUNKS_PER_SOURCE,
    )
    write_json(results, OUTPUT_JSON)
    print(f"{len(results)} genes salvos em {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
