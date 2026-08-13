from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


POLICY_FILE = Path(__file__).resolve().parent / "resources" / "gene_entity_policies.json"
RESOLUTION_FILE = Path(__file__).resolve().parent / "resources" / "gene_entity_resolution.json"
INSUFFICIENT_MESSAGE = "The retrieved literature is insufficient to support a gene-specific interpretation."
EVIDENCE_LEVELS = {"direct", "ortholog", "paralog", "family", "general"}
RELATIONSHIPS = {"same_gene", "ortholog", "paralog", "family", "none", "unknown"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
STRONG_CLAIM_RE = re.compile(
    r"\b(?:critical|crucial|essential|indispensable|major|central|required for|"
    r"demonstrates?|proves?|controls?)\b",
    re.IGNORECASE,
)
CONDITION_PATTERNS = {
    "drought": r"\b(?:drought|water deficit|dehydration)\b",
    "salt": r"\b(?:salt|salinity|nacl)\b",
    "cold": r"\b(?:cold|chilling|freezing)\b",
    "heat": r"\b(?:heat|heat shock|high temperature)\b",
    "pathogen": r"\b(?:pathogen|infection|infected|disease)\b",
    "dark": r"\b(?:dark|dark-induced)\b",
    "light": r"\b(?:light|de-etiolation)\b",
    "ABA": r"\b(?:ABA|abscisic acid)\b",
    "TBM": r"\bTBM\b",
    "IM": r"\bIM\b",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


@lru_cache(maxsize=1)
def load_entity_policies(path: Path = POLICY_FILE) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Entity policy must be a JSON object: {path}")
    return {str(key): value for key, value in loaded.items() if isinstance(value, dict)}


def entity_policy_for_gene(gene: Mapping[str, Any]) -> dict[str, Any]:
    return load_entity_policies().get(str(gene.get("gene_id", "")), {})


@lru_cache(maxsize=1)
def load_entity_resolution(path: Path = RESOLUTION_FILE) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    genes = loaded.get("genes", {}) if isinstance(loaded, dict) else {}
    return {str(key): value for key, value in genes.items() if isinstance(value, dict)}


def entity_resolution_for_gene(gene: Mapping[str, Any]) -> dict[str, Any]:
    return load_entity_resolution().get(str(gene.get("gene_id", "")), {"status": "unresolved"})


def _rule_matches(text: str, rule: Mapping[str, Any]) -> bool:
    lowered = text.lower()
    any_terms = [str(term).lower() for term in rule.get("any", [])]
    all_terms = [str(term).lower() for term in rule.get("all", [])]
    unless_terms = [str(term).lower() for term in rule.get("unless_any", [])]
    positive = (not any_terms or any(term in lowered for term in any_terms)) and (
        not all_terms or all(term in lowered for term in all_terms)
    )
    return positive and not any(term in lowered for term in unless_terms)


def blocked_chunk_reason(gene: Mapping[str, Any], chunk: Mapping[str, Any]) -> str | None:
    policy = entity_policy_for_gene(gene)
    text = " ".join(
        _text(chunk.get(field, ""))
        for field in ("article_title", "section", "text")
    )
    for index, rule in enumerate(policy.get("blocked_chunk_rules", []), start=1):
        if isinstance(rule, dict) and _rule_matches(text, rule):
            return f"entity_policy_rule_{index}"
    for item in policy.get("contextual_aliases", []):
        if not isinstance(item, dict):
            continue
        alias = _text(item.get("alias", "")).lower()
        required = [str(term).lower() for term in item.get("require_any", [])]
        lowered = text.lower()
        if alias and alias in lowered and required and not any(term in lowered for term in required):
            return f"ambiguous_alias_without_context:{alias}"
    return None


def classify_chunk_evidence(
    gene: Mapping[str, Any],
    chunk: Mapping[str, Any],
) -> dict[str, Any]:
    blocked_reason = blocked_chunk_reason(gene, chunk)
    payload = chunk.get("payload_match", {})
    payload = payload if isinstance(payload, dict) else {}
    text = _text(chunk.get("text", "")).lower()
    gene_id = _text(gene.get("gene_id", "")).lower()
    primary_name = _text(gene.get("primary_name", "")).lower()
    resolution = entity_resolution_for_gene(gene)
    stable_ids = [_text(value).lower() for value in resolution.get("stable_ids", []) if _text(value)]
    ortholog_terms = []
    for ortholog in resolution.get("validated_orthologs", []):
        if isinstance(ortholog, dict):
            ortholog_terms.extend(
                _text(value).lower()
                for field in ("stable_ids", "aliases")
                for value in ortholog.get(field, [])
                if _text(value)
            )
    alias_matches = [
        *payload.get("alias_payload_matches", []),
        *payload.get("alias_text_matches", []),
    ]
    exact_id = (bool(gene_id) and gene_id in text) or any(value in text for value in stable_ids)
    ortholog_signal = any(value in text for value in ortholog_terms)
    exact_name = bool(primary_name) and primary_name in text
    name_signal = exact_name or bool(alias_matches)
    family_signal = bool(payload.get("protein_family_matches"))
    process_signal = bool(payload.get("go_matches") or payload.get("context_payload_matches"))
    species = [str(value) for value in chunk.get("species_mentions", []) if _text(value)]
    chunk_text = _text(chunk.get("text", ""))
    conditions = [name for name, pattern in CONDITION_PATTERNS.items() if re.search(pattern, chunk_text, re.IGNORECASE)]
    species_condition_pairs = []
    for sentence in re.split(r"(?<=[.!?;])\s+", chunk_text):
        sentence_species = [value for value in species if _text(value).lower() in sentence.lower()]
        sentence_conditions = [name for name, pattern in CONDITION_PATTERNS.items() if re.search(pattern, sentence, re.IGNORECASE)]
        species_condition_pairs.extend(
            {"species": species_value, "condition": condition}
            for species_value in sentence_species
            for condition in sentence_conditions
        )

    if blocked_reason:
        relationship = "none"
        evidence_level = "general"
    elif exact_id:
        relationship = "same_gene"
        evidence_level = "direct"
    elif ortholog_signal:
        relationship = "ortholog"
        evidence_level = "ortholog"
    elif name_signal:
        # Textual identity is not sufficient to claim validated orthology or the
        # same genomic entity, so keep the relationship explicitly unresolved.
        relationship = "unknown"
        evidence_level = "general"
    elif family_signal:
        relationship = "family"
        evidence_level = "family"
    else:
        relationship = "none"
        evidence_level = "general"

    return {
        "relationship_to_query": relationship,
        "evidence_level": evidence_level,
        "name_signal": name_signal,
        "exact_id_signal": exact_id,
        "ortholog_signal": ortholog_signal,
        "family_signal": family_signal,
        "process_signal": process_signal,
        "species": species,
        "conditions": conditions,
        "species_condition_pairs": species_condition_pairs,
        "blocked": bool(blocked_reason),
        "blocked_reason": blocked_reason or "",
    }


def annotate_chunks_for_generation(
    gene: Mapping[str, Any], chunks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    annotated = []
    for chunk in chunks:
        item = dict(chunk)
        item["evidence_assessment"] = classify_chunk_evidence(gene, chunk)
        annotated.append(item)
    return annotated


def _citations(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates = re.findall(r"C\d+", value)
    elif isinstance(value, list):
        candidates = [str(item).strip() for item in value]
    else:
        candidates = []
    return list(dict.fromkeys(ref for ref in candidates if re.fullmatch(r"C\d+", ref)))


def _normalize_claim(raw: Mapping[str, Any]) -> dict[str, Any]:
    evidence_level = _text(raw.get("evidence_level", "general")).lower()
    relationship = _text(raw.get("relationship_to_query", "unknown")).lower()
    confidence = _text(raw.get("confidence", "low")).lower()
    return {
        "claim": _text(raw.get("claim", "")),
        "citations": _citations(raw.get("citations", [])),
        "evidence_level": evidence_level if evidence_level in EVIDENCE_LEVELS else "general",
        "relationship_to_query": relationship if relationship in RELATIONSHIPS else "unknown",
        "species": _text(raw.get("species", "")),
        "conditions": [
            _text(value) for value in raw.get("conditions", []) if _text(value)
        ] if isinstance(raw.get("conditions", []), list) else [],
        "evidence_method": raw.get("evidence_method", []) if isinstance(raw.get("evidence_method", []), list) else [],
        "confidence": confidence if confidence in CONFIDENCE_LEVELS else "low",
    }


def validate_atomic_claims(
    claims: Any,
    chunks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chunk_by_ref = {str(chunk.get("citation_id", "")): chunk for chunk in chunks}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    raw_claims = claims if isinstance(claims, list) else []

    for index, raw in enumerate(raw_claims, start=1):
        if not isinstance(raw, dict):
            rejected.append({"claim_index": index, "reason": "claim_not_object"})
            continue
        claim = _normalize_claim(raw)
        reasons = []
        if not claim["claim"]:
            reasons.append("empty_claim")
        if not claim["citations"]:
            reasons.append("missing_citation")
        cited_chunks = [chunk_by_ref.get(ref) for ref in claim["citations"]]
        if any(chunk is None for chunk in cited_chunks):
            reasons.append("unknown_citation")
        assessments = [
            chunk.get("evidence_assessment", {})
            for chunk in cited_chunks
            if isinstance(chunk, dict)
        ]
        if any(assessment.get("blocked") for assessment in assessments):
            reasons.append("blocked_entity_evidence")
        if claim["relationship_to_query"] == "same_gene" and not any(
            assessment.get("relationship_to_query") == "same_gene" for assessment in assessments
        ):
            reasons.append("unverified_same_gene_attribution")
        if claim["evidence_level"] == "direct" and not any(
            assessment.get("evidence_level") == "direct" for assessment in assessments
        ):
            reasons.append("unverified_direct_evidence")
        if claim["relationship_to_query"] in {"ortholog", "paralog"} and not any(
            assessment.get("relationship_to_query") == claim["relationship_to_query"]
            for assessment in assessments
        ):
            reasons.append(f"unverified_{claim['relationship_to_query']}_attribution")
        if claim["relationship_to_query"] == "family" and not any(
            assessment.get("relationship_to_query") == "family"
            or assessment.get("family_signal")
            or assessment.get("name_signal")
            for assessment in assessments
        ):
            reasons.append("unverified_family_attribution")
        indirect_gene_attribution = re.search(
            r"\b(?:the|this|query) gene(?:'s)?\b|\bits function\b",
            claim["claim"],
            re.IGNORECASE,
        )
        if claim["relationship_to_query"] in {"family", "none"} and indirect_gene_attribution:
            reasons.append("indirect_evidence_attributed_to_query_gene")
        if claim["evidence_level"] in {"ortholog", "paralog", "family"} and not any(
            assessment.get("evidence_level") == claim["evidence_level"]
            for assessment in assessments
        ):
            reasons.append(f"unverified_{claim['evidence_level']}_evidence")
        if claim["relationship_to_query"] in {"same_gene", "unknown"} and assessments and all(
            assessment.get("relationship_to_query") in {"family", "none"} for assessment in assessments
        ):
            reasons.append("family_or_context_used_as_gene_specific")
        if STRONG_CLAIM_RE.search(claim["claim"]) and claim["evidence_level"] not in {"direct"}:
            reasons.append("unsupported_claim_strength")
        supported_conditions = {
            condition.lower()
            for assessment in assessments
            for condition in assessment.get("conditions", [])
        }
        for condition in claim["conditions"]:
            if condition.lower() not in supported_conditions:
                reasons.append(f"unsupported_condition:{condition}")
        # A condition explicitly written in the claim must also occur in at
        # least one cited chunk, even if the model omitted the conditions field.
        for name, pattern in CONDITION_PATTERNS.items():
            if re.search(pattern, claim["claim"], re.IGNORECASE) and name.lower() not in supported_conditions:
                reasons.append(f"unsupported_condition_in_text:{name}")
        if claim["species"] and claim["conditions"]:
            pairs = [
                pair
                for assessment in assessments
                for pair in assessment.get("species_condition_pairs", [])
            ]
            for condition in claim["conditions"]:
                if not any(
                    claim["species"].lower() in _text(pair.get("species", "")).lower()
                    or _text(pair.get("species", "")).lower() in claim["species"].lower()
                    for pair in pairs
                    if _text(pair.get("condition", "")).lower() == condition.lower()
                ):
                    reasons.append(f"unverified_species_condition_pair:{claim['species']}:{condition}")

        if reasons:
            rejected.append({"claim_index": index, "claim": claim["claim"], "reasons": reasons})
        else:
            accepted.append(claim)
    return accepted, rejected


def render_claims(claims: list[dict[str, Any]]) -> str:
    return " ".join(
        f"{claim['claim']} [{', '.join(claim['citations'])}]"
        for claim in claims
    ).strip()
