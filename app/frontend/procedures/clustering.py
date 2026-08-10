import asyncio

import flet as ft
import httpx

from ..components.general_components import create_button
from .jobs import wait_for_job
from .utils import log_message



async def wait_for_clustering_job_with_progress(
    page,
    token,
    job_id,
):
    """Aguarda o job e envia seu progresso ao terminal."""
    headers = {
        "Authorization": f"Bearer {token}",
        "ngrok-skip-browser-warning": "true",
    }
    cursor = "0:0"
    last_message = None

    job_task = asyncio.create_task(
        wait_for_job(token, job_id)
    )

    async def fetch_progress(client):
        nonlocal cursor, last_message

        response = await client.get(
            f"http://localhost:8890/pipeline/jobs/{job_id}/progress",
            headers=headers,
            params={"cursor": cursor},
            timeout=20,
        )

        if response.status_code != 200:
            return

        body = response.json()
        cursor = body.get("cursor", cursor)

        for raw_line in body.get("lines", []):
            message = str(raw_line).strip()

            if message.startswith("[") and "] " in message:
                message = message.split("] ", 1)[1].strip()

            if message.startswith("PROGRESS:"):
                message = message.split(":", 1)[1].strip()

            if not message or message == last_message:
                continue

            last_message = message
            await log_message(page, message)

    async with httpx.AsyncClient() as client:
        while not job_task.done():
            try:
                await fetch_progress(client)
            except Exception:
                pass

            await asyncio.sleep(1.5)

        try:
            await fetch_progress(client)
        except Exception:
            pass

    return await job_task


async def show_clustering(
    page, token, user_id, container_amostras, container_pre_visualizacao, refresh_stage_counts=None
):
    """Frontend-only: lista figuras de cluster já geradas em users/{user_id}/DEG
    e inicia o pipeline completo de clusterização, interpretação e RAG.
    """
    # Fetch clustering entries from backend DB (stage_id=9)
    files = []
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}

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
            resp = await client.get("http://localhost:8890/samples/stages/9", headers=headers)
        if resp.status_code != 200:
            await log_message(page, f"Erro ao buscar entradas de clustering: {resp.text}")
            resp_data = []
        else:
            resp_data = resp.json()
        # resp_data is a list of sample stage dicts with 'name' and optional 'size'
        for item in resp_data:
            files.append(
                {
                    "sheet": item.get("name"),
                    "file": "cluster.png",
                    "metrics": "metrics.png",
                    "size": item.get("size", ""),
                }
            )
    except Exception as ex:
        await log_message(page, f"Erro ao buscar entradas de clustering: {ex}")

    async def _view_image(e, url):
        try:
            img = ft.Image(src=url, fit=ft.ImageFit.CONTAIN)
            container_pre_visualizacao.content = ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, controls=[img]
            )
            page.update()
        except Exception as ex:
            await log_message(page, f"Erro ao abrir imagem: {ex}")

    async def display_clustering_image(page, token, user_id, sheet, filename):
        """Fetch image bytes from backend and return an InteractiveViewer control."""
        try:
            headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
            url = f"http://localhost:8890/clustering/file?file={filename}&sheet={sheet}"
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return ft.Column(
                    controls=[
                        ft.Icon("error_outline", color="red"),
                        ft.Text(
                            f"Não foi possível abrir esta visualização "
                            f"(HTTP {resp.status_code}).",
                            color="red",
                            text_align=ft.TextAlign.CENTER,
                        ),
                        ft.Text(
                            "Use o seletor acima para tentar outra figura "
                            "ou feche o visualizador.",
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                )
            data = resp.content
            import base64

            image_base64 = base64.b64encode(data).decode("utf-8")
            image_control = ft.Image(src_base64=image_base64, fit=ft.ImageFit.CONTAIN, expand=True)
            interactive_viewer = ft.InteractiveViewer(
                min_scale=0.5,
                max_scale=15,
                boundary_margin=ft.margin.all(10),
                content=image_control,
                constrained=True,
            )
            return interactive_viewer
        except Exception as ex:
            await log_message(page, f"Erro ao criar viewer da imagem: {ex}")
            return ft.Text(f"Erro: {ex}", color="red")

    async def _start_clustering(e):
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}

        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8890/clustering/contrasts", headers=headers)
            if resp.status_code != 200:
                await log_message(page, f"Erro ao buscar contrasts: {resp.text}")
                return
            data = resp.json().get("contrasts", [])

        # Build modal with checkboxes for contrasts
        checkboxes = []
        for c in data:
            label = f"{c['sheet']} {'(ok)' if c.get('clustered') else '(nenhuma clusterização)'}"
            cb = ft.Checkbox(label=label, value=False, data=c["sheet"])
            checkboxes.append(cb)

        async def _confirm_start(e):
            selected = [cb.data for cb in checkboxes if cb.value]
            if not selected:
                await log_message(page, "Nenhum contraste selecionado.")
                return

            payload = {"sheets": selected}
            # Allow long-running request: set a high timeout (or None to disable)
            async with httpx.AsyncClient(timeout=None) as client:
                resp = await client.post("http://localhost:8890/clustering/run", json=payload, headers=headers)
            if resp.status_code not in (200, 202):
                await log_message(page, f"Erro ao iniciar clusterização: {resp.text}")
            else:
                body = resp.json()
                job_id = body.get("job_id")
                if job_id:
                    await log_message(page, f"Clusterização enfileirada (job {job_id}).")
                    result = await wait_for_clustering_job_with_progress(page, token, job_id)
                    status = result.get("status")
                    if status == "COMPLETED":
                        await log_message(page, "Clusterização, interpretação e RAG concluídos com sucesso.")
                    else:
                        await log_message(page, f"Clusterização finalizada com status {status}.")
                else:
                    await log_message(page, "Clusterização iniciada.")
                await _refresh_stage_counts_if_needed()
                await show_clustering(
                    page, token, user_id, container_amostras, container_pre_visualizacao, refresh_stage_counts
                )
            dlg.open = False
            page.update()

        async def _cancel(e):
            try:
                dlg.open = False
            except Exception:
                pass
            page.update()

        dlg = ft.AlertDialog(
            title=ft.Text("Iniciar Clusterização Semântica"),
            content=ft.Column(controls=checkboxes),
            actions=[
                ft.TextButton("Cancelar", on_click=_cancel),
                ft.ElevatedButton("Iniciar Clusterização", on_click=_confirm_start),
            ],
            actions_alignment="end",
        )
        page.open(dlg)
        page.update()

    if not files:
        container_amostras.content.controls = [
            ft.Column(
                controls=[
                    ft.Text("Nenhuma figura de cluster encontrada."),
                    create_button("Executar Pipeline Completo", _start_clustering, color="primary", expand=False),
                ]
            )
        ]
    else:
        rows = []
        result_checkboxes = []

        async def _sync_all_results(e):
            select_all_results.value = (
                bool(result_checkboxes)
                and all(
                    checkbox.value
                    for checkbox in result_checkboxes
                )
            )
            page.update()

        async def _toggle_all_results(e):
            selected = bool(e.control.value)

            for checkbox in result_checkboxes:
                checkbox.value = selected

            page.update()

        select_all_results = ft.Checkbox(
            value=False,
            tooltip="Selecionar todas as clusterizações",
            on_change=_toggle_all_results,
        )

        async def _delete_selected(e):
            selected = [
                checkbox.data
                for checkbox in result_checkboxes
                if checkbox.value
            ]

            if not selected:
                await log_message(
                    page,
                    "Nenhuma clusterização selecionada.",
                )
                return

            async def _cancel_delete(ev):
                dialog.open = False
                page.update()

            async def _confirm_delete(ev):
                dialog.open = False
                page.update()

                deleted = []
                failures = []

                async with httpx.AsyncClient(
                    timeout=60.0
                ) as client:
                    for sheet_name in selected:
                        try:
                            response = await client.delete(
                                (
                                    "http://localhost:8890"
                                    f"/clustering/{sheet_name}"
                                ),
                                headers=headers,
                            )

                            if response.status_code == 200:
                                deleted.append(sheet_name)
                            else:
                                failures.append(
                                    (
                                        sheet_name,
                                        response.status_code,
                                        response.text,
                                    )
                                )
                        except Exception as error:
                            failures.append(
                                (
                                    sheet_name,
                                    "exception",
                                    str(error),
                                )
                            )

                if deleted:
                    await log_message(
                        page,
                        (
                            "Clusterizações excluídas: "
                            + ", ".join(deleted)
                        ),
                    )

                for (
                    sheet_name,
                    status,
                    detail,
                ) in failures:
                    await log_message(
                        page,
                        (
                            "Erro ao excluir "
                            f"{sheet_name}: "
                            f"{status} - {detail}"
                        ),
                    )

                await _refresh_stage_counts_if_needed()

                await show_clustering(
                    page,
                    token,
                    user_id,
                    container_amostras,
                    container_pre_visualizacao,
                    refresh_stage_counts,
                )

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text(
                    "Excluir clusterizações"
                ),
                content=ft.Text(
                    (
                        "Confirma a exclusão de "
                        f"{len(selected)} resultado(s)?\n\n"
                        + "\n".join(selected)
                    )
                ),
                actions=[
                    ft.TextButton(
                        "Cancelar",
                        on_click=_cancel_delete,
                    ),
                    ft.ElevatedButton(
                        "Excluir",
                        on_click=_confirm_delete,
                    ),
                ],
                actions_alignment="end",
            )

            page.open(dialog)
            page.update()

        for entry in files:
            sheet = entry.get("sheet", "")

            result_checkbox = ft.Checkbox(
                value=False,
                data=sheet,
                on_change=_sync_all_results,
            )
            result_checkboxes.append(
                result_checkbox
            )

            # build URLs for cluster and metrics
            # icon buttons: view (opens dropdown+viewer+download) and delete (call backend)
            async def _open_viewer(e, sheet_name=sheet):
                # Permite voltar mesmo quando a imagem retorna erro.
                previous_preview_content = container_pre_visualizacao.content

                dropdown = ft.Dropdown(
                    options=[ft.dropdown.Option("Cluster"), ft.dropdown.Option("Metrics")],
                    value="Cluster",
                )

                img_placeholder = ft.Container(expand=True, content=ft.Text("Carregando..."))

                async def on_change(e):
                    sel = e.control.value
                    filename = "cluster.png" if sel == "Cluster" else "metrics.png"
                    viewer = await display_clustering_image(page, token, user_id, sheet_name, filename)
                    img_placeholder.content = viewer
                    page.update()

                dropdown.on_change = on_change

                async def close_viewer(e):
                    container_pre_visualizacao.content = (
                        previous_preview_content
                    )
                    page.update()

                close_icon_btn = ft.IconButton(
                    icon="close",
                    tooltip="Fechar visualizador",
                    on_click=close_viewer,
                )

                async def download_current_image(e):
                    try:
                        if not dropdown.value:
                            await log_message(page, "Nenhuma figura selecionada para download.")
                            return
                        import urllib.parse

                        fname = "cluster.png" if dropdown.value == "Cluster" else "metrics.png"
                        fname_enc = urllib.parse.quote(fname, safe="")
                        download_url = (
                            f"http://localhost:8890/clustering/file?file={fname_enc}&sheet={sheet_name}&token={token}"
                        )
                        page.launch_url(download_url)
                    except Exception as ex:
                        await log_message(page, f"Erro ao iniciar download da figura: {ex}")

                download_icon_btn = ft.IconButton(
                    icon="file_download", tooltip="Baixar figura", on_click=download_current_image
                )

                # load default
                img_placeholder.content = await display_clustering_image(
                    page, token, user_id, sheet_name, "cluster.png"
                )

                # Place the dropdown + download + image inside the preview container
                container_pre_visualizacao.content = ft.Container(
                    expand=True,
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                [
                                    dropdown,
                                    ft.Container(width=8),
                                    download_icon_btn,
                                    close_icon_btn,
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                            ),
                            ft.Container(height=10),
                            img_placeholder,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=0,
                    ),
                )

                page.update()

            async def _delete_sheet(e, sheet_name=sheet):
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.delete(
                            f"http://localhost:8890/clustering/{sheet_name}",
                            headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
                        )
                    if resp.status_code == 200:
                        await log_message(page, f"Clusterização {sheet_name} excluída.")
                        await _refresh_stage_counts_if_needed()
                        await show_clustering(
                            page, token, user_id, container_amostras, container_pre_visualizacao, refresh_stage_counts
                        )
                    else:
                        await log_message(
                            page, f"Erro ao excluir clusterização {sheet_name}: {resp.status_code} - {resp.text}"
                        )
                except Exception as ex:
                    await log_message(page, f"Erro ao excluir clusterização: {ex}")

            async def _open_cluster_report(e, sheet_name=sheet):
                try:
                    from urllib.parse import quote

                    report_url = (
                        "http://localhost:8890/clustering/report"
                        f"?sheet={quote(str(sheet_name))}"
                        f"&token={quote(str(token))}"
                    )
                    page.launch_url(report_url)
                except Exception as ex:
                    await log_message(
                        page,
                        f"Erro ao abrir detalhes da clusterização: {ex}",
                    )

            view_btn = ft.IconButton(
                icon="visibility",
                tooltip="Ver figuras",
                on_click=_open_viewer,
            )
            report_btn = ft.IconButton(
                icon="account_tree",
                tooltip="Explorar genes e clusters",
                on_click=_open_cluster_report,
            )

            rows.append(
                ft.DataRow(cells=[ft.DataCell(ft.Text(sheet)), ft.DataCell(result_checkbox), ft.DataCell(ft.Row(controls=[view_btn, report_btn]))])
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
                ft.DataColumn(select_all_results),
                ft.DataColumn(
                    ft.Text(
                        "Actions",
                        weight=ft.FontWeight.BOLD,
                    )
                ),
            ],
            rows=rows,
            expand=False,
        )

        table_scroll = ft.Row(
            controls=[tabela],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            wrap=False,
        )

        container_amostras.content.controls = [
            table_scroll,
            create_button(
                "Excluir",
                _delete_selected,
                color="red",
                expand=False,
            ),
            create_button(
                "Executar Pipeline Completo",
                _start_clustering,
                color="primary",
                expand=False,
            ),
        ]

    page.update()
