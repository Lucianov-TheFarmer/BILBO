"""Keep the current automatic pipeline visible on the main screen."""

import asyncio
from collections import Counter

import flet as ft
import httpx

from .deg import _format_deg_progress
from .jobs import format_output_size
from .translations import t
from .utils import log_message

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
        data="terminal_progress_pipeline",
        border=ft.border.all(1, "outline"), border_radius=8,
        padding=ft.padding.all(10),
        content=ft.Column([title, summary, bar, details], spacing=5),
    )
    llm_title = ft.Text(weight=ft.FontWeight.BOLD)
    llm_phase = ft.Text(size=11)
    llm_bar = ft.ProgressBar(value=None, width=270)
    llm_card = ft.Container(
        data="terminal_progress_llm",
        border=ft.border.all(1, "outline"), border_radius=8,
        padding=ft.padding.all(10),
        content=ft.Column([llm_title, llm_bar, llm_phase], spacing=5),
    )
    def show_card(control):
        if control not in terminal.controls:
            if control is card and llm_card in terminal.controls:
                terminal.controls.insert(terminal.controls.index(llm_card), control)
            else:
                terminal.controls.append(control)

    def hide_card(control):
        if control in terminal.controls:
            terminal.controls.remove(control)

    previous_steps = None
    previous_run = None
    previous_llm = None
    previous_llm_state = None
    deg_cursors = {}
    deg_format_states = {}
    job_event_cursors = {}

    while getattr(page, "container_terminal", None) is terminal_container:
        lang = page.session.get("lang") or "pt"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{API}/pipeline/runs", headers=headers)
                response.raise_for_status()
                runs = response.json()
                run = next((item for item in runs if item["status"] == "RUNNING"), None)
                tracked_run_id = getattr(page, "pipeline_monitor_run_id", None)
                if run is None and tracked_run_id:
                    run = next((item for item in runs if item["id"] == tracked_run_id), None)
                if run is None and previous_run:
                    run = next((item for item in runs if item["id"] == previous_run), None)
                if run:
                    steps = run["steps"]
                    active = [step for step in steps if step["status"] in ACTIVE]
                    observed = [step for step in steps if step["status"] in ACTIVE or step["status"] in ("FAILED", "CANCELED")][:12]
                    observed += [step for step in steps if step["status"] == "COMPLETED"][-4:]
                    jobs = await asyncio.gather(*[
                        client.get(f"{API}/jobs/{step['job_id']}", headers=headers)
                        for step in observed if step.get("job_id")
                    ], return_exceptions=True)
                    job_details = {job.json()["job_id"]: job.json()
                                   for job in jobs if getattr(job, "status_code", None) == 200}
                llm_response = await client.get(f"{API}/jobs?stage=llm", headers=headers)
                llm_response.raise_for_status()
                llm_jobs = llm_response.json()
                latest_llm_state = ((llm_jobs[0]["job_id"], llm_jobs[0]["status"])
                                    if llm_jobs else None)
                llm_item = next((item for item in llm_jobs if item["status"] in ACTIVE), None)
                if llm_item is None and previous_llm:
                    llm_item = next((item for item in llm_jobs if item["job_id"] == previous_llm), None)
                llm_job = None
                if llm_item:
                    llm_detail = await client.get(f"{API}/jobs/{llm_item['job_id']}", headers=headers)
                    if llm_detail.status_code == 200:
                        llm_job = llm_detail.json()
            if run:
                show_card(card)
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
                bar.visible = status == "RUNNING"
                bar.color = "red" if status == "FAILED" else "green" if status == "COMPLETED" else None
                details.controls.clear()
                visible = [step for step in steps if step["status"] in ACTIVE]
                if not visible:
                    visible = [step for step in steps if step["status"] in ("FAILED", "CANCELED")][:4]
                if not visible and status == "COMPLETED":
                    visible = [step for step in steps if step["status"] == "COMPLETED"][-4:]
                if not visible and status == "RUNNING":
                    visible = [step for step in steps if step["status"] == "WAITING"][:4]
                for step in visible[:8]:
                    stage = (t("pipeline_samples", lang) if step["stage"] == "input" else
                             t("pipeline_stage_" + step["stage"], lang))
                    job = job_details.get(step.get("job_id"), {})
                    result = job.get("result") or {}
                    percent = result.get("progress_percent")
                    phase = result.get("progress_message") or ""
                    if result.get("progress_source") == "rag_checkpoint":
                        phase = t("pipeline_llm_rag_progress", lang).format(
                            done=result["progress_done"], total=result["progress_total"])
                    if result.get("progress_log"):
                        phase = str(result["progress_log"]).splitlines()[-1]
                        if "] " in phase:
                            phase = phase.split("] ", 1)[1]
                        phase = phase.removeprefix("PROGRESS: ")
                    if result.get("progress_source") == "alignment_log":
                        phase = t("alignment_phase_" + str(result.get("progress_phase") or "starting"), lang)
                    status_key = "pipeline_queued" if step["status"] == "PENDING" else "pipeline_" + step["status"].lower()
                    label = f"{step['sample']} · {stage}: {t(status_key, lang)}"
                    if isinstance(percent, (int, float)):
                        label += f" · {percent:.0f}%"
                    if isinstance(result.get("output_bytes"), int):
                        growth = t("analysis_output_growth", lang).format(
                            size=format_output_size(result["output_bytes"]))
                        phase = f"{phase} · {growth}" if phase else growth
                    if phase:
                        label += f" · {phase[:100]}"
                    warning = result.get("monitor_warning") or {}
                    if warning.get("code") in ("no_recent_events", "no_recent_tool_output"):
                        key = "pipeline_monitor_tool_stale" if warning["code"] == "no_recent_tool_output" else "pipeline_monitor_stale"
                        label += " · " + t(key, lang).format(
                            minutes=max(1, int(warning.get("silent_seconds", 0)) // 60))
                    if step.get("error_message"):
                        label += f" · {step['error_message'][:150]}"
                    details.controls.append(ft.Text(label, size=11))
                for job_id, job in job_details.items():
                    if any(step.get("job_id") == job_id and step["stage"] == "deg" for step in steps):
                        continue  # DEG already streams the same journal through its detailed formatter.
                    lines = str((job.get("result") or {}).get("progress_log") or "").splitlines()
                    if not lines:
                        continue
                    previous = job_event_cursors.get(job_id)
                    if previous in lines:
                        fresh = lines[lines.index(previous) + 1:]
                    else:
                        fresh = lines[-3:]
                    for line in fresh[-5:]:
                        message = line.split("] ", 1)[-1].removeprefix("PROGRESS: ")
                        await log_message(page, message, container_terminal=terminal_container)
                    job_event_cursors[job_id] = lines[-1]
                for step in steps:
                    if step["stage"] != "deg" or not step.get("job_id"):
                        continue
                    job_id = step["job_id"]
                    try:
                        async with httpx.AsyncClient(timeout=10) as progress_client:
                            response = await progress_client.get(
                                f"{API}/pipeline/jobs/{job_id}/progress",
                                headers=headers,
                                params={"cursor": deg_cursors.get(job_id, "0:0")},
                            )
                        if response.status_code != 200:
                            continue
                        progress = response.json()
                        deg_cursors[job_id] = progress.get("cursor", "0:0")
                        state = deg_format_states.setdefault(job_id, {
                            "contrast_index": 0, "full_index": 0, "last_raw": None})
                        total = len(
                            (job_details.get(job_id, {}).get("payload") or {}).get("contrast_ids")
                            or (run["config"].get("design") or {}).get("contrast_ids") or [])
                        for line in progress.get("lines", []):
                            message = _format_deg_progress(line, state, total)
                            if message:
                                await log_message(page, message, container_terminal=terminal_container)
                    except Exception:
                        pass
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
            elif card in terminal.controls:
                hide_card(card)
                page.update()
            if latest_llm_state != previous_llm_state:
                previous_llm_state = latest_llm_state
                try:
                    await refresh_tables()
                except Exception:
                    pass
            pipeline_llm_jobs = {step.get("job_id") for step in (run or {}).get("steps", [])
                                 if step["stage"] == "llm"}
            if llm_job and llm_job["job_id"] not in pipeline_llm_jobs:
                previous_llm = llm_job["job_id"]
                show_card(llm_card)
                llm_title.value = f"{t('pipeline_stage_llm', lang)} · {t('pipeline_' + llm_job['status'].lower(), lang)}"
                result = llm_job.get("result") or {}
                lines = str(result.get("progress_log") or "").splitlines()
                llm_phase.value = (t("pipeline_llm_rag_progress", lang).format(
                    done=result["progress_done"], total=result["progress_total"])
                    if result.get("progress_source") == "rag_checkpoint" else
                    lines[-1][:180] if lines else t("pipeline_llm_waiting", lang))
                percent = result.get("progress_percent")
                llm_bar.value = (max(0, min(1, percent / 100))
                                 if isinstance(percent, (int, float)) else
                                 1 if llm_job["status"] == "COMPLETED" else
                                 0 if llm_job["status"] == "PENDING" else None)
                llm_bar.color = "red" if llm_job["status"] == "FAILED" else "blue"
                llm_bar.visible = llm_job["status"] in ACTIVE
                page.update()
            elif llm_card in terminal.controls:
                hide_card(llm_card)
                page.update()
        except Exception as exc:
            show_card(card)
            title.value = t("pipeline_progress_title", lang)
            summary.value = t("pipeline_progress_unavailable", lang).format(error=str(exc)[:100])
            page.update()
        await asyncio.sleep(5)
