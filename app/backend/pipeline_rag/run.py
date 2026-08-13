from __future__ import annotations

import http.client
import json
import os
import re
import time
import urllib.error
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
from .evidence_validation import (
    INSUFFICIENT_MESSAGE,
    annotate_chunks_for_generation,
    entity_policy_for_gene,
    entity_resolution_for_gene,
    render_claims,
    validate_atomic_claims,
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
    "finalize_interpretation_result",
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
LLM_NUM_PREDICT = int(os.environ.get("RAG_LLM_NUM_PREDICT", "1536"))


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
            "evidence_assessment": chunk.get("evidence_assessment", {}),
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
        "Entity policy for this gene:\n"
        f"{json.dumps(entity_policy_for_gene(gene), ensure_ascii=False)}\n\n"
        "Validated entity resolution for this gene:\n"
        f"{json.dumps(entity_resolution_for_gene(gene), ensure_ascii=False)}\n\n"
        "Return valid JSON only, with exactly one top-level key: claims. "
        "Return at most three claims, each supported by a different primary evidence focus.\n"
        "The JSON schema is:\n"
        "{"
        '"claims": ['
        "{"
        '"claim": "exactly one cautious biological proposition", '
        '"citations": ["C1"], '
        '"evidence_level": "direct|ortholog|paralog|family|general", '
        '"relationship_to_query": "same_gene|ortholog|paralog|family|none|unknown", '
        '"species": "species explicitly supported by the cited text or empty", '
        '"conditions": ["treatment or environmental condition explicitly supported by cited text"], '
        '"evidence_method": ["method explicitly present in the cited text"], '
        '"confidence": "high|medium|low"'
        "}"
        "]"
        "}\n"
        "Every biological claim must be represented by exactly one claims item. "
        "Each claims item must contain exactly one proposition and at least one "
        "valid chunk_ref in citations. Keep each claim below 40 words. Copy only "
        "species and treatment conditions that occur in the same cited evidence. Do not "
        "cite a chunk unless it supports the entire claim. Never use cluster "
        "interpretations, the input name, or parametric knowledge as evidence. "
        "Never claim same_gene, direct evidence, or validated orthology from name "
        "similarity alone. If evidence concerns an unresolved homolog, family, "
        "another species, or general process, state that limitation inside the "
        "claim and use the matching relationship/evidence level. For family or "
        "general evidence, begin with 'Family members...' or identify the cited "
        "species; never say 'the gene' or attribute that function to the query. "
        "Avoid stronger "
        "causal language than the source. If no cautious cited proposition can be "
        "made, return an empty claims list."
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
            "claims": [],
            "cross_chunk_synthesis": "",
            "interpretation": strip_markdown(result),
        }
    if not isinstance(result, dict):
        return {"chunk_interpretations": [], "claims": [], "cross_chunk_synthesis": "", "interpretation": ""}

    chunk_interpretations = result.get("chunk_interpretations", [])
    if not isinstance(chunk_interpretations, list):
        chunk_interpretations = []
    claims = result.get("claims", [])
    if not isinstance(claims, list):
        claims = []
    cross_chunk_synthesis = strip_markdown(str(result.get("cross_chunk_synthesis", "") or ""))
    interpretation = strip_markdown(
        str(result.get("interpretation") or result.get("final_interpretation") or cross_chunk_synthesis or "")
    )
    return {
        "chunk_interpretations": [item for item in chunk_interpretations if isinstance(item, dict)],
        "claims": [item for item in claims if isinstance(item, dict)],
        "cross_chunk_synthesis": cross_chunk_synthesis,
        "interpretation": interpretation,
    }


def parse_interpretation_response(text: str) -> dict[str, Any]:
    parsed = extract_json_object(text)
    if parsed is None:
        return {
            "model_output_valid": False,
            "raw_model_output": text,
            "chunk_interpretations": [],
            "claims": [],
            "cross_chunk_synthesis": "",
            "interpretation": "",
        }
    normalized = normalize_interpretation_result(parsed)
    normalized["model_output_valid"] = True
    normalized["raw_model_output"] = text
    return normalized


def finalize_interpretation_result(
    gene: pd.Series,
    chunks: list[dict[str, Any]],
    result: Any,
) -> dict[str, Any]:
    normalized = normalize_interpretation_result(result)
    model_output_valid = not isinstance(result, dict) or result.get("model_output_valid", True)
    raw_model_output = result.get("raw_model_output", "") if isinstance(result, dict) else ""
    response_metadata = result.get("model_response_metadata", {}) if isinstance(result, dict) else {}
    if not model_output_valid:
        invalid = insufficient_interpretation(status="invalid_model_output")
        invalid["raw_model_output"] = raw_model_output
        invalid["rejected_claims"] = [{"reason": "invalid_json"}]
        invalid["model_response_metadata"] = response_metadata
        return invalid
    claims, rejected_claims = validate_atomic_claims(normalized["claims"], chunks)
    if not claims:
        insufficient = insufficient_interpretation()
        insufficient["chunk_interpretations"] = normalized["chunk_interpretations"]
        insufficient["rejected_claims"] = rejected_claims
        insufficient["raw_model_output"] = raw_model_output
        insufficient["model_response_metadata"] = response_metadata
        return insufficient
    interpretation = render_claims(claims)
    return {
        "status": "supported_claims",
        "claims": claims,
        "rejected_claims": rejected_claims,
        "raw_model_output": raw_model_output,
        "model_response_metadata": response_metadata,
        "chunk_interpretations": normalized["chunk_interpretations"],
        "cross_chunk_synthesis": interpretation,
        "interpretation": interpretation,
    }


def insufficient_interpretation(status: str = "insufficient_evidence") -> dict[str, Any]:
    message = INSUFFICIENT_MESSAGE
    return {
        "status": status,
        "claims": [],
        "rejected_claims": [],
        "raw_model_output": "",
        "model_response_metadata": {},
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
    num_predict: int = LLM_NUM_PREDICT,
) -> dict[str, Any]:
    if not chunks:
        return insufficient_interpretation()

    payload = {
        "model": model,
        "stream": False,
        "think": False,
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
        "options": {"temperature": 0.0, "num_ctx": num_ctx, "num_predict": num_predict},
    }
    request = urllib.request.Request(
        ollama_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        result = json.load(response)
    parsed = parse_interpretation_response(result.get("message", {}).get("content", ""))
    parsed["model_response_metadata"] = {
        "done": result.get("done"),
        "done_reason": result.get("done_reason", ""),
        "prompt_eval_count": result.get("prompt_eval_count"),
        "eval_count": result.get("eval_count"),
        "thinking_present": bool(result.get("message", {}).get("thinking")),
    }
    return parsed


def analyze_genes(
    genes: pd.DataFrame,
    collection: dict[str, Any],
    cluster_interpretations: dict[str, str] | None = None,
    n_results: int = N_RESULTS,
    candidate_results: int = CANDIDATE_RESULTS,
    max_chunks_per_source: int = MAX_CHUNKS_PER_SOURCE,
    interpreter=interpret_gene,
    llm_model: str = LLM_MODEL,
    on_result=None,
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
        chunks = annotate_chunks_for_generation(gene, add_citation_ids(chunks))
        interpretation_result = finalize_interpretation_result(
            gene,
            chunks,
            interpreter(gene, chunks, gene_cluster_interpretations),
        )
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
                    "facets": list(queries.get("facets", ())),
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
                "interpretation_status": interpretation_result["status"],
                "claims": interpretation_result["claims"],
                "rejected_claims": interpretation_result["rejected_claims"],
                "raw_model_output": interpretation_result["raw_model_output"],
                "model_response_metadata": (
                    interpretation_result.get("model_response_metadata", {})
                    if isinstance(interpretation_result, dict)
                    else {}
                ),
                "chunk_interpretations": interpretation_result["chunk_interpretations"],
                "cross_chunk_synthesis": interpretation_result["cross_chunk_synthesis"],
                "interpretation": interpretation_result["interpretation"],
            }
        )
        if on_result is not None:
            on_result(results)
    return results


def write_json(results: list[dict[str, Any]], output_file: Path = OUTPUT_JSON) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_file.with_suffix(output_file.suffix + ".tmp")
    temporary.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(output_file)


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
    llm_num_predict: int = LLM_NUM_PREDICT,
    selected_only: bool = True,
    gene_limit: int | None = None,
    n_results: int = N_RESULTS,
    candidate_results: int = CANDIDATE_RESULTS,
    max_chunks_per_source: int = MAX_CHUNKS_PER_SOURCE,
    resume: bool = False,
    llm_attempts: int = 3,
) -> list[dict[str, Any]]:
    genes = load_prioritized_genes(
        input_file=input_file,
        selected_only=selected_only,
        limit=gene_limit,
    )
    if genes.empty:
        write_json([], output_file)
        return []

    existing_results: list[dict[str, Any]] = []
    if resume and output_file.is_file():
        loaded = json.loads(output_file.read_text(encoding="utf-8"))
        if not isinstance(loaded, list) or not all(isinstance(item, dict) for item in loaded):
            raise ValueError(f"Invalid RAG checkpoint: {output_file}")
        existing_results = loaded
        completed_gene_ids = {str(item.get("gene_id", "")) for item in existing_results}
        genes = genes.loc[~genes["gene_id"].astype(str).isin(completed_gene_ids)].reset_index(drop=True)
        if genes.empty:
            return existing_results

    store = load_collection(qdrant_url, collection_name, bm25_metadata_path)
    interpretations = load_cluster_interpretations(interpretations_file)

    def configured_interpreter(gene, chunks, cluster_interpretations):
        for attempt in range(1, llm_attempts + 1):
            try:
                return interpret_gene(
                    gene,
                    chunks,
                    cluster_interpretations,
                    ollama_url=ollama_url,
                    model=llm_model,
                    num_ctx=llm_num_ctx,
                    num_predict=llm_num_predict,
                )
            except (ConnectionError, TimeoutError, http.client.RemoteDisconnected, urllib.error.URLError):
                if attempt == llm_attempts:
                    raise
                wait_seconds = 5 * attempt
                print(
                    f"Ollama request failed for {gene['gene_id']} "
                    f"(attempt {attempt}/{llm_attempts}); retrying in {wait_seconds}s",
                    flush=True,
                )
                time.sleep(wait_seconds)

        raise RuntimeError("unreachable")

    def checkpoint(partial_results: list[dict[str, Any]]) -> None:
        write_json([*existing_results, *partial_results], output_file)

    results = analyze_genes(
        genes,
        store,
        cluster_interpretations=interpretations,
        n_results=n_results,
        candidate_results=candidate_results,
        max_chunks_per_source=max_chunks_per_source,
        interpreter=configured_interpreter,
        llm_model=llm_model,
        on_result=checkpoint,
    )
    combined_results = [*existing_results, *results]
    write_json(combined_results, output_file)
    return combined_results


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
