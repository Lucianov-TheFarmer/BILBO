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
    # Extract the sample code from the sample name (e.g. 'SRR11196539_1.fastq' -> 'SRR11196539_1')
    sample_code = sample_name.split('.')[0]
    # Derive the base SRA code without _1/_2 suffix (folder name used in QC)
    sra_base = re.sub(r'(_[12])$', '', sample_code)

    # Define the path to the zip file and the image inside it based on analysis_type
    if analysis_type == "QC":
        # fastqc output is stored under ../users/<user>/QC/<sra_base>/<sample_code>_fastqc.zip
        zip_path = f"../users/{user_id}/QC/{sra_base}/{sample_code}_fastqc.zip"
        image_path = f"{sample_code}_fastqc/Images/{graph_type_to_image[graph_type]}"
    elif analysis_type == "QC_PostTrim":
        # sample_code example: SRR11196539_1_post_trim -> trimmed_sample_code: SRR11196539_1_trimmed
        trimmed_sample_code = sample_code.replace("_post_trim", "_trimmed")
        # Remove trailing _trimmed then remove _1/_2 to get folder base (same convention as pre-trim QC)
        tmp_base = re.sub(r'_trimmed$', '', trimmed_sample_code)
        sra_base_trimmed = re.sub(r'(_[12])$', '', tmp_base)
        zip_path = f"../users/{user_id}/QC_PostTrim/{sra_base_trimmed}/{trimmed_sample_code}_fastqc.zip"
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
        image_control = ft.Image(src_base64=image_base64, fit=ft.ImageFit.CONTAIN, expand=True)

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
        return ft.Text(f"Error: File not found - {e}", color="red")
    except Exception as e:
        logger.error(f"Error extracting or displaying graph: {e}", exc_info=True)
        return ft.Text(f"Error: {e}", color="red")

async def display_log(page, log_content):
    """Displays the log content in the viewer."""
    try:
        formatted_content = re.sub(r"\s*\|\s*", ": ", log_content)
        formatted_content = re.sub(r"\t", "    ", formatted_content)
        formatted_content = re.sub(r"^\s+", "", formatted_content, flags=re.MULTILINE)

        titles = [
            "UNIQUE READS:",
            "MULTI-MAPPING READS:",
            "UNMAPPED READS:",
            "CHIMERIC READS:"
        ]
        for title in titles:
            formatted_content = formatted_content.replace(title, f"\n{title}")

        log_control = ft.Text(
            formatted_content,
            selectable=True,
            style=ft.TextStyle(size=12, font_family="Consolas"),
            text_align=ft.TextAlign.LEFT,
        )

        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.expand == 2 and isinstance(container.content, ft.Column):
                                container.content.controls = [
                                    ft.Container(
                                        expand=True,
                                        content=ft.ListView(
                                            controls=[log_control],
                                            spacing=10,
                                            expand=True,
                                        ),
                                        padding=ft.padding.all(10),
                                    )
                                ]
                                page.update()
                                return
    except Exception as e:
        logger.error(f"Erro ao exibir o log no viewer: {e}", exc_info=True)

async def display_quantification_log(page, log_content):
    try:

        log_control = ft.Text(
            log_content,
            selectable=True,
            style=ft.TextStyle(size=12, font_family="Consolas"),
            text_align=ft.TextAlign.LEFT,
        )


        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.expand == 2 and isinstance(container.content, ft.Column):
                                container.content.controls = [
                                    ft.Container(
                                        expand=True,
                                        content=ft.ListView(
                                            controls=[log_control],
                                            spacing=10,
                                            expand=True,
                                        ),
                                        padding=ft.padding.all(10),
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
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as log_file:
                log_content = log_file.read()
        else:
            log_content = f"Erro: Arquivo de log não encontrado em {log_path}"


        await display_log(page, log_content)
    except Exception as e:
        logger.error(f"Erro ao exibir o log de alinhamento: {e}", exc_info=True)
        await display_log(page, f"Erro ao exibir o log de alinhamento: {e}")

async def view_quantification_log(page, token, sample_name, user_id):
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
                            if isinstance(container, ft.Container) and container.key == "container_preview":
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

async def view_barplot_image(page, token, user_id, filename):
    """Displays the barplot image in the container_pre_visualizacao."""
    try:
        # Constrói o caminho local do arquivo (mesmo padrão usado em deg.py)
        import os
        deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
        file_path = os.path.join(deg_dir, filename)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {filename}")

        # Lê a imagem diretamente do arquivo (mesmo padrão usado em deg.py)
        with open(file_path, "rb") as f:
            image_data = f.read()

        # Converte para base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')

        # Cria o controle de imagem
        image_control = ft.Image(
            src_base64=image_base64,
            fit=ft.ImageFit.CONTAIN,
            expand=True
        )

        # Cria o viewer interativo
        interactive_viewer = ft.InteractiveViewer(
            min_scale=0.5,
            max_scale=15,
            boundary_margin=ft.margin.all(10),
            content=image_control,
            constrained=True
        )

        # Extrai título limpo do nome do arquivo
        display_title = filename.replace('BARPLOT.MULTIPLO - ', '').replace('.png', '')

        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.key == "container_preview":
                                container.content.controls = [
                                    ft.Container(
                                        expand=True,
                                        content=ft.Column(
                                            controls=[
                                                ft.Container(height=10),
                                                interactive_viewer
                                            ],
                                            alignment=ft.MainAxisAlignment.CENTER,
                                            spacing=0,
                                        )
                                    )
                                ]
                                page.update()
                                return

        # Se não encontrou o container, loga erro
        logger.error("container_pre_visualizacao não encontrado")

    except Exception as e:
        logger.error(f"Erro ao exibir barplot: {e}", exc_info=True)
        # Mostra erro no container_pre_visualizacao
        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.expand == 2 and isinstance(container.content, ft.Column):
                                container.content.controls = [
                                    ft.Container(
                                        expand=True,
                                        content=ft.Text(
                                            f"Erro ao carregar imagem: {e}",
                                            color="red",
                                            size=16,
                                            weight=ft.FontWeight.BOLD,
                                            text_align=ft.TextAlign.CENTER,
                                        ),
                                        alignment=ft.alignment.center,
                                        padding=ft.padding.all(10),
                                    )
                                ]
                                page.update()
                                return

async def view_venn_image(page, token, user_id, filename):
    """Displays the Venn diagram image in the container_pre_visualizacao."""
    try:
        # Constrói o caminho local do arquivo (mesmo padrão usado em deg.py)
        import os
        deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
        file_path = os.path.join(deg_dir, filename)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {filename}")

        # Lê a imagem diretamente do arquivo (mesmo padrão usado em deg.py)
        with open(file_path, "rb") as f:
            image_data = f.read()

        # Converte para base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')

        # Cria o controle de imagem
        image_control = ft.Image(
            src_base64=image_base64,
            fit=ft.ImageFit.CONTAIN,
            expand=True
        )

        # Cria o viewer interativo
        interactive_viewer = ft.InteractiveViewer(
            min_scale=0.5,
            max_scale=15,
            boundary_margin=ft.margin.all(10),
            content=image_control,
            constrained=True
        )

        # Extrai título limpo do nome do arquivo
        display_title = filename.replace('VENN.DIAGRAM - ', '').replace('.png', '')

        # Encontra e atualiza o container_pre_visualizacao (mesmo padrão usado em deg.py e preprocess.py)
        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.key == "container_preview":
                                container.content.controls = [
                                    ft.Container(
                                        expand=True,
                                        content=ft.Column(
                                            controls=[
                                                ft.Container(height=10),
                                                interactive_viewer
                                            ],
                                            alignment=ft.MainAxisAlignment.CENTER,
                                            spacing=0,
                                        )
                                    )
                                ]
                                page.update()
                                return

        # Se não encontrou o container, loga erro
        logger.error("container_pre_visualizacao não encontrado")

    except Exception as e:
        logger.error(f"Erro ao exibir diagrama de Venn: {e}", exc_info=True)
        # Mostra erro no container_pre_visualizacao
        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.expand == 2 and isinstance(container.content, ft.Column):
                                container.content.controls = [
                                    ft.Container(
                                        expand=True,
                                        content=ft.Text(
                                            f"Erro ao carregar diagrama de Venn: {e}",
                                            color="red",
                                            size=16,
                                            weight=ft.FontWeight.BOLD,
                                            text_align=ft.TextAlign.CENTER,
                                        ),
                                        alignment=ft.alignment.center,
                                        padding=ft.padding.all(10),
                                    )
                                ]
                                page.update()
                                return

async def view_heatmap_image(page, token, filename, user_id):
    """
    Exibe um heatmap na área de pré-visualização
    """
    try:
        # Constrói o caminho para o arquivo de heatmap
        image_path = f"../users/{user_id}/DEG/{filename}"

        # Verifica se o arquivo existe
        if not os.path.exists(image_path):
            logger.error(f"Arquivo de heatmap não encontrado: {image_path}")
            return

        # Lê o arquivo de imagem
        with open(image_path, 'rb') as f:
            image_data = f.read()

        # Codifica em base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        data_url = f"data:image/png;base64,{image_base64}"

        # Procura o container de pré-visualização
        container_pre_visualizacao = None
        for control in page.controls:
            if hasattr(control, 'controls'):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.key == "container_preview":
                                container_pre_visualizacao = container
                                break

        if container_pre_visualizacao:
            # Atualiza o conteúdo com o heatmap
            container_pre_visualizacao.content.controls = [
                ft.Container(
                    content=ft.InteractiveViewer(
                        content=ft.Image(
                            src=data_url,
                            fit=ft.ImageFit.CONTAIN,
                            border_radius=8,
                        ),
                        min_scale=0.1,
                        max_scale=10.0,
                        # interaction_flags removed for compatibility with current flet versions
                        constrained=True,
                        boundary_margin=ft.margin.all(10),
                    ),
                    expand=True,
                    alignment=ft.alignment.center,
                    padding=ft.padding.all(10),
                    border_radius=8,
                )
            ]
            page.update()
            logger.info(f"Heatmap exibido com sucesso: {filename}")
        else:
            logger.error("Container de pré-visualização não encontrado")

    except Exception as e:
        logger.error(f"Erro ao exibir heatmap: {e}")
        # Exibe mensagem de erro no container de pré-visualização
        for control in page.controls:
            if hasattr(control, 'controls'):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.expand == 2 and isinstance(container.content, ft.Column):
                                container.content.controls = [
                                    ft.Container(
                                        expand=True,
                                        content=ft.Text(
                                            f"Erro ao carregar heatmap: {e}",
                                            color="red",
                                            size=16,
                                            weight=ft.FontWeight.BOLD,
                                            text_align=ft.TextAlign.CENTER,
                                        ),
                                        alignment=ft.alignment.center,
                                        padding=ft.padding.all(10),
                                    )
                                ]
                                page.update()
                                return
