"""Google Drive import modal in Sample Management."""

import asyncio

import flet as ft
import httpx

from .translations import t


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
    state = {"session": None, "open": True, "jobs": []}
    status_labels = {
        "pt": {"PENDING": "Na fila", "RUNNING": "Baixando", "COMPLETED": "Concluído", "FAILED": "Falhou", "CANCELED": "Cancelado"},
        "en": {"PENDING": "Queued", "RUNNING": "Downloading", "COMPLETED": "Complete", "FAILED": "Failed", "CANCELED": "Canceled"},
        "es": {"PENDING": "En cola", "RUNNING": "Descargando", "COMPLETED": "Terminado", "FAILED": "Error", "CANCELED": "Cancelado"},
    }.get(lang, {})

    def update_status(message):
        status_text.value = message
        page.update()

    async def close(_):
        state["open"] = False
        dialog.open = False
        page.update()
        await refresh_samples(page, bilbo_token, container_menu_direita, tabela_amostras_local)

    async def connect(_):
        connect_button.disabled = True
        page.update()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(f"{API}/drive/session", params={"lang": lang}, headers=headers)
                if response.status_code == 503:
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
            recent.controls.extend(ft.Text(f"{job['base']}: {status_labels.get(job['status'], job['status'])}") for job in jobs)
            recent.height = 100 if jobs else 0
            page.update()
        except Exception:
            pass

    async def poll_selection():
        while state["open"] and not state["jobs"]:
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
                    picker_holder.height = 390
                    picker_holder.content = ft.WebView(url=picker_url, expand=True)
                    picker_fallback.visible = True
                    picker_fallback.on_click = lambda e: page.launch_url(picker_url)
                    page.update()
                if data["status"] == "selected":
                    picker_holder.height = 0
                    picker_holder.content = None
                    picker_fallback.visible = False
                    files = data["files"]
                    groups = {}
                    for file in files:
                        groups.setdefault(file["base"], {})[file["mate"]] = file
                    selection.controls = [ft.Text(t("drive_select", lang))]
                    selection.height = 300
                    for base, pair in sorted(groups.items()):
                        names = "  |  ".join(f"R{mate}: {pair[mate]['name']}" for mate in sorted(pair))
                        total = sum(item["size"] for item in pair.values()) / 1024**3
                        selection.controls.append(ft.Text(f"{base} — {names} — {total:.1f} GiB"))
                    complete = bool(groups) and all(set(pair) == {1, 2} for pair in groups.values())
                    import_button.disabled = not complete
                    update_status("" if complete else t("drive_incomplete", lang))
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
                state["jobs"] = response.json()["job_ids"]
            update_status(t("drive_progress", lang))
            page.run_task(poll_jobs)
        except Exception as exc:
            import_button.disabled = False
            update_status(str(exc))

    async def poll_jobs():
        while state["open"]:
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    responses = await asyncio.gather(*[
                        client.get(f"{API}/drive/jobs/{job_id}", headers=headers)
                        for job_id in state["jobs"]
                    ])
                jobs = [r.json() for r in responses]
                selection.controls = []
                for job in jobs:
                    progress = job.get("progress") or {}
                    transferred = ""
                    if progress.get("total"):
                        transferred = f" — {progress['file']}: {int(progress['bytes']) / 1024**3:.1f}/{int(progress['total']) / 1024**3:.1f} GiB"
                    selection.controls.append(ft.Text(f"{job['base']}: {status_labels.get(job['status'], job['status'])}{transferred}" + (f" — {job['error']}" if job.get("error") else "")))
                if all(job["status"] in ("COMPLETED", "FAILED", "CANCELED") for job in jobs):
                    update_status(t("drive_done", lang) if all(job["status"] == "COMPLETED" for job in jobs) else t("drive_failed", lang))
                    return
                page.update()
            except Exception as exc:
                update_status(str(exc))
                return
            await asyncio.sleep(5)

    import_button.on_click = start_import
    connect_button = ft.ElevatedButton(t("drive_connect", lang), on_click=connect)
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(t("menu_import_drive", lang)),
        content=ft.Container(width=750, content=ft.Column(tight=True, scroll=ft.ScrollMode.AUTO, controls=[
            ft.Text(t("drive_intro", lang)),
            ft.Text(t("drive_no_setup", lang), size=12, italic=True),
            connect_button, status_text, picker_holder, picker_fallback, selection, import_button, recent,
        ])),
        actions=[ft.TextButton(t("menu_close", lang), on_click=close)],
    )
    page.open(dialog)
    page.update()
    page.run_task(load_recent)
