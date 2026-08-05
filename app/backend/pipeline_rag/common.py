from __future__ import annotations

import json
import math
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

ARTICLES_DIR = Path(os.environ.get("RAG_ARTICLES_DIR", "/rag/articles"))
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or None
COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION", "banco_literatura_bio")
BM25_METADATA_PATH = Path(os.environ.get("BM25_METADATA_PATH", "outputs/bm25_metadata.json"))
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"

OLLAMA_BATCH_EMBEDDING_URL = os.environ.get(
    "OLLAMA_EMBEDDING_URL",
    os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + "/api/embed",
)
EMBEDDING_MODEL = os.environ.get("RAG_EMBEDDING_MODEL", "bge-m3:latest")

TARGET_WORDS = 350
OVERLAP_SENTENCES = 2
MIN_CHUNK_WORDS = 30
BATCH_SIZE = 8
RESET_COLLECTION = True
LIMIT_ARTICLES: int | None = None
SKIP_LOW_VALUE_SECTIONS = True
SKIP_TABLE_LIKE_CHUNKS = True
PROGRESS_INTERVAL = 50
ANNOTATE_LITERATURE_ENTITIES = os.environ.get("RAG_ANNOTATE_LITERATURE_ENTITIES", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
LITERATURE_ENTITY_PATTERN_FILE = Path(
    os.environ.get(
        "RAG_ENTITY_PATTERN_FILE",
        str(Path(__file__).resolve().parent / "resources" / "literature_entity_patterns.json"),
    )
)
LITERATURE_ENTITY_BATCH_SIZE = 16

ENTITY_PAYLOAD_FIELDS = (
    "gene_like_mentions",
    "species_mentions",
    "cellular_component_mentions",
    "simple_chemical_mentions",
    "protein_family_mentions",
    "go_mentions",
)

LOW_VALUE_SECTION_RE = re.compile(
    r"""
    ^(?:\d+(?:\.\d+)*\s*)?
    (?:
        (?:
            references?
            |bibliography
            |literature\s+cited
            |parsed\s+citations?
            |acknowledg(?:e)?ments?
            |funding
            |author\s+contributions?
            |data\s+availability
            |supplement(?:ary)?(?:\s+(?:material|materials|information))?
            |supporting\s+information
            |abbreviations?
            |keywords?
            |accession\s+numbers?
            |tables?
            |figures?
            |materials?\s+(?:and|&)\s+methods?
            |methods?
            |star\+methods
        )\b
        |(?:supplementary\s+)?(?:fig(?:ure)?\.?|table)\s*\d*
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
TABLE_PIPE_THRESHOLD = 12
TABLE_BR_THRESHOLD = 8
REFERENCE_TEXT_MARKERS = (
    "google scholar",
    "pubmed:",
    "refhub.elsevier.com",
    "doi.org/",
)

WORD_RE = re.compile(r"\S+")
TERM_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*")
BM25_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def clean_text(text: str) -> str:
    text = re.sub(r"<span[^>]*>\s*</span>", " ", str(text))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def usable_text(value: Any) -> str:
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none"} else text


def normalize_section_title(section: str) -> str:
    section = re.sub(r"[*_`#>\[\]()]|<[^>]+>", " ", str(section))
    section = re.sub(r"\s+", " ", section)
    return section.strip().lower()


def is_low_value_section(section: str) -> bool:
    return bool(LOW_VALUE_SECTION_RE.search(normalize_section_title(section)))


def is_table_like_text(text: str) -> bool:
    normalized = str(text).lower()
    pipe_count = normalized.count("|")
    br_count = normalized.count("<br")
    return pipe_count >= TABLE_PIPE_THRESHOLD or (
        pipe_count >= TABLE_PIPE_THRESHOLD // 2 and br_count >= TABLE_BR_THRESHOLD
    )


def low_value_chunk_reason(section: str, text: str) -> str | None:
    if is_low_value_section(section):
        return "low_value_section"
    if is_table_like_text(text):
        return "table_like_text"

    normalized_text = str(text).strip().lower()
    if normalized_text.startswith(("references ", "**references", "references -")):
        return "reference_like_text"
    if any(marker in normalized_text for marker in REFERENCE_TEXT_MARKERS):
        return "reference_like_text"
    return None


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def unique_texts(parts: list[str]) -> list[str]:
    unique = []
    seen = set()
    for part in parts:
        key = re.sub(r"\s+", " ", str(part).lower()).strip()
        if key and key not in seen:
            unique.append(part)
            seen.add(key)
    return unique


def text_terms(text: str, stopwords: set[str], min_length: int = 4) -> list[str]:
    terms = []
    for term in TERM_RE.findall(str(text).lower()):
        if len(term) < min_length or term in stopwords:
            continue
        terms.append(term)
        if "-" in term:
            terms.extend(part for part in term.split("-") if len(part) >= min_length and part not in stopwords)
    return list(dict.fromkeys(terms))


NAME_TERM_STOPWORDS = set(
    "probable putative protein proteins family domain containing chloroplastic "
    "mitochondrial uncharacterized like isoform subunit large chain class".split()
)
CONTEXT_TERM_STOPWORDS = NAME_TERM_STOPWORDS | set(
    "process activity binding response regulation positive negative cellular "
    "component located central cluster theme".split()
)


def name_terms(name: str) -> list[str]:
    return text_terms(name, NAME_TERM_STOPWORDS, min_length=3)


def context_terms(text: str) -> list[str]:
    return text_terms(text, CONTEXT_TERM_STOPWORDS, min_length=5)


def matched_terms(text: str, terms: list[str]) -> list[str]:
    normalized = " ".join(TERM_RE.findall(str(text).lower()))
    token_set = set(normalized.split())
    return [term for term in terms if term in token_set or term in normalized]


def normalized_phrase(text: str) -> str:
    return " ".join(TERM_RE.findall(usable_text(text).lower()))


def phrase_matches(text: str, phrases: list[str] | tuple[str, ...]) -> list[str]:
    normalized = normalized_phrase(text)
    matches = []
    for phrase in phrases:
        normalized_candidate = normalized_phrase(phrase)
        if normalized_candidate and normalized_candidate in normalized:
            matches.append(phrase)
    return unique_texts(matches)


def list_payload(chunk: dict[str, Any], field: str) -> list[str]:
    value = chunk.get(field, [])
    if isinstance(value, list):
        return [usable_text(item) for item in value if usable_text(item)]
    return [usable_text(value)] if usable_text(value) else []


def mention_matches_query_terms(mentions: list[str], terms: list[str]) -> list[str]:
    return unique_texts([mention for mention in mentions if matched_terms(mention, terms)])


def payload_match_summary(
    chunk: dict[str, Any],
    queries: dict[str, Any],
) -> dict[str, Any]:
    text = chunk.get("text", "")
    aliases = queries.get("aliases") or (queries["bm25"],)
    gene_mentions = list_payload(chunk, "gene_like_mentions")
    protein_family_mentions = list_payload(chunk, "protein_family_mentions")
    go_mentions = list_payload(chunk, "go_mentions")
    context_mentions = list_payload(chunk, "cellular_component_mentions") + list_payload(
        chunk, "simple_chemical_mentions"
    )
    context_terms_for_query = context_terms(queries["embedding"])

    go_matches = []
    for mention in go_mentions:
        if phrase_matches(mention, queries.get("context_phrases", ())) or matched_terms(
            mention,
            context_terms_for_query,
        ):
            go_matches.append(mention)

    return {
        "alias_text_matches": unique_texts(phrase_matches(text, aliases)),
        "alias_payload_matches": unique_texts(
            [alias for alias in aliases if phrase_matches(" ".join(gene_mentions), (alias,))]
        ),
        "protein_family_matches": mention_matches_query_terms(
            protein_family_mentions,
            name_terms(queries["bm25"]),
        ),
        "go_matches": unique_texts(go_matches),
        "context_payload_matches": mention_matches_query_terms(
            context_mentions,
            context_terms_for_query,
        ),
    }


def add_payload_match_summaries(
    chunks: list[dict[str, Any]],
    queries: dict[str, Any],
) -> list[dict[str, Any]]:
    enriched = []
    for chunk in chunks:
        enriched_chunk = dict(chunk)
        enriched_chunk["payload_match"] = payload_match_summary(enriched_chunk, queries)
        enriched.append(enriched_chunk)
    return enriched


def tokenize_for_bm25(text: str) -> list[str]:
    tokens = []
    for token in BM25_TOKEN_RE.findall(str(text).lower()):
        if len(token) < 2:
            continue
        tokens.append(token)
        if "-" in token:
            tokens.extend(part for part in token.split("-") if len(part) >= 2)
    return tokens


def build_bm25_model(texts: list[str]) -> dict[str, Any]:
    document_frequencies: dict[str, int] = {}
    total_tokens = 0
    for text in texts:
        tokens = tokenize_for_bm25(text)
        total_tokens += len(tokens)
        for token in set(tokens):
            document_frequencies[token] = document_frequencies.get(token, 0) + 1

    vocabulary = {token: index for index, token in enumerate(sorted(document_frequencies), start=1)}
    doc_count = len(texts)
    idf = {
        token: math.log(1 + (doc_count - frequency + 0.5) / (frequency + 0.5))
        for token, frequency in document_frequencies.items()
    }
    return {
        "vocabulary": vocabulary,
        "idf": idf,
        "avg_doc_length": total_tokens / doc_count if doc_count else 0.0,
        "doc_count": doc_count,
        "k1": 1.5,
        "b": 0.75,
    }


def bm25_sparse_vector(text: str, model: dict[str, Any]) -> tuple[list[int], list[float]]:
    tokens = tokenize_for_bm25(text)
    if not tokens:
        return [], []

    term_frequencies: dict[str, int] = {}
    for token in tokens:
        if token in model["vocabulary"]:
            term_frequencies[token] = term_frequencies.get(token, 0) + 1

    doc_length = len(tokens)
    denominator_length = (
        model["k1"] * (1 - model["b"] + model["b"] * doc_length / model["avg_doc_length"])
        if model["avg_doc_length"]
        else model["k1"]
    )
    values_by_index = {}
    for token, frequency in term_frequencies.items():
        denominator = frequency + denominator_length
        score = model["idf"][token] * frequency * (model["k1"] + 1) / denominator
        if score > 0:
            values_by_index[model["vocabulary"][token]] = score

    items = sorted(values_by_index.items())
    return [index for index, _ in items], [value for _, value in items]


def write_bm25_model(
    model: dict[str, Any],
    metadata_path: Path = BM25_METADATA_PATH,
) -> None:
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(
            {
                "vocabulary": model["vocabulary"],
                "idf": model["idf"],
                "avg_doc_length": model["avg_doc_length"],
                "doc_count": model["doc_count"],
                "k1": model["k1"],
                "b": model["b"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def load_bm25_model(metadata_path: Path = BM25_METADATA_PATH) -> dict[str, Any]:
    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    return {
        "vocabulary": {str(token): int(index) for token, index in data["vocabulary"].items()},
        "idf": {str(token): float(value) for token, value in data["idf"].items()},
        "avg_doc_length": float(data["avg_doc_length"]),
        "doc_count": int(data["doc_count"]),
        "k1": float(data.get("k1", 1.5)),
        "b": float(data.get("b", 0.75)),
    }


def embed_texts(texts: list[str]) -> list[list[float]]:
    payload = {
        "model": EMBEDDING_MODEL,
        "input": [clean_text(text) for text in texts],
    }
    request = urllib.request.Request(
        OLLAMA_BATCH_EMBEDDING_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        result = json.load(response)
    return result["embeddings"]
