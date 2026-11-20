"""The main terminal must show progress even after the configuration dialog closes."""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from frontend.procedures import pipeline_monitor, utils  # noqa: E402


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


class _DegClient(_Client):
    async def get(self, url, **_kwargs):
        if url.endswith("/pipeline/runs"):
            return _Response([{"id": "run-deg", "status": "RUNNING",
                               "config": {"name": "DEG test", "design": {"contrast_ids": [1]}},
                               "steps": [{"id": "step-deg", "stage": "deg", "sample": "__all__",
                                          "status": "RUNNING", "job_id": "job-deg"}]}])
        if url.endswith("/pipeline/jobs/job-deg/progress"):
            return _Response({"cursor": "1:1", "lines": [
                "[2026-11-15T11:40:00+00:00] PROGRESS: DEG — anotação UniProt iniciada."]})
        if url.endswith("/jobs/job-deg"):
            return _Response({"job_id": "job-deg", "payload": {"contrast_ids": [1]},
                              "result": {"progress_log": "[now] PROGRESS: DEG — anotação UniProt iniciada."}})
        return await super().get(url)


class _FinishedQualityClient(_Client):
    def __init__(self, status):
        self.status = status

    async def get(self, url, **_kwargs):
        if url.endswith("/pipeline/runs"):
            return _Response([{"id": "run-qc", "status": self.status,
                               "config": {"name": "Quality test"},
                               "steps": [{"id": "step-qc", "stage": "qc_raw", "sample": "S1",
                                          "status": self.status, "job_id": "job-qc",
                                          "error_message": "FastQC exited after running out of memory" if self.status == "FAILED" else None}]}])
        if url.endswith("/jobs/job-qc"):
            event = ("FastQC ran out of memory (exit code 137)." if self.status == "FAILED"
                     else "FastQC completed successfully.")
            return _Response({"job_id": "job-qc", "status": self.status,
                              "result": {"progress_log": f"[now] PROGRESS: {event}"}})
        return await super().get(url)


class _StaleQualityClient(_Client):
    async def get(self, url, **_kwargs):
        if url.endswith("/jobs/job-1"):
            return _Response({"job_id": "job-1", "result": {
                "progress_percent": 85,
                "monitor_warning": {"code": "no_recent_events", "silent_seconds": 660},
            }})
        return await super().get(url)


class _TrimmingGrowthClient(_Client):
    async def get(self, url, **_kwargs):
        if url.endswith("/pipeline/runs"):
            return _Response([{"id": "run-trim", "status": "RUNNING", "config": {"name": "Trim"},
                              "steps": [{"id": "step-trim", "stage": "trimming", "sample": "A1",
                                         "status": "RUNNING", "job_id": "job-trim"}]}])
        if url.endswith("/jobs/job-trim"):
            return _Response({"job_id": "job-trim", "status": "RUNNING",
                              "result": {"output_bytes": 2 * 1024**3,
                                         "progress_message": "Executando Trimmomatic."}})
        return await super().get(url)


class PipelineMonitorTest(unittest.IsolatedAsyncioTestCase):
    async def _one_poll(self, client, tracked_run_id=None, lang="pt"):
        terminal = ft.Container(content=ft.ListView(controls=[]), visible=True)
        page = SimpleNamespace(container_terminal=terminal,
                               session={"lang": lang}, update=lambda: None,
                               pipeline_monitor_run_id=tracked_run_id)
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
        self.assertEqual([], terminal.content.controls)
        self.assertTrue(terminal.visible)

    async def test_run_that_finished_before_first_poll_stays_visible_this_session(self):
        terminal, _ = await self._one_poll(_HistoryOnlyClient(), tracked_run_id="old")
        self.assertTrue(terminal.content.controls[0].visible)
        self.assertIn("Previous session", terminal.content.controls[0].content.controls[0].value)

    async def test_new_terminal_messages_leave_progress_card_at_bottom(self):
        terminal, _ = await self._one_poll(_Client())
        page = SimpleNamespace(container_terminal=terminal, update=lambda: None)
        await utils.log_message(page, "Pipeline iniciado")
        self.assertEqual("Pipeline iniciado", terminal.content.controls[0].value)
        self.assertEqual("terminal_progress_pipeline", terminal.content.controls[1].data)

    async def test_running_llm_reappears_after_login(self):
        terminal, refreshes = await self._one_poll(_ActiveLlmClient())
        self.assertEqual("terminal_progress_llm", terminal.content.controls[0].data)
        self.assertIn("6/53", terminal.content.controls[0].content.controls[2].value)
        self.assertAlmostEqual(.113, terminal.content.controls[0].content.controls[1].value)
        self.assertEqual([True], refreshes)

    async def test_finished_llm_refreshes_tables_without_reopening_terminal_card(self):
        terminal, refreshes = await self._one_poll(_FinishedLlmClient())
        self.assertEqual([], terminal.content.controls)
        self.assertEqual([True], refreshes)

    async def test_deg_details_are_logged_without_empty_placeholder(self):
        terminal, _ = await self._one_poll(_DegClient())
        self.assertEqual("DEG — anotação UniProt iniciada.", terminal.content.controls[0].value)
        self.assertEqual("terminal_progress_pipeline", terminal.content.controls[1].data)
        self.assertEqual(2, len(terminal.content.controls))

    async def test_failed_quality_explains_failure_in_terminal(self):
        terminal, _ = await self._one_poll(_FinishedQualityClient("FAILED"), tracked_run_id="run-qc")
        self.assertIn("exit code 137", terminal.content.controls[0].value)
        self.assertEqual("terminal_progress_pipeline", terminal.content.controls[1].data)

    async def test_completed_quality_reports_success_in_terminal(self):
        terminal, _ = await self._one_poll(_FinishedQualityClient("COMPLETED"), tracked_run_id="run-qc")
        self.assertIn("completed successfully", terminal.content.controls[0].value)

    async def test_stalled_job_warning_is_translated(self):
        for lang, expected in (("pt", "Sem atualização"), ("en", "No update"),
                               ("es", "Sin actualizaciones")):
            with self.subTest(lang=lang):
                terminal, _ = await self._one_poll(_StaleQualityClient(), lang=lang)
                card = terminal.content.controls[0]
                detail = card.content.controls[3].controls[0].value
                self.assertIn(expected, detail)

    async def test_trimming_output_growth_is_visible(self):
        terminal, _ = await self._one_poll(_TrimmingGrowthClient())
        detail = terminal.content.controls[0].content.controls[3].controls[0].value
        self.assertIn("2.00 GiB", detail)
        self.assertIn("Saída em crescimento", detail)

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
        self.assertEqual("terminal_progress_pipeline", card.data)
        self.assertIn("Test", card.content.controls[0].value)
        self.assertIn("42%", card.content.controls[3].controls[0].value)
        self.assertEqual([True], refreshes)


if __name__ == "__main__":
    unittest.main()
