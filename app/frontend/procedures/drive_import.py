"""Google Drive import modal in Sample Management."""

import asyncio

import flet as ft
import httpx

from .translations import t
from .utils import log_message


API = "http://bioinfo-container:8890"


async def show_drive_import_modal(page, bilbo_token, refresh_samples, container_menu_direita, tabela_amostras_local):
    lang = page.session.get("lang") or "pt"
    headers = {"Authorization": f"Bearer {bilbo_token}"}
    status_text = ft.Text("")
    selection = ft.Column(scroll=ft.ScrollMode.AUTO, height=0)
    picker_holder = ft.Container(height=0)
    picker_fallback = ft.TextButton(t("drive_picker_tab", lang), visible=False)
    recent = ft.Column(scroll=ft.ScrollMode.AUTO, height=0)
    import_button = ft.ElevatedButton(t("drive_import", lang), disabled=True)
    state = {"session": None, "open": True, "jobs": [], "selection_ready": False, "import_started": False}
    monitoring = getattr(page, "_drive_monitoring", None)
    if monitoring is None:
        monitoring = set()
        page._drive_monitoring = monitoring
    cards = getattr(page, "_drive_progress_cards", None)
    if cards is None:
        cards = {}
        page._drive_progress_cards = cards
    status_labels = {
        "pt": {"PENDING": "Na fila", "RUNNING": "Baixando", "COMPLETED": "Concluído", "FAILED": "Falhou", "CANCELED": "Cancelado"},
        "en": {"PENDING": "Queued", "RUNNING": "Downloading", "COMPLETED": "Complete", "FAILED": "Failed", "CANCELED": "Canceled"},
        "es": {"PENDING": "En cola", "RUNNING": "Descargando", "COMPLETED": "Terminado", "FAILED": "Error", "CANCELED": "Cancelado"},
    }.get(lang, {})

    def update_status(message):
        status_text.value = message
        page.update()

    def job_line(job):
        progress = job.get("progress") or {}
        transferred = ""
        if job["status"] == "RUNNING" and progress.get("total"):
            transferred = f" — {progress['file']}: {int(progress['bytes']) / 1024**3:.1f}/{int(progress['total']) / 1024**3:.1f} GiB"
        return f"{job['base']}: {status_labels.get(job['status'], job['status'])}{transferred}" + (f" — {job['error']}" if job.get("error") else "")

    def update_terminal_card(job):
        container = getattr(page, "container_terminal", None)
        terminal = container if isinstance(container, ft.ListView) else getattr(container, "content", None)
        if not isinstance(terminal, ft.ListView):
            return
        job_id = job["id"]
        if job_id not in cards:
            title = ft.Text(f"Google Drive — {job['base']}")
            bar = ft.ProgressBar(value=None, width=260)
            detail = ft.Text(t("drive_queued", lang), size=11)
            terminal.controls.append(ft.Container(
                border=ft.border.all(1, "black12"), border_radius=8,
                padding=ft.padding.symmetric(horizontal=10, vertical=8),
                content=ft.Column(spacing=4, controls=[title, bar, detail])))
            cards[job_id] = (bar, detail)
        bar, detail = cards[job_id]
        state_name = job["status"]
        progress = job.get("progress") or {}
        files = job.get("files") or []
        if state_name == "RUNNING" and progress.get("total"):
            mate = 2 if str(progress.get("file", "")).endswith("_2.fastq.gz") else 1
            done = int(progress.get("bytes") or 0)
            current_total = int(progress["total"])
            total = sum(int(file["size"]) for file in files)
            previous = sum(int(file["size"]) for file in files if int(file["mate"]) < mate)
            bar.value = min(0.99, (previous + done) / total) if total else None
            detail.value = f"{t('drive_downloading', lang)} R{mate} ({done / 1024**3:.1f}/{current_total / 1024**3:.1f} GiB)"
        elif state_name == "COMPLETED":
            bar.value = 1
            bar.color = "green"
            detail.value = t("drive_job_complete", lang)
        elif state_name in ("FAILED", "CANCELED"):
            bar.color = "red"
            detail.value = str(job.get("error") or t("drive_job_failed", lang))
        else:
            bar.value = None
            detail.value = t("drive_queued", lang) if state_name == "PENDING" else t("drive_downloading", lang)
        page.update()

    async def close(_):
        state["open"] = False
        page.close(dialog)

    async def connect(_):
        connect_button.disabled = True
        page.update()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(f"{API}/drive/session", params={"lang": lang}, headers=headers)
                if response.status_code == 503:
                    connect_button.disabled = False
                    update_status(t("drive_not_configured", lang))
                    return
                response.raise_for_status()
                data = response.json()
            state["session"] = data["session_id"]
            update_status(t("drive_wait", lang))
            page.launch_url(data["authorization_url"])
            page.run_task(poll_selection)
        except Exception as exc:
            connect_button.disabled = False
            update_status(str(exc))

    async def load_recent():
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(f"{API}/drive/jobs", headers=headers)
                response.raise_for_status()
                jobs = response.json()
            recent.controls = [ft.Text(t("drive_recent", lang))]
            recent.controls.extend(ft.Text(job_line(job)) for job in jobs)
            recent.height = 100 if jobs else 0
            page.update()
            active_ids = [job["id"] for job in jobs if job["status"] in ("PENDING", "RUNNING") and job["id"] not in monitoring]
            if active_ids:
                state["jobs"] = active_ids
                monitoring.update(active_ids)
                page.run_task(poll_jobs, active_ids)
        except Exception:
            pass

    async def poll_selection():
        while state["open"] and state["session"] and not state["selection_ready"]:
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.get(f"{API}/drive/session/{state['session']}", headers=headers)
                    response.raise_for_status()
                    data = response.json()
                if data["status"] == "authorization_failed":
                    update_status(t("drive_failed", lang))
                    return
                if data["status"] == "selecting" and picker_holder.height == 0:
                    picker_url = f"http://localhost:8890/drive/picker?session={state['session']}"
                    picker_holder.height = 300
                    picker_holder.content = ft.WebView(url=picker_url, expand=True)
                    picker_fallback.visible = True
                    picker_fallback.on_click = lambda e: page.launch_url(picker_url)
                    page.update()
                if data["status"] == "selected":
                    state["selection_ready"] = True
                    picker_holder.height = 0
                    picker_holder.content = None
                    picker_fallback.visible = False
                    files = data["files"]
                    existing = set(data.get("existing_bases") or [])
                    importing = set(data.get("importing_bases") or [])
                    groups = {}
                    for file in files:
                        groups.setdefault(file["base"], {})[file["mate"]] = file
                    selection.controls = [ft.Text(t("drive_select", lang))]
                    selection.height = 300
                    for base, pair in sorted(groups.items()):
                        names = "  |  ".join(f"R{mate}: {pair[mate]['name']}" for mate in sorted(pair))
                        total = sum(item["size"] for item in pair.values()) / 1024**3
                        note = (t("drive_already_present", lang) if base in existing else
                                t("drive_already_importing", lang) if base in importing else "")
                        selection.controls.append(ft.Text(f"{base} — {names} — {total:.1f} GiB" +
                                                          (f" — {note}" if note else "")))
                    complete = bool(groups) and all(set(pair) == {1, 2} for pair in groups.values())
                    available = set(groups) - existing - importing
                    import_button.disabled = not complete or not available
                    skipped = sorted(existing | importing)
                    update_status((t("drive_skipped", lang).format(names=", ".join(skipped)) if skipped else "")
                                  if complete else t("drive_incomplete", lang))
                    return
            except Exception as exc:
                update_status(str(exc))
                return
            await asyncio.sleep(3)

    async def start_import(_):
        import_button.disabled = True
        page.update()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(f"{API}/drive/session/{state['session']}/import", headers=headers)
                response.raise_for_status()
                result = response.json()
                state["jobs"] = result["job_ids"]
                state["import_started"] = bool(state["jobs"])
            skipped = sorted(set(result.get("skipped_existing") or []) |
                             set(result.get("skipped_importing") or []))
            message = t("drive_progress", lang) if state["jobs"] else t("drive_nothing_to_import", lang)
            if skipped:
                message += "\n" + t("drive_skipped", lang).format(names=", ".join(skipped))
            update_status(message)
            if state["jobs"]:
                monitoring.update(state["jobs"])
                page.run_task(poll_jobs, list(state["jobs"]))
            try:
                await refresh_samples(page, bilbo_token, container_menu_direita, tabela_amostras_local)
            except Exception:
                pass  # The job monitor will retry the table refresh.
        except httpx.HTTPStatusError as exc:
            import_button.disabled = False
            detail = exc.response.json().get("detail", "") if exc.response.headers.get("content-type", "").startswith("application/json") else ""
            update_status(t("drive_no_selection", lang) if exc.response.status_code == 409 and detail == "No Drive files selected" else detail or str(exc))
        except Exception as exc:
            import_button.disabled = False
            update_status(str(exc))

    async def poll_jobs(job_ids):
        last_seen = {}
        polls = 0
        failures = 0
        try:
            while True:
                try:
                    async with httpx.AsyncClient(timeout=20) as client:
                        responses = await asyncio.gather(*[
                            client.get(f"{API}/drive/jobs/{job_id}", headers=headers)
                            for job_id in job_ids
                        ])
                    for response in responses:
                        response.raise_for_status()
                    jobs = [response.json() for response in responses]
                    changed = False
                    for job in jobs:
                        update_terminal_card(job)
                        progress = job.get("progress") or {}
                        file_name = progress.get("file", "") if job["status"] == "RUNNING" else ""
                        current = (job["status"], file_name)
                        previous = last_seen.get(job["id"])
                        if current != previous:
                            changed = True
                            if previous and previous[1] and previous[1] != file_name and job["status"] == "RUNNING":
                                await log_message(page, f"{t('drive_verified', lang)}: {previous[1]}")
                            label_key = {
                                "PENDING": "drive_queued", "RUNNING": "drive_downloading",
                                "COMPLETED": "drive_job_complete", "FAILED": "drive_job_failed",
                            }.get(job["status"])
                            label = t(label_key, lang) if label_key else status_labels.get(job["status"], job["status"])
                            await log_message(page, f"Google Drive — {job['base']}: {label}" + (f" {file_name}" if file_name else "") + (f" — {job['error']}" if job.get("error") else ""))
                            last_seen[job["id"]] = current
                    if state["open"] and state["jobs"] == job_ids and (not state["selection_ready"] or state["import_started"]):
                        selection.height = 200
                        selection.controls = [ft.Text(job_line(job)) for job in jobs]
                        if all(job["status"] in ("COMPLETED", "FAILED", "CANCELED") for job in jobs):
                            update_status(t("drive_done", lang) if all(job["status"] == "COMPLETED" for job in jobs) else t("drive_failed", lang))
                        else:
                            page.update()
                    if changed or polls % 3 == 0:
                        await refresh_samples(page, bilbo_token, container_menu_direita, tabela_amostras_local)
                    if all(job["status"] in ("COMPLETED", "FAILED", "CANCELED") for job in jobs):
                        return
                    polls += 1
                    failures = 0
                except Exception as exc:
                    if state["open"]:
                        update_status(str(exc))
                    failures += 1
                    if failures >= 12:
                        return
                await asyncio.sleep(5)
        finally:
            monitoring.difference_update(job_ids)

    import_button.on_click = start_import
    connect_button = ft.ElevatedButton(t("drive_connect", lang), on_click=connect)
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Row(controls=[
            ft.Text(t("menu_import_drive", lang), expand=True),
            ft.IconButton(icon=ft.Icons.CLOSE, tooltip=t("menu_close", lang), on_click=close),
        ]),
        content=ft.Container(width=750, height=420, content=ft.Column(tight=True, scroll=ft.ScrollMode.AUTO, controls=[
            ft.Text(t("drive_intro", lang)),
            ft.Text(t("drive_no_setup", lang), size=12, italic=True),
            connect_button, status_text, picker_holder, picker_fallback, selection, import_button, recent,
        ])),
        actions=[ft.TextButton(t("menu_close", lang), on_click=close)],
    )
    page.open(dialog)
    page.update()
    page.run_task(load_recent)
