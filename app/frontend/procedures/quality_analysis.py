import flet as ft
import asyncio
import httpx
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def show_quality_analysis_modal(page, token):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    samples = []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://bioinfo-container:8000/samples?status=Completed", headers=headers, follow_redirects=True)
            if response.status_code == 200:
                samples = response.json()
            else:
                logger.error(f"Erro ao obter amostras: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

    # Function to select or deselect all samples
    async def toggle_select_all(e):
        for row in tabela_analise_qualidade.rows:
            row.cells[3].content.value = e.control.value
        await page.update_async()

    # Function to start quality analysis
    async def start_quality_analysis(e):
        selected_samples = [row.cells[0].content.value for row in tabela_analise_qualidade.rows if row.cells[3].content.value]
        if not selected_samples:
            logger.error("Nenhuma amostra selecionada.")
            return
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("http://bioinfo-container:8000/quality_analysis/", json={"samples": selected_samples}, headers=headers)
                if response.status_code == 200:
                    logger.info("Análise de qualidade iniciada com sucesso!")
                    dlg_modal_analise_qualidade.open = False  # Close the modal
                else:
                    logger.error(f"Erro ao iniciar análise de qualidade: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"An error occurred: {e}")

    # Create the table with samples
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
                    ft.DataCell(ft.Text(sample["sra_code"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Checkbox()),
                ],
            ) for sample in samples
        ],
    )

    # Create the modal dialog
    dlg_modal_analise_qualidade = ft.AlertDialog(
        title=ft.Text("Análise de Qualidade"),
        content=ft.Container(
            content=ft.ListView(
                spacing=10,
                controls=[ft.Container(
                    content=tabela_analise_qualidade,
                )]
            ),
           width=520
        ),
        actions=[
            ft.Container(
                content=ft.TextButton(
                    "Iniciar análise de qualidade",
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                    width=200,
                    height=40,
                    on_click=start_quality_analysis  # Call the new function
                )
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.dialog = dlg_modal_analise_qualidade
    dlg_modal_analise_qualidade.open = True
    await page.update_async()
