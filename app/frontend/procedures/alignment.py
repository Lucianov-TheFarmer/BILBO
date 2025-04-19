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
    global tabela_genomas_referencia, tabela_genomas_disponiveis

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

    # Cria a tabela de genomas disponíveis
    tabela_genomas_disponiveis = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Accession", style=ft.TextStyle(size=12))),
            ft.DataColumn(ft.Text("Assembly Name", style=ft.TextStyle(size=12))),
            ft.DataColumn(ft.Text("Organism Name", style=ft.TextStyle(size=12))),
            ft.DataColumn(ft.Text("Length", style=ft.TextStyle(size=12))),
            ft.DataColumn(ft.Text("Submission Date", style=ft.TextStyle(size=12))),
            ft.DataColumn(ft.Text("", style=ft.TextStyle(size=12))),
        ],
        rows=[],
        column_spacing=10,  # Reduce column spacing
    )

    # Campo de texto para o taxon
    search_type_dropdown = ft.Dropdown(
        options=[
            ft.DropdownOption("taxon", "Taxon"),
            ft.DropdownOption("accession", "Accession"),
        ],
        value="taxon",
        width=150,
    )

    search_field = ft.TextField(
        label="Digite o termo de pesquisa",
        hint_text="Ex.: Saccharum ou GCA_000001405.28",
        width=400,
    )

    # Botão para buscar genomas
    async def buscar_genomas_handler(e):
        headers = {"Authorization": f"Bearer {token}"}
        search_type = search_type_dropdown.value
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://bioinfo-container:8000/genomes/search?{search_type}={search_field.value}",
                    headers=headers,
                )
                if response.status_code == 200:
                    data = response.json()["genomes"]
                    tabela_genomas_disponiveis.rows.clear()

                    def format_sequence_length(length):
                        try:
                            length = int(length)
                            if length >= 1e9:
                                return f"{length / 1e9:.2f} GB"
                            elif length >= 1e6:
                                return f"{length / 1e6:.2f} MB"
                            else:
                                return f"{length} B"
                        except ValueError:
                            return "N/A"  # Handle invalid or non-numeric values

                    def format_submission_date(date):
                        return date.split("T")[0] if "T" in date else date

                    for genome in data:
                        tabela_genomas_disponiveis.rows.append(
                            ft.DataRow(
                                cells=[
                                    ft.DataCell(ft.Text(genome["Assembly Accession"], style=ft.TextStyle(size=10))),
                                    ft.DataCell(ft.Text(genome["Assembly Name"], style=ft.TextStyle(size=10))),
                                    ft.DataCell(
                                        ft.Text(
                                            genome["Organism Name"],
                                            style=ft.TextStyle(size=10),
                                            max_lines=None,  # Allow wrapping for long text
                                        )
                                    ),
                                    ft.DataCell(
                                        ft.Text(
                                            format_sequence_length(genome.get("Assembly Stats Total Sequence Length", "0")),
                                            style=ft.TextStyle(size=10),
                                            no_wrap=True,  # Ensure it stays on one line
                                        )
                                    ),
                                    ft.DataCell(
                                        ft.Text(
                                            format_submission_date(genome["Assembly BioSample Submission date"]),
                                            style=ft.TextStyle(size=10),
                                        )
                                    ),
                                    ft.DataCell(
                                        ft.Checkbox(),
                                        # alignment=ft.alignment.center,  # Center the checkbox
                                    ),
                                ],
                            )
                        )
                    page.update()
                else:
                    await log_message(page, f"Erro ao buscar genomas: {response.status_code} - {response.text}")
        except Exception as ex:
            await log_message(page, f"Erro ao buscar genomas: {ex}")

    buscar_genomas_button = ft.IconButton(
        icon=ft.icons.SEARCH,
        on_click=buscar_genomas_handler,
        tooltip="Buscar",
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
    )

    # Layout do formulário
    form_layout = ft.Row(
        controls=[
            search_type_dropdown,
            search_field,
            buscar_genomas_button,
        ],
        spacing=10,
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
                    ft.Container(height=10),  # Add space above
                    ft.Text("Buscar genomas disponíveis", style=ft.TextStyle(size=14, weight="bold")),
                    ft.Container(height=10),  # Add space below
                    form_layout,
                    ft.Container(height=10),  # Add space below
                    tabela_genomas_disponiveis,
                ],
            ),
            width=800,  # Ajusta o tamanho do modal
        ),
        actions=[
            ft.TextButton(
                "Indexar Genoma",
                # on_click=indexar_genoma_handler,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    # Exibe o modal
    page.open(dlg_modal_genomas)
