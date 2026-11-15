"""Pipeline DEG sheets can be opened from the differential analysis stage."""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from frontend.procedures import deg  # noqa: E402


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, *_args, **_kwargs):
        return SimpleNamespace(status_code=200, json=lambda: {
            "sheets": ["Control_vs_Drought"], "run_id": "run123", "run_name": "Test pipeline"})


class PipelineDEGUITest(unittest.TestCase):
    def test_pipeline_sheet_has_viewers_without_manual_delete(self):
        asyncio.run(self._check_view())

    async def _check_view(self):
        page = SimpleNamespace(session={"lang": "pt"}, update=lambda: None)
        container = SimpleNamespace(content=ft.ListView(controls=[]))
        with patch.object(deg.httpx, "AsyncClient", return_value=_Client()), \
             patch.object(deg, "show_sheet_as_table", new_callable=AsyncMock) as show_table, \
             patch.object(deg, "show_deg_dropdown", new_callable=AsyncMock) as show_figures:
            await deg.show_deg_results(page, "token", 3, container, run_id="run123")
            column = container.content.controls[0]
            self.assertIn("Test pipeline", column.controls[0].value)
            table = column.controls[1].controls[0].content
            buttons = table.rows[0].cells[2].content.controls
            await buttons[0].on_click(None)
            await buttons[1].on_click(None)
            self.assertEqual(1, len(column.controls[3].controls))
        self.assertEqual("run123", show_table.await_args.args[-1])
        self.assertEqual("run123", show_figures.await_args.kwargs["run_id"])


if __name__ == "__main__":
    unittest.main()
