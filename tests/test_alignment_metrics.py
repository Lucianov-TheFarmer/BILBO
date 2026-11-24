"""STAR mapping counts remain available for both manual and pipeline alignments."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from frontend.procedures.alignment_metrics import parse_star_final_log  # noqa: E402
from frontend.procedures.alignment import create_tabela_alinhamento, update_tabela_alinhamento  # noqa: E402
from frontend.procedures.viewer import view_alignment_metrics  # noqa: E402


STAR_LOG = """
 Number of input reads | 1000
 Uniquely mapped reads number | 400
 Number of reads mapped to multiple loci | 300
 Number of reads mapped to too many loci | 100
 Number of reads unmapped: too many mismatches | 20
 Number of reads unmapped: too short | 80
 Number of reads unmapped: other | 100
 Number of splices: Total | 25
 Mismatch rate per base, % | 0.47%
"""


class AlignmentMetricsTest(unittest.IsolatedAsyncioTestCase):
    def test_star_categories_are_exclusive(self):
        metrics = parse_star_final_log(STAR_LOG)
        self.assertEqual(700, metrics["mapped_reads"])
        self.assertEqual(200, metrics["unmapped_reads"])
        self.assertEqual(1000, metrics["mapped_reads"] + metrics["too_many_loci"] +
                         metrics["unmapped_reads"])
        self.assertEqual(0.47, metrics["mismatch_rate"])

    def test_incomplete_log_has_no_misleading_summary(self):
        with self.assertRaises(ValueError):
            parse_star_final_log("Number of input reads | 1000")

    async def test_result_opens_in_preview_with_close_button(self):
        preview = ft.Container(content=ft.Column([ft.Text("previous")]))
        page = SimpleNamespace(container_preview=preview,
                               session={"lang": "en"}, update=lambda: None)
        with patch.object(Path, "read_text", return_value=STAR_LOG):
            await view_alignment_metrics(page, "sample.bam", 7)
        column = preview.content.controls[0].content
        self.assertEqual(2, len(column.controls))
        self.assertIn("Alignment results", column.controls[0].controls[0].value)
        self.assertIsInstance(column.controls[0].controls[1], ft.IconButton)
        labels = [item.value for item in column.controls[1].controls if isinstance(item, ft.Text)]
        self.assertTrue(any("700" in label and "70.00%" in label for label in labels))

    async def test_completed_alignment_shows_result_icon_beside_log(self):
        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def get(self, *_args, **_kwargs):
                return SimpleNamespace(status_code=200, json=lambda: [{
                    "name": "sample.bam", "size": "2 GB", "status": "COMPLETED"}])

        page = SimpleNamespace(session={"lang": "en"}, update=lambda: None)
        table = create_tabela_alinhamento(page, "token")
        with patch("frontend.procedures.alignment.httpx.AsyncClient", return_value=Client()):
            await update_tabela_alinhamento(page, "token", 7)
        actions = table.rows[0].cells[3].content.controls
        self.assertEqual(2, len(actions))
        self.assertEqual("View log", actions[0].tooltip)
        self.assertEqual("View alignment results", actions[1].tooltip)
        self.assertFalse(actions[1].disabled)


if __name__ == "__main__":
    unittest.main()
