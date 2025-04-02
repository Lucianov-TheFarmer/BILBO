import flet as ft
import httpx
import logging
import asyncio
import json  # Import JSON for serialization
from .utils import log_message

# Configure logging
logging.basicConfig(level=logging.INFO)  # Set to DEBUG level
logger = logging.getLogger(__name__)

async def show_trimmagem_modal(page, token, tabela_amostras_local, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    samples = []

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:  # Enable follow_redirects
            response = await client.get("http://bioinfo-container:8000/samples?status=Completed", headers=headers)
            if response.status_code == 200:
                samples = response.json()
            else:
                logger.info(f"Erro ao obter amostras: {response.status_code} - {response.text}")
    except Exception as e:
        logger.info(f"An error occurred while fetching samples: {e}")

    # Function to select or deselect all samples
    async def toggle_select_all(e):
        for row in tabela_trimmagem.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    async def toggle_select_sample(e):
        """Toggle selection of a sample and ensure PE pairs are selected together."""
        selected_sample = e.control.data  # Retrieve the sample's SRA code
        is_selected = e.control.value

        # Check if the sample is PE (has _1.fastq and _2.fastq)
        if selected_sample.endswith("_1.fastq"):
            paired_sample = selected_sample.replace("_1.fastq", "_2.fastq")
            for row in tabela_trimmagem.rows:
                if row.cells[0].content.value == paired_sample:
                    row.cells[3].content.value = is_selected  # Select or deselect the paired sample
                    break
        elif selected_sample.endswith("_2.fastq"):
            paired_sample = selected_sample.replace("_2.fastq", "_1.fastq")
            for row in tabela_trimmagem.rows:
                if row.cells[0].content.value == paired_sample:
                    row.cells[3].content.value = is_selected
                    break
                
        # Update the page to reflect changes
        page.update()

    # Create the table with samples
    tabela_trimmagem = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all)),  # Add toggle_select_sample handler
        ],
        rows=[
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sample["sra_code"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Checkbox(data=sample["sra_code"], on_change=toggle_select_sample)),  # Pass the SRA code as data
                ],
            ) for sample in samples
        ],
    )

    # Check if the table is empty
    if not tabela_trimmagem.rows:
        empty_message = ft.Column(
            controls=[
                ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
                ft.Text("Nenhuma amostra baixada", style=ft.TextStyle(size=16), text_align="center"),
                ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        iniciar_trimmagem_disabled = True  # Disable the button
    else:
        empty_message = None
        iniciar_trimmagem_disabled = False  # Enable the button

    # Create input fields for parameters
    def numeric_input_validator(e):
        if not e.control.value.isdigit():
            e.control.value = ''.join(filter(str.isdigit, e.control.value))
            page.update()

    async def handle_adapter_change(e):
        if e.control.value == "Personalizado":
            dlg_modal_trimmagem.open = False  # Hide the first modal
            page.update()
            page.open(custom_adapter_modal)
            page.update()

    def is_valid_fasta(content):
        """Validate if the content is in FASTA format."""
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
        custom_adapter_modal.open = False  # Close the second modal
        page.open(dlg_modal_trimmagem)
        page.update()

    # Generalized function to create TextField
    def create_text_field(label, value, tooltip, width=280, on_change=numeric_input_validator, visible=True, disabled=False):
        return ft.TextField(
            label=label,
            value=value,
            width=width,
            on_change=on_change,
            tooltip=tooltip,
            visible=visible,
            disabled=disabled,
        )

    # Create input fields for parameters using the generalized function
    threads_field = create_text_field(
        label="Threads",
        value="1",
        tooltip="Número de threads a serem utilizados para processamento paralelo."
    )
    phred_dropdown = ft.Dropdown(
        label="Codificação Phred",
        options=[
            ft.dropdown.Option("autodetect"),
            ft.dropdown.Option("phred33"),
            ft.dropdown.Option("phred64"),
        ],
        width=280,
        value="autodetect",
        tooltip="Codificação Phred para os arquivos FASTQ. Use 'autodetect' para detectar automaticamente."
    )
    custom_adapter_content = None  # Store the custom adapter content
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
            width=280,
            value="TruSeq3-PE.fa",  # Default value
            on_change=handle_adapter_change,
            tooltip="Selecione o arquivo de adaptadores para remoção. Escolha 'Personalizado' para fornecer seu próprio conteúdo."
        ),
        create_text_field(
            label="Seed mismatches",
            value="2",
            tooltip="Número máximo de mismatches permitidos no alinhamento inicial ('seed') de 16 bases entre o adapter e a sequência.\n\nValor padrão: 2 (recomendado).\nImpacto: Valores mais altos aumentam a sensibilidade, mas podem levar a falsos positivos."
        ),
        create_text_field(
            label="Threshold palíndromo",
            value="30",
            tooltip="Limiar de precisão para o alinhamento no modo palíndromo (usado em dados paired-end).\n\nValor padrão: 30 (recomendado para paired-end).\nExplicação: Um valor alto garante que apenas adapters com alinhamento muito preciso sejam removidos."
        ),
        create_text_field(
            label="Threshold simples",
            value="10",
            tooltip="Limiar de precisão para o alinhamento no modo simples (usado em dados single-end).\n\nValor padrão: 10 (recomendado para single-end).\nExplicação: Valores mais baixos são suficientes para single-end, pois o alinhamento é menos complexo."
        ),
        create_text_field(
            label="Comprimento mínimo adaptador",
            value="8",
            tooltip="Comprimento mínimo de adapter que deve ser detectado para remoção.\n\nValor padrão: 8 (histórico), mas pode ser reduzido para 1 sem riscos.\nImpacto: Valores menores permitem remover fragmentos muito curtos de adapters."
        ),
        create_text_field(
            label="",
            value="",
            tooltip="",
            visible=True,
            disabled=True  # Invisible TextField for alignment
        ),
    ]
    sliding_window_fields = [
        create_text_field(
            label="Tamanho janela",
            value="4",
            tooltip="Número de bases analisadas em cada janela deslizante para calcular a qualidade média.\n\nValor padrão: 4 (típico).\nExemplo: Uma janela de 4 bases avalia a qualidade média a cada 4 bases."
        ),
        create_text_field(
            label="Qualidade mínima",
            value="15",
            tooltip="Qualidade média mínima (em Phred) exigida dentro da janela para manter as bases.\n\nValor padrão: 15 (equivalente a 97% de precisão).\nImpacto: Se a média da janela estiver abaixo desse valor, a sequência é cortada a partir dali."
        ),
    ]
    max_info_fields = [
        create_text_field(
            label="Comprimento alvo",
            value="40",
            tooltip="Comprimento mínimo desejado para as reads após o trim.\n\nValor padrão: 40 (suficiente para alinhamento único em genomas pequenos).\nExplicação: Reads mais curtas que isso são penalizadas."
        ),
        create_text_field(
            label="Strictness",
            value="0.5",
            tooltip="Balanceia entre manter bases adicionais (valores baixos) ou priorizar qualidade (valores altos).\n\nValor padrão: 0.5 (equilíbrio).\nEscala: 0 (favorece comprimento) a 1 (favorece qualidade)."
        ),
    ]
    leading_field = create_text_field(
        label="LEADING - Qualidade mínima",
        value="3",
        tooltip="Remove bases de baixa qualidade no início da read (5').\n\nValor padrão: 3 (qualidade Phred 3, muito baixa).\nExemplo: Se a primeira base tiver qualidade 2, é removida."
    )
    trailing_field = create_text_field(
        label="TRAILING - Qualidade mínima",
        value="3",
        tooltip="Remove bases de baixa qualidade no final da read (3').\n\nValor padrão: 3 (similar a LEADING)."
    )
    crop_field = create_text_field(
        label="CROP - Comprimento",
        value="",
        tooltip="Corta a read para um comprimento fixo, independentemente da qualidade.\n\nExemplo: Se CROP:50, apenas as primeiras 50 bases são mantidas."
    )
    headcrop_field = create_text_field(
        label="HEADCROP - Número de bases",
        value="",
        tooltip="Remove um número fixo de bases do início da read (útil para primers).\n\nExemplo: HEADCROP:5 remove as 5 primeiras bases."
    )
    minlen_field = create_text_field(
        label="MINLEN - Comprimento mínimo",
        value="36",
        tooltip="Descarta reads com comprimento menor que o especificado.\n\nValor padrão: 36 (comum para garantir reads úteis)."
    )
    avgqual_field = create_text_field(
        label="AVGQUAL - Qualidade média",
        value="",
        tooltip="Descarta reads cuja qualidade média (Phred) esteja abaixo do valor.\n\nExemplo: AVGQUAL:20 remove reads com média de qualidade < 20."
    )

    # Modal for custom adapter input
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

    # Organize input fields into a structured layout
    form_layout = ft.Row(
        controls=[
            ft.Column(
                controls=[
                    # Threads and Phred in the same row with top margin
                    ft.Container(
                        content=ft.Text("", style=ft.TextStyle(size=14))
                    ),
                    ft.Row(
                        controls=[
                            threads_field,
                            phred_dropdown,
                        ],
                        spacing=27,
                    ),
                    ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
                    ft.Text("IlluminaClip Parameters", style=ft.TextStyle(size=14, weight="bold")),
                    # IlluminaClip split into two columns
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
                                    illumina_clip_fields[5],  # Invisible TextField for alignment
                                ],
                                expand=1,
                            ),
                        ]
                    ),
                    ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
                    ft.Text("SlidingWindow Parameters", style=ft.TextStyle(size=14, weight="bold")),
                    # SlidingWindow in one row with two columns
                    ft.Row(
                        controls=[
                            sliding_window_fields[0],  # Tamanho janela
                            sliding_window_fields[1],  # Qualidade mínima
                        ],
                        spacing=27
                    ),
                    ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
                    ft.Text("MaxInfo Parameters", style=ft.TextStyle(size=14, weight="bold")),
                    # MaxInfo in one row with two columns
                    ft.Row(
                        controls=[
                            max_info_fields[0],  # Comprimento alvo
                            max_info_fields[1],  # Strictness
                        ],
                        spacing=27
                    ),
                    ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38),
                    ft.Text("Other Parameters", style=ft.TextStyle(size=14, weight="bold")),
                    # Other Parameters split into two columns with three rows
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
                expand=1,  # Make the column expand to use available space
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,  # Center the form layout
    )

    # Function to start trimmagem
    async def start_trimmagem(e):
        logger.info("Start trimmagem button clicked.")  # Log when the function is triggered

        selected_samples = [row.cells[0].content.value for row in tabela_trimmagem.rows if row.cells[3].content.value]
        logger.info(f"Selected samples: {selected_samples}")  # Log selected samples

        if not selected_samples:
            logger.info("Nenhuma amostra selecionada.")
            return

        # Validate custom adapter content if "Personalizado" is selected
        if illumina_clip_fields[0].value == "Personalizado" and not is_valid_fasta(custom_adapter_content):
            await log_message(page, "O conteúdo do adaptador personalizado não é um arquivo FASTA válido.")
            return

        await log_message(page, f"Iniciando trimmagem para {selected_samples}")
        dlg_modal_trimmagem.open = False
        page.update()

        # Collect parameters
        try:
            illumina_clip_value = illumina_clip_fields[0].value

            params = {
                "threads": threads_field.value,
                "phred": phred_dropdown.value,
                "illumina_clip": json.dumps({  # Serialize as JSON
                    "Arquivo adaptadores": illumina_clip_value,
                    "Conteudo personalizado": custom_adapter_content if illumina_clip_value == "Personalizado" else None,
                    "Seed mismatches": illumina_clip_fields[1].value,
                    "Threshold palindromo": illumina_clip_fields[2].value,
                    "Threshold simples": illumina_clip_fields[3].value,
                    "Comprimento minimo adaptador": illumina_clip_fields[4].value
                }),
                "sliding_window": json.dumps({  # Serialize as JSON
                    "Tamanho janela": sliding_window_fields[0].value,
                    "Qualidade minima": sliding_window_fields[1].value,
                }),
                "max_info": json.dumps({  # Serialize as JSON
                    "Comprimento alvo": max_info_fields[0].value,
                    "Strictness": max_info_fields[1].value,
                }),
                "leading": leading_field.value,
                "trailing": trailing_field.value,
                "crop": int(crop_field.value) if crop_field.value.strip() else None,  # Send None if empty
                "headcrop": int(headcrop_field.value) if headcrop_field.value.strip() else None,  # Send None if empty
                "minlen": minlen_field.value,
                "avgqual": int(avgqual_field.value) if avgqual_field.value.strip() else None,  # Send None if empty
            }
            logger.info(f"Collected parameters: {params}")  # Log collected parameters
        except Exception as ex:
            logger.info(f"Error while collecting parameters: {ex}")
            return

        try:
            async with httpx.AsyncClient() as client:
                # Enviar todos os samples selecionados em uma única requisição
                form_data = {
                    "selected_samples": json.dumps(selected_samples),  # Serializa os samples selecionados
                    "threads": params["threads"],
                    "phred": params["phred"],
                    "illumina_clip": params["illumina_clip"],  # Já serializado
                    "sliding_window": params["sliding_window"],  # Já serializado
                    "max_info": params["max_info"],  # Já serializado
                    "leading": params["leading"],
                    "trailing": params["trailing"],
                    "crop": params["crop"] if params["crop"] is not None else None,  # Envia None se vazio
                    "headcrop": params["headcrop"] if params["headcrop"] is not None else None,  # Envia None se vazio
                    "minlen": params["minlen"],
                    "avgqual": params["avgqual"] if params["avgqual"] is not None else None,  # Envia None se vazio
                }
 
                response = await client.post(
                    "http://bioinfo-container:8000/trimmagem/",
                    data=form_data,  # Envia como form data
                    headers=headers,
                )

        except Exception as e:
            error_message = f"An error occurred while starting trimmagem: {e}"
            logger.error(error_message)
            await log_message(page, error_message)

    # Create the modal dialog
    dlg_modal_trimmagem = ft.AlertDialog(
        title=ft.Text("Iniciar Trimmagem"),
        content=ft.Container(
            content=ft.ListView(
                # spacing=10,
                controls=[
                    empty_message if empty_message else tabela_trimmagem,  # Show message if table is empty
                    form_layout,  # Use the updated form layout
                ],
            ),
            width=600,  # Increase the width to accommodate the full layout
        ),
        actions=[
            ft.Container(
                content=ft.TextButton(
                    "Iniciar Trimmagem",
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                    width=200,
                    height=40,
                    on_click=start_trimmagem if not iniciar_trimmagem_disabled else None,  # Disable click if no samples
                )
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_trimmagem)
