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
            if not all(c in "ACGTNacgtn" for c in lines[i]):
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

    threads_field = ft.TextField(label="Threads", value="1", on_change=numeric_input_validator)
    phred_dropdown = ft.Dropdown(
        label="Codificação Phred",
        options=[
            ft.dropdown.Option("autodetect"),
            ft.dropdown.Option("phred33"),
            ft.dropdown.Option("phred64"),
        ],
        value="autodetect"
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
            value="TruSeq3-PE.fa",  # Default value
            on_change=handle_adapter_change,  # Use the synchronous wrapper
        ),
        ft.TextField(label="Seed mismatches", value="2", on_change=numeric_input_validator),
        ft.TextField(label="Threshold palíndromo", value="30", on_change=numeric_input_validator),
        ft.TextField(label="Threshold simples", value="10", on_change=numeric_input_validator),
        ft.TextField(label="Comprimento mínimo adaptador", value="8", on_change=numeric_input_validator),
        ft.Checkbox(label="Manter ambas reads", value=False),
    ]

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

    sliding_window_fields = [
        ft.TextField(label="Tamanho janela", value="4", on_change=numeric_input_validator),
        ft.TextField(label="Qualidade mínima", value="15", on_change=numeric_input_validator),
    ]
    max_info_fields = [
        ft.TextField(label="Comprimento alvo", value="40", on_change=numeric_input_validator),
        ft.TextField(label="Strictness", value="0.5", on_change=numeric_input_validator),
    ]
    leading_field = ft.TextField(label="LEADING - Qualidade mínima", value="3", on_change=numeric_input_validator)
    trailing_field = ft.TextField(label="TRAILING - Qualidade mínima", value="3", on_change=numeric_input_validator)
    crop_field = ft.TextField(label="CROP - Comprimento", value="", on_change=numeric_input_validator)
    headcrop_field = ft.TextField(label="HEADCROP - Número de bases", value="", on_change=numeric_input_validator)
    minlen_field = ft.TextField(label="MINLEN - Comprimento mínimo", value="36", on_change=numeric_input_validator)
    avgqual_field = ft.TextField(label="AVGQUAL - Qualidade média", value="", on_change=numeric_input_validator)

    # Organize input fields into two columns
    form_layout = ft.Row(
        controls=[
            ft.Column(
                controls=[
                    threads_field,
                    illumina_clip_fields[0],
                    illumina_clip_fields[2],
                    sliding_window_fields[0],
                    max_info_fields[0],
                    leading_field,
                    crop_field,
                    minlen_field,
                ],
                spacing=10,
                expand=1,  # Make the column expand to use available space
            ),
            ft.Column(
                controls=[
                    phred_dropdown,
                    illumina_clip_fields[1],
                    illumina_clip_fields[3],
                    sliding_window_fields[1],
                    max_info_fields[1],
                    trailing_field,
                    headcrop_field,
                    avgqual_field,
                ],
                spacing=10,
                expand=1,  # Make the column expand to use available space
            ),
        ],
        spacing=20,
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
                    "Comprimento minimo adaptador": illumina_clip_fields[4].value,
                    "Manter ambas reads": "true" if illumina_clip_fields[5].value else "false",
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
                for sample in selected_samples:
                    # Flatten the parameters for form submission
                    form_data = {
                        "sra_code": sample,
                        "threads": params["threads"],
                        "phred": params["phred"],
                        "illumina_clip": params["illumina_clip"],  # Already serialized
                        "sliding_window": params["sliding_window"],  # Already serialized
                        "max_info": params["max_info"],  # Already serialized
                        "leading": params["leading"],
                        "trailing": params["trailing"],
                        "crop": params["crop"] if params["crop"] is not None else None,  # Send None if empty
                        "headcrop": params["headcrop"] if params["headcrop"] is not None else None,  # Send None if empty
                        "minlen": params["minlen"],
                        "avgqual": params["avgqual"] if params["avgqual"] is not None else None,  # Send None if empty
                    }

                    response = await client.post(
                        "http://bioinfo-container:8000/trimmagem/",
                        data=form_data,  # Send as form data
                        headers=headers,
                    )
                    if response.status_code == 200:
                        logger.info(f"Trimmagem iniciada para {sample} com sucesso!")
                    else:
                        logger.info(f"Erro ao iniciar trimmagem para {sample}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.info(f"An error occurred while starting trimmagem: {e}")

    # Create the modal dialog
    dlg_modal_trimmagem = ft.AlertDialog(
        title=ft.Text("Iniciar Trimmagem"),
        content=ft.Container(
            content=ft.ListView(
                spacing=10,
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
