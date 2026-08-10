import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.backend.scripts import llm


class PrototypePipelineOrchestrationTest(unittest.TestCase):
    def test_cluster_interpretation_precedes_prioritization_and_rag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            users_root = Path(temp_dir)
            clustering_dir = users_root / "7" / "clustering" / "Contrast_A"
            features_dir = clustering_dir / "features"
            clusters_dir = clustering_dir / "clusters"
            features_dir.mkdir(parents=True)
            clusters_dir.mkdir(parents=True)
            (features_dir / "genes_filtered.csv").write_text("gene_id\ngene-1\n", encoding="utf-8")
            calls = []

            def fake_cluster_interpretation(_clusters_dir, output_file, **_kwargs):
                calls.append("cluster_interpretation")
                pd.DataFrame(
                    [
                        {
                            "ontology": "BP",
                            "direction": "up",
                            "cluster": 1,
                            "n_genes": 3,
                            "interpretation": "Shared response process.",
                        }
                    ]
                ).to_csv(output_file, index=False)
                return {"output": str(output_file), "interpreted_clusters": 1}

            def fake_prioritization(*args):
                calls.append("prioritization")
                output_file = args[-1]
                frame = pd.DataFrame(
                    [
                        {
                            "rank": 1,
                            "selected_for_search": True,
                            "gene_id": "gene-1",
                            "primary_name": "GENE1",
                            "represented_ontologies": "BP; MF",
                        }
                    ]
                )
                output_file.parent.mkdir(parents=True, exist_ok=True)
                frame.to_csv(output_file, index=False)
                return frame

            def fake_rag(**kwargs):
                calls.append("rag")
                result = [
                    {
                        "gene_id": "gene-1",
                        "primary_name": "GENE1",
                        "interpretation": "Supported interpretation [C1].",
                        "chunks": [
                            {
                                "citation_id": "C1",
                                "source": "paper.md",
                                "section": "Results",
                            }
                        ],
                    }
                ]
                kwargs["output_file"].write_text(json.dumps(result), encoding="utf-8")
                return result

            with (
                patch.object(llm, "_users_root", return_value=users_root),
                patch.object(llm, "run_cluster_interpretation", fake_cluster_interpretation),
                patch.object(llm, "run_prioritization", fake_prioritization),
                patch.object(llm, "run_rag", fake_rag),
            ):
                result = llm.run_llm(
                    sheet_name="Contrast_A",
                    out_dir=str(users_root / "7" / "llm" / "Contrast_A"),
                    user_id=7,
                )

            self.assertEqual(
                ["cluster_interpretation", "prioritization", "rag"],
                calls,
            )
            self.assertEqual(1, result["interpreted_clusters"])
            self.assertEqual(1, result["selected_genes"])
            self.assertEqual(1, result["interpreted_genes"])
            self.assertTrue(Path(result["report"]).exists())
            self.assertTrue(Path(result["json"]).exists())


if __name__ == "__main__":
    unittest.main()
