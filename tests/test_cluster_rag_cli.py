from __future__ import annotations

from argparse import Namespace
from pathlib import Path
import tempfile
import unittest

from app.backend.scripts import cluster_rag_cli


class ClusterRagCliTest(unittest.TestCase):
    def test_safe_name_normalizes_external_labels(self) -> None:
        self.assertEqual(
            "Treatment_A_Control",
            cluster_rag_cli.safe_name("Treatment A / Control", field="sheet"),
        )

    def test_safe_name_rejects_empty_labels(self) -> None:
        with self.assertRaisesRegex(ValueError, "sheet"):
            cluster_rag_cli.safe_name(" / ", field="sheet")

    def test_run_rejects_missing_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = Namespace(
                deg_xlsx=str(root / "missing.xlsx"),
                sheet="contrast",
                output_dir=str(root / "output"),
                run_id="test",
                skip_rag=False,
            )

            with self.assertRaisesRegex(FileNotFoundError, "DEG workbook"):
                cluster_rag_cli.run(args)


if __name__ == "__main__":
    unittest.main()
