import flet as ft
import asyncio
import httpx
import logging
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
        heading_row_color=ft.colors.with_opacity(0.75, ft.colors.PRIMARY),
        columns=[
            ft.DataColumn(ft.Text("Identificação", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Status", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_pos_trimmagem)),
            ft.DataColumn(ft.Text("Ações", weight=ft.FontWeight.BOLD)),
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
                                ft.DataCell(ft.IconButton(icon=ft.icons.VISIBILITY, on_click=view_sample_details_handler)),
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
    # Display the dropdown menu and the initial graph
    dropdown_menu = create_dropdown_menu(page, token, sample_name, user_id, analysis_type)
    initial_graph = await display_graph(page, token, "Per base sequence quality", sample_name, user_id, analysis_type)

    # Find the container_pre_visualizacao and update its content
    for control in page.controls:
        if isinstance(control, ft.Row):
            for column in control.controls:
                if isinstance(column, ft.Column):
                    for container in column.controls:
                        if isinstance(container, ft.Container) and container.expand == 2 and isinstance(container.content, ft.Column):
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

        # Correctly access the text inside the Container
        for row in tabela_amostras_pos_trimmagem.rows:
            if isinstance(row.cells[2].content, ft.Checkbox) and row.cells[2].content.value:
                container = row.cells[0].content  # This is the Container
                if isinstance(container, ft.Container) and isinstance(container.content, ft.Row):
                    text_widget = container.content.controls[0].content  # Access the Text widget inside the Row
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
            border_radius=ft.border_radius.all(4),
            multiline=False,
            expand=1
        ),
        actions=[
            ft.TextButton("Excluir", on_click=confirm_delete, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=200, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_excluir_analise)

async def show_quality_analysis_post_trim_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    samples = []

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Obter amostras trimmadas (stage_id=3)
            response_stage_3 = await client.get("http://bioinfo-container:8000/samples/stages/3", headers=headers)
            if response_stage_3.status_code == 200:
                trimmed_samples = response_stage_3.json()
                logger.info(f"Trimmed samples (stage_id=3): {trimmed_samples}")
            else:
                logger.error(f"Erro ao obter amostras trimmadas: {response_stage_3.status_code} - {response_stage_3.text}")
                trimmed_samples = []

            # Obter amostras já analisadas pós-trimmagem (stage_id=4)
            response_stage_4 = await client.get("http://bioinfo-container:8000/samples/stages/4", headers=headers)
            if response_stage_4.status_code == 200:
                analyzed_samples = {sample["name"].replace("_post_trim.html", "_trimmed.fastq") for sample in response_stage_4.json()}
                logger.info(f"Analyzed samples (stage_id=4): {analyzed_samples}")
            else:
                logger.error(f"Erro ao obter amostras analisadas: {response_stage_4.status_code} - {response_stage_4.text}")
                analyzed_samples = set()

            # Filtrar amostras trimmadas que ainda não foram analisadas pós-trimmagem
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
                if response.status_code == 200:
                    logger.info(f"Análise de qualidade pós-trimmagem iniciada para {selected_samples} com sucesso!")
                    await update_tabela_amostras_pos_trimmagem(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)
                    page.update()
                else:
                    logger.error(f"Erro ao iniciar análise de qualidade pós-trimmagem para {selected_samples}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"An error occurred while starting post-trimmagem quality analysis: {e}", exc_info=True)

    tabela_analise_qualidade = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all)),
        ],
        rows=[
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sample["name"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Checkbox()),
                ],
            ) for sample in samples
        ],
    )

    if not tabela_analise_qualidade.rows:
        empty_message = ft.Column(
            controls=[
                ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
                ft.Text("Nenhuma amostra disponível para análise de qualidade pós-trimmagem", style=ft.TextStyle(size=16), text_align="center"),
                ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
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
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_analise_qualidade)