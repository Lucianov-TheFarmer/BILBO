import asyncio
import inspect
import logging
from typing import Optional
import httpx
import flet as ft
from .translations import t
from .utils import log_message

logger = logging.getLogger(__name__)


async def wait_for_job(
    token: str,
    job_id: str,
    *,
    interval: float = 2.0,
    on_update=None,
    page=None,
):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    last_event = None
    connection_warned = False
    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            try:
                response = await client.get(f"http://localhost:8890/jobs/{job_id}", headers=headers)
                response.raise_for_status()
                if connection_warned and page is not None:
                    await log_message(page, t("job_monitor_reconnected", page.session.get("lang") or "pt"))
                connection_warned = False
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403, 404):
                    raise
                if not connection_warned:
                    logger.warning("Could not poll job %s; retrying: %s", job_id, exc)
                    if page is not None:
                        await log_message(page, t("job_monitor_reconnecting", page.session.get("lang") or "pt"))
                    connection_warned = True
                await asyncio.sleep(interval)
                continue
            payload = response.json()
            if page is not None:
                lines = str((payload.get("result") or {}).get("progress_log") or "").splitlines()
                if lines:
                    fresh = lines[lines.index(last_event) + 1:] if last_event in lines else lines[-3:]
                    for line in fresh[-5:]:
                        await log_message(page, line.split("] ", 1)[-1].removeprefix("PROGRESS: "))
                    last_event = lines[-1]

            if on_update is not None:
                try:
                    maybe_result = on_update(payload)
                    if inspect.isawaitable(maybe_result):
                        await maybe_result
                except Exception:
                    logger.exception("Could not update progress for job %s", job_id)

            status = payload.get("status")
            if status in {"COMPLETED", "FAILED", "CANCELED"}:
                return payload
            await asyncio.sleep(interval)


async def wait_with_progress(page, token: str, job_id: str, title: str, on_update=None):
    """Show per-sample job progress in the existing terminal panel."""
    container = getattr(page, "container_terminal", None)
    terminal = container if isinstance(container, ft.ListView) else getattr(container, "content", None)
    if not isinstance(terminal, ft.ListView):
        return await wait_for_job(token, job_id, on_update=on_update)
    label = ft.Text(title)
    detail = ft.Text("0%", size=11)
    bar = ft.ProgressBar(value=0, width=260)
    terminal.controls.append(ft.Container(
        border=ft.border.all(1, "black12"), border_radius=8,
        padding=ft.padding.symmetric(horizontal=10, vertical=8),
        content=ft.Column(spacing=4, controls=[label, bar, detail])))
    page.update()

    async def update(payload):
        if on_update is not None:
            maybe_result = on_update(payload)
            if inspect.isawaitable(maybe_result):
                await maybe_result
        result = payload.get("result") or {}
        status = payload.get("status") or "PENDING"
        lang = page.session.get("lang") or "pt"
        status_label = t({"PENDING": "drive_queued", "RUNNING": "status_running",
                          "COMPLETED": "drive_job_complete", "FAILED": "drive_job_failed"}.get(status, status), lang)
        percent = result.get("progress_percent")
        if status == "COMPLETED":
            percent = 100
        if isinstance(percent, (float, int)):
            bar.value = min(1, max(0, percent / 100))
        else:
            bar.value = None
        current = result.get("progress_message") or ""
        completed = result.get("completed_samples")
        total = result.get("total_samples")
        if status == "COMPLETED" and not total:
            total = len((payload.get("payload") or {}).get("samples") or []) or None
            completed = total
        if status == "RUNNING" and result.get("progress_source") == "fastqc_log" and current.endswith(": 100%"):
            current = t("qc_finalizing", lang)
        if result.get("progress_source") == "alignment_log":
            phase = result.get("progress_phase") or "starting"
            current = t(f"alignment_phase_{phase}", lang)
            records = result.get("processed_records")
            if isinstance(records, int) and records > 0:
                current += f" · {records:,} {t('alignment_records', lang)}"
        count = f"{completed}/{total} · " if completed is not None and total else ""
        detail.value = f"{count}{current} · {status_label}"
        warning = result.get("monitor_warning") or {}
        if warning.get("code") in ("no_recent_events", "no_recent_tool_output"):
            detail.value += " · " + t(
                "pipeline_monitor_tool_stale" if warning["code"] == "no_recent_tool_output"
                else "pipeline_monitor_stale", lang).format(
                minutes=max(1, int(warning.get("silent_seconds", 0)) // 60))
        if status in ("FAILED", "CANCELED"):
            bar.color = "red"
            detail.value = str(payload.get("error_message") or detail.value)
        elif status == "COMPLETED":
            bar.color = "green"
        page.update()

    return await wait_for_job(token, job_id, on_update=update, page=page)
