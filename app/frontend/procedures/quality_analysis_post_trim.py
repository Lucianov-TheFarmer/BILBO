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

def create_tabela_amostras_pos_trimmagem(page, token):
    global tabela_amostras_pos_trimmagem

    async def toggle_select_all_pos_trimmagem(e):
        for row in tabela_amostras_pos_trimmagem.rows:
            row.cells[2].content.value = e.control.value
        page.update()

    tabela_amostras_pos_trimmagem = ft.DataTable(
        heading_row_color="primary",
        columns=[
            ft.DataColumn(ft.Text("Identificação", weight="bold")),
            ft.DataColumn(ft.Text("Status", weight="bold")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_pos_trimmagem)),
            ft.DataColumn(ft.Text("Ações", weight="bold")),
        ],
        rows=[],
    )
    return tabela_amostras_pos_trimmagem

async def update_tabela_amostras_pos_trimmagem(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://bioinfo-container:8000/samples/stages/4", headers=headers)
            if response.status_code == 200:
                samples = response.json()
                logger.info(f"Data received from backend: {samples}")
                tabela_amostras_pos_trimmagem.rows.clear()
                for sample in samples:
                    def view_sample_details_handler(e, s=sample["name"]):
                        asyncio.run(view_sample_details(page, token, s, user_id, analysis_type="QC_PostTrim"))

                    async def download_handler(e, s=sample["name"]):
                        download_url = f"http://localhost:8000/download/qualidade2/{s}?token={token}"
                        page.launch_url(download_url)
                        await log_message(page, f"Download iniciado para {s}")

                    # Only show view/download when status is Completed
                    actions = []
                    try:
                        status = (sample.get("status") or "").lower()
                    except Exception:
                        status = ""
                    if status == "completed":
                        actions.append(ft.IconButton(icon="visibility", on_click=view_sample_details_handler))
                        actions.append(ft.IconButton(icon="download", on_click=download_handler))

                    tabela_amostras_pos_trimmagem.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(
                                    ft.Container(
                                        content=ft.Row(
                                            controls=[
                                                ft.Container(
                                                    content=ft.Text(
                                                        sample["name"],
                                                        style=ft.TextStyle(size=12),
                                                        max_lines=1,
                                                        overflow="ellipsis"
                                                    )
                                                )
                                            ],
                                            scroll=ft.ScrollMode.AUTO,
                                        ),
                                        width=130
                                    )
                                ),
                                ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Checkbox()),
                                ft.DataCell(ft.Row(actions)),
                            ],
                        )
                    )
                logger.info("Table updated successfully with new data.")
                await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                page.update()
            else:
                logger.error(f"Erro ao obter amostras pós-trimmagem: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred while updating the post-trimmagem quality analysis table: {e}", exc_info=True)

async def view_sample_details(page, token, sample_name, user_id, analysis_type):
    dropdown_menu = create_dropdown_menu(page, token, sample_name, user_id, analysis_type)
    initial_graph = await display_graph(page, token, "Per base sequence quality", sample_name, user_id, analysis_type)

    for control in page.controls:
        if isinstance(control, ft.Row):
            for column in control.controls:
                if isinstance(column, ft.Column):
                    for container in column.controls:
                        if isinstance(container, ft.Container) and container.key == "container_preview":
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

async def delete_quality_analysis_post_trim_results(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    async def confirm_delete(e):
        selected_samples = []

        for row in tabela_amostras_pos_trimmagem.rows:
            if isinstance(row.cells[2].content, ft.Checkbox) and row.cells[2].content.value:
                container = row.cells[0].content
                if isinstance(container, ft.Container) and isinstance(container.content, ft.Row):
                    text_widget = container.content.controls[0].content
                    if isinstance(text_widget, ft.Text):
                        selected_samples.append(text_widget.value)

        if not selected_samples:
            logger.error("Nenhum resultado de análise selecionado.")
            return

        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                for sample_name in selected_samples:
                    response = await client.delete(f"http://bioinfo-container:8000/quality_analysis_post_trim/{sample_name}", headers=headers)
                    if response.status_code == 200:
                        logger.info(f"Resultado da análise {sample_name} excluído com sucesso!")
                    else:
                        logger.error(f"Erro ao excluir resultado da análise {sample_name}: {response.status_code} - {response.text}")

            await update_tabela_amostras_pos_trimmagem(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)
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

async def show_quality_analysis_post_trim_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    samples = []

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response_stage_3 = await client.get("http://bioinfo-container:8000/samples/stages/3", headers=headers)
            if response_stage_3.status_code == 200:
                trimmed_samples = response_stage_3.json()
                logger.info(f"Trimmed samples (stage_id=3): {trimmed_samples}")
            else:
                logger.error(f"Erro ao obter amostras trimmadas: {response_stage_3.status_code} - {response_stage_3.text}")
                trimmed_samples = []
            response_stage_4 = await client.get("http://bioinfo-container:8000/samples/stages/4", headers=headers)
            if response_stage_4.status_code == 200:
                analyzed_samples = {sample["name"].replace("_post_trim.html", "_trimmed.fastq") for sample in response_stage_4.json()}
                logger.info(f"Analyzed samples (stage_id=4): {analyzed_samples}")
            else:
                logger.error(f"Erro ao obter amostras analisadas: {response_stage_4.status_code} - {response_stage_4.text}")
                analyzed_samples = set()

            samples = [sample for sample in trimmed_samples if sample["name"] not in analyzed_samples]
            logger.info(f"Samples available for post-trimmagem quality analysis: {samples}")

    except Exception as e:
        logger.error(f"An error occurred while fetching samples: {e}", exc_info=True)

    if not samples:
        logger.warning("No samples available for post-trimmagem quality analysis after filtering.")
    else:
        logger.info(f"Number of samples available for post-trimmagem quality analysis: {len(samples)}")

    async def toggle_select_all(e):
        for row in tabela_analise_qualidade.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    async def start_quality_analysis_post_trim(e):
        selected_samples = [row.cells[0].content.value for row in tabela_analise_qualidade.rows if row.cells[3].content.value]
        if not selected_samples:
            logger.error("Nenhuma amostra selecionada.")
            return
        await log_message(page, f"Iniciando análise de qualidade pós-trimmagem para {selected_samples}")
        dlg_modal_analise_qualidade.open = False
        page.update()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post("http://bioinfo-container:8000/quality_analysis_post_trim/start", json={"samples": selected_samples}, headers=headers)
                if response.status_code in (200, 202):
                    body = response.json()
                    job_id = body.get("job_id")
                    if job_id:
                        await log_message(page, f"QC pós-trim enfileirado (job {job_id}).")
                        result = await wait_for_job(token, job_id)
                        status = result.get("status")
                        await log_message(page, f"QC pós-trim finalizado com status {status}.")
                    logger.info(f"Análise de qualidade pós-trimmagem iniciada para {selected_samples} com sucesso!")
                    await update_tabela_amostras_pos_trimmagem(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)
                    page.update()
                else:
                    logger.error(f"Erro ao iniciar análise de qualidade pós-trimmagem para {selected_samples}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"An error occurred while starting post-trimmagem quality analysis: {e}", exc_info=True)

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
                ft.Text("Nenhuma amostra disponível para análise de qualidade pós-trimmagem", style=ft.TextStyle(size=16), text_align="center"),
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
        title=ft.Text("Análise de Qualidade Pós-Trimmagem"),
        content=ft.Container(
            content=ft.ListView(
                spacing=10,
                controls=[
                    empty_message if empty_message else tabela_analise_qualidade,
                ]
            ),
            width=600,
        ),
        actions=[
            ft.Container(
                content=ft.TextButton(
                    "Iniciar análise de qualidade pós-trimmagem",
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                    width=400,
                    height=40,
                    on_click=start_quality_analysis_post_trim if not iniciar_analise_disabled else None,
                )
            ),
        ],
        actions_alignment="center",
    )

    page.open(dlg_modal_analise_qualidade)
