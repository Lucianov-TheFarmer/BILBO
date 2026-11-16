"""Deleting the last DEG sheet must replace the stale results table."""

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
        return SimpleNamespace(status_code=200, json=lambda: {"sheets": ["Control_vs_Drought"]})

    async def request(self, method, *_args, **_kwargs):
        assert method == "DELETE"
        return SimpleNamespace(status_code=200, json=lambda: {
            "deleted_sheets": ["Control_vs_Drought"],
            "remaining_sheets": {"DEG.xlsx": [], "DEG_full.xlsx": []},
        })


class DEGDeleteUITest(unittest.TestCase):
    def test_last_sheet_disappears_and_count_refreshes(self):
        asyncio.run(self._check_last_sheet_deletion())

    async def _check_last_sheet_deletion(self):
        dialogs = []
        page = SimpleNamespace(session={"lang": "pt"}, open=dialogs.append,
                               update=lambda: None)
        container = SimpleNamespace(content=ft.ListView(controls=[]))
        refresh = AsyncMock()
        with patch.object(deg.httpx, "AsyncClient", return_value=_Client()), \
             patch.object(deg, "log_message", new_callable=AsyncMock):
            await deg.show_deg_results(page, "token", 3, container, refresh)
            column = container.content.controls[0]
            table = column.controls[0].controls[0].content
            table.rows[0].cells[1].content.value = True
            await column.controls[2].controls[1].content.on_click(None)
            self.assertEqual(1, len(dialogs))
            await dialogs[0].actions[1].on_click(None)

        self.assertFalse(dialogs[0].open)
        self.assertIsInstance(container.content.controls[0].content, ft.Text)
        refresh.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
