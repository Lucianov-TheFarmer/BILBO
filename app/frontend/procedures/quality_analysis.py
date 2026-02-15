import flet as ft
import asyncio
import httpx
import logging
from .jobs import wait_for_job
from .utils import log_message
from .viewer import create_dropdown_menu, display_graph

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_tabela_amostras_qc(page, token):
    global tabela_amostras_qc
    
    async def toggle_select_all_qc(e):
        for row in tabela_amostras_qc.rows:
            row.cells[2].content.value = e.control.value
        page.update()

    tabela_amostras_qc = ft.DataTable(
        heading_row_color="primary",
        columns=[
            ft.DataColumn(ft.Text("Identificação", weight="bold")),
            ft.DataColumn(ft.Text("Status", weight="bold")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_qc)),
            ft.DataColumn(ft.Text("Ações", weight="bold")),
        ],
        rows=[],
    )
    return tabela_amostras_qc

async def update_quality_analysis_table(page, token, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://bioinfo-container:8000/quality_analysis/completed", headers=headers)
            if response.status_code == 200:
                samples = response.json()
                logger.info(f"Data received from backend: {samples}")
                tabela_amostras_qc.rows.clear()
                for sample in samples:
                    def view_sample_details_handler(e, s=sample["name"]):
                        asyncio.run(view_sample_details(page, token, s, user_id, analysis_type="QC"))
                    
                    async def download_handler(e, s=sample["name"]):
                        download_url = f"http://localhost:8000/download/qualidade1/{s}?token={token}"
                        page.launch_url(download_url)
                        await log_message(page, f"Download iniciado para {s}")


                    # Build actions: include 'view' and 'download' only when QC is completed
                    actions = []
                    try:
                        status = (sample.get("status") or "").lower()
                    except Exception:
                        status = ""

                    if status == "completed":
                        actions.append(ft.IconButton(icon="visibility", on_click=view_sample_details_handler))
                        actions.append(ft.IconButton(icon="download", on_click=download_handler))

                    tabela_amostras_qc.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(sample["name"] or sample["sra_code"], size=12)),
                                ft.DataCell(ft.Text(sample["status"], size=12)),
                                ft.DataCell(ft.Checkbox()),
                                ft.DataCell(ft.Row(actions)),
                            ],
                        )
                    )
                logger.info("Table updated successfully with new data.")
                page.update()
            else:
                logger.error(f"Erro ao obter amostras processadas: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred while updating the quality analysis table: {e}", exc_info=True)

async def view_sample_details(page, token, sample_name, user_id, analysis_type):
    dropdown_menu = create_dropdown_menu(page, token, sample_name, user_id, analysis_type)
    initial_graph = await display_graph(page, token, "Per base sequence quality", sample_name, user_id, analysis_type)
    # Find the preview container by key (container_preview) and update it
    for control in page.controls:
        if isinstance(control, ft.Row):
            for column in control.controls:
                if isinstance(column, ft.Column):
                    for container in column.controls:
                        if isinstance(container, ft.Container) and getattr(container, 'key', None) == "container_preview":
                            container.content.controls = [
                                ft.Container(
                                    expand=True,
                                    content=ft.Column(
                                        controls=[dropdown_menu, initial_graph]
                                    )
                                )
                            ]
                            page.update()
                            return

async def delete_quality_analysis_results(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    async def confirm_delete(e):
        selected_samples = []

        for row in tabela_amostras_qc.rows:
            if isinstance(row.cells[2].content, ft.Checkbox) and row.cells[2].content.value:
                sample_name = row.cells[0].content.value
                if isinstance(sample_name, str):
                    selected_samples.append(sample_name)

        if not selected_samples:
            logger.error("Nenhum resultado de análise selecionado.")
            return

        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                for sample_name in selected_samples:
                    response = await client.delete(f"http://bioinfo-container:8000/quality_analysis/{sample_name}", headers=headers)
                    if response.status_code == 200:
                        logger.info(f"Resultado da análise {sample_name} excluído com sucesso!")
                    else:
                        logger.error(f"Erro ao excluir resultado da análise {sample_name}: {response.status_code} - {response.text}")

            await update_quality_analysis_table(page, token, user_id)
            await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
            page.update()
        except Exception as e:
            logger.error(f"Erro ao excluir resultados de análise de qualidade: {e}", exc_info=True)

        dlg_modal_excluir_analise.open = False
        page.update()

    dlg_modal_excluir_analise = ft.AlertDialog(
        title=ft.Text("Confirmar exclusão"),
        content=ft.TextField(
            hint_text="Digite 'Confirmar' para excluir os resultados selecionados.",
            border_radius=4,
            multiline=False,
            expand=1
        ),
        actions=[
            ft.TextButton("Excluir", on_click=confirm_delete, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=200, height=40),
        ],
        actions_alignment="center",
    )

    page.open(dlg_modal_excluir_analise)

async def show_quality_analysis_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    samples = []

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response_stage_1 = await client.get("http://bioinfo-container:8000/samples/stages/1", headers=headers)
            if response_stage_1.status_code == 200:
                downloaded_samples = response_stage_1.json()
                logger.info(f"Amostras baixadas (stage_id=1): {downloaded_samples}")
            else:
                logger.error(f"Erro ao obter amostras baixadas: {response_stage_1.status_code} - {response_stage_1.text}")
                downloaded_samples = []

            response_stage_2 = await client.get("http://bioinfo-container:8000/samples/stages/2", headers=headers)
            if response_stage_2.status_code == 200:
                analyzed_samples = {sample["name"].replace(".html", ".fastq") for sample in response_stage_2.json()}
                logger.info(f"Amostras analisadas (stage_id=2): {analyzed_samples}")
            else:
                logger.error(f"Erro ao obter amostras analisadas: {response_stage_2.status_code} - {response_stage_2.text}")
                analyzed_samples = set()

            samples = [sample for sample in downloaded_samples if sample["name"] not in analyzed_samples]
            logger.info(f"Amostras disponíveis para análise de qualidade: {samples}")

    except Exception as e:
        logger.error(f"An error occurred while fetching samples: {e}", exc_info=True)

    if not samples:
        logger.warning("Nenhuma amostra disponível para análise de qualidade após o filtro.")
    else:
        logger.info(f"Número de amostras disponíveis para análise de qualidade: {len(samples)}")

    async def toggle_select_all(e):
        for row in tabela_analise_qualidade.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    async def start_quality_analysis(e):
        selected_samples = [row.cells[0].content.value for row in tabela_analise_qualidade.rows if row.cells[3].content.value]
        if not selected_samples:
            logger.error("Nenhuma amostra selecionada.")
            return
        await log_message(page, f"Iniciando análise de qualidade para {selected_samples}")
        dlg_modal_analise_qualidade.open = False
        page.update()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post("http://bioinfo-container:8000/quality_analysis/", json={"samples": selected_samples}, headers=headers)
                if response.status_code in (200, 202):
                    body = response.json()
                    job_id = body.get("job_id")
                    if job_id:
                        await log_message(page, f"QC enfileirado (job {job_id}).")
                        result = await wait_for_job(token, job_id)
                        status = result.get("status")
                        await log_message(page, f"QC finalizado com status {status}.")
                    logger.info(f"Análise de qualidade iniciada para {selected_samples} com sucesso!")
                    await update_quality_analysis_table(page, token, user_id)
                    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                    page.update()
                else:
                    logger.error(f"Erro ao iniciar análise de qualidade para {selected_samples}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"An error occurred while starting quality analysis: {e}", exc_info=True)

    tabela_analise_qualidade = ft.DataTable(
        heading_row_color="black12",
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all)),
        ],
        rows=[
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sample["name"], size=12)),
                    ft.DataCell(ft.Text(sample["size"], size=12)),
                    ft.DataCell(ft.Text(sample["status"], size=12)),
                    ft.DataCell(ft.Checkbox()),
                ],
            ) for sample in samples
        ],
    )

    if not tabela_analise_qualidade.rows:
        empty_message = ft.Column(
            controls=[
                ft.Divider(height=1, thickness=1, color="black38"),
                ft.Text("Nenhuma amostra disponível para análise de qualidade", size=16, text_align="center"),
                ft.Divider(height=1, thickness=1, color="black38"),
            ],
            alignment="center",
            horizontal_alignment="center",
        )
        iniciar_analise_disabled = True
    else:
        empty_message = None
        iniciar_analise_disabled = False

    dlg_modal_analise_qualidade = ft.AlertDialog(
        title=ft.Text("Análise de Qualidade"),
        content=ft.Container(
            content=ft.ListView(
                spacing=10,
                controls=[
                    empty_message if empty_message else tabela_analise_qualidade,
                ]
            ),
            width=520,
        ),
        actions=[
            ft.Container(
                content=ft.TextButton(
                    "Iniciar análise de qualidade",
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                    width=200,
                    height=40,
                    on_click=start_quality_analysis if not iniciar_analise_disabled else None,
                )
            ),
        ],
        actions_alignment="center",
    )

    page.open(dlg_modal_analise_qualidade)
    await update_quality_analysis_table(page, token, user_id)
