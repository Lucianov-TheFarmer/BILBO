import flet as ft
import httpx
import logging
import asyncio
import json
from .jobs import wait_for_job
from .utils import log_message
from .viewer import view_alignment_log

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
            row.cells[4].content.value = e.control.value
        page.update()

    tabela_alinhamento = ft.DataTable(
        heading_row_color="primary",
        columns=[
            ft.DataColumn(ft.Text("Identificação", weight="bold")),
            ft.DataColumn(ft.Text("Tamanho", weight="bold")),
            ft.DataColumn(ft.Text("Status", weight="bold")),
            ft.DataColumn(ft.Text("Log", weight="bold")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_alignment)),
        ],
        rows=[],
        column_spacing=15,
    )
    return tabela_alinhamento

async def update_tabela_alinhamento(page, token, user_id):
    """Updates the alignment table with data from the backend."""
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://bioinfo-container:8000/alignment/", headers=headers)
            if response.status_code == 200:
                samples = response.json()
                tabela_alinhamento.rows.clear()
                for sample in samples:
                    def view_log_handler(e, s=sample["name"]):
                        asyncio.run(view_alignment_log(page, token, s, user_id))

                    log_button_disabled = sample["status"] != "Completed"

                    tabela_alinhamento.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(sample["name"], size=12)),
                                ft.DataCell(ft.Text(sample["size"], size=12)),
                                ft.DataCell(ft.Text(sample["status"], size=12)),
                                ft.DataCell(
                                    ft.IconButton(
                                        icon="description",
                                        tooltip="Visualizar log",
                                        on_click=view_log_handler if not log_button_disabled else None,
                                        disabled=log_button_disabled,
                                    )
                                ),
                                ft.DataCell(ft.Checkbox()),
                            ]
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

async def iniciar_alinhamento(page, token, user_id, selected_samples, genome, params, atualizar_tabela, container_menu_direita, tabela_amostras_local):
    """Starts the alignment process for selected samples."""
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                "http://bioinfo-container:8000/alignment/add_samples",
                data={
                    "samples": json.dumps(selected_samples),
                    "genome": genome,
                },
                headers=headers,
            )
            if response.status_code != 200:
                await log_message(page, f"Erro ao adicionar amostras: {response.text}")
                return

            basenames = list({sample.split('_')[0] for sample in selected_samples})
            
            for basename in basenames:
                response = await client.post(
                    "http://bioinfo-container:8000/alignment/start",
                    data={"sample": basename, "genome": genome},
                    params={"threads": params["threads"]},
                    headers=headers,
                )
                if response.status_code in (200, 202):
                    await update_tabela_alinhamento(page, token, user_id)
                    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                    body = response.json()
                    job_id = body.get("job_id")
                    if job_id:
                        await log_message(page, f"Alinhamento enfileirado para {basename} (job {job_id}).")
                        result = await wait_for_job(token, job_id)
                        status = result.get("status")
                        if status == "COMPLETED":
                            await log_message(page, f"Alinhamento concluído para {basename}.")
                        else:
                            await log_message(page, f"Alinhamento de {basename} finalizado com status {status}.")
                        await update_tabela_alinhamento(page, token, user_id)
                        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                else:
                    await log_message(page, f"Erro ao iniciar alinhamento para {basename}: {response.text}")
    except Exception as e:
        await log_message(page, f"Erro ao iniciar alinhamento: {e}")

async def excluir_alinhamento(page, token, user_id, selected_samples, container_menu_direita, tabela_amostras_local, atualizar_tabela):
    """Exclui os alinhamentos selecionados após confirmação."""
    async def confirm_delete(e):
        if confirmation_field.value.strip().lower() != "confirmar":
            await log_message(page, "Confirmação inválida. Digite 'Confirmar' para prosseguir.")
            return

        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                for sample in selected_samples:
                    response = await client.delete(f"http://bioinfo-container:8000/alignment/{sample}", headers=headers)
                    if response.status_code == 200:
                        await log_message(page, f"Alinhamento {sample} excluído com sucesso!")
                    else:
                        logger.error(f"Erro ao excluir alinhamento {sample}: {response.text}")
            await update_tabela_alinhamento(page, token, user_id)
            await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
            page.update()
        except Exception as e:
            logger.error(f"Erro ao excluir alinhamentos: {e}", exc_info=True)

        dlg_modal_excluir_alinhamento.open = False
        page.update()

    confirmation_field = ft.TextField(
        hint_text="Digite 'Confirmar' para excluir os alinhamentos selecionados.",
        border_radius=4,
        multiline=False,
        expand=1,
    )
    dlg_modal_excluir_alinhamento = ft.AlertDialog(
        title=ft.Text("Confirmar exclusão"),
        content=confirmation_field,
        actions=[
            ft.TextButton(
                "Excluir",
                on_click=confirm_delete,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            ),
        ],
        actions_alignment="center",
    )

    page.open(dlg_modal_excluir_alinhamento)

async def show_alignment_modal(page, token, user_id, atualizar_tabela, container_menu_direita, tabela_amostras_local):
    """Exibe o modal para configurar e iniciar o alinhamento."""
    global tabela_trimmados, tabela_genomas_referencia

    async def toggle_select_sample(e):
        selected_sample = e.control.data
        is_selected = e.control.value
        
        paired_sample = None
        if selected_sample.endswith("_1_trimmed.fastq"):
            paired_sample = selected_sample.replace("_1_trimmed.fastq", "_2_trimmed.fastq")
        elif selected_sample.endswith("_2_trimmed.fastq"):
            paired_sample = selected_sample.replace("_2_trimmed.fastq", "_1_trimmed.fastq")

        if paired_sample:
            for row in tabela_trimmados.rows:
                if row.cells[0].content.value == paired_sample:
                    row.cells[3].content.value = is_selected
                    break
        page.update()

    async def toggle_select_all_trimmados(e):
        for row in tabela_trimmados.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    tabela_trimmados = ft.DataTable(
        heading_row_color="black12",
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_trimmados)),
        ],
        rows=[],
    )

    def handle_checkbox_selection(row_index):
        for i, row in enumerate(tabela_genomas_referencia.rows):
            checkbox = row.cells[3].content
            checkbox.value = (i == row_index)
        page.update()

    tabela_genomas_referencia = ft.DataTable(
        heading_row_color="black12",
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("")),
        ],
        rows=[],
    )

    async def update_tabela_trimmados():
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                response_trimmados = await client.get("http://bioinfo-container:8000/samples/stages/3", headers=headers)
                trimmed_samples = response_trimmados.json() if response_trimmados.status_code == 200 else []

                response_alinhadas = await client.get("http://bioinfo-container:8000/alignment/", headers=headers)
                aligned_samples = {s["name"].replace(".bam", "") for s in response_alinhadas.json()} if response_alinhadas.status_code == 200 else set()

                available_samples = [
                    s for s in trimmed_samples
                    if s["name"].replace("_1_trimmed.fastq", "").replace("_2_trimmed.fastq", "") not in aligned_samples
                ]

                tabela_trimmados.rows.clear()
                for sample in available_samples:
                    tabela_trimmados.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(sample["name"], size=12)),
                                ft.DataCell(ft.Text(sample["size"], size=12)),
                                ft.DataCell(ft.Text(sample["status"], size=12)),
                                ft.DataCell(ft.Checkbox(data=sample["name"], on_change=toggle_select_sample)),
                            ],
                        )
                    )
                page.update()
        except Exception as e:
            logger.error(f"Erro ao atualizar tabela de trimmados: {e}")

    async def update_tabela_genomas_referencia():
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://bioinfo-container:8000/genomes/", headers=headers)
                if response.status_code == 200:
                    genomes = response.json()
                    tabela_genomas_referencia.rows.clear()
                    for index, genome in enumerate(genomes):
                        tabela_genomas_referencia.rows.append(
                            ft.DataRow(
                                cells=[
                                    ft.DataCell(ft.Text(genome["name"], size=12)),
                                    ft.DataCell(ft.Text(genome["size"], size=12)),
                                    ft.DataCell(ft.Text(genome["status"], size=12)),
                                    ft.DataCell(ft.Checkbox(on_change=lambda e, i=index: handle_checkbox_selection(i))),
                                ],
                            )
                        )
                    page.update()
        except Exception as e:
            logger.error(f"Erro ao atualizar tabela de genomas: {e}")

    # Fields for STAR parameters
    threads_field = ft.TextField(label="Threads", value="4", width=300)
    out_filter_type_field = ft.TextField(label="outFilterType", value="", width=300)
    out_filter_multimap_field = ft.TextField(label="outFilterMultimapNmax", value="", width=300)
    align_sj_overhang_min_field = ft.TextField(label="alignSJoverhangMin", value="", width=300)
    align_sjdb_overhang_min_field = ft.TextField(label="alignSJDBoverhangMin", value="", width=300)
    out_filter_mismatch_max_field = ft.TextField(label="outFilterMismatchNmax", value="", width=300)
    out_filter_mismatch_over_read_field = ft.TextField(label="outFilterMismatchNoverReadLmax", value="", width=300)
    align_intron_min_field = ft.TextField(label="alignIntronMin", value="", width=300)
    align_intron_max_field = ft.TextField(label="alignIntronMax", value="", width=300)
    align_mates_gap_max_field = ft.TextField(label="alignMatesGapMax", value="", width=300)

    async def start_alignment(e):
        selected_samples = [r.cells[0].content.value for r in tabela_trimmados.rows if r.cells[-1].content.value]
        selected_genomes = [r.cells[0].content.value for r in tabela_genomas_referencia.rows if r.cells[-1].content.value]

        if not selected_samples or not selected_genomes:
            await log_message(page, "Selecione amostras e um genoma de referência.")
            return

        params = {"threads": threads_field.value} # Simplified for brevity, add others as needed

        dlg_modal_alignment.open = False
        page.update()

        await log_message(page, f"Iniciando alinhamento para as amostras: {', '.join(selected_samples)}")
        await iniciar_alinhamento(page, token, user_id, selected_samples, selected_genomes[0], params, atualizar_tabela, container_menu_direita, tabela_amostras_local)

    dlg_modal_alignment = ft.AlertDialog(
        title=ft.Text("Configurar Alinhamento"),
        content=ft.Container(
            content=ft.ListView(
                controls=[
                    ft.Text("Amostras Trimmadas", weight="bold", size=14),
                    tabela_trimmados,
                    ft.Divider(height=1, thickness=1, color="black38"),
                    ft.Text("Genomas de Referência", weight="bold", size=14),
                    tabela_genomas_referencia,
                    ft.Divider(height=1, thickness=1, color="black38"),
                    ft.Text("Parâmetros adicionais do STAR", weight="bold", size=14),
                    ft.Row(
                        controls=[
                            ft.Column(controls=[threads_field, out_filter_type_field, out_filter_multimap_field, align_sj_overhang_min_field, align_sjdb_overhang_min_field], spacing=20, horizontal_alignment="center"),
                            ft.Column(controls=[out_filter_mismatch_max_field, out_filter_mismatch_over_read_field, align_intron_min_field, align_intron_max_field, align_mates_gap_max_field], spacing=20, horizontal_alignment="center"),
                        ],
                        spacing=50,
                        alignment="center",
                    ),
                ],
            ),
            width=900,
        ),
        actions=[ft.TextButton("Iniciar Alinhamento", on_click=start_alignment)],
        actions_alignment="center",
    )

    await update_tabela_trimmados()
    await update_tabela_genomas_referencia()
    page.open(dlg_modal_alignment)

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
                                    ft.DataCell(ft.Text(genome["name"], size=12)),
                                    ft.DataCell(ft.Text(genome["size"], size=12)),
                                    ft.DataCell(ft.Text(genome["status"], size=12)),
                                    ft.DataCell(
                                        ft.Row(
                                            controls=[
                                                ft.IconButton(
                                                    icon="description",
                                                    on_click=lambda e, acc=genome["name"].split('(')[-1].strip(')'): view_gff_analysis(acc, page, token) if genome.get("status", "").lower() == "completed" else None,
                                                    disabled=genome.get("status", "").lower() != "completed"
                                                ),
                                                ft.IconButton(
                                                    icon="delete",
                                                    icon_color="red",
                                                    on_click=lambda e, acc=genome["name"].split('(')[-1].strip(')'): open_confirmation_modal(acc),
                                                ),
                                            ],
                                            alignment="center",
                                            spacing=10,
                                        )
                                    ),
                                ],
                            )
                        )
                    page.update()
                else:
                    await log_message(page, f"Erro ao atualizar tabela de genomas: {response.text}")
        except Exception as ex:
            await log_message(page, f"Erro ao atualizar tabela de genomas: {ex}")

    async def fetch_gff_analysis(accession, token):
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://bioinfo-container:8000/genomes/{accession}/analyze", headers=headers)
                return response.json()["output"] if response.status_code == 200 else f"Erro: {response.text}"
        except Exception as ex:
            return f"Erro ao chamar o backend: {ex}"

    def view_gff_analysis(accession, page, token):
        dlg_gff_analysis = ft.AlertDialog(
            title=ft.Text(f"Análise do GFF para {accession}"),
            content=ft.Text("Carregando..."),
        )
        page.open(dlg_gff_analysis)
        analysis_result = asyncio.run(fetch_gff_analysis(accession, token))
        dlg_gff_analysis.content = ft.Text(analysis_result, selectable=True)
        page.update()

    async def delete_genome(accession):
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                dlg_modal_excluir_genoma.open = False
                page.update()
                response = await client.delete(f"http://bioinfo-container:8000/genomes/{accession}", headers=headers)
                if response.status_code == 200:
                    await log_message(page, f"Genoma {accession} excluído com sucesso.")
                    await update_tabela_genomas_referencia()
                else:
                    await log_message(page, f"Erro ao excluir genoma: {response.text}")
        except Exception as ex:
            await log_message(page, f"Erro ao excluir genoma: {ex}")

    def open_confirmation_modal(accession):
        global dlg_modal_excluir_genoma
        dlg_modal_excluir_genoma = ft.AlertDialog(
            title=ft.Text("Confirmar exclusão"),
            content=ft.TextField(hint_text="Digite 'Confirmar' para excluir."),
            actions=[
                ft.TextButton(
                    "Excluir",
                    on_click=lambda e: asyncio.run(delete_genome(accession)),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                ),
            ],
            actions_alignment="center",
        )
        page.open(dlg_modal_excluir_genoma)

    tabela_genomas_referencia = ft.DataTable(
        heading_row_color="black12",
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("Ações")),
        ],
        rows=[],
    )

    await update_tabela_genomas_referencia()

    tabela_genomas_disponiveis = ft.DataTable(
        heading_row_color="black12",
        columns=[
            ft.DataColumn(ft.Text("Accession", size=12)),
            ft.DataColumn(ft.Text("Assembly Name", size=12)),
            ft.DataColumn(ft.Text("Organism Name", size=12)),
            ft.DataColumn(ft.Text("Length", size=12)),
            ft.DataColumn(ft.Text("Submission Date", size=12)),
            ft.DataColumn(ft.Text("", size=12)),
        ],
        rows=[],
        column_spacing=10,
    )

    search_type_dropdown = ft.Dropdown(options=[ft.dropdown.Option("taxon"), ft.dropdown.Option("accession")], value="taxon", width=150)
    search_field = ft.TextField(label="Digite o termo de pesquisa", width=300)
    sjdb_overhang_field = ft.TextField(label="sjdbOverhang", value="100", width=140)
    threads_field = ft.TextField(label="Threads", value="4", width=90)

    async def buscar_genomas_handler(e):
        headers = {"Authorization": f"Bearer {token}"}
        search_type = search_type_dropdown.value
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://bioinfo-container:8000/genomes/search?{search_type}={search_field.value}", headers=headers)
                if response.status_code == 200:
                    data = response.json()["genomes"]
                    update_rows_with_checkboxes(data)
                else:
                    await log_message(page, f"Erro ao buscar genomas: {response.text}")
        except Exception as ex:
            await log_message(page, f"Erro ao buscar genomas: {ex}")

    buscar_genomas_button = ft.IconButton(icon="search", on_click=buscar_genomas_handler)

    def handle_checkbox_selection(row_index):
        for i, row in enumerate(tabela_genomas_disponiveis.rows):
            row.cells[5].content.value = (i == row_index)
        page.update()

    async def indexar_genoma_handler(e):
        selected_row = next((r for r in tabela_genomas_disponiveis.rows if r.cells[5].content.value), None)
        if not selected_row:
            await log_message(page, "Nenhum genoma selecionado.")
            return
        
        accession = selected_row.cells[0].content.value
        organism_name = selected_row.cells[2].content.value
        sjdb_overhang = sjdb_overhang_field.value
        threads = threads_field.value

        dlg_modal_genomas.open = False
        page.update()
        await download_genome(page, token, accession, organism_name, sjdb_overhang, threads)

    def update_rows_with_checkboxes(data):
        tabela_genomas_disponiveis.rows.clear()
        for i, genome in enumerate(data):
            tabela_genomas_disponiveis.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(genome["Assembly Accession"], size=12)),
                        ft.DataCell(ft.Text(genome["Assembly Name"], size=12)),
                        ft.DataCell(ft.Text(genome["Organism Name"], size=12, max_lines=None)),
                        ft.DataCell(ft.Text(str(genome.get("Assembly Stats Total Sequence Length", "0")), size=12, no_wrap=True)),
                        ft.DataCell(ft.Text(str(genome.get("Assembly BioSample Submission date", "")).split("T")[0], size=12)),
                        ft.DataCell(ft.Checkbox(on_change=lambda e, i=i: handle_checkbox_selection(i))),
                    ],
                )
            )
        page.update()

    form_layout = ft.Row(
        controls=[search_type_dropdown, search_field, buscar_genomas_button, ft.Container(width=25), sjdb_overhang_field, threads_field],
        spacing=10,
        alignment="start",
    )

    dlg_modal_genomas = ft.AlertDialog(
        title=ft.Text("Genomas de Referência"),
        content=ft.Container(
            content=ft.ListView(
                controls=[
                    tabela_genomas_referencia,
                    ft.Divider(height=1, thickness=1, color="black38"),
                    ft.Text("Buscar genomas disponíveis", weight="bold", size=14),
                    form_layout,
                    tabela_genomas_disponiveis,
                ],
            ),
            width=800,
        ),
        actions=[ft.TextButton("Indexar Genoma", on_click=indexar_genoma_handler)],
        actions_alignment="center",
    )
    page.open(dlg_modal_genomas)

async def download_genome(page, token, accession, organism_name, sjdb_overhang, threads):
    """Download a genome and trigger indexing."""
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=3600) as client:
            await log_message(page, f"Iniciando download do genoma {accession}...")
            response = await client.post(f"http://bioinfo-container:8000/genomes/download", params={"accession": accession}, headers=headers)
            if response.status_code == 200:
                # Simplified - assuming immediate indexing after download starts
                await index_genome(page, token, accession, organism_name, int(sjdb_overhang), int(threads))
            else:
                await log_message(page, f"Erro ao iniciar download: {response.text}")
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
                params={"accession": accession, "organism_name": organism_name, "sjdb_overhang": sjdb_overhang, "threads": threads},
                headers=headers,
            )
            if response.status_code == 200:
                await log_message(page, f"Genoma {organism_name} ({accession}) indexado com sucesso.")
            else:
                await log_message(page, f"Erro ao indexar genoma: {response.text}")
    except Exception as ex:
        await log_message(page, f"Erro ao indexar genoma: {ex}")
