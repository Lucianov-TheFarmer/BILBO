import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.backend.scripts import cluster_interpretation as interpret_clusters


class InterpretClustersTest(unittest.TestCase):
    def test_one_call_per_cluster_with_only_function_and_go(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            clusters_dir = Path(temp_dir) / "clusters"
            output_file = clusters_dir / "interpretations.csv"

            for ontology, go_column in interpret_clusters.ONTOLOGIES.items():
                (clusters_dir / ontology).mkdir(parents=True)
                for filename_prefix in interpret_clusters.DIRECTIONS.values():
                    input_file = clusters_dir / ontology / f"{filename_prefix}_clusters.csv"
                    with input_file.open("w", newline="", encoding="utf-8") as handle:
                        writer = csv.DictWriter(
                            handle,
                            fieldnames=["cluster", "function", go_column],
                        )
                        writer.writeheader()
                        writer.writerow({"cluster": 1, "function": "function", go_column: "go"})
                        writer.writerow({"cluster": -1, "function": "ignored", go_column: "ignored"})

            calls = []

            def fake_call(ontology, evidence, **_kwargs):
                calls.append((ontology, evidence))
                return "Resumo do cluster."

            with (
                patch.object(interpret_clusters, "CLUSTERS_DIR", clusters_dir),
                patch.object(interpret_clusters, "OUTPUT_FILE", output_file),
                patch.object(interpret_clusters, "call_model", fake_call),
            ):
                interpret_clusters.main()
                interpret_clusters.main()

            self.assertEqual(6, len(calls))
            self.assertTrue(all(set(gene) == {"function", "go"} for _, evidence in calls for gene in evidence))

    def test_prompt_focuses_on_each_ontology(self) -> None:
        self.assertIn("biological process", interpret_clusters.build_prompt("BP"))
        self.assertIn("molecular function", interpret_clusters.build_prompt("MF"))
        self.assertIn("cellular localization", interpret_clusters.build_prompt("CC"))


if __name__ == "__main__":
    unittest.main()
