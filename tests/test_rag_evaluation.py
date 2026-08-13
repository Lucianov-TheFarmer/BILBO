from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.rag_evaluation.annotations import citation_refs, split_claims, write_interpretation_template
from benchmarks.rag_evaluation.evaluate import evaluate_interpretations, evaluate_retrieval
from benchmarks.rag_evaluation.metrics import cohen_kappa, ndcg_at_k, precision_at_k, reciprocal_rank


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class RagEvaluationTest(unittest.TestCase):
    def test_information_retrieval_metrics(self) -> None:
        grades = [2, 0, 1, 0, 0]
        self.assertEqual(0.4, precision_at_k(grades, 5))
        self.assertEqual(1.0, reciprocal_rank(grades))
        self.assertGreater(ndcg_at_k(grades, 5, [2, 1, 0, 0, 0]), 0.9)

    def test_claim_split_and_citations(self) -> None:
        claims = split_claims("Gene A responds to stress [C1]. It is localized in roots [C2, C3].")
        self.assertEqual(2, len(claims))
        self.assertEqual("C2;C3", citation_refs(claims[1]))

    def test_retrieval_evaluation_uses_pooled_qrels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rankings = root / "rankings.csv"
            annotations = root / "annotations.csv"
            write_csv(
                rankings,
                [
                    {"method": "hybrid", "query_id": "q1", "pool_id": "a", "rank": 1, "chunk_id": "a"},
                    {"method": "hybrid", "query_id": "q1", "pool_id": "b", "rank": 2, "chunk_id": "b"},
                ],
            )
            write_csv(
                annotations,
                [
                    {"pool_id": "a", "query_id": "q1", "relevance_grade": 2},
                    {"pool_id": "b", "query_id": "q1", "relevance_grade": 0},
                    {"pool_id": "c", "query_id": "q1", "relevance_grade": 1},
                ],
            )
            result = evaluate_retrieval(rankings, annotations, k=2)
        self.assertEqual(0.5, result["summary"][0]["pooled_recall_at_2"])

    def test_interpretation_template_and_accuracy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rag_json = root / "rag.json"
            template = root / "claims.csv"
            rag_json.write_text(
                json.dumps(
                    [
                        {
                            "gene_id": "g1",
                            "primary_name": "Gene 1",
                            "interpretation": "Gene 1 participates in growth [C1].",
                            "chunks": [{"citation_id": "C1", "source": "paper", "section": "Results", "text": "Evidence"}],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(1, write_interpretation_template(rag_json, template))
            with template.open(encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            rows[0]["annotator_id"] = "expert-1"
            rows[0]["claim_label"] = "supported"
            rows[0]["citations_correct"] = "1"
            write_csv(template, rows)
            result = evaluate_interpretations(template)
        self.assertEqual(1.0, result["claim_accuracy_strict"])
        self.assertEqual(1.0, result["citation_accuracy"])

    def test_structured_claim_template_preserves_evidence_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rag_json = root / "rag.json"
            template = root / "claims.csv"
            rag_json.write_text(
                json.dumps(
                    [
                        {
                            "gene_id": "g1",
                            "primary_name": "Gene 1",
                            "interpretation_status": "supported_claims",
                            "claims": [
                                {
                                    "claim": "A related family participates in growth.",
                                    "citations": ["C1"],
                                    "evidence_level": "family",
                                    "relationship_to_query": "family",
                                    "species": "Arabidopsis thaliana",
                                    "confidence": "medium",
                                }
                            ],
                            "chunks": [{"citation_id": "C1", "source": "paper", "section": "Results", "text": "Evidence"}],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            self.assertEqual(1, write_interpretation_template(rag_json, template))
            with template.open(encoding="utf-8") as stream:
                row = next(csv.DictReader(stream))
        self.assertEqual("C1", row["cited_chunks"])
        self.assertEqual("family", row["evidence_level"])
        self.assertEqual("family", row["relationship_to_query"])

    def test_cohen_kappa(self) -> None:
        self.assertEqual(1.0, cohen_kappa(["a", "b"], ["a", "b"]))


if __name__ == "__main__":
    unittest.main()
