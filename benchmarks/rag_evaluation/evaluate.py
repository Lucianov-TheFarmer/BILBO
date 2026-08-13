from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .annotations import CLAIM_LABELS
from .metrics import (
    bootstrap_mean_ci,
    mean,
    ndcg_at_k,
    pairwise_kappas,
    pooled_recall_at_k,
    precision_at_k,
    reciprocal_rank,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    # Spreadsheet applications commonly add an UTF-8 BOM when exporting CSV.
    # utf-8-sig transparently accepts files both with and without that marker.
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def evaluate_retrieval(rankings_csv: Path, annotations_csv: Path, *, k: int = 10) -> dict[str, Any]:
    annotations = read_csv(annotations_csv)
    missing = [row["pool_id"] for row in annotations if row.get("relevance_grade", "").strip() not in {"0", "1", "2"}]
    if missing:
        raise ValueError(f"Missing/invalid relevance_grade for {len(missing)} pooled documents")
    grades = {row["pool_id"]: int(row["relevance_grade"]) for row in annotations}
    pool_grades_by_query: dict[str, list[int]] = defaultdict(list)
    relevant_by_query: Counter[str] = Counter()
    for row in annotations:
        pool_grades_by_query[row["query_id"]].append(int(row["relevance_grade"]))
        if int(row["relevance_grade"]) >= 1:
            relevant_by_query[row["query_id"]] += 1

    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(rankings_csv):
        grouped[(row["method"], row["query_id"])].append(row)

    per_query = []
    for (method, query_id), rows in sorted(grouped.items()):
        rows.sort(key=lambda row: int(row["rank"]))
        ranked_grades = [grades[row["pool_id"]] for row in rows]
        per_query.append(
            {
                "method": method,
                "query_id": query_id,
                "precision_at_5": precision_at_k(ranked_grades, 5),
                f"ndcg_at_{k}": ndcg_at_k(ranked_grades, k, pool_grades_by_query[query_id]),
                "mrr_direct": reciprocal_rank(ranked_grades, relevant_grade=2),
                f"pooled_recall_at_{k}": pooled_recall_at_k(
                    ranked_grades, relevant_by_query[query_id], k
                ),
            }
        )

    summary = []
    methods = sorted({row["method"] for row in per_query})
    metric_names = ["precision_at_5", f"ndcg_at_{k}", "mrr_direct", f"pooled_recall_at_{k}"]
    for method in methods:
        method_rows = [row for row in per_query if row["method"] == method]
        item: dict[str, Any] = {"method": method, "queries": len(method_rows)}
        for metric in metric_names:
            values = [float(row[metric]) for row in method_rows]
            low, high = bootstrap_mean_ci(values)
            item[metric] = mean(values)
            item[f"{metric}_ci95_low"] = low
            item[f"{metric}_ci95_high"] = high
        summary.append(item)
    return {"protocol": {"grades": {"0": "irrelevant", "1": "indirect", "2": "direct"}, "k": k}, "summary": summary, "per_query": per_query}


def evaluate_interpretations(annotations_csv: Path, rag_json: Path | None = None) -> dict[str, Any]:
    rows = read_csv(annotations_csv)
    completed = [row for row in rows if row.get("claim_label", "").strip()]
    invalid = [row for row in completed if row["claim_label"].strip().lower() not in CLAIM_LABELS]
    if invalid:
        raise ValueError(f"Invalid claim_label in {len(invalid)} rows")
    if not completed:
        raise ValueError("No annotated claims found")
    normalized = [{**row, "claim_label": row["claim_label"].strip().lower()} for row in completed]
    counts = Counter(row["claim_label"] for row in normalized)
    citation_rows = [row for row in normalized if row.get("citations_correct", "").strip() in {"0", "1"}]
    accuracy_by_annotator = {}
    for annotator in sorted({row["annotator_id"] for row in normalized}):
        annotator_rows = [row for row in normalized if row["annotator_id"] == annotator]
        accuracy_by_annotator[annotator] = mean(row["claim_label"] == "supported" for row in annotator_rows)
    result = {
        "annotated_claims": len(normalized),
        "unique_claims": len({row["claim_id"] for row in normalized}),
        "claim_accuracy_strict": counts["supported"] / len(normalized),
        "claim_accuracy_strict_by_annotator": accuracy_by_annotator,
        "label_counts": dict(counts),
        "label_proportions": {label: counts[label] / len(normalized) for label in CLAIM_LABELS},
        "citation_accuracy": mean(int(row["citations_correct"]) for row in citation_rows) if citation_rows else None,
        "pairwise_cohen_kappa": pairwise_kappas(
            normalized, item_key="claim_id", annotator_key="annotator_id", label_key="claim_label"
        ),
    }
    if rag_json is not None:
        rag_results = json.loads(rag_json.read_text(encoding="utf-8"))
        if not isinstance(rag_results, list):
            raise ValueError("RAG JSON must contain a list of gene results")
        total_genes = len(rag_results)
        abstained_genes = sum(
            item.get("interpretation_status") == "insufficient_evidence"
            for item in rag_results
            if isinstance(item, dict)
        )
        generated_claims = sum(
            len(item.get("claims", []))
            for item in rag_results
            if isinstance(item, dict) and isinstance(item.get("claims", []), list)
        )
        rejected_claims = sum(
            len(item.get("rejected_claims", []))
            for item in rag_results
            if isinstance(item, dict) and isinstance(item.get("rejected_claims", []), list)
        )
        result["generation"] = {
            "total_genes": total_genes,
            "answered_genes": total_genes - abstained_genes,
            "abstained_genes": abstained_genes,
            "answer_coverage": (total_genes - abstained_genes) / total_genes if total_genes else None,
            "abstention_rate": abstained_genes / total_genes if total_genes else None,
            "accepted_claims": generated_claims,
            "deterministically_rejected_claims": rejected_claims,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate BILBO expert-evaluation metrics.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    retrieval = subparsers.add_parser("retrieval")
    retrieval.add_argument("--rankings", type=Path, required=True)
    retrieval.add_argument("--annotations", type=Path, required=True)
    retrieval.add_argument("--output", type=Path, required=True)
    retrieval.add_argument("--k", type=int, default=10)
    interpretations = subparsers.add_parser("interpretations")
    interpretations.add_argument("--annotations", type=Path, required=True)
    interpretations.add_argument("--output", type=Path, required=True)
    interpretations.add_argument("--rag-json", type=Path)
    args = parser.parse_args()
    result = (
        evaluate_retrieval(args.rankings, args.annotations, k=args.k)
        if args.command == "retrieval"
        else evaluate_interpretations(args.annotations, args.rag_json)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
