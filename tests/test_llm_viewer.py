"""The LLM report preview loads incrementally and can be closed."""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from frontend.procedures import llm  # noqa: E402


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url, **_kwargs):
        if url.endswith("/llm/rag/status"):
            result = {"ready": True, "state": "ready"}
        elif url.endswith("/llm/contrasts"):
            result = {"contrasts": [{"sheet": "Control_vs_Drought", "files": ["report.md"]}]}
        elif url.endswith("/samples/stages/10"):
            result = [{"name": "Control_vs_Drought", "status": "COMPLETED"}]
        elif "report.md" in url:
            return SimpleNamespace(status_code=200, text="".join(
                "## Section {}\n\n{}\n\n".format(index, "text " * 1200)
                for index in range(6)
            ))
        else:
            raise AssertionError(url)
        return SimpleNamespace(status_code=200, json=lambda: result)


class LLMViewerTest(unittest.TestCase):
    def test_markdown_preview_scroll_and_close(self):
        asyncio.run(self._check_markdown_preview())

    async def _check_markdown_preview(self):
        page = SimpleNamespace(session={"lang": "pt"}, update=lambda: None)
        table_container = SimpleNamespace(content=ft.ListView(controls=[]))
        original_preview = ft.Column(controls=[])
        preview_container = SimpleNamespace(content=original_preview)
        with patch.object(llm.httpx, "AsyncClient", return_value=_Client()):
            await llm.show_llm(page, "token", 3, table_container, preview_container)
            table = table_container.content.controls[1].controls[0]
            view_button = table.rows[0].cells[3].content.controls[1]
            await view_button.on_click(None)

        viewer = preview_container.content.content
        report_list = viewer.controls[1]
        self.assertEqual(3, len(report_list.controls))  # two sections and Load more
        await report_list.on_scroll(SimpleNamespace(pixels=1000, max_scroll_extent=1200))
        self.assertEqual(5, len(report_list.controls))
        await viewer.controls[0].controls[2].on_click(None)
        self.assertIs(preview_container.content, original_preview)


if __name__ == "__main__":
    unittest.main()
