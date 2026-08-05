from __future__ import annotations

import hashlib
import re
import warnings
from pathlib import Path
from typing import Any, Iterable

from .common import (
    ARTICLES_DIR,
    LIMIT_ARTICLES,
    MIN_CHUNK_WORDS,
    OVERLAP_SENTENCES,
    PROGRESS_INTERVAL,
    SKIP_LOW_VALUE_SECTIONS,
    SKIP_TABLE_LIKE_CHUNKS,
    TARGET_WORDS,
    clean_text,
    count_words,
    is_low_value_section,
    is_table_like_text,
)

DEFAULT_PATTERN_FILE = Path(__file__).resolve().parent / "resources" / "literature_entity_patterns.json"
DEFAULT_SPACY_MODEL = "en_ner_bionlp13cg_md"
SPAN_KEY = "literature_terms"
MAX_MENTIONS_PER_FIELD = 80

NER_LABEL_FIELDS = {
    "GENE_OR_GENE_PRODUCT": "gene_like_mentions",
    "ORGANISM": "species_mentions",
    "CELLULAR_COMPONENT": "cellular_component_mentions",
    "SIMPLE_CHEMICAL": "simple_chemical_mentions",
}
SPAN_LABEL_FIELDS = {
    "SPECIES": "species_mentions",
    "PROTEIN_FAMILY": "protein_family_mentions",
    "GO_TERM": "go_mentions",
}
MENTION_FIELDS = tuple(dict.fromkeys(tuple(NER_LABEL_FIELDS.values()) + tuple(SPAN_LABEL_FIELDS.values())))

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9_*\"'(\[])")


def normalize_mention(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text))
    return text.strip(" \t\n\r,.;:()[]{}")


def unique_mentions(
    mentions: Iterable[str],
    limit: int = MAX_MENTIONS_PER_FIELD,
) -> list[str]:
    unique = []
    seen = set()
    for mention in mentions:
        normalized = normalize_mention(mention)
        key = normalized.lower()
        if not key or key in seen:
            continue
        unique.append(normalized)
        seen.add(key)
        if len(unique) >= limit:
            break
    return unique


def _load_terms(data: dict[str, Any], key: str) -> list[str]:
    values = data.get(key, [])
    if not isinstance(values, list):
        raise ValueError(f"Campo '{key}' deve ser uma lista em {DEFAULT_PATTERN_FILE}.")
    return unique_mentions(str(value) for value in values)


def load_pattern_terms(
    pattern_file: Path = DEFAULT_PATTERN_FILE,
) -> tuple[list[str], list[str], list[str]]:
    import json

    data = json.loads(pattern_file.read_text(encoding="utf-8"))
    return (
        _load_terms(data, "species_terms"),
        _load_terms(data, "protein_family_terms"),
        _load_terms(data, "go_terms"),
    )


def make_span_patterns(
    protein_family_terms: Iterable[str],
    go_terms: Iterable[str],
    species_terms: Iterable[str] = (),
) -> list[dict[str, str]]:
    patterns = [{"label": "SPECIES", "pattern": term} for term in species_terms]
    patterns.extend({"label": "PROTEIN_FAMILY", "pattern": term} for term in protein_family_terms)
    patterns.extend({"label": "GO_TERM", "pattern": term} for term in go_terms)
    return patterns


def load_annotator(
    pattern_file: Path = DEFAULT_PATTERN_FILE,
    model_name: str = DEFAULT_SPACY_MODEL,
) -> Any:
    try:
        import spacy
    except ImportError as exc:
        raise RuntimeError(
            "scispaCy nao esta disponivel neste Python. "
            "Rode a indexacao com .venv-scispacy/bin/python ou desative "
            "ANNOTATE_LITERATURE_ENTITIES em rag/common.py."
        ) from exc

    species_terms, protein_family_terms, go_terms = load_pattern_terms(pattern_file)
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Possible set union at position .*",
            category=FutureWarning,
        )
        nlp = spacy.load(model_name)
    if "literature_span_ruler" in nlp.pipe_names:
        nlp.remove_pipe("literature_span_ruler")
    ruler = nlp.add_pipe(
        "span_ruler",
        name="literature_span_ruler",
        config={"spans_key": SPAN_KEY, "phrase_matcher_attr": "LOWER"},
        last=True,
    )
    ruler.add_patterns(
        make_span_patterns(
            species_terms=species_terms,
            protein_family_terms=protein_family_terms,
            go_terms=go_terms,
        )
    )
    return nlp


def annotate(nlp: Any, text: str) -> dict[str, Any]:
    return payload_from_doc(nlp(str(text)))


def annotate_many(
    nlp: Any,
    texts: list[str],
    batch_size: int = 16,
) -> list[dict[str, Any]]:
    docs = nlp.pipe((str(text) for text in texts), batch_size=batch_size)
    return [payload_from_doc(doc) for doc in docs]


def payload_from_doc(doc: Any) -> dict[str, Any]:
    mentions_by_field: dict[str, list[str]] = {field: [] for field in MENTION_FIELDS}
    for entity in doc.ents:
        field = NER_LABEL_FIELDS.get(entity.label_)
        if field:
            mentions_by_field[field].append(entity.text)
    for span in doc.spans.get(SPAN_KEY, []):
        field = SPAN_LABEL_FIELDS.get(span.label_)
        if field:
            mentions_by_field[field].append(span.text)

    payload: dict[str, Any] = {}
    for field, mentions in mentions_by_field.items():
        unique = unique_mentions(mentions)
        payload[field] = unique
        payload[f"has_{field.removesuffix('_mentions')}_mention"] = bool(unique)
    return payload


def article_title(text: str, default_title: str) -> str:
    for line in text.splitlines():
        match = HEADING_RE.match(line.strip())
        if match and match.group(2).strip().lower() not in {"article", "references"}:
            return clean_text(match.group(2))
    return default_title


def split_sections(text: str) -> list[dict[str, Any]]:
    sections = []
    current_title = "Article"
    current_level = 1
    current_lines: list[str] = []

    for line in text.splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            section_text = clean_text("\n".join(current_lines))
            if section_text:
                sections.append(
                    {
                        "title": current_title,
                        "heading_level": current_level,
                        "text": section_text,
                    }
                )
            current_level = len(match.group(1))
            current_title = clean_text(match.group(2))
            current_lines = [current_title]
        else:
            current_lines.append(line)

    section_text = clean_text("\n".join(current_lines))
    if section_text:
        sections.append(
            {
                "title": current_title,
                "heading_level": current_level,
                "text": section_text,
            }
        )
    return sections


def split_sentences(text: str) -> list[str]:
    paragraphs = [clean_text(paragraph) for paragraph in re.split(r"\n{2,}", text)]
    sentences = []
    for paragraph in paragraphs:
        if paragraph:
            sentences.extend(sentence.strip() for sentence in SENTENCE_RE.split(paragraph) if sentence.strip())
    return sentences


def split_long_sentence(sentence: str, target_words: int) -> list[str]:
    words = sentence.split()
    if len(words) <= target_words:
        return [sentence]
    return [" ".join(words[index : index + target_words]) for index in range(0, len(words), target_words)]


def chunk_section(
    section: dict[str, Any],
    section_index: int,
    article_file: Path,
    title: str,
    target_words: int,
    overlap_sentences: int,
    min_chunk_words: int,
    skip_table_like_chunks: bool,
) -> list[dict[str, Any]]:
    sentences = [
        part for sentence in split_sentences(section["text"]) for part in split_long_sentence(sentence, target_words)
    ]
    chunks = []
    current: list[str] = []
    current_words = 0

    def keep_overlap() -> None:
        nonlocal current, current_words
        current = current[-overlap_sentences:] if overlap_sentences else []
        current_words = sum(count_words(sentence) for sentence in current)

    def emit() -> None:
        nonlocal current_words
        if not current:
            return
        chunk_text = clean_text(" ".join(current))
        word_count = count_words(chunk_text)
        if word_count < min_chunk_words or (skip_table_like_chunks and is_table_like_text(chunk_text)):
            keep_overlap()
            return
        chunk_index = len(chunks)
        digest = hashlib.sha1(
            f"{article_file.name}:{section_index}:{section['title']}:{chunk_index}".encode()
        ).hexdigest()[:12]
        chunks.append(
            {
                "id": f"{article_file.stem}_{digest}",
                "text": chunk_text,
                "metadata": {
                    "fonte": article_file.name,
                    "article_title": title,
                    "section_index": section_index,
                    "section": section["title"],
                    "heading_level": section["heading_level"],
                    "chunk_index": chunk_index,
                    "word_count": word_count,
                    "chunking": "word_sentence_overlap",
                },
            }
        )
        keep_overlap()

    for sentence in sentences:
        sentence_words = count_words(sentence)
        if current and current_words + sentence_words > target_words:
            emit()
        current.append(sentence)
        current_words += sentence_words

    emit()
    return chunks


def chunk_article(
    article_file: Path,
    target_words: int = TARGET_WORDS,
    overlap_sentences: int = OVERLAP_SENTENCES,
    min_chunk_words: int = MIN_CHUNK_WORDS,
    skip_low_value_sections: bool = True,
    skip_table_like_chunks: bool = True,
) -> list[dict[str, Any]]:
    text = article_file.read_text(encoding="utf-8")
    title = article_title(text, article_file.stem)
    chunks = []
    for section_index, section in enumerate(split_sections(text)):
        if skip_low_value_sections and is_low_value_section(section["title"]):
            continue
        chunks.extend(
            chunk_section(
                section=section,
                section_index=section_index,
                article_file=article_file,
                title=title,
                target_words=target_words,
                overlap_sentences=overlap_sentences,
                min_chunk_words=min_chunk_words,
                skip_table_like_chunks=skip_table_like_chunks,
            )
        )
    return chunks


def iter_chunks(
    articles_dir: Path = ARTICLES_DIR,
    target_words: int = TARGET_WORDS,
    overlap_sentences: int = OVERLAP_SENTENCES,
    min_chunk_words: int = MIN_CHUNK_WORDS,
    limit_articles: int | None = LIMIT_ARTICLES,
    progress_interval: int = PROGRESS_INTERVAL,
    skip_low_value_sections: bool = SKIP_LOW_VALUE_SECTIONS,
    skip_table_like_chunks: bool = SKIP_TABLE_LIKE_CHUNKS,
) -> list[dict[str, Any]]:
    article_files = sorted(articles_dir.glob("*.md"))
    if limit_articles is not None:
        article_files = article_files[:limit_articles]

    chunks = []
    for index, article_file in enumerate(article_files, start=1):
        article_chunks = chunk_article(
            article_file=article_file,
            target_words=target_words,
            overlap_sentences=overlap_sentences,
            min_chunk_words=min_chunk_words,
            skip_low_value_sections=skip_low_value_sections,
            skip_table_like_chunks=skip_table_like_chunks,
        )
        if index == 1 or index == len(article_files) or index % progress_interval == 0:
            print(f"{index}/{len(article_files)} artigos; {len(chunks) + len(article_chunks)} chunks")
        chunks.extend(article_chunks)
    return chunks
