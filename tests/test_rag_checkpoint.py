from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.backend.pipeline_rag import run as rag


class RagCheckpointTest(unittest.TestCase):
    def test_write_json_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rag.json"
            rag.write_json([{"gene_id": "g1"}], output)

            self.assertEqual([{"gene_id": "g1"}], json.loads(output.read_text(encoding="utf-8")))
            self.assertFalse(output.with_suffix(".json.tmp").exists())

    def test_run_rag_resumes_after_completed_gene_and_checkpoints_next(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            genes_file = root / "genes.csv"
            output = root / "rag.json"
            pd.DataFrame(
                {
                    "rank": [1, 2],
                    "selected_for_search": [True, True],
                    "gene_id": ["g1", "g2"],
                    "primary_name": ["Gene 1", "Gene 2"],
                    "search_query": ["query 1", "query 2"],
                    "represented_clusters": ["", ""],
                }
            ).to_csv(genes_file, index=False)
            rag.write_json([{"gene_id": "g1", "interpretation": "done"}], output)

            def fake_analyze(genes, *args, **kwargs):
                self.assertEqual(["g2"], genes["gene_id"].tolist())
                partial = [{"gene_id": "g2", "interpretation": "new"}]
                kwargs["on_result"](partial)
                return partial

            with patch.object(rag, "load_collection", return_value={}), patch.object(
                rag, "load_cluster_interpretations", return_value={}
            ), patch.object(rag, "analyze_genes", side_effect=fake_analyze):
                results = rag.run_rag(
                    input_file=genes_file,
                    output_file=output,
                    interpretations_file=root / "interpretations.csv",
                    qdrant_url="http://qdrant",
                    collection_name="test",
                    bm25_metadata_path=root / "bm25.json",
                    resume=True,
                )

            self.assertEqual(["g1", "g2"], [item["gene_id"] for item in results])
            self.assertEqual(results, json.loads(output.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
