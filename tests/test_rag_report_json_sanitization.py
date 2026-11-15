"""Keep missing gene labels and non-finite CSV values out of RAG reports."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from backend.pipeline_rag.retrieval import load_prioritized_genes  # noqa: E402
from backend.pipeline_rag.run import write_json  # noqa: E402
from backend.scripts.generate_rag_html import _json_safe  # noqa: E402


class RagReportJsonTest(unittest.TestCase):
    def test_missing_primary_name_uses_gene_id(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            path = Path(temp) / "genes.csv"
            path.write_text("gene_id,primary_name,selected_for_search\nGENE1,,True\n", encoding="utf-8")
            genes = load_prioritized_genes(path)
            self.assertEqual(genes.iloc[0]["primary_name"], "GENE1")

    def test_nested_nonfinite_values_become_json_null(self):
        value = _json_safe({"records": [{"name": float("nan"),
                                          "score": float("inf")}], "valid": 0.5})
        self.assertIsNone(value["records"][0]["name"])
        self.assertIsNone(value["records"][0]["score"])
        self.assertIn('"name": null', json.dumps(value, allow_nan=False))

    def test_rag_checkpoint_is_strict_json(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            path = Path(temp) / "checkpoint.json"
            write_json([{"gene_id": "GENE1", "primary_name": float("nan")}], path)
            result = json.loads(path.read_text(encoding="utf-8"),
                                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            self.assertIsNone(result[0]["primary_name"])


if __name__ == "__main__":
    unittest.main()
