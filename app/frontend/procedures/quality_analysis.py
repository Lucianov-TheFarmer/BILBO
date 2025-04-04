import flet as ft
import asyncio
import httpx
import logging
from .utils import log_message  # Import the functions
from .viewer import create_dropdown_menu, display_graph  # Updated import

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_tabela_amostras_qc(page, token):  # Updated function signature
    global tabela_amostras_qc
    
    async def toggle_select_all_qc(e):
        for row in tabela_amostras_qc.rows:
            row.cells[2].content.value = e.control.value
        page.update()

    tabela_amostras_qc = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_qc)),  # Add checkbox to the header
            ft.DataColumn(ft.Text("Ações")),  # Add actions column
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
                tabela_amostras_qc.rows.clear()  # Limpar as linhas existentes na tabela
                for sample in samples:
                    # Criar um handler síncrono para chamar a função assíncrona
                    def view_sample_details_handler(e, s=sample["name"]):
                        asyncio.run(view_sample_details(page, token, s, user_id))

                    # Adicionar uma nova linha para cada amostra retornada
                    tabela_amostras_qc.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(sample["name"] or sample["sra_code"], style=ft.TextStyle(size=12))),  # Mostrar o nome ou o sra_code
                                ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Checkbox()),  # Adicionar checkbox para seleção
                                ft.DataCell(ft.IconButton(icon=ft.icons.VISIBILITY, on_click=view_sample_details_handler)),  # Botão para visualizar detalhes
                            ],
                        )
                    )
                logger.info("Table updated successfully with new data.")
                page.update()  # Atualizar a página para refletir as mudanças na tabela
            else:
                logger.error(f"Erro ao obter amostras processadas: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred while updating the quality analysis table: {e}", exc_info=True)

async def view_sample_details(page, token, sample_name, user_id):
    # Display the dropdown menu and the initial graph
    dropdown_menu = create_dropdown_menu(page, token, sample_name, user_id)
    initial_graph = await display_graph(page, token, "Per base sequence quality", sample_name, user_id)
    
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

async def delete_quality_analysis_results(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    async def confirm_delete(e):
        selected_samples = [row.cells[0].content.value for row in tabela_amostras_qc.rows if row.cells[2].content.value]
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
        except Exception as e:
            logger.error(f"An error occurred while deleting quality analysis results: {e}", exc_info=True)
        await update_quality_analysis_table(page, token, user_id)
        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)  # Update the container_menu_direita
        page.update()
        dlg_modal_excluir_analise.open = False  # Close the modal
        page.update()  # Update the page to reflect the modal closure

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

async def show_quality_analysis_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    samples = []

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # Obter amostras baixadas (stage_id=1)
            response_stage_1 = await client.get("http://bioinfo-container:8000/samples/stages/1", headers=headers)
            if response_stage_1.status_code == 200:
                downloaded_samples = response_stage_1.json()
                logger.info(f"Amostras baixadas (stage_id=1): {downloaded_samples}")
            else:
                logger.error(f"Erro ao obter amostras baixadas: {response_stage_1.status_code} - {response_stage_1.text}")
                downloaded_samples = []

            # Obter amostras já analisadas (stage_id=2)
            response_stage_2 = await client.get("http://bioinfo-container:8000/samples/stages/2", headers=headers)
            if response_stage_2.status_code == 200:
                analyzed_samples = {sample["name"].replace(".html", ".fastq") for sample in response_stage_2.json()}
                logger.info(f"Amostras analisadas (stage_id=2): {analyzed_samples}")
            else:
                logger.error(f"Erro ao obter amostras analisadas: {response_stage_2.status_code} - {response_stage_2.text}")
                analyzed_samples = set()

            # Filtrar amostras baixadas que ainda não foram analisadas
            samples = [sample for sample in downloaded_samples if sample["name"] not in analyzed_samples]
            logger.info(f"Amostras disponíveis para análise de qualidade: {samples}")

    except Exception as e:
        logger.error(f"An error occurred while fetching samples: {e}", exc_info=True)

    # Verificar se as amostras estão sendo corretamente processadas
    if not samples:
        logger.warning("Nenhuma amostra disponível para análise de qualidade após o filtro.")
    else:
        logger.info(f"Número de amostras disponíveis para análise de qualidade: {len(samples)}")

    # Function to select or deselect all samples
    async def toggle_select_all(e):
        for row in tabela_analise_qualidade.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    # Function to start quality analysis
    async def start_quality_analysis(e):
        selected_samples = [row.cells[0].content.value for row in tabela_analise_qualidade.rows if row.cells[3].content.value]
        if not selected_samples:
            logger.error("Nenhuma amostra selecionada.")
            return
        await log_message(page, f"Iniciando análise de qualidade para {selected_samples}")
        dlg_modal_analise_qualidade.open = False  # Close the modal
        page.update()  # Update the page to reflect the modal closure
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:  # Increase the timeout to 60 seconds
                response = await client.post("http://bioinfo-container:8000/quality_analysis/", json={"samples": selected_samples}, headers=headers)
                if response.status_code == 200:
                    logger.info(f"Análise de qualidade iniciada para {selected_samples} com sucesso!")
                    await update_quality_analysis_table(page, token, user_id)
                    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)  # Update the container_menu_direita
                    page.update()
                else:
                    logger.error(f"Erro ao iniciar análise de qualidade para {selected_samples}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"An error occurred while starting quality analysis: {e}", exc_info=True)

    # Criar a tabela com as amostras disponíveis para análise de qualidade
    tabela_analise_qualidade = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all)),  # Add on_change event
        ],
        rows=[
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sample["name"], style=ft.TextStyle(size=12))),  # Use 'name' instead of 'sra_code'
                    ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Checkbox()),
                ],
            ) for sample in samples
        ],
    )

    # Check if the table is empty
    if not tabela_analise_qualidade.rows:
        empty_message = ft.Column(
            controls=[
                ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
                ft.Text("Nenhuma amostra disponível para análise de qualidade", style=ft.TextStyle(size=16), text_align="center"),
                ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        iniciar_analise_disabled = True  # Disable the button
    else:
        empty_message = None
        iniciar_analise_disabled = False  # Enable the button

    # Create the modal dialog
    dlg_modal_analise_qualidade = ft.AlertDialog(
        title=ft.Text("Análise de Qualidade"),
        content=ft.Container(
            content=ft.ListView(
                spacing=10,
                controls=[
                    empty_message if empty_message else tabela_analise_qualidade,  # Show message if table is empty
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
                    on_click=start_quality_analysis if not iniciar_analise_disabled else None,  # Disable click if no samples
                )
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_analise_qualidade)
    await update_quality_analysis_table(page, token, user_id)