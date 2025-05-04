import flet as ft
import asyncio
import httpx
import logging
import zipfile
import os
from io import BytesIO
import base64  # New import
import re  # Importar regex

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dictionary to map dropdown options to image filenames
graph_type_to_image = {
    "Per base sequence quality": "per_base_quality.png",
    "Per tile sequence quality": "per_tile_quality.png",
    "Per sequence quality scores": "per_sequence_quality.png",
    "Per base sequence content": "per_base_sequence_content.png",
    "Per sequence GC content": "per_sequence_gc_content.png",
    "Per base N content": "per_base_n_content.png",
    "Sequence Length Distribution": "sequence_length_distribution.png",
    "Sequence Duplication Levels": "duplication_levels.png",
    "Adapter Content": "adapter_content.png",
}

async def display_graph(page, token, graph_type, sample_name, user_id, analysis_type):
    # Extract the sample code from the sample name
    sample_code = sample_name.split('.')[0]

    # Define the path to the zip file and the image inside it based on analysis_type
    if analysis_type == "QC":
        zip_path = f"../users/{user_id}/QC/{sample_code}.fastq/{sample_code}_fastqc.zip"
        image_path = f"{sample_code}_fastqc/Images/{graph_type_to_image[graph_type]}"
    elif analysis_type == "QC_PostTrim":
        trimmed_sample_code = sample_code.replace("_post_trim", "_trimmed")
        zip_path = f"../users/{user_id}/QC_PostTrim/{trimmed_sample_code}.fastq/{trimmed_sample_code}_fastqc.zip"
        image_path = f"{trimmed_sample_code}_fastqc/Images/{graph_type_to_image[graph_type]}"
    else:
        logger.error(f"Unsupported analysis type: {analysis_type}")
        return None

    # Extract the image from the zip file
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            with zip_ref.open(image_path) as image_file:
                image_data = image_file.read()

        # Encode the image data to base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')

        # Create an Image control with the extracted image data
        image_control = ft.Image(src_base64=image_base64, fit=ft.ImageFit.CONTAIN)

        # Create an InteractiveViewer with the extracted image data
        interactive_viewer = ft.InteractiveViewer(
            min_scale=0.1,
            max_scale=15,
            boundary_margin=ft.margin.all(20),
            on_interaction_start=lambda e: print(e),
            on_interaction_end=lambda e: print(e),
            on_interaction_update=lambda e: print(e),
            content=image_control
        )

        return interactive_viewer
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return ft.Text(f"Error: File not found - {e}", color=ft.colors.RED)
    except Exception as e:
        logger.error(f"Error extracting or displaying graph: {e}", exc_info=True)
        return ft.Text(f"Error: {e}", color=ft.colors.RED)

async def display_log(page, log_content):
    """Displays the log content in the viewer."""
    try:
        # Usar regex para substituir os espaços variáveis, ajustar o formato do texto e remover espaços iniciais
        formatted_content = re.sub(r"\s*\|\s*", ": ", log_content)  # Substituir "|       " ou "| " por ": "
        formatted_content = re.sub(r"\t", "    ", formatted_content)  # Substituir tabulações por espaços
        formatted_content = re.sub(r"^\s+", "", formatted_content, flags=re.MULTILINE)  # Remover espaços no início das linhas

        # Adicionar quebras de linha antes dos títulos do relatório
        titles = [
            "UNIQUE READS:",
            "MULTI-MAPPING READS:",
            "UNMAPPED READS:",
            "CHIMERIC READS:"
        ]
        for title in titles:
            formatted_content = formatted_content.replace(title, f"\n{title}")

        # Criar um controle de texto com fonte monoespaçada para alinhamento
        log_control = ft.Text(
            formatted_content,
            selectable=True,
            style=ft.TextStyle(size=12, font_family="Consolas"),  # Fonte monoespaçada
            text_align=ft.TextAlign.LEFT,  # Alinhar o texto à esquerda
        )

        # Atualizar o container de pré-visualização mantendo o tamanho original e permitindo rolagem
        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.expand == 2 and isinstance(container.content, ft.Column):
                                container.content.controls = [
                                    ft.Container(
                                        expand=True,  # Garantir que o container mantenha o tamanho original
                                        content=ft.ListView(
                                            controls=[log_control],
                                            spacing=10,
                                            expand=True,  # Permitir que o conteúdo ocupe todo o espaço disponível
                                        ),
                                        padding=ft.padding.all(10),  # Adicionar padding para melhor visualização
                                    )
                                ]
                                page.update()
                                return
    except Exception as e:
        logger.error(f"Erro ao exibir o log no viewer: {e}", exc_info=True)

async def display_quantification_log(page, log_content):
    """Exibe o conteúdo do log de quantificação no viewer."""
    try:
        # Criar um controle de texto com fonte monoespaçada para alinhamento
        log_control = ft.Text(
            log_content,
            selectable=True,
            style=ft.TextStyle(size=12, font_family="Consolas"),  # Fonte monoespaçada
            text_align=ft.TextAlign.LEFT,  # Alinhar o texto à esquerda
        )

        # Atualizar o container de pré-visualização mantendo o tamanho original e permitindo rolagem
        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.expand == 2 and isinstance(container.content, ft.Column):
                                container.content.controls = [
                                    ft.Container(
                                        expand=True,  # Garantir que o container mantenha o tamanho original
                                        content=ft.ListView(
                                            controls=[log_control],
                                            spacing=10,
                                            expand=True,  # Permitir que o conteúdo ocupe todo o espaço disponível
                                        ),
                                        padding=ft.padding.all(10),  # Adicionar padding para melhor visualização
                                    )
                                ]
                                page.update()
                                return
    except Exception as e:
        logger.error(f"Erro ao exibir o log de quantificação no viewer: {e}", exc_info=True)

async def view_alignment_log(page, token, sample_name, user_id):
    """Displays the alignment log in the viewer."""
    log_path = f"../users/{user_id}/alignment/{sample_name.replace('.bam', '')}/{sample_name.replace('.bam', 'Log.final.out')}"
    try:
        # Ler o arquivo de log diretamente do sistema de arquivos
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as log_file:
                log_content = log_file.read()
        else:
            log_content = f"Erro: Arquivo de log não encontrado em {log_path}"

        # Atualizar o viewer com o conteúdo do log
        await display_log(page, log_content)
    except Exception as e:
        logger.error(f"Erro ao exibir o log de alinhamento: {e}", exc_info=True)
        await display_log(page, f"Erro ao exibir o log de alinhamento: {e}")

async def view_quantification_log(page, token, sample_name, user_id):
    """Exibe o log de quantificação no viewer."""
    log_path = f"../users/{user_id}/quantification/{sample_name}"
    try:
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as log_file:
                log_content = log_file.read()
        else:
            log_content = f"Erro: Arquivo de log não encontrado em {log_path}"

        await display_quantification_log(page, log_content)
    except Exception as e:
        logger.error(f"Erro ao exibir o log de quantificação: {e}", exc_info=True)
        await display_quantification_log(page, f"Erro ao exibir o log de quantificação: {e}")

def create_dropdown_menu(page, token, sample_name, user_id, analysis_type):
    async def on_change(e):
        selected_graph = e.control.value
        graph_control = await display_graph(page, token, selected_graph, sample_name, user_id, analysis_type)
        
        # Find the container_pre_visualizacao and update its content
        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.expand == 2 and isinstance(container.content, ft.Column):
                                container.content.controls[0].content.controls[1] = graph_control
                                page.update()
                                return

    async def on_change_handler(e):
        await on_change(e)

    return ft.Container(
        margin=ft.margin.all(10),
        content=ft.Column(
            controls=[
                ft.Row(  # Wrap the dropdown in a Row to centralize it
                    controls=[
                        ft.Dropdown(
                            options=[
                                ft.dropdown.Option("Per base sequence quality"),
                                ft.dropdown.Option("Per tile sequence quality"),
                                ft.dropdown.Option("Per sequence quality scores"),
                                ft.dropdown.Option("Per base sequence content"),
                                ft.dropdown.Option("Per sequence GC content"),
                                ft.dropdown.Option("Per base N content"),
                                ft.dropdown.Option("Sequence Length Distribution"),
                                ft.dropdown.Option("Sequence Duplication Levels"),
                                ft.dropdown.Option("Adapter Content"),
                            ],
                            width=300,
                            on_change=on_change_handler,
                            value="Per base sequence quality",  # Set the default selected value
                        )
                    ],
                    alignment=ft.MainAxisAlignment.CENTER  # Center the dropdown horizontally
                )
            ]
        )
    )