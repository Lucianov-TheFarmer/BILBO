from .translations import t
import flet as ft
import httpx
import logging
import asyncio
import json
import re
import time
from .utils import log_message
from .jobs import wait_with_progress

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _paired_trimmed_name(name):
    value = str(name)

    pairs = (
        ("_1_trimmed.fastq.gz", "_2_trimmed.fastq.gz"),
        ("_1_trimmed.fastq", "_2_trimmed.fastq"),
        ("_R1_trimmed.fastq.gz", "_R2_trimmed.fastq.gz"),
        ("_R1_trimmed.fastq", "_R2_trimmed.fastq"),
    )

    for first, second in pairs:
        if value.endswith(first):
            return value[:-len(first)] + second
        if value.endswith(second):
            return value[:-len(second)] + first

    return None


# Global variables
tabela_selecao_trimmagem = None

_FASTQ_PAIR_RE = re.compile(
    r"^(?P<base>.+?)(?P<tag>_R?[12])(?P<ext>\.(?:fastq|fq)(?:\.gz)?)$",
    re.IGNORECASE,
)


def _paired_fastq_name(name):
    """Retorna o nome do mate correspondente, preservando extensão e padrão R1/R2."""
    match = _FASTQ_PAIR_RE.match(str(name))
    if not match:
        return None

    tag = match.group("tag")
    mate = "2" if tag.endswith("1") else "1"

    return (
        f"{match.group('base')}"
        f"{tag[:-1]}{mate}"
        f"{match.group('ext')}"
    )


def create_tabela_amostras_trimmadas(page, token):
    """Creates the table for trimmed samples."""
    global tabela_amostras_trimmadas, toggle_select_sample

    async def toggle_select_all_trimmadas(e):
        for row in tabela_amostras_trimmadas.rows:
            if not row.cells[3].content.disabled:
                row.cells[3].content.value = e.control.value
        page.update()

    async def toggle_select_sample(e):
        """Toggle selection of a sample and ensure PE pairs are selected together."""
        selected_sample = e.control.data 
        is_selected = e.control.value
        paired_sample = _paired_trimmed_name(selected_sample)

        if paired_sample:
            for row in tabela_amostras_trimmadas.rows:
                sample_name = row.cells[0].content.content.controls[0].content.value
                if sample_name == paired_sample:
                    row.cells[3].content.value = is_selected
                    break

        page.update()

    tabela_amostras_trimmadas = ft.DataTable(
        heading_row_color="primary",
        columns=[
            ft.DataColumn(ft.Text(t("table_identification", page.session.get("lang") or "pt"), weight="bold")),
            ft.DataColumn(ft.Text(t("table_size", page.session.get("lang") or "pt"), weight="bold")),
            ft.DataColumn(ft.Text(t("table_status", page.session.get("lang") or "pt"), weight="bold")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_trimmadas)),
        ],
        rows=[],
    )
    return tabela_amostras_trimmadas

async def update_trimmagem_table(page, token):
    """Updates the table with trimmed samples."""
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://bioinfo-container:8890/samples/stages/3", headers=headers)
            if response.status_code == 200:
                samples = response.json()
                tabela_amostras_trimmadas.rows.clear()
                for sample in samples:
                    lang = page.session.get("lang") or "pt"
                    state = str(sample.get("status") or "").upper()
                    display_status = t({"PENDING": "pipeline_queued",
                                        "RUNNING": "pipeline_running",
                                        "FAILED": "pipeline_failed",
                                        "COMPLETED": "pipeline_completed"}.get(state, state), lang)
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
                                            scroll="auto",
                                        ),
                                        width=130
                                    )
                                ),
                                ft.DataCell(ft.Text(sample.get("size") or t("sra_size_pending", lang), style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Text(display_status, style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Checkbox(data=sample["name"], disabled=state != "COMPLETED",
                                                        on_change=toggle_select_sample))
                            ],
                        )
                    )
                page.update()
            else:
                logger.error(f"Erro ao obter amostras trimmadas: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred while updating the trimmagem table: {e}", exc_info=True)

async def delete_trimmed_samples(page, token, tabela_amostras_trimmadas, container_menu_direita, tabela_amostras_local, atualizar_tabela):
    """Deletes selected trimmed samples."""
    async def confirm_delete(e):
        selected_samples = []

        for row in tabela_amostras_trimmadas.rows:
            if isinstance(row.cells[3].content, ft.Checkbox) and row.cells[3].content.value:
                sample_name = row.cells[0].content.content.controls[0].content.value
                logger.info(f"Sample selected for deletion: {sample_name}")
                if isinstance(sample_name, str):
                    selected_samples.append(sample_name)

        if not selected_samples:
            logger.error("Nenhuma amostra selecionada para exclusão.")
            return

        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                for sample_name in selected_samples:
                    if sample_name.endswith("_trimmed_trimmed.fastq.gz"):
                        sample_name = sample_name.replace(
                            "_trimmed_trimmed.fastq.gz",
                            "_trimmed.fastq.gz",
                        )
                    elif sample_name.endswith("_trimmed_trimmed.fastq"):
                        sample_name = sample_name.replace(
                            "_trimmed_trimmed.fastq",
                            "_trimmed.fastq",
                        )
                    response = await client.delete(f"http://bioinfo-container:8890/trimmagem/{sample_name}", headers=headers)
                    if response.status_code == 200:
                        logger.info(f"Amostra trimmada {sample_name} excluída com sucesso!")
                    else:
                        logger.error(f"Erro ao excluir amostra trimmada {sample_name}: {response.status_code} - {response.text}")

            await update_trimmagem_table(page, token)
            await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
            page.update()
        except Exception as e:
            logger.error(f"Erro ao excluir amostras trimmadas: {e}", exc_info=True)

        dlg_modal_excluir_trimmagem.open = False
        page.update()

    dlg_modal_excluir_trimmagem = ft.AlertDialog(
        title=ft.Text(t("confirm_delete", page.session.get("lang") or "pt")),
        content=ft.TextField(
            hint_text=t("confirm_delete_hint", page.session.get("lang") or "pt"),
            border_radius=4,
            multiline=False,
            expand=1,
        ),
        actions=[
            ft.TextButton(
                t("delete_selected", page.session.get("lang") or "pt"),
                on_click=confirm_delete,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            ),
        ],
        actions_alignment="center",
    )

    page.open(dlg_modal_excluir_trimmagem)

async def show_trimmagem_modal(page, token, container_menu_direita, tabela_amostras_local,  atualizar_tabela):
    global tabela_selecao_trimmagem 

    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}

    # Recriar a tabela a cada abertura evita reutilizar um controle preso
    # a um AlertDialog anterior.
    tabela_selecao_trimmagem = create_tabela_selecao_trimmagem(page, token)

    await update_tabela_selecao_trimmagem(page, token)

    if not tabela_selecao_trimmagem.rows:
        empty_message = ft.Column(
            controls=[
                ft.Divider(height=1, thickness=1, color="black38"),
                ft.Text(t("trim_empty", page.session.get("lang") or "pt"), style=ft.TextStyle(size=16), text_align="center"),
                ft.Divider(height=1, thickness=1, color="black38"),
            ],
            alignment="center",
            horizontal_alignment="center",
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
            dlg_modal_trimmagem.open = False 
            page.update()
            page.open(custom_adapter_modal)
            page.update()

    def is_valid_fasta(content):
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
        custom_adapter_modal.open = False
        page.open(dlg_modal_trimmagem)
        page.update()

    threads_field = ft.TextField(
        label="Threads",
        value="1",
        tooltip=t("trim_help_0", page.session.get("lang") or "pt"),
        on_change=numeric_input_validator,
        width=280,
    )
    memory_field = ft.TextField(
        label=t("trimming_memory_mb", page.session.get("lang") or "pt"),
        value="1024", keyboard_type=ft.KeyboardType.NUMBER, width=280,
    )
    phred_dropdown = ft.Dropdown(
        label=t("trim_phred", page.session.get("lang") or "pt"),
        options=[
            ft.dropdown.Option("autodetect"),
            ft.dropdown.Option("phred33"),
            ft.dropdown.Option("phred64"),
        ],
        value="autodetect",
        tooltip=t("trim_help_1", page.session.get("lang") or "pt"),
        width=280,
    )
    custom_adapter_content = None

    illumina_clip_fields = [
        ft.Dropdown(
            label=t("trim_adapter_file", page.session.get("lang") or "pt"),
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
            tooltip=t("trim_help_8", page.session.get("lang") or "pt"),
            width=280,
            on_change=handle_adapter_change,
        ),
        ft.TextField(
            label="Seed mismatches",
            value="2",
            tooltip=t("trim_help_9", page.session.get("lang") or "pt"),
            on_change=numeric_input_validator,
            width=280,
        ),
        ft.TextField(
            label=t("trim_palindrome", page.session.get("lang") or "pt"),
            value="30",
            tooltip=t("trim_help_10", page.session.get("lang") or "pt"),
            on_change=numeric_input_validator,
            width=280,
        ),
        ft.TextField(
            label=t("trim_simple", page.session.get("lang") or "pt"),
            value="10",
            tooltip=t("trim_help_11", page.session.get("lang") or "pt"),
            on_change=numeric_input_validator,
            width=280,
        ),
        ft.TextField(
            label=t("trim_adapter_min", page.session.get("lang") or "pt"),
            value="8",
            tooltip=t("trim_help_12", page.session.get("lang") or "pt"),
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

    sliding_window_fields = [
        ft.TextField(
            label=t("trim_window", page.session.get("lang") or "pt"),
            value="4",
            tooltip=t("trim_help_13", page.session.get("lang") or "pt"),
            width=280,
        ),
        ft.TextField(
            label=t("trim_min_quality", page.session.get("lang") or "pt"),
            value="15",
            tooltip=t("trim_help_14", page.session.get("lang") or "pt"),
            width=280,
        ),
    ]

    max_info_fields = [
        ft.TextField(
            label=t("trim_target", page.session.get("lang") or "pt"),
            value="40",
            tooltip=t("trim_help_15", page.session.get("lang") or "pt"),
            width=280,
        ),
        ft.TextField(
            label="Strictness",
            value="0.5",
            tooltip=t("trim_help_16", page.session.get("lang") or "pt"),
            width=280,
        ),
    ]

    leading_field = ft.TextField(
        label=t("trim_leading", page.session.get("lang") or "pt"),
        value="3",
        tooltip=t("trim_help_2", page.session.get("lang") or "pt"),
        width=280,
    )

    trailing_field = ft.TextField(
        label=t("trim_trailing", page.session.get("lang") or "pt"),
        value="3",
        tooltip=t("trim_help_3", page.session.get("lang") or "pt"),
        width=280,
    )

    crop_field = ft.TextField(
        label=t("trim_crop", page.session.get("lang") or "pt"),
        value="",
        tooltip=t("trim_help_4", page.session.get("lang") or "pt"),
        width=280,
    )

    headcrop_field = ft.TextField(
        label=t("trim_headcrop", page.session.get("lang") or "pt"),
        value="",
        tooltip=t("trim_help_5", page.session.get("lang") or "pt"),
        width=280,
    )

    minlen_field = ft.TextField(
        label=t("trim_minlen", page.session.get("lang") or "pt"),
        value="36",
        tooltip=t("trim_help_6", page.session.get("lang") or "pt"),
        width=280,
    )

    avgqual_field = ft.TextField(
        label=t("trim_avgqual", page.session.get("lang") or "pt"),
        value="",
        tooltip=t("trim_help_7", page.session.get("lang") or "pt"),
        width=280,
    )

    custom_adapter_field = ft.TextField(
        label=t("trim_custom_adapters", page.session.get("lang") or "pt"),
        hint_text=t("trim_adapter_hint", page.session.get("lang") or "pt"),
        multiline=True,
        expand=True,
    )
    custom_adapter_modal = ft.AlertDialog(
        title=ft.Text(t("trim_custom_adapters", page.session.get("lang") or "pt")),
        content=custom_adapter_field,
        actions=[
            ft.TextButton(
                t("menu_save", page.session.get("lang") or "pt"),
                on_click=save_custom_adapter,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            )
        ],
        actions_alignment="center",
    )

    async def start_trimmagem(e):
        logger.info("Start trimmagem button clicked.")

        selected_samples = [row.cells[0].content.value for row in tabela_selecao_trimmagem.rows if row.cells[3].content.value]
        logger.info(f"Selected samples: {selected_samples}")

        if not selected_samples:
            logger.info("Nenhuma amostra selecionada.")
            return
        try:
            memory_mb = int(memory_field.value)
            if not 512 <= memory_mb <= 32768:
                raise ValueError()
        except (TypeError, ValueError):
            await log_message(page, t("trimming_memory_invalid", page.session.get("lang") or "pt"))
            return

        # Validate custom adapter content if "Personalizado" is selected
        if illumina_clip_fields[0].value == "Personalizado" and not is_valid_fasta(custom_adapter_content):
            await log_message(page, "O conteúdo do adaptador personalizado não é um arquivo FASTA válido.")
            return

        await log_message(page, f"Iniciando trimmagem para {selected_samples}")
        dlg_modal_trimmagem.open = False
        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
        await update_trimmagem_table(page, token) 
        page.update()

        # Collect parameters
        try:
            illumina_clip_value = illumina_clip_fields[0].value

            params = {
                "threads": threads_field.value,
                "memory_mb": memory_mb,
                "phred": phred_dropdown.value,
                "illumina_clip": json.dumps({
                    "Arquivo adaptadores": illumina_clip_value,
                    "Conteudo personalizado": custom_adapter_content if illumina_clip_value == "Personalizado" else None,
                    "Seed mismatches": illumina_clip_fields[1].value,
                    "Threshold palindromo": illumina_clip_fields[2].value,
                    "Threshold simples": illumina_clip_fields[3].value,
                    "Comprimento minimo adaptador": illumina_clip_fields[4].value
                }),
                "sliding_window": json.dumps({
                    "Tamanho janela": sliding_window_fields[0].value,
                    "Qualidade minima": sliding_window_fields[1].value,
                }),
                "max_info": json.dumps({
                    "Comprimento alvo": max_info_fields[0].value,
                    "Strictness": max_info_fields[1].value,
                }),
                "leading": leading_field.value,
                "trailing": trailing_field.value,
                "crop": int(crop_field.value) if crop_field.value.strip() else None,
                "headcrop": int(headcrop_field.value) if headcrop_field.value.strip() else None,
                "minlen": minlen_field.value,
                "avgqual": int(avgqual_field.value) if avgqual_field.value.strip() else None,
            }
            logger.info(f"Collected parameters: {params}")
        except Exception as ex:
            logger.error(f"Error while collecting parameters: {ex}")
            return

        # Retry logic for HTTP request
        max_retries = 1
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(
                        "http://bioinfo-container:8890/trimmagem/jobs",
                        data={
                            "selected_samples": json.dumps(selected_samples),
                            "threads": params["threads"],
                            "memory_mb": params["memory_mb"],
                            "phred": params["phred"],
                            "illumina_clip": params["illumina_clip"],
                            "sliding_window": params["sliding_window"],
                            "max_info": params["max_info"],
                            "leading": params["leading"],
                            "trailing": params["trailing"],
                            "crop": params["crop"],
                            "headcrop": params["headcrop"],
                            "minlen": params["minlen"],
                            "avgqual": params["avgqual"],
                        },
                        headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
                    )

                    if response.status_code == 202:
                        job_ids = response.json().get("job_ids") or []
                        await log_message(page, f"Trimmagem: {len(job_ids)} job(s) na fila.")
                        last_refresh = [0.0]
                        async def refresh_during_trimming(_payload):
                            if time.monotonic() - last_refresh[0] >= 5:
                                last_refresh[0] = time.monotonic()
                                await update_trimmagem_table(page, token)
                        await asyncio.gather(*(wait_with_progress(
                            page, token, job_id, t("trim_start", page.session.get("lang") or "pt"),
                            on_update=refresh_during_trimming)
                            for job_id in job_ids))
                        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                        await update_trimmagem_table(page, token)
                        page.update()
                        return
                    else:
                        logger.error(f"Erro ao iniciar trimmagem: {response.status_code} - {response.text}")
                        await log_message(page, f"Erro ao iniciar trimmagem: {response.status_code} - {response.text}")
            except httpx.RequestError as e:
                logger.error(f"Tentar {attempt + 1}/{max_retries} falhou: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)  # Wait before retrying
                else:
                    await log_message(page, f"Falha ao conectar ao backend após {max_retries} tentativas.")
                    return
            except Exception as e:
                logger.error(f"Erro inesperado: {e}", exc_info=True)
                return

    # Organize input fields into a structured layout with two columns
    form_layout = ft.Column(
        controls=[
            ft.Text(" ", style=ft.TextStyle(size=16)),
            ft.Row(
                controls=[
                    threads_field,
                    memory_field,
                    phred_dropdown,
                ],
                spacing=27
            ),
            ft.Divider(height=1, thickness=1, color="black38"),
            ft.Text(t("trim_illumina_params", page.session.get("lang") or "pt"), style=ft.TextStyle(size=14, weight="bold")),
            ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            illumina_clip_fields[0],
                            illumina_clip_fields[1],
                            illumina_clip_fields[2],
                        ],
                        expand=1,
                    ),
                    ft.Column(
                        controls=[
                            illumina_clip_fields[3],
                            illumina_clip_fields[4],
                            illumina_clip_fields[5],
                        ],
                        expand=1,
                    ),
                ],
            ),
            ft.Divider(height=1, thickness=1, color="black38"),
            ft.Text(t("trim_sliding_params", page.session.get("lang") or "pt"), style=ft.TextStyle(size=14, weight="bold")),
            ft.Row(
                controls=[
                    sliding_window_fields[0],  
                    sliding_window_fields[1],  
                ],
                spacing=27
            ),
            ft.Divider(height=1, thickness=1, color="black38"),
            ft.Text(t("trim_maxinfo_params", page.session.get("lang") or "pt"), style=ft.TextStyle(size=14, weight="bold")),
            ft.Row(
                controls=[
                    max_info_fields[0], 
                    max_info_fields[1],
                ],
                spacing=27
            ),
            ft.Divider(height=1, thickness=1, color="black38"),
            ft.Text(t("trim_other_params", page.session.get("lang") or "pt"), style=ft.TextStyle(size=14, weight="bold")),
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
        alignment="center",
    )

    dlg_modal_trimmagem = ft.AlertDialog(
        title=ft.Text(t("trim_start", page.session.get("lang") or "pt")),
        content=ft.Container(
            content=ft.ListView(
                controls=[
                    empty_message if empty_message else tabela_selecao_trimmagem, 
                    form_layout,
                ],
            ),
            width=600,
        ),
        actions=[
            ft.TextButton(
                t("trim_start", page.session.get("lang") or "pt"),
                on_click=start_trimmagem if not iniciar_trimmagem_disabled else None,
                disabled=iniciar_trimmagem_disabled,
            ),
        ],
        actions_alignment="center",
    )

    page.open(dlg_modal_trimmagem)

async def processar_trimmagem(page, token, selected_samples, container_menu_direita, tabela_amostras_local, atualizar_tabela):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            logger.info("Preparando os dados para a requisição de trimmagem.")
            form_data = {"selected_samples": json.dumps(selected_samples)}
            response = await client.post(
                "http://bioinfo-container:8890/trimmagem/jobs",
                data=form_data,
                headers=headers,
            )
            if response.status_code == 202:
                last_refresh = [0.0]
                async def refresh_during_trimming(_payload):
                    if time.monotonic() - last_refresh[0] >= 5:
                        last_refresh[0] = time.monotonic()
                        await update_trimmagem_table(page, token)
                await asyncio.gather(*(wait_with_progress(
                    page, token, job_id, t("trim_start", page.session.get("lang") or "pt"),
                    on_update=refresh_during_trimming)
                    for job_id in response.json().get("job_ids") or []))
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

def create_tabela_selecao_trimmagem(page, token):
    global tabela_selecao_trimmagem

    async def toggle_select_all_selecao(e):
        for row in tabela_selecao_trimmagem.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    tabela_selecao_trimmagem = ft.DataTable(
        heading_row_color="black12",
        columns=[
            ft.DataColumn(ft.Text(t("table_identification", page.session.get("lang") or "pt"))),
            ft.DataColumn(ft.Text(t("table_size", page.session.get("lang") or "pt"))),
            ft.DataColumn(ft.Text(t("table_status", page.session.get("lang") or "pt"))),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_selecao)),
        ],
        rows=[],
    )
    return tabela_selecao_trimmagem

async def update_tabela_selecao_trimmagem(page, token):
    global tabela_selecao_trimmagem

    async def toggle_select_sample(e):
        selected_sample = e.control.data
        is_selected = e.control.value

        paired_sample = _paired_fastq_name(selected_sample)

        if paired_sample:
            for row in tabela_selecao_trimmagem.rows:
                sample_name = row.cells[0].content.value
                if sample_name == paired_sample:
                    row.cells[3].content.value = is_selected 
                    break

        page.update()

    if tabela_selecao_trimmagem is None:
        tabela_selecao_trimmagem = create_tabela_selecao_trimmagem(page, token)

    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response_stage_1 = await client.get("http://bioinfo-container:8890/samples/stages/1", headers=headers)
            if response_stage_1.status_code == 200:
                downloaded_samples = response_stage_1.json()
            else:
                logger.error(f"Erro ao obter amostras baixadas: {response_stage_1.status_code} - {response_stage_1.text}")
                downloaded_samples = []

            response_stage_3 = await client.get("http://bioinfo-container:8890/samples/stages/3", headers=headers)
            if response_stage_3.status_code == 200:
                trimmed_samples = {
                    sample["sra_code"]
                    for sample in response_stage_3.json()
                    if str(sample.get("status") or "").upper()
                    in {"PENDING", "RUNNING", "COMPLETED"}
                }
            else:
                logger.error(f"Erro ao obter amostras trimmadas: {response_stage_3.status_code} - {response_stage_3.text}")
                trimmed_samples = set()

            samples = [sample for sample in downloaded_samples if sample["sra_code"] not in trimmed_samples]

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
