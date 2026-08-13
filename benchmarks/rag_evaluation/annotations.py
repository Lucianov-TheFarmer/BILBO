from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any


CLAIM_LABELS = ("supported", "partially_supported", "unsupported", "contradicted")


def stable_id(*parts: str) -> str:
    content = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def split_claims(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text)).strip()
    if not normalized:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z])", normalized) if part.strip()]


def citation_refs(text: str) -> str:
    refs = []
    for group in re.findall(r"\[([^]]*C\d+[^]]*)\]", str(text)):
        refs.extend(re.findall(r"C\d+", group))
    return ";".join(dict.fromkeys(refs))


def write_interpretation_template(rag_json: Path, output_csv: Path) -> int:
    results = json.loads(rag_json.read_text(encoding="utf-8"))
    rows = []
    for result in results:
        gene_id = str(result.get("gene_id", ""))
        chunks = result.get("chunks", [])
        evidence = "\n\n".join(
            f"[{chunk.get('citation_id', '')}] {chunk.get('source', '')} — {chunk.get('section', '')}\n{chunk.get('text', '')}"
            for chunk in chunks
        )
        structured_claims = result.get("claims", [])
        if isinstance(structured_claims, list) and structured_claims:
            claims = [item for item in structured_claims if isinstance(item, dict)]
        else:
            claims = [
                {
                    "claim": claim,
                    "citations": citation_refs(claim).split(";") if citation_refs(claim) else [],
                    "evidence_level": "",
                    "relationship_to_query": "",
                    "species": "",
                    "confidence": "",
                }
                for claim in split_claims(result.get("interpretation", ""))
                if claim != "The retrieved literature is insufficient to support a gene-specific interpretation."
            ]
        for claim_index, claim_item in enumerate(claims, start=1):
            claim = str(claim_item.get("claim", "")).strip()
            citations = claim_item.get("citations", [])
            cited_chunks = ";".join(str(ref) for ref in citations) if isinstance(citations, list) else citation_refs(str(citations))
            rows.append(
                {
                    "claim_id": stable_id(gene_id, str(claim_index), claim),
                    "gene_id": gene_id,
                    "primary_name": result.get("primary_name", ""),
                    "claim_index": claim_index,
                    "claim": claim,
                    "cited_chunks": cited_chunks,
                    "interpretation_status": result.get("interpretation_status", ""),
                    "evidence_level": claim_item.get("evidence_level", ""),
                    "relationship_to_query": claim_item.get("relationship_to_query", ""),
                    "evidence_species": claim_item.get("species", ""),
                    "evidence_conditions": ";".join(claim_item.get("conditions", [])) if isinstance(claim_item.get("conditions", []), list) else "",
                    "model_confidence": claim_item.get("confidence", ""),
                    "retrieved_evidence": evidence,
                    "annotator_id": "",
                    "claim_label": "",
                    "citations_correct": "",
                    "expert_correction": "",
                    "notes": "",
                }
            )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else [
        "claim_id", "gene_id", "primary_name", "claim_index", "claim", "cited_chunks",
        "interpretation_status", "evidence_level", "relationship_to_query", "evidence_species", "evidence_conditions", "model_confidence",
        "retrieved_evidence", "annotator_id", "claim_label", "citations_correct", "expert_correction", "notes",
    ]
    with output_csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Create a claim-level expert annotation sheet from BILBO RAG JSON.")
    parser.add_argument("--rag-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count = write_interpretation_template(args.rag_json, args.output)
    print(f"Wrote {count} claims to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
