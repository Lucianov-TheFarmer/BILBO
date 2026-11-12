import asyncio
import inspect
from typing import Optional
import httpx
import flet as ft


async def wait_for_job(
    token: str,
    job_id: str,
    *,
    interval: float = 2.0,
    timeout: Optional[float] = 7200.0,
    on_update=None,
):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    elapsed = 0.0
    async with httpx.AsyncClient(timeout=60.0) as client:
        # BILBO_OPTIONAL_JOB_TIMEOUT
        while timeout is None or elapsed <= timeout:
            response = await client.get(f"http://localhost:8890/jobs/{job_id}", headers=headers)
            response.raise_for_status()
            payload = response.json()

            if on_update is not None:
                try:
                    maybe_result = on_update(payload)
                    if inspect.isawaitable(maybe_result):
                        await maybe_result
                except Exception:
                    pass

            status = payload.get("status")
            if status in {"COMPLETED", "FAILED", "CANCELED"}:
                return payload
            await asyncio.sleep(interval)
            elapsed += interval
    raise TimeoutError(f"Job {job_id} did not finish within {timeout} seconds")


async def wait_with_progress(page, token: str, job_id: str, title: str):
    """Show per-sample job progress in the existing terminal panel."""
    container = getattr(page, "container_terminal", None)
    terminal = container if isinstance(container, ft.ListView) else getattr(container, "content", None)
    if not isinstance(terminal, ft.ListView):
        return await wait_for_job(token, job_id)
    label = ft.Text(title)
    detail = ft.Text("0%", size=11)
    bar = ft.ProgressBar(value=0, width=260)
    terminal.controls.append(ft.Container(
        border=ft.border.all(1, "black12"), border_radius=8,
        padding=ft.padding.symmetric(horizontal=10, vertical=8),
        content=ft.Column(spacing=4, controls=[label, bar, detail])))
    page.update()

    def update(payload):
        result = payload.get("result") or {}
        status = payload.get("status") or "PENDING"
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
        count = f"{completed}/{total} · " if completed is not None and total else ""
        detail.value = f"{count}{current} · {status}"
        if status in ("FAILED", "CANCELED"):
            bar.color = "red"
            detail.value = str(payload.get("error_message") or detail.value)
        elif status == "COMPLETED":
            bar.color = "green"
        page.update()

    return await wait_for_job(token, job_id, on_update=update)
