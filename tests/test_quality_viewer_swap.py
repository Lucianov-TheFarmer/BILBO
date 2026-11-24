"""The FastQC selector replaces its figure without changing the layout."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from frontend.procedures.viewer import create_dropdown_menu  # noqa: E402


class QualityViewerSwapTest(unittest.IsolatedAsyncioTestCase):
    async def test_dropdown_replaces_the_figure_in_its_placeholder(self):
        page = SimpleNamespace(update=lambda: None)
        initial = ft.Text("initial")
        placeholder = ft.Container(content=initial)
        dropdown_menu = create_dropdown_menu(page, "token", "sample.html", 1, "quality",
                                             placeholder)
        dropdown = dropdown_menu.content.controls[0].controls[0]
        layout = ft.Column([dropdown_menu, placeholder])
        replacement = ft.Text("replacement")
        with patch("frontend.procedures.viewer.display_graph", new_callable=AsyncMock,
                   return_value=replacement):
            dropdown.value = "Sequence Length Distribution"
            await dropdown.on_change(SimpleNamespace(control=dropdown))
        self.assertIs(placeholder.content, replacement)
        self.assertEqual(2, len(layout.controls))


if __name__ == "__main__":
    unittest.main()
