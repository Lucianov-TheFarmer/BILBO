"""The main terminal must show progress even after the configuration dialog closes."""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from frontend.procedures import pipeline_monitor  # noqa: E402


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url, **_kwargs):
        if url.endswith("/pipeline/runs"):
            return _Response([{"id": "run-1", "status": "RUNNING", "config": {"name": "Test"},
                              "steps": [{"id": "step-1", "stage": "qc_raw", "sample": "A1",
                                         "status": "RUNNING", "job_id": "job-1"}]}])
        if url.endswith("/jobs?stage=llm"):
            return _Response([])
        return _Response({"job_id": "job-1", "result": {"progress_percent": 42,
                           "progress_message": "A1_1.fastq.gz: 42%"}})


class _HistoryOnlyClient(_Client):
    async def get(self, url, **_kwargs):
        if url.endswith("/pipeline/runs"):
            return _Response([{"id": "old", "status": "COMPLETED",
                               "config": {"name": "Previous session"}, "steps": []}])
        if url.endswith("/jobs?stage=llm"):
            return _Response([])
        raise AssertionError(url)


class _ActiveLlmClient(_HistoryOnlyClient):
    async def get(self, url, **_kwargs):
        if url.endswith("/jobs?stage=llm"):
            return _Response([{"job_id": "llm-1", "status": "RUNNING"}])
        if url.endswith("/jobs/llm-1"):
            return _Response({"job_id": "llm-1", "status": "RUNNING",
                              "result": {"progress_source": "rag_checkpoint",
                                         "progress_done": 6, "progress_total": 53,
                                         "progress_percent": 11.3}})
        return await super().get(url)


class _FinishedLlmClient(_HistoryOnlyClient):
    async def get(self, url, **_kwargs):
        if url.endswith("/jobs?stage=llm"):
            return _Response([{"job_id": "llm-old", "status": "COMPLETED"}])
        return await super().get(url)


class PipelineMonitorTest(unittest.IsolatedAsyncioTestCase):
    async def _one_poll(self, client):
        terminal = ft.Container(content=ft.ListView(controls=[]), visible=True)
        page = SimpleNamespace(container_terminal=terminal,
                               session={"lang": "pt"}, update=lambda: None)
        refreshes = []

        async def stop_after_first_update(_seconds):
            raise asyncio.CancelledError()

        async def refresh_tables():
            refreshes.append(True)

        with patch.object(pipeline_monitor.httpx, "AsyncClient", return_value=client), \
             patch.object(pipeline_monitor.asyncio, "sleep", stop_after_first_update):
            with self.assertRaises(asyncio.CancelledError):
                await pipeline_monitor.monitor_pipeline(page, "token", terminal, refresh_tables)
        return terminal, refreshes

    async def test_completed_run_from_previous_session_stays_out_of_terminal(self):
        terminal, _ = await self._one_poll(_HistoryOnlyClient())
        self.assertFalse(terminal.content.controls[0].visible)
        self.assertTrue(terminal.visible)

    async def test_running_llm_reappears_after_login(self):
        terminal, refreshes = await self._one_poll(_ActiveLlmClient())
        self.assertTrue(terminal.content.controls[1].visible)
        self.assertIn("6/53", terminal.content.controls[1].content.controls[2].value)
        self.assertAlmostEqual(.113, terminal.content.controls[1].content.controls[1].value)
        self.assertEqual([True], refreshes)

    async def test_finished_llm_refreshes_tables_without_reopening_terminal_card(self):
        terminal, refreshes = await self._one_poll(_FinishedLlmClient())
        self.assertFalse(terminal.content.controls[1].visible)
        self.assertEqual([True], refreshes)

    async def test_running_job_appears_in_terminal(self):
        terminal = ft.Container(content=ft.ListView(controls=[]))
        page = SimpleNamespace(container_terminal=terminal,
                               session={"lang": "pt"}, update=lambda: None)
        refreshes = []

        async def refresh_tables():
            refreshes.append(True)

        async def stop_after_first_update(_seconds):
            raise asyncio.CancelledError()

        with patch.object(pipeline_monitor.httpx, "AsyncClient", return_value=_Client()), \
             patch.object(pipeline_monitor.asyncio, "sleep", stop_after_first_update):
            with self.assertRaises(asyncio.CancelledError):
                await pipeline_monitor.monitor_pipeline(page, "token", terminal, refresh_tables)

        card = terminal.content.controls[0]
        self.assertTrue(card.visible)
        self.assertIn("Test", card.content.controls[0].value)
        self.assertIn("42%", card.content.controls[3].controls[0].value)
        self.assertEqual([True], refreshes)


if __name__ == "__main__":
    unittest.main()
