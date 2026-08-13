from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from .common import (
    BM25_METADATA_PATH,
    COLLECTION_NAME,
    DENSE_VECTOR_NAME,
    ENTITY_PAYLOAD_FIELDS,
    QDRANT_API_KEY,
    QDRANT_URL,
    SPARSE_VECTOR_NAME,
    add_payload_match_summaries,
    bm25_sparse_vector,
    context_terms,
    embed_texts,
    load_bm25_model,
    low_value_chunk_reason,
    matched_terms,
    name_terms,
    payload_match_summary,
    unique_texts,
    usable_text,
)

INPUT_FILE = Path("outputs/prioritized_genes.csv")
SELECTED_ONLY = True
GENE_LIMIT: int | None = None
CLUSTER_INTERPRETATIONS_FILE = Path("clusters/interpretations.csv")
QDRANT_ENDPOINT = QDRANT_URL
COLLECTION = COLLECTION_NAME
BM25_METADATA = BM25_METADATA_PATH
N_RESULTS = 5
CANDIDATE_RESULTS = 40
MAX_CHUNKS_PER_SOURCE = 2


def load_prioritized_genes(
    input_file: Path = INPUT_FILE,
    selected_only: bool = SELECTED_ONLY,
    limit: int | None = GENE_LIMIT,
) -> pd.DataFrame:
    genes = pd.read_csv(input_file)
    if selected_only:
        selected = genes["selected_for_search"].astype(str).str.lower().eq("true")
        genes = genes.loc[selected].copy()
    if limit is not None:
        genes = genes.head(limit)
    return genes.reset_index(drop=True)


def split_parenthetical_aliases(text: str) -> list[str]:
    aliases = []
    for alias in re.findall(r"\(([^()]+)\)", usable_text(text)):
        alias = alias.strip()
        if alias and not alias.lower().startswith(("ec ", "go:")):
            aliases.append(alias)
    return aliases


def compact_uniprot_name(text: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", usable_text(text)).strip()


def symbol_aliases(text: str) -> list[str]:
    aliases = []
    for token in re.findall(r"\b[A-Za-z]{1,8}[A-Za-z-]*\d+[A-Za-z0-9-]*\b", text):
        token = token.strip("-")
        if len(token) >= 3 and not token.upper().startswith("GO"):
            aliases.append(token)
    return aliases


def aliases_for_gene(gene: pd.Series) -> tuple[str, ...]:
    uniprot_name = usable_text(gene.get("Uniprot gene names", ""))
    candidates = [
        usable_text(gene.get("primary_name", "")),
        usable_text(gene.get("Name GFF", "")),
        compact_uniprot_name(uniprot_name),
        *split_parenthetical_aliases(uniprot_name),
    ]
    candidates.extend(symbol_aliases(" ".join(candidates + [uniprot_name])))

    aliases = []
    for candidate in candidates:
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,;")
        if len(candidate) < 3:
            continue
        if name_terms(candidate) or re.search(r"\d", candidate):
            aliases.append(candidate)
    return tuple(unique_texts(aliases))


def bm25_query_for_gene(gene: pd.Series) -> str:
    aliases = aliases_for_gene(gene)
    return " ".join(aliases[:6]) if aliases else usable_text(gene.get("primary_name", ""))


def ontology_terms_from_search_query(gene: pd.Series) -> str:
    query = usable_text(gene.get("search_query", ""))
    name = bm25_query_for_gene(gene)
    if not query:
        return ""
    if name and query.lower().startswith(name.lower()):
        return query[len(name) :].lstrip(" ,;:-")
    return query


def context_phrases_from_query(text: str) -> tuple[str, ...]:
    phrases = [phrase.strip(" ,;:-") for phrase in re.split(r"[,;|]", usable_text(text))]
    return tuple(unique_texts([phrase for phrase in phrases if phrase]))


def facet_queries_for_gene(gene: pd.Series) -> tuple[dict[str, str], ...]:
    primary_name = usable_text(gene.get("primary_name", ""))
    phrases = context_phrases_from_query(ontology_terms_from_search_query(gene))
    facets = [{"facet": "identity", "query": primary_name}]
    rules = (
        ("localization", ("membrane", "nucleus", "cytoplasm", "chloroplast", "mitochond", "golgi", "localization")),
        ("expression_or_stress", ("response", "stress", "drought", "salt", "cold", "heat", "infection", "expression")),
        ("phenotype_or_development", ("development", "elongation", "germination", "growth", "senescence", "phenotype")),
        ("molecular_function", ("activity", "binding", "channel", "enzyme", "transport")),
    )
    used = set()
    for phrase in phrases:
        if phrase.lower() == primary_name.lower():
            continue
        lowered = phrase.lower()
        facet = "biological_process"
        for candidate, terms in rules:
            if any(term in lowered for term in terms):
                facet = candidate
                break
        key = (facet, phrase.lower())
        if key in used:
            continue
        used.add(key)
        facets.append({"facet": facet, "query": f"{primary_name}, {phrase}"})
    return tuple(facets[:5])


def retrieval_queries_for_gene(
    gene: pd.Series,
    cluster_interpretations: list[dict[str, str]],
) -> dict[str, Any]:
    del cluster_interpretations
    embedding_query = ontology_terms_from_search_query(gene)
    return {
        "bm25": bm25_query_for_gene(gene),
        "embedding": embedding_query,
        "aliases": aliases_for_gene(gene),
        "context_phrases": context_phrases_from_query(embedding_query),
        "facets": facet_queries_for_gene(gene),
    }


def load_cluster_interpretations(
    interpretations_file: Path = CLUSTER_INTERPRETATIONS_FILE,
) -> dict[str, str]:
    if not interpretations_file.exists():
        return {}
    interpretations = pd.read_csv(interpretations_file)
    return {
        f"{row.ontology}:{row.direction}:{int(row.cluster)}": row.interpretation for row in interpretations.itertuples()
    }


def cluster_interpretations_for_gene(
    gene: pd.Series,
    interpretations: dict[str, str],
) -> list[dict[str, str]]:
    clusters = []
    for cluster_id in str(gene.get("represented_clusters", "")).split(";"):
        cluster_id = cluster_id.strip()
        if cluster_id and cluster_id in interpretations:
            clusters.append({"cluster": cluster_id, "interpretation": interpretations[cluster_id]})
    return clusters


def load_collection(
    qdrant_url: str = QDRANT_ENDPOINT,
    collection_name: str = COLLECTION,
    bm25_metadata_path: Path = BM25_METADATA,
) -> dict[str, Any]:
    if not bm25_metadata_path.exists():
        raise FileNotFoundError(f"Metadata BM25 nao encontrada: {bm25_metadata_path}")

    from qdrant_client import QdrantClient

    return {
        "client": QdrantClient(url=qdrant_url, api_key=QDRANT_API_KEY),
        "collection_name": collection_name,
        "bm25_model": load_bm25_model(bm25_metadata_path),
    }


def citation_id_for_index(index: int) -> str:
    return f"C{index}"


def add_citation_ids(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cited = []
    for index, chunk in enumerate(chunks, start=1):
        cited_chunk = dict(chunk)
        cited_chunk["citation_id"] = citation_id_for_index(index)
        cited.append(cited_chunk)
    return cited


def rerank_chunks_by_name_and_context(
    chunks: list[dict[str, Any]],
    queries: dict[str, Any],
) -> list[dict[str, Any]]:
    chunks = add_payload_match_summaries(chunks, queries)
    gene_terms = name_terms(queries["bm25"])
    ontology_terms = context_terms(queries["embedding"])

    def key(chunk: dict[str, Any]) -> tuple[int, int, int, int, int, int, int, int]:
        text = chunk.get("text", "")
        payload_match = chunk.get("payload_match", {})
        alias_score = len(payload_match.get("alias_payload_matches", [])) * 2 + len(
            payload_match.get("alias_text_matches", [])
        )
        family_score = len(payload_match.get("protein_family_matches", []))
        go_score = len(payload_match.get("go_matches", []))
        payload_context_score = len(payload_match.get("context_payload_matches", []))
        name_hit_count = len(matched_terms(text, gene_terms))
        context_hit_count = len(matched_terms(text, ontology_terms))
        any_name = alias_score > 0 or name_hit_count > 0 or family_score > 0
        any_context = go_score > 0 or payload_context_score > 0 or context_hit_count > 0
        return (
            -alias_score,
            -int(any_name and any_context),
            -family_score,
            -go_score,
            -payload_context_score,
            -name_hit_count,
            -context_hit_count,
            int(chunk.get("hit_rank", 0)),
        )

    return sorted(chunks, key=key)


def select_retrieved_chunks(
    chunks: list[dict[str, Any]],
    n_results: int,
    max_chunks_per_source: int = MAX_CHUNKS_PER_SOURCE,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    deferred_by_source: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()

    for chunk in chunks:
        if low_value_chunk_reason(chunk.get("section", ""), chunk.get("text", "")):
            continue
        source = str(chunk.get("source", ""))
        if source and source_counts[source] >= max_chunks_per_source:
            deferred_by_source.append(chunk)
            continue
        selected.append(chunk)
        source_counts[source] += 1
        if len(selected) == n_results:
            break

    if len(selected) < n_results:
        selected.extend(deferred_by_source[: n_results - len(selected)])

    reranked = []
    for hit_rank, chunk in enumerate(selected[:n_results], start=1):
        reranked_chunk = dict(chunk)
        reranked_chunk["retrieved_rank"] = reranked_chunk.pop("hit_rank")
        reranked_chunk["hit_rank"] = hit_rank
        reranked_chunk["citation_id"] = citation_id_for_index(hit_rank)
        reranked.append(reranked_chunk)
    return reranked


def _collect_payload_values(
    payload_matches: list[dict[str, Any]],
    field: str,
) -> list[str]:
    return unique_texts([value for match in payload_matches for value in match.get(field, [])])


def evidence_signals(
    gene: pd.Series,
    queries: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    combined_text = " ".join(chunk.get("text", "") for chunk in chunks)
    gene_terms = name_terms(queries["bm25"])
    context_terms_for_query = context_terms(queries["embedding"])
    matched = matched_terms(combined_text, gene_terms)
    context_matched = matched_terms(combined_text, context_terms_for_query)
    primary_name = usable_text(gene.get("primary_name", ""))
    full_name = bool(primary_name) and primary_name.lower() in combined_text.lower()
    payload_matches = [chunk.get("payload_match") or payload_match_summary(chunk, queries) for chunk in chunks]
    alias_payload_matches = _collect_payload_values(payload_matches, "alias_payload_matches")
    alias_text_matches = _collect_payload_values(payload_matches, "alias_text_matches")
    protein_family_matches = _collect_payload_values(payload_matches, "protein_family_matches")
    go_matches = _collect_payload_values(payload_matches, "go_matches")
    context_payload_matches = _collect_payload_values(payload_matches, "context_payload_matches")

    def has_name_signal(chunk: dict[str, Any], match: dict[str, Any]) -> bool:
        return bool(
            match.get("alias_payload_matches")
            or match.get("alias_text_matches")
            or matched_terms(chunk.get("text", ""), gene_terms)
        )

    observed_signal_types = []
    if full_name or matched or alias_payload_matches or alias_text_matches:
        observed_signal_types.append("name_or_alias")
    if protein_family_matches:
        observed_signal_types.append("protein_family")
    if go_matches:
        observed_signal_types.append("go_process")
    if context_payload_matches or context_matched:
        observed_signal_types.append("context")

    return {
        "observed_signal_types": observed_signal_types,
        "retrieval_overview": {
            "chunks_returned": len(chunks),
            "sources_returned": len({c.get("source", "") for c in chunks if c.get("source")}),
            "sections_returned": unique_texts([chunk.get("section", "") for chunk in chunks if chunk.get("section")])[
                :20
            ],
            "chunks_with_payload_signal": sum(
                bool(
                    match.get("alias_payload_matches")
                    or match.get("protein_family_matches")
                    or match.get("go_matches")
                    or match.get("context_payload_matches")
                )
                for match in payload_matches
            ),
            "chunks_with_name_or_alias_signal": sum(
                has_name_signal(chunk, match) for chunk, match in zip(chunks, payload_matches)
            ),
            "chunks_with_family_or_process_signal": sum(
                bool(
                    match.get("protein_family_matches")
                    or match.get("go_matches")
                    or match.get("context_payload_matches")
                )
                for match in payload_matches
            ),
        },
        "name_and_alias_matches": {
            "full_name_in_text": full_name,
            "matched_name_terms": matched[:20],
            "alias_payload_matches": alias_payload_matches[:20],
            "alias_text_matches": alias_text_matches[:20],
        },
        "biological_context_matches": {
            "protein_family_mentions": protein_family_matches[:20],
            "go_mentions": go_matches[:20],
            "context_payload_mentions": context_payload_matches[:20],
            "context_text_terms": context_matched[:20],
        },
    }


def search_chunks(
    store: dict[str, Any],
    queries: dict[str, Any],
    n_results: int,
    candidate_results: int = CANDIDATE_RESULTS,
    max_chunks_per_source: int = MAX_CHUNKS_PER_SOURCE,
) -> list[dict[str, Any]]:
    from qdrant_client import models

    facet_queries = [item["query"] for item in queries.get("facets", ()) if item.get("query")]
    if not facet_queries:
        facet_queries = [queries["embedding"]]
    dense_queries = embed_texts(facet_queries)
    sparse_indices, sparse_values = bm25_sparse_vector(
        queries["bm25"],
        store["bm25_model"],
    )
    if sparse_indices:
        prefetch = [
            models.Prefetch(
                query=models.SparseVector(indices=sparse_indices, values=sparse_values),
                using=SPARSE_VECTOR_NAME,
                limit=candidate_results,
            )
        ]
        prefetch.extend(
            models.Prefetch(query=dense_query, using=DENSE_VECTOR_NAME, limit=candidate_results)
            for dense_query in dense_queries
        )
        response = store["client"].query_points(
            collection_name=store["collection_name"],
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=candidate_results,
            with_payload=True,
        )
    else:
        response = store["client"].query_points(
            collection_name=store["collection_name"],
            prefetch=[
                models.Prefetch(query=dense_query, using=DENSE_VECTOR_NAME, limit=candidate_results)
                for dense_query in dense_queries
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=candidate_results,
            with_payload=True,
        )

    chunks = []
    for index, point in enumerate(response.points, start=1):
        payload = point.payload or {}
        chunks.append(
            {
                "hit_rank": index,
                "chunk_id": payload.get("chunk_id", ""),
                "source": payload.get("fonte", ""),
                "article_title": payload.get("article_title", ""),
                "section": payload.get("section", ""),
                "text": payload.get("text", ""),
                **{field: payload.get(field, []) for field in ENTITY_PAYLOAD_FIELDS},
            }
        )
    return select_retrieved_chunks(
        rerank_chunks_by_name_and_context(chunks, queries),
        n_results=n_results,
        max_chunks_per_source=max_chunks_per_source,
    )
