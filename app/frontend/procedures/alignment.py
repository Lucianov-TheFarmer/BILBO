import flet as ft
import httpx
import logging
import asyncio
import json
import websockets
from .utils import log_message
from .viewer import view_alignment_log  # Importar a função de exibição de logs

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
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("Log")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_alignment)),  # Checkbox in the header
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
                        # Executar a função assíncrona no contexto do loop de eventos
                        asyncio.run(view_alignment_log(page, token, s, user_id))

                    # Determinar se o botão de log deve estar ativo ou inativo
                    log_button_disabled = sample["status"] != "Completed"

                    tabela_alinhamento.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(sample["name"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                                ft.DataCell(
                                    ft.IconButton(
                                        icon=ft.icons.DESCRIPTION,
                                        tooltip="Visualizar log",
                                        on_click=view_log_handler if not log_button_disabled else None,
                                        disabled=log_button_disabled,  # Desativar botão se não for "Completed"
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
            # Add all samples to the database
            response = await client.post(
                "http://bioinfo-container:8000/alignment/add_samples",
                data={
                    "samples": json.dumps(selected_samples),  # Serializar a lista como JSON
                    "genome": genome,
                },
                headers=headers,
            )
            if response.status_code != 200:
                logger.error(f"Erro ao adicionar amostras: {response.status_code} - {response.text}")
                await log_message(page, f"Erro ao adicionar amostras: {response.status_code} - {response.text}")
                return

            # Extrair basenames únicos das amostras
            basenames = list({sample.split('_')[0] for sample in selected_samples})
            logger.info(f"Basenames identificados no frontend: {basenames}")

            # Process samples one by one
            for basename in basenames:
                response = await client.post(
                    "http://bioinfo-container:8000/alignment/start",
                    data={"sample": basename, "genome": genome, "token": token},
                    params={"threads": params["threads"]},
                    headers=headers,
                )
                if response.status_code == 200:
                    await update_tabela_alinhamento(page, token, user_id)  # Replace `1` with the actual user_id
                    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)

                    # Intercept WebSocket logs
                    async with websockets.connect(f"ws://bioinfo-container:8000/ws?token={token}") as websocket:
                        async for message in websocket:
                            if f"Alinhamento concluído para {basename}" in message:
                                await log_message(page, message)
                                await update_tabela_alinhamento(page, token, user_id)  # Replace `1` with the actual user_id
                                await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                                break  # Sair do loop WebSocket após receber a mensagem de conclusão
                else:
                    logger.error(f"Erro ao iniciar alinhamento para {basename}: {response.status_code} - {response.text}")
                    await log_message(page, f"Erro ao iniciar alinhamento para {basename}: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Erro ao iniciar alinhamento: {e}", exc_info=True)
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
                        logger.info(f"Alinhamento {sample} excluído com sucesso!")
                        await log_message(page, f"Alinhamento {sample} excluído com sucesso!")
                    else:
                        logger.error(f"Erro ao excluir alinhamento {sample}: {response.status_code} - {response.text}")
            await update_tabela_alinhamento(page, token, user_id)  # Replace `1` with the actual user_id
            await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
            page.update()
        except Exception as e:
            logger.error(f"Erro ao excluir alinhamentos: {e}", exc_info=True)

        dlg_modal_excluir_alinhamento.open = False
        page.update()

    # Modal de confirmação
    confirmation_field = ft.TextField(
        hint_text="Digite 'Confirmar' para excluir os alinhamentos selecionados.",
        border_radius=ft.border_radius.all(4),
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
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_excluir_alinhamento)

async def show_alignment_modal(page, token, user_id, atualizar_tabela, container_menu_direita, tabela_amostras_local):
    """Exibe o modal para configurar e iniciar o alinhamento."""
    global tabela_trimmados, tabela_genomas_referencia

    # Tabela de amostras trimmadas
    async def toggle_select_sample(e):
        """Seleciona ou desmarca uma amostra e garante que pares PE sejam selecionados juntos."""
        selected_sample = e.control.data  # Recupera o nome da amostra
        is_selected = e.control.value

        # Verifica se a amostra é PE (possui _1_trimmed.fastq e _2_trimmed.fastq)
        if selected_sample.endswith("_1_trimmed.fastq"):
            paired_sample = selected_sample.replace("_1_trimmed.fastq", "_2_trimmed.fastq")
        elif selected_sample.endswith("_2_trimmed.fastq"):
            paired_sample = selected_sample.replace("_2_trimmed.fastq", "_1_trimmed.fastq")
        else:
            paired_sample = None

        # Atualiza o estado da amostra pareada
        if paired_sample:
            for row in tabela_trimmados.rows:
                sample_name = row.cells[0].content.value
                if sample_name == paired_sample:
                    row.cells[3].content.value = is_selected  # Seleciona ou desmarca a amostra pareada
                    break

        # Atualiza a página para refletir as mudanças
        page.update()

    async def toggle_select_all_trimmados(e):
        """Seleciona ou desmarca todas as amostras na tabela."""
        for row in tabela_trimmados.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    tabela_trimmados = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_trimmados)),  # Checkbox no cabeçalho
        ],
        rows=[],
    )

    # Tabela de genomas de referência
    def handle_checkbox_selection(row_index):
        """Permite selecionar apenas um genoma de referência por vez."""
        for i, row in enumerate(tabela_genomas_referencia.rows):
            checkbox = row.cells[3].content
            checkbox.value = (i == row_index)  # Apenas o checkbox clicado permanece selecionado
        page.update()

    tabela_genomas_referencia = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("")),  # Sem checkbox no cabeçalho
        ],
        rows=[],
    )

    # Atualiza a tabela de amostras trimmadas
    async def update_tabela_trimmados():
        """Atualiza a tabela de amostras trimmadas disponíveis para alinhamento."""
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                # Obter amostras trimmadas (stage_id=3)
                response_trimmados = await client.get("http://bioinfo-container:8000/samples/stages/3", headers=headers)
                if response_trimmados.status_code == 200:
                    trimmed_samples = response_trimmados.json()
                    logger.info(f"Amostras trimmadas (stage_id=3): {trimmed_samples}")
                else:
                    logger.error(f"Erro ao obter amostras trimmadas: {response_trimmados.status_code} - {response_trimmados.text}")
                    trimmed_samples = []

                # Obter amostras já alinhadas (stage_id=5)
                response_alinhadas = await client.get("http://bioinfo-container:8000/alignment/", headers=headers)
                if response_alinhadas.status_code == 200:
                    aligned_samples = {sample["name"].replace(".bam", "") for sample in response_alinhadas.json()}
                    logger.info(f"Amostras alinhadas (stage_id=5): {aligned_samples}")
                else:
                    logger.error(f"Erro ao obter amostras alinhadas: {response_alinhadas.status_code} - {response_alinhadas.text}")
                    aligned_samples = set()

                # Filtrar amostras trimmadas que ainda não foram alinhadas
                available_samples = [
                    sample for sample in trimmed_samples
                    if sample["name"].replace("_1_trimmed.fastq", "").replace("_2_trimmed.fastq", "") not in aligned_samples
                ]
                logger.info(f"Amostras disponíveis para alinhamento: {available_samples}")

                # Atualizar a tabela com as amostras disponíveis
                tabela_trimmados.rows.clear()
                for sample in available_samples:
                    tabela_trimmados.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(sample["name"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Checkbox(data=sample["name"], on_change=toggle_select_sample)),
                            ],
                        )
                    )
                page.update()
        except Exception as e:
            logger.error(f"Erro ao atualizar tabela de trimmados: {e}")

    # Atualiza a tabela de genomas de referência
    async def update_tabela_genomas_referencia():
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://bioinfo-container:8000/genomes/", headers=headers)
                if response.status_code == 200:
                    genomes = response.json()
                    tabela_genomas_referencia.rows.clear()
                    for index, genome in enumerate(genomes):  # Use enumerate to get the correct row index
                        tabela_genomas_referencia.rows.append(
                            ft.DataRow(
                                cells=[
                                    ft.DataCell(ft.Text(genome["name"], style=ft.TextStyle(size=12))),
                                    ft.DataCell(ft.Text(genome["size"], style=ft.TextStyle(size=12))),
                                    ft.DataCell(ft.Text(genome["status"], style=ft.TextStyle(size=12))),
                                    ft.DataCell(ft.Checkbox(on_change=lambda e, row_index=index: handle_checkbox_selection(row_index))),
                                ],
                            )
                        )
                    page.update()
        except Exception as e:
            logger.error(f"Erro ao atualizar tabela de genomas: {e}")

    # Campos de parâmetros do STAR
    threads_field = ft.TextField(
        label="Threads",
        value="4",
        tooltip="Número de threads para o STAR. Valor padrão: 4.",
        width=300,
    )
    out_filter_type_field = ft.TextField(
        label="outFilterType",
        value="",
        tooltip="Reduz junções espúrias (Opcional). Ex.: BySJout.",
        width=300,
    )
    out_filter_multimap_field = ft.TextField(
        label="outFilterMultimapNmax",
        value="",
        tooltip="Máximo de alinhamentos múltiplos permitidos (Opcional).",
        width=300,
    )
    align_sj_overhang_min_field = ft.TextField(
        label="alignSJoverhangMin",
        value="",
        tooltip="Sobreposição mínima para junções não anotadas (Opcional).",
        width=300,
    )
    align_sjdb_overhang_min_field = ft.TextField(
        label="alignSJDBoverhangMin",
        value="",
        tooltip="Sobreposição mínima para junções anotadas (Opcional).",
        width=300,
    )
    out_filter_mismatch_max_field = ft.TextField(
        label="outFilterMismatchNmax",
        value="",
        tooltip="Máximo de mismatches por par (Opcional).",
        width=300,
    )
    out_filter_mismatch_over_read_field = ft.TextField(
        label="outFilterMismatchNoverReadLmax",
        value="",
        tooltip="Máximo de mismatches relativo ao comprimento da leitura (Opcional).",
        width=300,
    )
    align_intron_min_field = ft.TextField(
        label="alignIntronMin",
        value="",
        tooltip="Comprimento mínimo do intron (Opcional).",
        width=300,
    )
    align_intron_max_field = ft.TextField(
        label="alignIntronMax",
        value="",
        tooltip="Comprimento máximo do intron (Opcional).",
        width=300,
    )
    align_mates_gap_max_field = ft.TextField(
        label="alignMatesGapMax",
        value="",
        tooltip="Distância máxima entre mates (Opcional).",
        width=300,
    )

    # Função para iniciar o alinhamento
    async def start_alignment(e):
        selected_samples = [row.cells[0].content.value for row in tabela_trimmados.rows if row.cells[-1].content.value]
        selected_genomes = [row.cells[0].content.value for row in tabela_genomas_referencia.rows if row.cells[-1].content.value]

        if not selected_samples:
            await log_message(page, "Nenhuma amostra selecionada para alinhamento.")
            return
        if not selected_genomes:
            await log_message(page, "Nenhum genoma de referência selecionado.")
            return

        params = {
            "threads": threads_field.value,
            "outFilterType": out_filter_type_field.value,
            "outFilterMultimapNmax": out_filter_multimap_field.value,
            "alignSJoverhangMin": align_sj_overhang_min_field.value,
            "alignSJDBoverhangMin": align_sjdb_overhang_min_field.value,
            "outFilterMismatchNmax": out_filter_mismatch_max_field.value,
            "outFilterMismatchNoverReadLmax": out_filter_mismatch_over_read_field.value,
            "alignIntronMin": align_intron_min_field.value,
            "alignIntronMax": align_intron_max_field.value,
            "alignMatesGapMax": align_mates_gap_max_field.value,
        }

        dlg_modal_alignment.open = False
        page.update()

        # Log com o nome das amostras
        await log_message(page, f"Iniciando alinhamento para as amostras: {', '.join(selected_samples)}")
        await iniciar_alinhamento(page, token, user_id, selected_samples, selected_genomes[0], params, atualizar_tabela, container_menu_direita, tabela_amostras_local)

    # Modal de alinhamento
    dlg_modal_alignment = ft.AlertDialog(
        title=ft.Text("Configurar Alinhamento"),
        content=ft.Container(
            content=ft.ListView(
                controls=[
                    ft.Text("Amostras Trimmadas", style=ft.TextStyle(size=14, weight="bold")),
                    ft.Container(height=10),
                    tabela_trimmados,
                    ft.Container(height=10),
                    ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
                    ft.Container(height=10),
                    ft.Text("Genomas de Referência", style=ft.TextStyle(size=14, weight="bold")),
                    ft.Container(height=10),
                    tabela_genomas_referencia,
                    ft.Container(height=10),
                    ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
                    ft.Container(height=10),
                    ft.Text("Parâmetros adicionais do STAR", style=ft.TextStyle(size=14, weight="bold")),
                    ft.Container(height=20),
                    ft.Row(
                        controls=[
                            ft.Column(
                                controls=[
                                    threads_field,
                                    out_filter_type_field,
                                    out_filter_multimap_field,
                                    align_sj_overhang_min_field,
                                    align_sjdb_overhang_min_field,
                                ],
                                spacing=20,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Column(
                                controls=[
                                    out_filter_mismatch_max_field,
                                    out_filter_mismatch_over_read_field,
                                    align_intron_min_field,
                                    align_intron_max_field,
                                    align_mates_gap_max_field,
                                ],
                                spacing=20,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=50,  # Espaçamento entre as colunas
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
            ),
            width=900,  # Largura ajustada para acomodar os campos maiores
        ),
        actions=[
            ft.TextButton(
                "Iniciar Alinhamento",
                on_click=start_alignment,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    # Atualiza as tabelas e abre o modal
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
        """Atualiza as linhas da tabela de genomas disponíveis com checkboxes."""
        tabela_genomas_disponiveis.rows.clear()
        for i, genome in enumerate(data):  # Corrigido para usar apenas dois valores (índice e item)
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

