import flet as ft
import httpx
import logging
import asyncio
import json  # Import JSON for serialization
from .utils import log_message

# Configure logging
logging.basicConfig(level=logging.INFO)  # Set to DEBUG level
logger = logging.getLogger(__name__)

tabela_selecao_trimmagem = None  # Inicializa a variável global como None

def create_tabela_amostras_trimmadas(page, token):  # Updated function signature
    global tabela_amostras_trimmadas, toggle_select_sample
    
    async def toggle_select_all_trimmadas(e):
        for row in tabela_amostras_trimmadas.rows:
            row.cells[2].content.value = e.control.value
        page.update()

    async def toggle_select_sample(e):
        """Toggle selection of a sample and ensure PE pairs are selected together."""
        selected_sample = e.control.data  # Retrieve the sample's SRA code
        is_selected = e.control.value

        # Check if the sample is PE (has _1.fastq and _2.fastq)
        if selected_sample.endswith("_1_trimmed.fastq"):
            paired_sample = selected_sample.replace("_1_trimmed.fastq", "_2_trimmed.fastq")
        elif selected_sample.endswith("_2_trimmed.fastq"):
            paired_sample = selected_sample.replace("_2_trimmed.fastq", "_1_trimmed.fastq")
        else:
            paired_sample = None

        # Update the state of the paired sample
        if paired_sample:
            for row in tabela_amostras_trimmadas.rows:
                # Access the Text inside the Container
                sample_name = row.cells[0].content.content.controls[0].content.value
                if sample_name == paired_sample:
                    row.cells[3].content.value = is_selected  # Select or deselect the paired sample
                    break

        # Update the page to reflect changes
        page.update()

    tabela_amostras_trimmadas = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_trimmadas)),  # Checkbox no cabeçalho
        ],
        rows=[],
    )
    return tabela_amostras_trimmadas

async def update_trimmagem_table(page, token):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://bioinfo-container:8000/samples/stages/3", headers=headers)
            if response.status_code == 200:
                samples = response.json()
                tabela_amostras_trimmadas.rows.clear()
                for sample in samples:
                    tabela_amostras_trimmadas.rows.append(
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
                                            scroll=ft.ScrollMode.HIDDEN,  # Add horizontal scroll
                                        ),
                                        width=130
                                    )
                                ),
                                ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Checkbox(data=sample["name"], on_change=toggle_select_sample))  # Checkbox individual
                            ],
                        )
                    )
                page.update()
            else:
                logger.error(f"Erro ao obter amostras trimmadas: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred while updating the trimmagem table: {e}", exc_info=True)

async def show_trimmagem_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela):
    """Exibe o modal de trimmagem com a tabela de seleção e o formulário de parâmetros."""
    global tabela_selecao_trimmagem  # Use a variável global para evitar problemas de escopo

    # Certifique-se de que a tabela foi criada antes de usá-la
    if tabela_selecao_trimmagem is None:
        tabela_selecao_trimmagem = create_tabela_selecao_trimmagem(page, token)

    await update_tabela_selecao_trimmagem(page, token)  # Atualiza a tabela de seleção

    # Verificar se a tabela de seleção está vazia
    if not tabela_selecao_trimmagem.rows:
        empty_message = ft.Column(
            controls=[
                ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
                ft.Text("Nenhuma amostra disponível para trimmagem", style=ft.TextStyle(size=16), text_align="center"),
                ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        iniciar_trimmagem_disabled = True
    else:
        empty_message = None
        iniciar_trimmagem_disabled = False

    # Criar campos do formulário
    def numeric_input_validator(e):
        if not e.control.value.isdigit():
            e.control.value = ''.join(filter(str.isdigit, e.control.value))
            page.update()

    async def handle_adapter_change(e):
        if e.control.value == "Personalizado":
            dlg_modal_trimmagem.open = False  # Fecha o modal principal
            page.update()
            page.open(custom_adapter_modal)  # Abre o modal de adaptadores personalizados
            page.update()

    def is_valid_fasta(content):
        """Valida se o conteúdo está no formato FASTA."""
        lines = content.strip().split("\n")
        if not lines or not lines[0].startswith(">"):
            return False
        for i in range(1, len(lines)):
            if lines[i].startswith(">"):
                continue
            if not all(c in "ACGTNacgtn " for c in lines[i]):
                return False
        return True

    async def save_custom_adapter(e):
        nonlocal custom_adapter_content
        if not is_valid_fasta(custom_adapter_field.value):
            custom_adapter_field.error_text = "O conteúdo inserido não é um arquivo FASTA válido."
            page.update()
            return
        custom_adapter_content = custom_adapter_field.value
        custom_adapter_modal.open = False  # Fecha o modal de adaptadores personalizados
        page.open(dlg_modal_trimmagem)  # Reabre o modal principal
        page.update()

    threads_field = ft.TextField(
        label="Threads",
        value="1",
        tooltip="Número de threads a serem utilizados para processamento paralelo.\n\n"
                "Valor padrão: 1. Aumente para melhorar o desempenho em máquinas com mais núcleos.",
        on_change=numeric_input_validator,
        width=280,
    )
    phred_dropdown = ft.Dropdown(
        label="Codificação Phred",
        options=[
            ft.dropdown.Option("autodetect"),
            ft.dropdown.Option("phred33"),
            ft.dropdown.Option("phred64"),
        ],
        value="autodetect",
        tooltip="Codificação Phred para os arquivos FASTQ. Use 'autodetect' para detectar automaticamente.\n\n"
                "Opções:\n- phred33: Codificação padrão para a maioria dos arquivos modernos.\n"
                "- phred64: Codificação antiga usada em alguns arquivos.",
        width=280,
    )
    custom_adapter_content = None  # Armazena o conteúdo do adaptador personalizado

    illumina_clip_fields = [
        ft.Dropdown(
            label="Arquivo adaptadores",
            options=[
                ft.dropdown.Option("NexteraPE-PE.fa"),
                ft.dropdown.Option("TruSeq2-PE.fa"),
                ft.dropdown.Option("TruSeq2-SE.fa"),
                ft.dropdown.Option("TruSeq3-PE-2.fa"),
                ft.dropdown.Option("TruSeq3-PE.fa"),
                ft.dropdown.Option("TruSeq3-SE.fa"),
                ft.dropdown.Option("Personalizado"),
            ],
            value="TruSeq3-PE.fa",
            tooltip="Selecione o arquivo de adaptadores para remoção. Escolha 'Personalizado' para fornecer seu próprio conteúdo.",
            width=280,
            on_change=handle_adapter_change,
        ),
        ft.TextField(
            label="Seed mismatches",
            value="2",
            tooltip="Número máximo de mismatches permitidos no alinhamento inicial ('seed').\n\n"
                    "Valor padrão: 2. Valores mais altos aumentam a sensibilidade, mas podem levar a falsos positivos.",
            on_change=numeric_input_validator,
            width=280,
        ),
        ft.TextField(
            label="Threshold palíndromo",
            value="30",
            tooltip="Limiar de precisão para o alinhamento no modo palíndromo (usado em dados paired-end).\n\n"
                    "Valor padrão: 30. Um valor alto garante que apenas adapters com alinhamento muito preciso sejam removidos.",
            on_change=numeric_input_validator,
            width=280,
        ),
        ft.TextField(
            label="Threshold simples",
            value="10",
            tooltip="Limiar de precisão para o alinhamento no modo simples (usado em dados single-end).\n\n"
                    "Valor padrão: 10. Valores mais baixos são suficientes para single-end, pois o alinhamento é menos complexo.",
            on_change=numeric_input_validator,
            width=280,
        ),
        ft.TextField(
            label="Comprimento mínimo adaptador",
            value="8",
            tooltip="Comprimento mínimo de adapter que deve ser detectado para remoção.\n\n"
                    "Valor padrão: 8. Valores menores permitem remover fragmentos muito curtos de adapters.",
            on_change=numeric_input_validator,
            width=280,
        ),
        ft.TextField(
            label="",
            width=280,
            visible=True,
            disabled=True
        ),
    ]

    # Definir os campos ausentes antes de usá-los no layout do formulário
    sliding_window_fields = [
        ft.TextField(
            label="Tamanho janela",
            value="4",
            tooltip="Número de bases analisadas em cada janela deslizante para calcular a qualidade média.\n\n"
                    "Valor padrão: 4 (típico). Exemplo: Uma janela de 4 bases avalia a qualidade média a cada 4 bases.",
            width=280,
        ),
        ft.TextField(
            label="Qualidade mínima",
            value="15",
            tooltip="Qualidade média mínima (em Phred) exigida dentro da janela para manter as bases.\n\n"
                    "Valor padrão: 15 (equivalente a 97% de precisão). Impacto: Se a média da janela estiver abaixo desse valor, "
                    "a sequência é cortada a partir dali.",
            width=280,
        ),
    ]

    max_info_fields = [
        ft.TextField(
            label="Comprimento alvo",
            value="40",
            tooltip="Comprimento mínimo desejado para as reads após o trim.\n\n"
                    "Valor padrão: 40 (suficiente para alinhamento único em genomas pequenos). Explicação: Reads mais curtas que isso são penalizadas.",
            width=280,
        ),
        ft.TextField(
            label="Strictness",
            value="0.5",
            tooltip="Balanceia entre manter bases adicionais (valores baixos) ou priorizar qualidade (valores altos).\n\n"
                    "Valor padrão: 0.5 (equilíbrio). Escala: 0 (favorece comprimento) a 1 (favorece qualidade).",
            width=280,
        ),
    ]

    leading_field = ft.TextField(
        label="LEADING - Qualidade mínima",
        value="3",
        tooltip="Remove bases de baixa qualidade no início da read (5').\n\n"
                "Valor padrão: 3 (qualidade Phred 3, muito baixa). Exemplo: Se a primeira base tiver qualidade 2, é removida.",
        width=280,
    )

    trailing_field = ft.TextField(
        label="TRAILING - Qualidade mínima",
        value="3",
        tooltip="Remove bases de baixa qualidade no final da read (3').\n\n"
                "Valor padrão: 3 (similar a LEADING).",
        width=280,
    )

    crop_field = ft.TextField(
        label="CROP - Comprimento",
        value="",
        tooltip="Corta a read para um comprimento fixo, independentemente da qualidade.\n\n"
                "Exemplo: Se CROP:50, apenas as primeiras 50 bases são mantidas.",
        width=280,
    )

    headcrop_field = ft.TextField(
        label="HEADCROP - Número de bases",
        value="",
        tooltip="Remove um número fixo de bases do início da read (útil para primers).\n\n"
                "Exemplo: HEADCROP:5 remove as 5 primeiras bases.",
        width=280,
    )

    minlen_field = ft.TextField(
        label="MINLEN - Comprimento mínimo",
        value="36",
        tooltip="Descarta reads com comprimento menor que o especificado.\n\n"
                "Valor padrão: 36 (comum para garantir reads úteis).",
        width=280,
    )

    avgqual_field = ft.TextField(
        label="AVGQUAL - Qualidade média",
        value="",
        tooltip="Descarta reads cuja qualidade média (Phred) esteja abaixo do valor.\n\n"
                "Exemplo: AVGQUAL:20 remove reads com média de qualidade < 20.",
        width=280,
    )

    # Modal para adaptadores personalizados
    custom_adapter_field = ft.TextField(
        label="Adaptadores Personalizados",
        hint_text="Insira o conteúdo dos adaptadores aqui",
        multiline=True,
        expand=True,
    )
    custom_adapter_modal = ft.AlertDialog(
        title=ft.Text("Adaptadores Personalizados"),
        content=custom_adapter_field,
        actions=[
            ft.TextButton(
                "Salvar",
                on_click=save_custom_adapter,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            )
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    # Função para iniciar a trimmagem
    async def start_trimmagem(e):
        selected_samples = [row.cells[0].content.value for row in tabela_selecao_trimmagem.rows if row.cells[3].content.value]
        if not selected_samples:
            logger.error("Nenhuma amostra selecionada para trimmagem.")
            return

        # Coletar parâmetros do formulário
        params = {
            "threads": threads_field.value,
            "phred": phred_dropdown.value,
            "illumina_clip": {
                "Arquivo adaptadores": illumina_clip_fields[0].value,
                "Seed mismatches": illumina_clip_fields[1].value,
                "Threshold palíndromo": illumina_clip_fields[2].value,
                "Threshold simples": illumina_clip_fields[3].value,
                "Comprimento mínimo adaptador": illumina_clip_fields[4].value,
            },
        }
        logger.info(f"Parâmetros coletados: {params}")

        await log_message(page, f"Iniciando trimmagem para {selected_samples}")
        dlg_modal_trimmagem.open = False
        page.update()

        # Lógica para iniciar a trimmagem
        await processar_trimmagem(page, token, selected_samples, container_menu_direita, tabela_amostras_local, atualizar_tabela)

    # Organize input fields into a structured layout with two columns
    form_layout = ft.Column(
        controls=[
            ft.Text(" ", style=ft.TextStyle(size=16)),
            ft.Row(
                controls=[
                    threads_field,
                    phred_dropdown,
                ],
                spacing=27
            ),
            ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
            ft.Text("IlluminaClip Parameters", style=ft.TextStyle(size=14, weight="bold")),
            ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            illumina_clip_fields[0],  # Arquivo adaptadores
                            illumina_clip_fields[1],  # Seed mismatches
                            illumina_clip_fields[2],  # Threshold palíndromo
                        ],
                        expand=1,
                    ),
                    ft.Column(
                        controls=[
                            illumina_clip_fields[3],  # Threshold simples
                            illumina_clip_fields[4],  # Comprimento mínimo adaptador
                            illumina_clip_fields[5],
                        ],
                        expand=1,
                    ),
                ],
            ),
            ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
            ft.Text("SlidingWindow Parameters", style=ft.TextStyle(size=14, weight="bold")),
            ft.Row(
                controls=[
                    sliding_window_fields[0],  # Tamanho janela
                    sliding_window_fields[1],  # Qualidade mínima
                ],
                spacing=27
            ),
            ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
            ft.Text("MaxInfo Parameters", style=ft.TextStyle(size=14, weight="bold")),
            ft.Row(
                controls=[
                    max_info_fields[0],  # Comprimento alvo
                    max_info_fields[1],  # Strictness
                ],
                spacing=27
            ),
            ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
            ft.Text("Other Parameters", style=ft.TextStyle(size=14, weight="bold")),
            ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            leading_field,  # LEADING
                            crop_field,  # CROP
                            minlen_field,  # MINLEN
                        ],
                        expand=1,
                    ),
                    ft.Column(
                        controls=[
                            trailing_field,  # TRAILING
                            headcrop_field,  # HEADCROP
                            avgqual_field,  # AVGQUAL
                        ],
                        expand=1,
                    ),
                ],
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
    )

    # Create the modal dialog
    dlg_modal_trimmagem = ft.AlertDialog(
        title=ft.Text("Iniciar Trimmagem"),
        content=ft.Container(
            content=ft.ListView(
                controls=[
                    empty_message if empty_message else tabela_selecao_trimmagem,  # Show message if table is empty
                    form_layout,  # Use the updated form layout
                ],
            ),
            width=600,  # Adjust width to fit the layout
        ),
        actions=[
            ft.TextButton(
                "Iniciar Trimmagem",
                on_click=start_trimmagem if not iniciar_trimmagem_disabled else None,
                disabled=iniciar_trimmagem_disabled,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_trimmagem)

async def processar_trimmagem(page, token, selected_samples, container_menu_direita, tabela_amostras_local, atualizar_tabela):
    """Processa a trimmagem para as amostras selecionadas."""
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            logger.info("Preparando os dados para a requisição de trimmagem.")
            form_data = {"selected_samples": json.dumps(selected_samples)}
            response = await client.post(
                "http://bioinfo-container:8000/trimmagem/",
                data=form_data,
                headers=headers,
            )
            if response.status_code == 200:
                logger.info("Trimmagem concluída com sucesso!")
                await log_message(page, "Trimmagem concluída com sucesso!")
                # Atualizar tabelas após o processamento
                await update_trimmagem_table(page, token)
                await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                page.update()
            else:
                logger.error(f"Erro ao iniciar trimmagem: {response.status_code} - {response.text}")
                await log_message(page, f"Erro ao iniciar trimmagem: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Erro ao processar trimmagem: {e}", exc_info=True)
        await log_message(page, f"Erro ao processar trimmagem: {e}")

async def make_request(method, url, headers=None, json=None, params=None):
    """Helper function to make HTTP requests."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=headers, json=json, params=params)
            response.raise_for_status()
            return response
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise

async def show_trimmagem_table(page, token, tabela_amostras_local):
    """Exibe a tabela de trimmagem no container_amostras."""
    await update_trimmagem_table(page, token)
    tabela_amostras_local.rows = tabela_amostras_trimmadas.rows  # Atualiza as linhas da tabela local
    page.update()

def create_tabela_selecao_trimmagem(page, token):
    """Cria a tabela para seleção de amostras para trimmagem."""
    global tabela_selecao_trimmagem

    async def toggle_select_all_selecao(e):
        """Seleciona ou desmarca todas as amostras na tabela de seleção."""
        for row in tabela_selecao_trimmagem.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    tabela_selecao_trimmagem = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_selecao)),  # Checkbox no cabeçalho
        ],
        rows=[],
    )
    return tabela_selecao_trimmagem

async def update_tabela_selecao_trimmagem(page, token):
    """Atualiza a tabela de seleção com amostras disponíveis para trimmagem."""
    global tabela_selecao_trimmagem  # Use a variável global para acessar a tabela

    async def toggle_select_sample(e):
        """Seleciona ou desmarca uma amostra e garante que pares PE sejam selecionados juntos."""
        selected_sample = e.control.data  # Recupera o código SRA da amostra
        is_selected = e.control.value

        # Verifica se a amostra é PE (possui _1.fastq e _2.fastq)
        if selected_sample.endswith("_1.fastq"):
            paired_sample = selected_sample.replace("_1.fastq", "_2.fastq")
        elif selected_sample.endswith("_2.fastq"):
            paired_sample = selected_sample.replace("_2.fastq", "_1.fastq")
        else:
            paired_sample = None

        # Atualiza o estado da amostra pareada
        if paired_sample:
            for row in tabela_selecao_trimmagem.rows:
                sample_name = row.cells[0].content.value
                if sample_name == paired_sample:
                    row.cells[3].content.value = is_selected  # Seleciona ou desmarca a amostra pareada
                    break

        # Atualiza a página para refletir as mudanças
        page.update()

    # Certifique-se de que a tabela foi criada antes de usá-la
    if tabela_selecao_trimmagem is None:
        tabela_selecao_trimmagem = create_tabela_selecao_trimmagem(page, token)

    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            # Obter amostras baixadas (stage_id=1)
            response_stage_1 = await client.get("http://bioinfo-container:8000/samples/stages/1", headers=headers)
            if response_stage_1.status_code == 200:
                downloaded_samples = response_stage_1.json()
            else:
                logger.error(f"Erro ao obter amostras baixadas: {response_stage_1.status_code} - {response_stage_1.text}")
                downloaded_samples = []

            # Obter amostras já trimmadas (stage_id=3)
            response_stage_3 = await client.get("http://bioinfo-container:8000/samples/stages/3", headers=headers)
            if response_stage_3.status_code == 200:
                trimmed_samples = {sample["sra_code"] for sample in response_stage_3.json()}
            else:
                logger.error(f"Erro ao obter amostras trimmadas: {response_stage_3.status_code} - {response_stage_3.text}")
                trimmed_samples = set()

            # Filtrar amostras baixadas que ainda não foram trimmadas
            samples = [sample for sample in downloaded_samples if sample["sra_code"] not in trimmed_samples]

            # Atualizar a tabela de seleção
            tabela_selecao_trimmagem.rows.clear()
            for sample in samples:
                tabela_selecao_trimmagem.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(sample["name"], style=ft.TextStyle(size=12))),
                            ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                            ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                            ft.DataCell(ft.Checkbox(data=sample["name"], on_change=toggle_select_sample)),  # Checkbox individual
                        ],
                    )
                )
            page.update()
    except Exception as e:
        logger.error(f"An error occurred while updating the selection table: {e}", exc_info=True)