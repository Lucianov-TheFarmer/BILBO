import flet as ft
import asyncio
import httpx
import logging
import zipfile
import os
from pathlib import Path
from io import BytesIO
import base64  # New import
import re  # Importar regex
from .translations import t
from .alignment_metrics import parse_star_final_log


def close_figure_button(page, preview):
    """Return a localized close control for the shared figure preview."""
    def close(_):
        preview.content.controls = [ft.Container(expand=True)]
        page.update()

    return ft.IconButton(icon="close", tooltip=t("viewer_close", page.session.get("lang") or "pt"),
                         on_click=close)

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

        preview = getattr(page, "container_preview", None)
        if isinstance(preview, ft.Container):
            preview.content.controls = [ft.Container(expand=True, content=ft.Column([
                ft.Row([close_figure_button(page, preview)], alignment=ft.MainAxisAlignment.END),
                ft.ListView(controls=[log_control], expand=True),
            ], expand=True))]
            page.update()
            return

        # Prefer the explicit preview container if present
        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and getattr(container, "key", None) == "container_preview":
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

        # Fallback: previous heuristic based on expand==2
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

        preview = getattr(page, "container_preview", None)
        if isinstance(preview, ft.Container):
            preview.content.controls = [ft.Container(expand=True, content=ft.Column([
                ft.Row([close_figure_button(page, preview)], alignment=ft.MainAxisAlignment.END),
                ft.ListView(controls=[log_control], expand=True),
            ], expand=True))]
            page.update()
            return


        # Prefer explicit preview container
        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and getattr(container, "key", None) == "container_preview":
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

        # Fallback heuristic
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
    base_name = sample_name.removesuffix(".bam")
    log_dir = f"../users/{user_id}/alignment/{base_name}"
    custom_log = f"{log_dir}/{base_name}_custom.log"
    log_path = custom_log if os.path.isfile(custom_log) else f"{log_dir}/{base_name}Log.final.out"
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


async def view_alignment_metrics(page, sample_name, user_id):
    """Show STAR mapping counts for a completed alignment in the shared preview."""
    lang = page.session.get("lang") or "pt"
    preview = getattr(page, "container_preview", None)
    if not isinstance(preview, ft.Container):
        return

    def count(value):
        separator = "." if lang in ("pt", "es") else ","
        return f"{int(value):,}".replace(",", separator)

    def percent(value, total):
        number = f"{100 * value / total:.2f}" if total else "0.00"
        return number.replace(".", "," if lang in ("pt", "es") else ".") + "%"

    def metric_row(label, value, total, color):
        return ft.Container(padding=ft.padding.symmetric(vertical=5), content=ft.Column([
            ft.Row([ft.Text(label, expand=True),
                    ft.Text(f"{count(value)} · {percent(value, total)}", weight="bold")]),
            ft.ProgressBar(value=min(1, value / total) if total else 0, color=color),
        ], spacing=3))

    content = []
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.bam", sample_name):
        content.append(ft.Text(t("alignment_metrics_missing", lang)))
    else:
        base_name = sample_name.removesuffix(".bam")
        path = Path("..") / "users" / str(user_id) / "alignment" / base_name / f"{base_name}Log.final.out"
        try:
            metrics = parse_star_final_log(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            content.append(ft.Text(t("alignment_metrics_missing", lang)))
        else:
            total = metrics["input_reads"]
            content.extend([
                ft.Text(t("alignment_metrics_note", lang), size=12, italic=True),
                ft.Text(f"{t('alignment_metrics_input', lang)}: {count(total)}", weight="bold"),
                ft.Text(f"{t('alignment_metrics_mapped', lang)}: "
                        f"{count(metrics['mapped_reads'])} · {percent(metrics['mapped_reads'], total)}",
                        weight="bold"),
                metric_row(t("alignment_metrics_unique", lang), metrics["unique_reads"], total, "green"),
                metric_row(t("alignment_metrics_multiple", lang), metrics["multiple_loci"], total, "blue"),
                metric_row(t("alignment_metrics_too_many", lang), metrics["too_many_loci"], total, "orange"),
                ft.Text(f"{t('alignment_metrics_unmapped', lang)}: "
                        f"{count(metrics['unmapped_reads'])} · {percent(metrics['unmapped_reads'], total)}",
                        weight="bold"),
                metric_row(t("alignment_metrics_mismatch", lang), metrics["unmapped_mismatches"], total, "red"),
                metric_row(t("alignment_metrics_short", lang), metrics["unmapped_short"], total, "red"),
                metric_row(t("alignment_metrics_other", lang), metrics["unmapped_other"], total, "red"),
            ])
            if "splices" in metrics:
                content.append(ft.Text(f"{t('alignment_metrics_splices', lang)}: {count(metrics['splices'])}"))
            if "mismatch_rate" in metrics:
                rate = f"{metrics['mismatch_rate']:.2f}".replace(".", "," if lang in ("pt", "es") else ".")
                content.append(ft.Text(f"{t('alignment_metrics_mismatch_rate', lang)}: {rate}%"))

    preview.content.controls = [ft.Container(expand=True, padding=12, content=ft.Column([
        ft.Row([ft.Text(f"{t('alignment_metrics_title', lang)} — {sample_name}",
                        weight="bold", expand=True), close_figure_button(page, preview)]),
        ft.ListView(controls=content, expand=True, spacing=8),
    ], expand=True))]
    page.update()


async def view_quality_log(page, sample_name, user_id, *, post_trim=False):
    stem = sample_name.removesuffix(".html")
    if post_trim:
        source_stem = stem.removesuffix("_post_trim") + "_trimmed"
        base = re.sub(r"_R?[12]$", "", stem.removesuffix("_post_trim"))
        directory = Path("..") / "users" / str(user_id) / "QC_PostTrim" / base
        candidates = [directory / f"{source_stem}_quality_analysis_post_trim.log"]
    else:
        base = re.sub(r"_R?[12]$", "", stem)
        directory = Path("..") / "users" / str(user_id) / "QC" / base
        candidates = ([path for path in directory.iterdir() if path.is_file() and
                       path.name.startswith(stem + ".") and path.name.endswith("_quality_analysis.log")]
                      if directory.is_dir() else [])
    log_path = next((path for path in candidates if path.is_file()), None)
    if log_path is None:
        await display_log(page, t("quality_log_missing", page.session.get("lang") or "pt"))
        return
    with log_path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        stream.seek(max(0, stream.tell() - 65536))
        content = stream.read().decode("utf-8", errors="replace")
    await display_log(page, content)

async def view_quantification_log(page, token, sample_name, user_id):
    base_name = sample_name.removesuffix(".txt")
    log_path = f"../users/{user_id}/logs/quantification/{base_name}.bam.log"
    try:
        if os.path.exists(log_path):
            with open(log_path, "rb") as log_file:
                log_file.seek(0, os.SEEK_END)
                log_file.seek(max(0, log_file.tell() - 65536))
                log_content = log_file.read().decode("utf-8", errors="replace")
        else:
            log_content = t("quant_log_historical_missing", page.session.get("lang") or "pt")

        await display_quantification_log(page, log_content)
    except Exception as e:
        logger.error(f"Erro ao exibir o log de quantificação: {e}", exc_info=True)
        await display_quantification_log(page, t("quant_log_unavailable", page.session.get("lang") or "pt"))


async def view_quantification_counts(page, token, sample_name):
    """Load HTSeq counts a small byte range at a time as the user scrolls."""
    preview = getattr(page, "container_preview", None)
    if not isinstance(preview, ft.Container):
        return
    lang = page.session.get("lang") or "pt"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}\.txt", sample_name):
        await display_quantification_log(page, t("quant_counts_unavailable", lang))
        return

    progress = ft.Text(size=12)
    more_button = ft.TextButton(t("viewer_load_more", lang))
    rows = ft.ListView(expand=True, spacing=8, build_controls_on_demand=True,
                       cache_extent=400, on_scroll_interval=250)
    rows.controls.append(more_button)
    offset = 0
    loading = False

    async def load_more():
        nonlocal offset, loading
        if loading or not more_button.visible and offset > 0:
            return
        loading = True
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"http://bioinfo-container:8890/quantification/counts/{sample_name}/chunk",
                    params={"offset": offset, "lines": 100},
                    headers={"Authorization": f"Bearer {token}"})
            if response.status_code != 200:
                raise ValueError(response.text[:300])
            payload = response.json()
            lines = payload.get("lines") or []
            if lines:
                rows.controls.insert(len(rows.controls) - 1,
                                     ft.Text("\n".join(lines), selectable=True,
                                             style=ft.TextStyle(size=12, font_family="Consolas")))
            offset = int(payload["next_offset"])
            size = int(payload["size"])
            value = f"{100 * offset / size:.1f}" if size else "100.0"
            progress.value = f"{value}%"
            more_button.visible = bool(payload.get("has_more"))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("Could not load HTSeq counts for %s: %s", sample_name, exc)
            rows.controls.insert(len(rows.controls) - 1,
                                 ft.Text(t("quant_counts_unavailable", lang), color="red"))
            more_button.visible = False
        finally:
            loading = False
            page.update()

    async def on_scroll(event):
        if more_button.visible and event.pixels >= event.max_scroll_extent - 500:
            await load_more()

    async def on_click(_event):
        await load_more()

    rows.on_scroll = on_scroll
    more_button.on_click = on_click
    preview.content.controls = [ft.Container(expand=True, padding=12, content=ft.Column([
        ft.Row([ft.Text(f"{t('quant_counts_title', lang)} — {sample_name}", expand=True,
                        weight="bold"), progress, close_figure_button(page, preview)]),
        rows,
    ], expand=True))]
    page.update()
    await load_more()

def create_dropdown_menu(page, token, sample_name, user_id, analysis_type, image_placeholder):
    async def on_change(e):
        selected_graph = e.control.value
        graph_control = await display_graph(page, token, selected_graph, sample_name, user_id, analysis_type)
        if e.control.value != selected_graph:
            return

        image_placeholder.content = graph_control
        page.update()

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
                                                ft.Row([close_figure_button(page, container)],
                                                       alignment=ft.MainAxisAlignment.END),
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
                                                ft.Row([close_figure_button(page, container)],
                                                       alignment=ft.MainAxisAlignment.END),
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
                ft.Row([close_figure_button(page, container_pre_visualizacao)],
                       alignment=ft.MainAxisAlignment.END),
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
