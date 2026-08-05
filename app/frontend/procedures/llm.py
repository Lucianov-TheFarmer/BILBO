import asyncio

import flet as ft
import httpx

from ..components.general_components import create_button
from .jobs import wait_for_job
from .utils import log_message


async def show_llm(page, token, user_id, container_amostras, container_pre_visualizacao, refresh_stage_counts=None):
    """List prototype cluster/RAG interpretations and their report artifacts."""
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    files = []

    async def _refresh_stage_counts_if_needed():
        if refresh_stage_counts is None:
            return
        try:
            maybe_result = refresh_stage_counts()
            if asyncio.iscoroutine(maybe_result):
                await maybe_result
        except Exception:
            pass

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8890/samples/stages/10", headers=headers)
        if resp.status_code != 200:
            await log_message(page, f"Erro ao buscar entradas LLM: {resp.text}")
            resp_data = []
        else:
            resp_data = resp.json()
        for item in resp_data:
            files.append({"sheet": item.get("name")})
    except Exception as ex:
        await log_message(page, f"Erro ao buscar entradas LLM: {ex}")

    async def _view_md(e, sheet_name):
        try:
            url = f"http://localhost:8890/llm/file?file=report.md&sheet={sheet_name}"
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url, headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
                )
            if resp.status_code != 200:
                await log_message(page, f"Erro ao buscar .md: {resp.status_code} - {resp.text}")
                return
            text = resp.text

            # render in preview container using Markdown renderer
            async def _navigate_md_link(ev):
                try:
                    await page.launch_url(ev.data)
                except Exception:
                    pass

            container_pre_visualizacao.content = ft.Container(
                expand=True,
                content=ft.ListView(
                    expand=True,
                    controls=[
                        ft.Markdown(
                            value=text,
                            selectable=True,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            on_tap_link=_navigate_md_link,
                            fit_content=False,
                        )
                    ],
                ),
            )
            page.update()
        except Exception as ex:
            await log_message(page, f"Erro ao visualizar .md: {ex}")

    async def _view_json(e, sheet_name):
        try:
            url = f"http://localhost:8890/llm/file?file=data.json&sheet={sheet_name}"
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url, headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
                )
            if resp.status_code != 200:
                await log_message(page, f"Erro ao buscar .json: {resp.status_code} - {resp.text}")
                return
            text = resp.text
            container_pre_visualizacao.content = ft.Container(
                expand=True,
                content=ft.ListView(controls=[ft.Text(text, selectable=True)], expand=True),
            )
            page.update()
        except Exception as ex:
            await log_message(page, f"Erro ao visualizar .json: {ex}")

    async def _delete_sheet(e, sheet_name):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(
                    f"http://localhost:8890/llm/{sheet_name}",
                    headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
                )
            if resp.status_code == 200:
                await log_message(page, f"LLM {sheet_name} excluído.")
                await _refresh_stage_counts_if_needed()
                await show_llm(
                    page, token, user_id, container_amostras, container_pre_visualizacao, refresh_stage_counts
                )
            else:
                await log_message(page, f"Erro ao excluir LLM {sheet_name}: {resp.status_code} - {resp.text}")
        except Exception as ex:
            await log_message(page, f"Erro ao excluir LLM: {ex}")

    rows = []
    for entry in files:
        sheet = entry.get("sheet")

        async def _view_md_handler(e, sheet_name=sheet):
            await _view_md(e, sheet_name)

        async def _view_json_handler(e, sheet_name=sheet):
            await _view_json(e, sheet_name)

        async def _delete_handler(e, sheet_name=sheet):
            await _delete_sheet(e, sheet_name)

        md_btn = ft.IconButton(icon="description", tooltip="Ver report (.md)", on_click=_view_md_handler)
        json_btn = ft.IconButton(icon="code", tooltip="Ver dados (.json)", on_click=_view_json_handler)
        del_btn = ft.IconButton(icon="delete", tooltip="Excluir", on_click=_delete_handler)

        rows.append(
            ft.DataRow(cells=[ft.DataCell(ft.Text(sheet)), ft.DataCell(ft.Row(controls=[md_btn, json_btn, del_btn]))])
        )

    tabela = ft.DataTable(
        heading_row_color="primary",
        data_row_color="surface",
        border=ft.border.all(0.5, "#000000"),
        columns=[
            ft.DataColumn(ft.Text("Contraste", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Actions", weight=ft.FontWeight.BOLD)),
        ],
        rows=rows,
        expand=True,
    )

    async def _start_llm(e):
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                resp_deg = await client.get("http://localhost:8890/deg/sheets", headers=headers)
                resp_llm = await client.get("http://localhost:8890/llm/contrasts", headers=headers)

            if resp_deg.status_code != 200:
                await log_message(page, f"Erro ao buscar abas DEG: {resp_deg.text}")
                return
            if resp_llm.status_code != 200:
                await log_message(page, f"Erro ao buscar entradas LLM: {resp_llm.text}")
                return

            sheets = resp_deg.json().get("sheets", [])
            existing = [c.get("sheet") for c in resp_llm.json().get("contrasts", [])]
            to_run = [s for s in sheets if s not in existing]

            if not to_run:
                await log_message(page, "Todas as abas já possuem interpretação LLM.")
                return

            checkboxes = [ft.Checkbox(label=s, value=False, data=s) for s in to_run]

            async def _confirm(e):
                selected = [cb.data for cb in checkboxes if cb.value]
                if not selected:
                    await log_message(page, "Nenhum contraste selecionado para LLM.")
                    return

                await log_message(page, f"Iniciando interpretação LLM para: {', '.join(selected)}")

                payload = {"sheets": selected}
                try:
                    async with httpx.AsyncClient(timeout=None) as client:
                        resp = await client.post("http://localhost:8890/llm/run", json=payload, headers=headers)
                    if resp.status_code not in (200, 202):
                        await log_message(page, f"Erro ao iniciar LLM: {resp.status_code} - {resp.text}")
                    else:
                        body = resp.json()
                        job_id = body.get("job_id")
                        if job_id:
                            await log_message(page, f"Interpretação LLM enfileirada (job {job_id}).")
                            result = await wait_for_job(token, job_id)
                            status = result.get("status")
                            if status == "COMPLETED":
                                await log_message(page, "Interpretação de clusters e RAG concluída com sucesso.")
                            else:
                                error_message = result.get("error_message")
                                if error_message:
                                    await log_message(page, f"Detalhe do erro: {error_message}")
                                await log_message(page, f"Interpretação LLM finalizada com status {status}.")
                        else:
                            await log_message(page, "Interpretação LLM iniciada.")
                        # refresh list
                        await _refresh_stage_counts_if_needed()
                        await show_llm(
                            page, token, user_id, container_amostras, container_pre_visualizacao, refresh_stage_counts
                        )
                except Exception as ex:
                    await log_message(page, f"Erro ao executar LLM: {ex}")

                dlg.open = False
                page.update()

            async def _cancel(e):
                try:
                    dlg.open = False
                except Exception:
                    pass
                page.update()

            dlg = ft.AlertDialog(
                title=ft.Text("Iniciar Interpretação por LLM"),
                content=ft.Column(controls=checkboxes),
                actions=[ft.TextButton("Cancelar", on_click=_cancel), ft.ElevatedButton("Iniciar", on_click=_confirm)],
                actions_alignment="end",
            )

            page.open(dlg)
            page.update()

        except Exception as ex:
            await log_message(page, f"Erro ao preparar modal LLM: {ex}")

    container_amostras.content.controls = [
        tabela,
        create_button("Reexecutar Interpretação e RAG", _start_llm, color="primary", expand=False),
    ]
    page.update()
