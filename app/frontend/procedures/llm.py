import asyncio
from urllib.parse import quote

import flet as ft
import httpx

from ..components.general_components import create_button
from .jobs import wait_for_job
from .utils import log_message


async def show_llm(page, token, user_id, container_amostras, container_pre_visualizacao, refresh_stage_counts=None):
    """List prototype cluster/RAG interpretations and their report artifacts."""
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    files = []

    rag_info: dict = {}
    try:
        async with httpx.AsyncClient() as client:
            rag_response = await client.get(
                "http://localhost:8890/llm/rag/status",
                headers=headers,
            )
        if rag_response.status_code == 200:
            rag_info = rag_response.json()
        else:
            rag_info = {
                "ready": False,
                "state": "error",
                "message": rag_response.text,
            }
    except Exception as ex:
        rag_info = {
            "ready": False,
            "state": "unreachable",
            "message": str(ex),
        }


    async def _refresh_stage_counts_if_needed():
        if refresh_stage_counts is None:
            return
        try:
            maybe_result = refresh_stage_counts()
            if asyncio.iscoroutine(maybe_result):
                await maybe_result
        except Exception:
            pass

    # BILBO_LLM_VALIDATED_RESULTS_ONLY
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://localhost:8890/llm/contrasts",
                headers=headers,
            )

        if resp.status_code != 200:
            await log_message(
                page,
                f"Erro ao buscar entradas LLM: {resp.text}",
            )
            resp_data = []
        else:
            payload = resp.json()
            resp_data = payload.get("contrasts", [])

        for item in resp_data:
            sheet_name = item.get("sheet")

            if sheet_name:
                files.append(
                    {
                        "sheet": sheet_name,
                        "files": item.get("files", []),
                    }
                )
    except Exception as ex:
        await log_message(
            page,
            f"Erro ao buscar entradas LLM: {ex}",
        )

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


    async def _view_html(e, sheet_name):
        try:
            url = (
                "http://localhost:8890/llm/file"
                f"?file=report.html&sheet={quote(str(sheet_name))}"
                f"&inline=true&token={quote(str(token))}"
            )
            await page.launch_url(url)
        except Exception as ex:
            await log_message(page, f"Erro ao abrir relatório HTML: {ex}")

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

    # BILBO_LLM_BULK_SELECTION
    rows = []
    result_checkboxes = []

    def _toggle_all_results(e):
        checked = bool(e.control.value)

        for checkbox in result_checkboxes:
            checkbox.value = checked

        page.update()

    def _sync_all_results(e):
        del e
        results_select_all.value = (
            bool(result_checkboxes)
            and all(
                bool(checkbox.value)
                for checkbox in result_checkboxes
            )
        )
        page.update()

    results_select_all = ft.Checkbox(
        value=False,
        tooltip="Selecionar todos os resultados",
        on_change=_toggle_all_results,
    )

    for entry in files:
        sheet = entry.get("sheet")
        result_checkbox = ft.Checkbox(
            value=False,
            data=sheet,
            on_change=_sync_all_results,
        )
        result_checkboxes.append(result_checkbox)

        async def _view_md_handler(e, sheet_name=sheet):
            await _view_md(e, sheet_name)

        async def _view_json_handler(e, sheet_name=sheet):
            await _view_json(e, sheet_name)

        async def _view_html_handler(e, sheet_name=sheet):
            await _view_html(e, sheet_name)

        md_btn = ft.IconButton(
            icon="description",
            tooltip="Ver report (.md)",
            on_click=_view_md_handler,
        )
        json_btn = ft.IconButton(
            icon="code",
            tooltip="Ver dados (.json)",
            on_click=_view_json_handler,
        )
        html_btn = ft.IconButton(
            icon="open_in_new",
            tooltip="Abrir relatório HTML",
            on_click=_view_html_handler,
        )
        rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sheet)),
                    ft.DataCell(result_checkbox),
                    ft.DataCell(
                        ft.Row(
                            # BILBO_LLM_NO_ROW_DELETE
                            controls=[
                                html_btn,
                                md_btn,
                                json_btn,
                            ]
                        )
                    ),
                ]
            )
        )

    tabela = ft.DataTable(
        heading_row_color="primary",
        data_row_color="surface",
        border=ft.border.all(0.5, "#000000"),
        columns=[
            ft.DataColumn(
                ft.Text(
                    "Contraste",
                    weight=ft.FontWeight.BOLD,
                )
            ),
            ft.DataColumn(results_select_all),
            ft.DataColumn(
                ft.Text(
                    "Ações",
                    weight=ft.FontWeight.BOLD,
                )
            ),
        ],
        rows=rows,
        expand=True,
    )


    # BILBO_LLM_HORIZONTAL_SCROLL
    tabela.expand = False
    tabela_scroll = ft.Row(
        controls=[tabela],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )


    async def _delete_selected_results(e):
        del e

        selected = [
            str(checkbox.data)
            for checkbox in result_checkboxes
            if checkbox.value
        ]

        if not selected:
            await log_message(
                page,
                "Selecione ao menos um resultado para excluir.",
            )
            return

        async def _cancel_delete(event):
            del event
            confirmation.open = False
            page.update()

        async def _confirm_delete(event):
            del event
            deleted = []
            errors = []

            try:
                async with httpx.AsyncClient(
                    timeout=120.0
                ) as client:
                    for sheet_name in selected:
                        response = await client.delete(
                            "http://localhost:8890/llm/"
                            + quote(sheet_name, safe=""),
                            headers=headers,
                        )

                        if response.status_code == 200:
                            deleted.append(sheet_name)
                        else:
                            errors.append(
                                f"{sheet_name}: "
                                f"{response.status_code} "
                                f"{response.text}"
                            )

                confirmation.open = False
                page.update()

                if deleted:
                    await log_message(
                        page,
                        "Resultados LLM excluídos: "
                        + ", ".join(deleted),
                    )

                if errors:
                    await log_message(
                        page,
                        "Falhas ao excluir resultados: "
                        + " | ".join(errors),
                    )

                await _refresh_stage_counts_if_needed()
                await show_llm(
                    page,
                    token,
                    user_id,
                    container_amostras,
                    container_pre_visualizacao,
                    refresh_stage_counts,
                )
            except Exception as ex:
                await log_message(
                    page,
                    f"Erro ao excluir resultados LLM: {ex}",
                )

        confirmation = ft.AlertDialog(
            modal=True,
            title=ft.Text("Excluir resultados?"),
            content=ft.Column(
                tight=True,
                controls=[
                    ft.Text(
                        "Serão removidas as interpretações:"
                    ),
                    ft.Text(
                        ", ".join(selected),
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(
                        "A clusterização e o banco RAG "
                        "serão preservados.",
                    ),
                ],
            ),
            actions=[
                ft.TextButton(
                    "Cancelar",
                    on_click=_cancel_delete,
                ),
                ft.ElevatedButton(
                    "Excluir",
                    icon="delete",
                    color="white",
                    bgcolor="red",
                    on_click=_confirm_delete,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        page.open(confirmation)
        page.update()


    async def _initialize_rag(e):
        del e
        await log_message(
            page,
            "Iniciando download e restauração do banco RAG compartilhado.",
        )
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    "http://localhost:8890/llm/rag/initialize",
                    headers=headers,
                )

            if response.status_code not in (200, 202):
                await log_message(
                    page,
                    f"Falha ao iniciar banco RAG: {response.status_code} - {response.text}",
                )
                return

            body = response.json()
            job_id = body.get("job_id")
            if job_id:
                await log_message(
                    page,
                    f"Inicialização RAG enfileirada (job {job_id}).",
                )
                result = await wait_for_job(token, job_id)
                if result.get("status") == "COMPLETED":
                    await log_message(
                        page,
                        "Banco RAG instalado e validado com sucesso.",
                    )
                else:
                    await log_message(
                        page,
                        "Inicialização RAG terminou com status "
                        f"{result.get('status')}: {result.get('error_message', '')}",
                    )
            else:
                await log_message(
                    page,
                    body.get("message", "Banco RAG já inicializado."),
                )

            await show_llm(
                page,
                token,
                user_id,
                container_amostras,
                container_pre_visualizacao,
                refresh_stage_counts,
            )
        except Exception as ex:
            await log_message(
                page,
                f"Erro durante inicialização do banco RAG: {ex}",
            )

    async def _start_llm(e):
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        if not rag_info.get("ready"):
            await log_message(page, "Inicialize o banco RAG antes de executar a interpretação.")
            return
        try:
            # BILBO_LLM_HIDE_ACTIVE_SHEETS
            async with httpx.AsyncClient() as client:
                resp_deg = await client.get(
                    "http://localhost:8890/deg/sheets",
                    headers=headers,
                )
                resp_llm = await client.get(
                    "http://localhost:8890/llm/contrasts",
                    headers=headers,
                )
                resp_stages = await client.get(
                    "http://localhost:8890/samples/stages/10",
                    headers=headers,
                )

            if resp_deg.status_code != 200:
                await log_message(
                    page,
                    f"Erro ao buscar abas DEG: {resp_deg.text}",
                )
                return

            if resp_llm.status_code != 200:
                await log_message(
                    page,
                    f"Erro ao buscar entradas LLM: {resp_llm.text}",
                )
                return

            if resp_stages.status_code != 200:
                await log_message(
                    page,
                    "Erro ao verificar interpretações em andamento: "
                    + resp_stages.text,
                )
                return

            sheets = resp_deg.json().get("sheets", [])

            completed_sheets = {
                item.get("sheet")
                for item in resp_llm.json().get(
                    "contrasts",
                    [],
                )
                if item.get("sheet")
            }

            active_sheets = {
                item.get("name")
                for item in resp_stages.json()
                if item.get("name")
                and str(
                    item.get("status") or ""
                ).upper() in {"PENDING", "RUNNING"}
            }

            unavailable_sheets = (
                completed_sheets | active_sheets
            )

            to_run = [
                sheet
                for sheet in sheets
                if sheet not in unavailable_sheets
            ]

            if not to_run:
                if active_sheets:
                    await log_message(
                        page,
                        "Nenhum contraste disponível. "
                        "Há interpretações PENDING ou RUNNING: "
                        + ", ".join(sorted(active_sheets)),
                    )
                else:
                    await log_message(
                        page,
                        "Todas as abas já possuem interpretação LLM.",
                    )
                return

            # BILBO_LLM_MODAL_SELECT_ALL
            checkboxes = [
                ft.Checkbox(
                    label=sheet_name,
                    value=False,
                    data=sheet_name,
                )
                for sheet_name in to_run
            ]

            def _toggle_all_llm(e):
                checked = bool(e.control.value)

                for checkbox in checkboxes:
                    checkbox.value = checked

                page.update()

            def _sync_all_llm(e):
                del e
                select_all_llm.value = (
                    bool(checkboxes)
                    and all(
                        bool(checkbox.value)
                        for checkbox in checkboxes
                    )
                )
                page.update()

            select_all_llm = ft.Checkbox(
                label="Selecionar todos",
                value=False,
                on_change=_toggle_all_llm,
            )

            for checkbox in checkboxes:
                checkbox.on_change = _sync_all_llm

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
                            # BILBO_LLM_LIVE_PROGRESS
                            seen_progress_lines = set()

                            async def _show_llm_progress(job_payload):
                                # BILBO_LLM_NESTED_PROGRESS
                                result_payload = job_payload.get('result') or {}
                                if not isinstance(result_payload, dict):
                                    result_payload = {}

                                progress_value = (
                                    job_payload.get('progress')
                                    or job_payload.get('progress_log')
                                    or job_payload.get('log')
                                    or result_payload.get('progress')
                                    or result_payload.get('progress_log')
                                    or result_payload.get('log')
                                    or ''
                                )

                                if isinstance(progress_value, list):
                                    progress_lines = [
                                        str(item)
                                        for item in progress_value
                                    ]
                                else:
                                    progress_lines = str(
                                        progress_value
                                    ).splitlines()

                                for progress_line in progress_lines:
                                    progress_line = progress_line.strip()

                                    if (
                                        not progress_line
                                        or progress_line
                                        in seen_progress_lines
                                    ):
                                        continue

                                    seen_progress_lines.add(
                                        progress_line
                                    )

                                    await log_message(
                                        page,
                                        progress_line,
                                    )

                            # BILBO_LLM_UNBOUNDED_WAIT
                            result = await wait_for_job(
                                token,
                                job_id,
                                timeout=None,
                                on_update=_show_llm_progress,
                            )
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
                content=ft.Column(
                    controls=[
                        select_all_llm,
                        ft.Divider(height=1),
                        *checkboxes,
                    ],
                    scroll=ft.ScrollMode.AUTO,
                ),
                actions=[ft.TextButton("Cancelar", on_click=_cancel), ft.ElevatedButton("Iniciar", on_click=_confirm)],
                actions_alignment="end",
            )

            page.open(dlg)
            page.update()

        except Exception as ex:
            await log_message(page, f"Erro ao preparar modal LLM: {ex}")

    rag_ready = bool(rag_info.get("ready"))
    rag_state = str(rag_info.get("state", "unknown"))
    points = rag_info.get("points_count")
    percent = rag_info.get("percent")

    if rag_ready:
        rag_label = f"RAG pronto — {points or 0} chunks indexados"
        rag_color = "green"
    elif rag_state == "downloading" and percent is not None:
        rag_label = f"Baixando banco RAG — {percent}%"
        rag_color = "orange"
    elif rag_state in {"extracting", "validating", "restoring"}:
        rag_label = f"Preparando banco RAG — {rag_state}"
        rag_color = "orange"
    elif rag_state == "failed":
        rag_label = f"Falha no banco RAG: {rag_info.get('error', '')}"
        rag_color = "red"
    else:
        rag_label = "Banco RAG não instalado"
        rag_color = "orange"

    rag_panel = ft.Container(
        padding=12,
        border=ft.border.all(1, rag_color),
        border_radius=10,
        content=ft.Row(
            controls=[
                ft.Icon(
                    "check_circle" if rag_ready else "database",
                    color=rag_color,
                ),
                ft.Text(rag_label, expand=True),
                ft.ElevatedButton(
                    "Inicializar banco RAG",
                    on_click=_initialize_rag,
                    disabled=rag_ready
                    or rag_state in {
                        "downloading",
                        "extracting",
                        "validating",
                        "restoring",
                    },
                ),
            ],
        ),
    )

    container_amostras.content.controls = [
        rag_panel,
        tabela_scroll,
        create_button(
            "Excluir resultados",
            _delete_selected_results,
            color="red",
            expand=False,
        ),
        create_button(
            "Executar Interpretação e RAG",
            _start_llm,
            color="primary",
            expand=False,
        ),
    ]
    page.update()
