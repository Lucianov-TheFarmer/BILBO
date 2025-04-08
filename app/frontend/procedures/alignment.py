import flet as ft
import httpx
import logging
import asyncio
from .utils import log_message

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variable for the alignment table
tabela_alinhamento = None

def create_tabela_alinhamento(page, token):
    """Creates the table for alignment."""
    global tabela_alinhamento

    async def toggle_select_all_alignment(e):
        """Select or deselect all rows in the alignment table."""
        for row in tabela_alinhamento.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    tabela_alinhamento = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("Log")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_alignment)),  # Checkbox in the header
        ],
        rows=[],
    )
    return tabela_alinhamento

async def update_tabela_alinhamento(page, token):
    """Updates the alignment table with data from the backend."""
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://bioinfo-container:8000/alignment/", headers=headers)
            if response.status_code == 200:
                samples = response.json()
                tabela_alinhamento.rows.clear()
                for sample in samples:
                    tabela_alinhamento.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(sample["name"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Text(sample["log"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Checkbox()),
                            ],
                        )
                    )
                page.update()
            else:
                logger.error(f"Erro ao obter dados de alinhamento: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Erro ao atualizar a tabela de alinhamento: {e}", exc_info=True)

async def iniciar_alinhamento(page, token, selected_samples):
    """Starts the alignment process for selected samples."""
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://bioinfo-container:8000/alignment/start",
                json={"samples": selected_samples},
                headers=headers,
            )
            if response.status_code == 200:
                logger.info("Alinhamento iniciado com sucesso!")
                await log_message(page, "Alinhamento iniciado com sucesso!")
                await update_tabela_alinhamento(page, token)
            else:
                logger.error(f"Erro ao iniciar alinhamento: {response.status_code} - {response.text}")
                await log_message(page, f"Erro ao iniciar alinhamento: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Erro ao iniciar alinhamento: {e}", exc_info=True)
        await log_message(page, f"Erro ao iniciar alinhamento: {e}")

async def excluir_alinhamento(page, token, selected_samples):
    """Deletes selected alignment results."""
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            for sample in selected_samples:
                response = await client.delete(f"http://bioinfo-container:8000/alignment/{sample}", headers=headers)
                if response.status_code == 200:
                    logger.info(f"Resultado de alinhamento {sample} excluído com sucesso!")
                else:
                    logger.error(f"Erro ao excluir alinhamento {sample}: {response.status_code} - {response.text}")
        await update_tabela_alinhamento(page, token)
    except Exception as e:
        logger.error(f"Erro ao excluir alinhamento: {e}", exc_info=True)

async def show_genomes_modal(page, token, user_id):
    """Exibe o modal para visualizar e indexar genomas de referência."""
    global tabela_genomas_referencia

    # Cria a tabela de genomas de referência
    async def toggle_select_all_genomes(e):
        """Select or deselect all rows in the genomes table."""
        for row in tabela_genomas_referencia.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    tabela_genomas_referencia = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Size")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_genomes)),  # Checkbox in the header
        ],
        rows=[],
    )

    # Campos do formulário
    threads_field = ft.TextField(
        label="Threads",
        value="1",
        tooltip="Número de threads para processamento paralelo.",
        width=400,
    )
    fasta_field = ft.TextField(
        label="Fasta",
        hint_text="Caminho para o arquivo FASTA",
        width=400,
    )
    gtf_field = ft.TextField(
        label="GTF",
        hint_text="Caminho para o arquivo GTF",
        width=400,
    )

    # Botão para indexar genoma
    async def indexar_genoma_handler(e):
        await log_message(page, "Indexação de genoma iniciada (função ainda não implementada).")

    # Layout do formulário
    form_layout = ft.Column(
        controls=[
            threads_field,
            fasta_field,
            gtf_field,
        ],
        spacing=20,
        alignment=ft.MainAxisAlignment.START,
    )

    # Modal
    dlg_modal_genomas = ft.AlertDialog(
        title=ft.Text("Genomas de Referência"),
        content=ft.Container(
            content=ft.ListView(
                controls=[
                    tabela_genomas_referencia,
                    ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
                    ft.Text("Parâmetros de Indexação", style=ft.TextStyle(size=14, weight="bold")),
                    form_layout,
                ],
            ),
            width=600,  # Ajusta o tamanho do modal
        ),
        actions=[
            ft.TextButton(
                "Indexar Genoma",
                on_click=indexar_genoma_handler,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    # Exibe o modal
    page.open(dlg_modal_genomas)
