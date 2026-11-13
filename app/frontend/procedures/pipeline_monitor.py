"""Keep the current automatic pipeline visible on the main screen."""

import asyncio
from collections import Counter

import flet as ft
import httpx

from .translations import t

API = "http://bioinfo-container:8890"
ACTIVE = {"PENDING", "RUNNING"}
DONE = {"COMPLETED", "SKIPPED"}


async def monitor_pipeline(page, token, terminal_container, refresh_tables):
    terminal = terminal_container.content
    headers = {"Authorization": f"Bearer {token}"}
    title = ft.Text(weight=ft.FontWeight.BOLD)
    summary = ft.Text(size=12)
    bar = ft.ProgressBar(value=0, width=270)
    details = ft.Column(spacing=3)
    card = ft.Container(
        border=ft.border.all(1, "outline"), border_radius=8,
        padding=ft.padding.all(10), visible=False,
        content=ft.Column([title, summary, bar, details], spacing=5),
    )
    terminal.controls.append(card)
    previous_steps = None
    previous_run = None

    while getattr(page, "container_terminal", None) is terminal_container:
        lang = page.session.get("lang") or "pt"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{API}/pipeline/runs", headers=headers)
                response.raise_for_status()
                runs = response.json()
                run = next((item for item in runs if item["status"] == "RUNNING"), None)
                if run is None:
                    run = next((item for item in runs if item["status"] != "DRAFT"), None)
                if run:
                    steps = run["steps"]
                    active = [step for step in steps if step["status"] in ACTIVE]
                    jobs = await asyncio.gather(*[
                        client.get(f"{API}/jobs/{step['job_id']}", headers=headers)
                        for step in active if step.get("job_id")
                    ], return_exceptions=True)
                    job_details = {job.json()["job_id"]: job.json()
                                   for job in jobs if getattr(job, "status_code", None) == 200}
            if run:
                card.visible = True
                status = run["status"]
                status_label = t("pipeline_" + status.lower(), lang)
                title.value = f"{t('pipeline_progress_title', lang)} · {run['config']['name']}"
                counts = Counter(step["status"] for step in steps)
                completed = sum(counts[state] for state in DONE)
                summary.value = t("pipeline_progress_summary", lang).format(
                    status=status_label, done=completed, total=len(steps),
                    running=counts["RUNNING"], queued=counts["PENDING"],
                    waiting=counts["WAITING"], failed=counts["FAILED"])
                bar.value = completed / len(steps) if steps else 0
                bar.color = "red" if status == "FAILED" else "green" if status == "COMPLETED" else None
                details.controls.clear()
                visible = [step for step in steps if step["status"] in ACTIVE]
                if not visible:
                    visible = [step for step in steps if step["status"] == "FAILED"][:4]
                for step in visible[:8]:
                    stage = (t("pipeline_samples", lang) if step["stage"] == "input" else
                             t("pipeline_stage_" + step["stage"], lang))
                    job = job_details.get(step.get("job_id"), {})
                    result = job.get("result") or {}
                    percent = result.get("progress_percent")
                    phase = result.get("progress_message") or ""
                    if result.get("progress_source") == "alignment_log":
                        phase = t("alignment_phase_" + str(result.get("progress_phase") or "starting"), lang)
                    status_key = "pipeline_queued" if step["status"] == "PENDING" else "pipeline_" + step["status"].lower()
                    label = f"{step['sample']} · {stage}: {t(status_key, lang)}"
                    if isinstance(percent, (int, float)):
                        label += f" · {percent:.0f}%"
                    if phase:
                        label += f" · {phase[:100]}"
                    if step.get("error_message"):
                        label += f" · {step['error_message'][:150]}"
                    details.controls.append(ft.Text(label, size=11))
                fingerprint = tuple(sorted((step["id"], step["status"]) for step in steps))
                if previous_run != run["id"] or previous_steps != fingerprint:
                    previous_run, previous_steps = run["id"], fingerprint
                    try:
                        await refresh_tables()
                    except Exception:
                        pass
                elif any(step["stage"] == "trimming" and step["status"] == "RUNNING"
                         for step in steps):
                    try:
                        await refresh_tables(False)
                    except Exception:
                        pass
                page.update()
            elif card.visible:
                card.visible = False
                page.update()
        except Exception as exc:
            card.visible = True
            title.value = t("pipeline_progress_title", lang)
            summary.value = t("pipeline_progress_unavailable", lang).format(error=str(exc)[:100])
            page.update()
        await asyncio.sleep(5)
