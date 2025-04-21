import flet as ft
import httpx
import logging
import asyncio
from .utils import log_message

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------------------------
# Table Management
# ----------------------------------------

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

# ----------------------------------------
# Alignment Operations
# ----------------------------------------

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

# ----------------------------------------
# Reference Genome Management
# ----------------------------------------

async def show_genomes_modal(page, token, user_id):
    """Exibe o modal para visualizar e excluir genomas de referência."""
    global tabela_genomas_referencia, tabela_genomas_disponiveis

    async def update_tabela_genomas_referencia():
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://bioinfo-container:8000/genomes/", headers=headers)
                if response.status_code == 200:
                    tabela_genomas_referencia.rows.clear()
                    for genome in response.json():
                        tabela_genomas_referencia.rows.append(
                            ft.DataRow(
                                cells=[
                                    ft.DataCell(ft.Text(genome["name"], style=ft.TextStyle(size=12))),
                                    ft.DataCell(ft.Text(genome["size"], style=ft.TextStyle(size=12))),
                                    ft.DataCell(ft.Text(genome["status"], style=ft.TextStyle(size=12))),
                                    ft.DataCell(
                                        ft.IconButton(
                                            icon=ft.icons.DELETE,
                                            tooltip="Excluir genoma",
                                            on_click=lambda e, accession=genome["name"].split("(")[-1].strip(")"): open_confirmation_modal(accession),
                                            icon_color=ft.colors.RED,
                                        )
                                    ),
                                ],
                            )
                        )
                    page.update()
                else:
                    await log_message(page, f"Erro ao atualizar tabela de genomas: {response.status_code} - {response.text}")
        except Exception as ex:
            await log_message(page, f"Erro ao atualizar tabela de genomas: {ex}")

    async def delete_genome(accession):
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                dlg_modal_excluir_genoma.open = False
                page.update()
                response = await client.delete(f"http://bioinfo-container:8000/genomes/{accession}", headers=headers)
                if response.status_code == 200:
                    await log_message(page, f"Genoma de referência {accession} excluído com sucesso.")
                    await update_tabela_genomas_referencia()
                else:
                    await log_message(page, f"Erro ao excluir genoma: {response.status_code} - {response.text}")
        except Exception as ex:
            await log_message(page, f"Erro ao excluir genoma: {ex}")

    def open_confirmation_modal(accession):
        global dlg_modal_excluir_genoma
        """Opens the confirmation modal for genome deletion."""
        dlg_modal_excluir_genoma = ft.AlertDialog(
            title=ft.Text("Confirmar exclusão"),
            content=ft.TextField(
                hint_text="Digite 'Confirmar' para excluir o genoma selecionado.",
                border_radius=ft.border_radius.all(4),
                multiline=False,
                expand=1,
            ),
            actions=[
                ft.TextButton(
                    "Excluir",
                    on_click=lambda e: asyncio.run(delete_genome(accession)),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                    width=200,
                    height=40,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
        )
        page.open(dlg_modal_excluir_genoma)

    tabela_genomas_referencia = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("Ações")),
        ],
        rows=[],
    )

    # Update the table when the modal is opened
    await update_tabela_genomas_referencia()

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
        column_spacing=10,
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
        width=300,
    )

    # Input fields for sjdbOverhang and threads
    sjdb_overhang_field = ft.TextField(
        label="sjdbOverhang",
        value="100",
        hint_text="Ex.: 100",
        width=140,
        tooltip="Use read_length - 1 (ex.: Para reads de 101bp, use 100)",
    )

    threads_field = ft.TextField(
        label="Threads",
        value="4",
        hint_text="Ex.: 4",
        width=90,
        tooltip="Insira o número de threads para o STAR (ex.: 4)",
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
                        genome["Assembly Stats Total Sequence Length"] = format_sequence_length(
                            genome.get("Assembly Stats Total Sequence Length", "0")
                        )
                        genome["Assembly BioSample Submission date"] = format_submission_date(
                            genome["Assembly BioSample Submission date"]
                        )

                    update_rows_with_checkboxes(data)
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

    # Handle checkbox selection to allow only one selection at a time
    def handle_checkbox_selection(row_index):
        for i, row in enumerate(tabela_genomas_disponiveis.rows):
            checkbox = row.cells[5].content
            checkbox.value = (i == row_index)  # Only the clicked checkbox remains selected
        page.update()

    # Botão para indexar genoma
    async def indexar_genoma_handler(e):
        """Handle genome download and indexing."""
        selected_row = next(
            (row for row in tabela_genomas_disponiveis.rows if row.cells[5].content.value), None
        )
        if not selected_row:
            await log_message(page, "Nenhum genoma selecionado para indexação.")
            return

        accession = selected_row.cells[0].content.value
        organism_name = selected_row.cells[2].content.value
        sjdb_overhang = sjdb_overhang_field.value
        threads = threads_field.value

        if not sjdb_overhang.isdigit() or not threads.isdigit():
            await log_message(page, "Valores inválidos para sjdbOverhang ou Threads.")
            return

        # Download and index genome
        dlg_modal_genomas.open = False
        page.update()
        await download_genome(page, token, accession, organism_name, sjdb_overhang, threads)

    # Update rows to include checkboxes with selection handling
    def update_rows_with_checkboxes(data):
        tabela_genomas_disponiveis.rows.clear()
        for i, genome in enumerate(data):
            tabela_genomas_disponiveis.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(genome["Assembly Accession"], style=ft.TextStyle(size=12))),
                        ft.DataCell(ft.Text(genome["Assembly Name"], style=ft.TextStyle(size=12))),
                        ft.DataCell(
                            ft.Text(
                                genome["Organism Name"],
                                style=ft.TextStyle(size=12),
                                max_lines=None,
                            )
                        ),
                        ft.DataCell(
                            ft.Text(
                                genome["Assembly Stats Total Sequence Length"],
                                style=ft.TextStyle(size=12),
                                no_wrap=True,
                            )
                        ),
                        ft.DataCell(
                            ft.Text(
                                genome["Assembly BioSample Submission date"],
                                style=ft.TextStyle(size=12),
                            )
                        ),
                        ft.DataCell(
                            ft.Checkbox(
                                value=False,
                                on_change=lambda e, row_index=i: handle_checkbox_selection(row_index),
                            )
                        ),
                    ],
                )
            )
        page.update()

    # Layout do formulário
    form_layout = ft.Row(
        controls=[
            search_type_dropdown,
            search_field,
            buscar_genomas_button,
            ft.Container(width=25),
            sjdb_overhang_field,
            threads_field,
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
                    ft.Container(height=10),
                    ft.Text("Buscar genomas disponíveis", style=ft.TextStyle(size=14, weight="bold")),
                    ft.Container(height=10),
                    form_layout,
                    ft.Container(height=10),
                    tabela_genomas_disponiveis,
                ],
            ),
            width=800,
        ),
        actions=[ft.TextButton(
                "Indexar Genoma",
                on_click=indexar_genoma_handler,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            )
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_genomas)

async def download_genome(page, token, accession, organism_name, sjdb_overhang, threads):
    """Download a genome and trigger indexing."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=3600) as client:
            await log_message(page, f"Iniciando download do genoma {accession}...")
            response = await client.post(
                f"http://bioinfo-container:8000/genomes/download",
                params={"accession": accession},
                headers=headers,
            )
            if response.status_code == 200:
                await log_message(page, f"Download do genoma {accession} concluído com sucesso.")
                await index_genome(page, token, accession, organism_name, int(sjdb_overhang), int(threads))
            else:
                await log_message(page, f"Erro ao baixar genoma: {response.status_code} - {response.text}")
    except Exception as ex:
        await log_message(page, f"Erro ao baixar genoma: {ex}")

async def index_genome(page, token, accession, organism_name, sjdb_overhang, threads):
    """Index a genome."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=3600) as client:
            await log_message(page, f"Iniciando indexação do genoma {organism_name} ({accession})...")
            response = await client.post(
                f"http://bioinfo-container:8000/genomes/index",
                params={
                    "accession": accession,
                    "organism_name": organism_name,
                    "sjdb_overhang": sjdb_overhang,
                    "threads": threads,
                },
                headers=headers,
            )
            if response.status_code == 200:
                await log_message(page, f"Genoma {organism_name} ({accession}) indexado com sucesso.")
            else:
                await log_message(page, f"Erro ao indexar genoma: {response.status_code} - {response.text}")
    except Exception as ex:
        await log_message(page, f"Erro ao indexar genoma: {ex}")

