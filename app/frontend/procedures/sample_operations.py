import flet as ft
import httpx
import logging
import asyncio
from .jobs import wait_for_job
from .utils import log_message
from .translations import t
from .quality_analysis import update_quality_analysis_table
from ..components.general_components import create_table  # Import reusable table

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track the WebSocket connection
first_check_done = False

tabela_amostras = create_table(
    columns=[
        ft.DataColumn(ft.Text("Identificação")),
        ft.DataColumn(ft.Text("Tamanho")),
        ft.DataColumn(ft.Text("Status")),
        ft.DataColumn(ft.Checkbox()),  # Add checkbox to the column header
    ],
    rows=[],
)

async def adicionar_amostra(e, page, token, container_menu_direita, tabela_amostras_local):
    async def inserir_sra_na_fila(sra_codes):
        sra_codes = [code.strip() for code in sra_codes.split(",") if code.strip()]
        if not sra_codes:
            logger.error("Insira um ou mais códigos SRA válidos.")
            return
        dlg_modal_adicionar_amostra.open = False
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://bioinfo-container:8890/samples/",
                    json={"sra_codes": sra_codes, "size": "Unknown"},
                    headers=headers,
                )
                if response.status_code == 200:
                    samples = response.json()
                    for sample in samples:
                        logger.info(f"Amostra {sample['sra_code']} adicionada com sucesso!")
                elif response.status_code == 400:
                    try:
                        detail = response.json().get("detail", "")
                    except Exception:
                        detail = response.text
                    logger.error(f"Erro ao adicionar amostras: {detail}")
                    await log_message(page, f"Erro ao adicionar amostras: {detail}")
                else:
                    logger.error(f"Erro ao adicionar amostras: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
        page.update()

    sra_code_field = ft.TextField(
        hint_text=t("sample_sra_hint", page.session.get("lang") or "pt"),
        border_radius=ft.border_radius.all(4),
        multiline=False,
        min_lines=1,
    )

    async def inserir_sra_na_fila_handler(e):
        await inserir_sra_na_fila(sra_code_field.value)

    dlg_modal_adicionar_amostra = ft.AlertDialog(
        title=ft.Text(t("sample_add_sra", page.session.get("lang") or "pt")),
        content=sra_code_field,
        actions=[
            ft.TextButton(t("sample_submit", page.session.get("lang") or "pt"), on_click=inserir_sra_na_fila_handler, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=500, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER
    )
    
    page.open(dlg_modal_adicionar_amostra)

async def excluir_amostras_selecionadas(e, page, token, container_menu_direita, tabela_amostras_local):
    async def confirmar_exclusao():
        amostras_selecionadas_para_exclusao = []
        page.close(dlg_modal_excluir_amostra)
        for row in tabela_amostras_local.rows:
            if isinstance(row.cells[3].content, ft.Checkbox) and not row.cells[3].content.disabled and row.cells[3].content.value:
                sample_name = row.cells[0].content.value
                if isinstance(sample_name, str):
                    amostras_selecionadas_para_exclusao.append(sample_name)

        if not amostras_selecionadas_para_exclusao:
            logger.error("Nenhuma amostra selecionada para exclusão.")
            return

        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        deleted_names = set()
        try:
            async with httpx.AsyncClient() as client:
                for sample_name in amostras_selecionadas_para_exclusao:
                    if sample_name in deleted_names:
                        continue
                    response = await client.delete(f"http://bioinfo-container:8890/samples/{sample_name}", headers=headers)
                    if response.status_code == 200:
                        result = response.json()
                        deleted_names.update(result.get("deleted_names") or [sample_name])
                        sample_code = result.get("sra_code") or sample_name
                        logger.info("Amostra %s excluída com sucesso!", sample_code)
                        await log_message(page, f"Amostra {sample_code} excluída com sucesso!")
                    else:
                        logger.error("Erro ao excluir amostra %s: %s - %s", sample_name, response.status_code, response.text)
                        await log_message(page, f"Erro ao excluir amostra {sample_name}: {response.status_code} - {response.text}")
            await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
            
        except Exception as e:
            logger.error(f"Erro ao excluir amostras: {e}", exc_info=True)

    confirm_field = ft.TextField(
        hint_text=t("confirm_delete_hint", page.session.get("lang") or "pt"),
        border_radius=ft.border_radius.all(4),
        multiline=False,
        expand=1
    )

    async def confirmar_exclusao_handler(e):
        if confirm_field.value == 'Confirmar':
            await confirmar_exclusao()

    dlg_modal_excluir_amostra = ft.AlertDialog(
        title=ft.Text(t("confirm_delete", page.session.get("lang") or "pt")),
        content=confirm_field,
        actions=[
            ft.TextButton(t("delete_selected", page.session.get("lang") or "pt"), on_click=confirmar_exclusao_handler, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=200, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_excluir_amostra)

async def make_request(method, url, headers=None, json=None, params=None):
    """Helper function to make HTTP requests."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=headers, json=json, params=params)
            response.raise_for_status()
            return response
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise


def _get_terminal_listview(page):
    container_terminal = getattr(page, "container_terminal", None)
    if container_terminal is None:
        return None
    if isinstance(container_terminal, ft.ListView):
        return container_terminal
    content = getattr(container_terminal, "content", None)
    if isinstance(content, ft.ListView):
        return content
    return None

async def atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local):
    lang = page.session.get("lang") or "pt"
    for column, key in zip(tabela_amostras.columns,
                           ("table_identification", "table_size", "table_status")):
        column.label.value = t(key, lang)
    global first_check_done
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    if not first_check_done:
        await make_request("POST", "http://bioinfo-container:8890/stages/", headers=headers)
        first_check_done = True

    response = await make_request("GET", "http://bioinfo-container:8890/samples/", headers=headers)
    samples = response.json()

    async def toggle_select_all(e):
        for row in tabela_amostras_local.rows:
            if not row.cells[3].content.disabled:
                row.cells[3].content.value = e.control.value
        page.update()

    tabela_amostras_local.rows.clear()
    tabela_amostras_local.columns[3] = ft.DataColumn(ft.Checkbox(on_change=toggle_select_all))
    for sample in samples:
        lang = page.session.get("lang") or "pt"
        display_size = t("sra_size_pending", lang) if str(sample.get("size") or "").lower() in ("unknown", "none", "") else sample["size"]
        display_status = {"PENDING": t("drive_queued", lang), "RUNNING": t("status_running", lang)}.get(str(sample.get("status") or "").upper(), sample["status"])
        
        async def download_sample_file(e, sample_name=sample["name"]):
            try:
                download_url = f"http://localhost:8890/download/obtencao/{sample_name}?token={token}"
                page.launch_url(download_url)
                await log_message(page, f"Download iniciado para {sample_name}")
                
            except Exception as e:
                logger.error(f"Erro no download de {sample_name}: {e}")
                await log_message(page, f"Erro no download de {sample_name}: {str(e)}")
        
        # Show download button only when sample status is Completed
        actions = []
        try:
            status = (sample.get("status") or "").lower()
        except Exception:
            status = ""

        if status == "completed":
            actions.append(ft.IconButton(
                icon="download",
                tooltip="Baixar arquivo da amostra",
                on_click=download_sample_file
            ))

        tabela_amostras_local.rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sample["name"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(display_size, style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(display_status, style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Checkbox()),
                    ft.DataCell(ft.Row(actions)),
                ],
            )
        )

    # Drive imports are jobs until both FASTQ files pass verification. Show
    # their live state without presenting an incomplete file as a ready sample.
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            drive_response = await client.get("http://bioinfo-container:8890/drive/jobs", headers=headers)
            drive_response.raise_for_status()
            drive_jobs = drive_response.json()
        lang = page.session.get("lang") or "pt"
        for job in drive_jobs:
            if job["status"] not in ("PENDING", "RUNNING"):
                continue
            progress = job.get("progress") or {}
            status_key = "drive_queued" if job["status"] == "PENDING" else "drive_downloading"
            status_text = t(status_key, lang)
            if job["status"] == "RUNNING" and progress.get("total"):
                mate = "R2" if str(progress.get("file", "")).endswith("_2.fastq.gz") else "R1"
                done = int(progress.get("bytes", 0)) / 1024**3
                total = int(progress["total"]) / 1024**3
                status_text += f" {mate} ({done:.1f}/{total:.1f} GiB)"
            tabela_amostras_local.rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(f"Drive: {job['base']}", size=12)),
                ft.DataCell(ft.Text(f"{job['size'] / 1024**3:.1f} GiB", size=12)),
                ft.DataCell(ft.Text(status_text, size=12)),
                ft.DataCell(ft.Checkbox(disabled=True)),
                ft.DataCell(ft.Row([])),
            ]))
    except Exception as exc:
        logger.warning("Could not load active Drive imports: %s", exc)

    stage_counts = {}
    # Fetch counts for stages 1..10
    for stage_id in range(1, 11):
        try:
            response = await make_request("GET", f"http://bioinfo-container:8890/samples/stages/{stage_id}", headers=headers)
            stage_rows = response.json()
            stage_counts[stage_id] = len(stage_rows)
        except Exception:
            stage_counts[stage_id] = 0



    # Análise Diferencial: contar resultados realmente produzidos.
    # Cada aba de DEG.xlsx corresponde a um resultado de contraste.
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://bioinfo-container:8890/results/deg_sheets",
                headers=headers,
            )
            if resp.status_code == 200:
                stage_counts[7] = len(resp.json().get("sheets", []))
            else:
                stage_counts[7] = 0
    except Exception:
        stage_counts[7] = 0

    # Map table rows order to corresponding stage ids. If UI order changes, update this map accordingly.
    stage_map = [1, 2, 3, 4, 5, 6, 8, 7, 9, 10]
    for i, row in enumerate(container_menu_direita.content.controls[0].rows):
        mapped_stage = stage_map[i] if i < len(stage_map) else (i + 1)
        # update the quantity cell (row.cells[1].content.content holds the Text)
        try:
            row.cells[1].content.content.value = str(stage_counts.get(mapped_stage, 0))
        except Exception:
            # fallback if structure differs
            try:
                row.cells[1].content.value = str(stage_counts.get(mapped_stage, 0))
            except Exception:
                pass

    page.update()

async def atualizar_tabela_por_estagio(e, page, token, stage_id, tabela_amostras_local, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://bioinfo-container:8890/samples/stages/{stage_id}", headers=headers)
        if response.status_code == 200:
            samples = response.json()
            tabela_amostras_local.rows.clear()
            for sample in samples:
                
                async def download_sample_file(e, sample_name=sample["name"]):
                    try:
                        download_url = f"http://localhost:8890/download/obtencao/{sample_name}?token={token}"
                        page.launch_url(download_url)
                        await log_message(page, f"Download iniciado para {sample_name}")
                        
                    except Exception as e:
                        logger.error(f"Erro no download de {sample_name}: {e}")
                        await log_message(page, f"Erro no download de {sample_name}: {str(e)}")
                
                tabela_amostras_local.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(sample["name"] or sample["sra_code"], style=ft.TextStyle(size=12))),
                            ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                            ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                            ft.DataCell(ft.Checkbox()),
                            # Show download button only when sample status is Completed
                            (ft.DataCell(ft.Row([ft.IconButton(icon="download", tooltip="Baixar arquivo da amostra", on_click=download_sample_file)])) if ((sample.get("status") or "").lower() == "completed") else ft.DataCell(ft.Row([]))),
                        ],
                    )
                )
            page.update()
            if stage_id == 2:
                await update_quality_analysis_table(page, token, user_id)
        else:
            logger.error(f"Erro ao atualizar tabela por estágio: {response.status_code} - {response.text}")

async def baixar_amostras(e, page, token, container_menu_direita, tabela_amostras_local):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://bioinfo-container:8890/samples/pending_count", headers=headers)
            if response.status_code == 200:
                pending_count = response.json().get("pending_count", 0)
                if pending_count == 0:
                    logger.info("No pending samples to download.")
                    await log_message(page, "No pending samples to download.")
                    return
                for _ in range(pending_count):
                    response = await client.post("http://bioinfo-container:8890/samples/download", headers=headers)
                    if response.status_code in (200, 202):
                        logger.info("Download enfileirado!")
                        body = response.json()
                        sample_name = body.get("sample_name", "Unknown")
                        job_id = body.get("job_id")
                        await log_message(page, f"Iniciando o download da amostra {sample_name}.")

                        terminal_listview = _get_terminal_listview(page)
                        lang = page.session.get("lang") or "pt"
                        progress_bar = ft.ProgressBar(value=None, width=260, color="green")
                        progress_title = ft.Text(f"Download {sample_name}: {t('drive_queued', lang)}")
                        progress_detail = ft.Text(t("sra_waiting_worker", lang), size=11, color="black54")
                        progress_container = ft.Container(
                            border=ft.border.all(1, "black12"),
                            border_radius=8,
                            padding=ft.padding.symmetric(horizontal=10, vertical=8),
                            content=ft.Column(
                                spacing=4,
                                controls=[progress_title, progress_bar, progress_detail],
                            ),
                        )
                        progress_visible = terminal_listview is not None
                        if progress_visible:
                            terminal_listview.controls.append(progress_container)

                        last_table_status = None

                        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                        page.update()

                        async def update_download_progress(job_payload):
                            nonlocal last_table_status
                            if not progress_visible:
                                return

                            status = str(job_payload.get("status") or "")
                            result_payload = job_payload.get("result") or {}
                            progress_percent = result_payload.get("progress_percent")
                            progress_message = str(result_payload.get("progress_message") or "").strip()
                            progress_phase = str(result_payload.get("progress_phase") or "").strip()
                            error_message = str(job_payload.get("error_message") or "").strip()

                            try:
                                percent = max(0.0, min(float(progress_percent), 100.0))
                            except (TypeError, ValueError):
                                percent = None
                            if status == "RUNNING" and percent is not None and percent >= 100.0:
                                percent = 99.0

                            if status == "COMPLETED":
                                percent = 100.0
                                progress_bar.color = "green"
                            elif status in {"FAILED", "CANCELED"}:
                                progress_bar.color = "red"

                            progress_bar.value = percent / 100.0 if percent is not None else None
                            progress_title.value = f"Download {sample_name}: {percent:.1f}%" if percent is not None else f"Download {sample_name}: {t('drive_queued', lang) if status == 'PENDING' else t('status_running', lang)}"

                            if status == "RUNNING" and progress_phase and percent is not None:
                                progress_detail.value = f"{t('sra_phase', lang)} {progress_phase}: {percent:.1f}%"
                            elif progress_message:
                                progress_detail.value = progress_message
                            elif status == "PENDING":
                                progress_detail.value = t("sra_waiting_worker", lang)
                            elif status == "RUNNING":
                                progress_detail.value = t("sra_downloading", lang)
                            elif status == "COMPLETED":
                                progress_detail.value = t("sra_completed", lang)
                            elif status == "FAILED":
                                progress_detail.value = error_message or t("sra_failed", lang)
                            elif status == "CANCELED":
                                progress_detail.value = t("sra_canceled", lang)

                            page.update()
                            if status != last_table_status:
                                last_table_status = status
                                await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)

                        if job_id:
                            result = await wait_for_job(token, job_id, on_update=update_download_progress)
                            final_status = result.get("status")
                            await log_message(page, f"Download da amostra {sample_name} finalizado com status {final_status}.")

                        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                        page.update()
                    elif response.status_code == 404:
                        logger.error(f"Download error: {response.status_code} - {response.text}")
                    else:
                        logger.error(f"Download error: {response.status_code} - {response.text}")
            else:
                logger.error(f"Failed to get pending samples count: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
    page.update()

async def atualizar_tamanho_amostras(page, token, sra_code, container_menu_direita):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("http://bioinfo-container:8890/samples/calculate_size", params={"sra_code": sra_code}, headers=headers)
            if response.status_code == 200:
                logger.info("Tamanho das amostras atualizado com sucesso!")
                await atualizar_tabela(page, token, container_menu_direita, tabela_amostras)
            else:
                logger.error(f"Erro ao atualizar tamanho das amostras: {response.status_code} - {response.text}")
                await log_message(page, f"Erro ao atualizar tamanho das amostras: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        await log_message(page, f"An error occurred: {e}")
