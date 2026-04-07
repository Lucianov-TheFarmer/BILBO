import flet as ft
import asyncio
import base64
import os
from importlib import metadata as importlib_metadata

from frontend.procedures.translations import t

from .sample_operations import adicionar_amostra
from .quality_analysis import show_quality_analysis_modal
from .trimmagem import show_trimmagem_modal
from .quality_analysis_post_trim import show_quality_analysis_post_trim_modal
from .alignment import show_alignment_modal, show_genomes_modal
from .quantification import show_quantification_modal
from .contrasts import show_contrasts_modal
from .preprocess import show_preprocess_modal, show_exploratory_dropdown
from .deg import run_deg_analysis, show_deg_results
from .results import (
    show_barplots_table,
    show_barplots_modal,
    show_venn_table,
    show_venn_modal,
    show_heatmaps_table,
    show_heatmap_modal,
)
from .upload import show_upload_fastq_modal


def _get_image_64(path):
    candidates = [
        path,
        os.path.join("/app/frontend", path),
        os.path.join("/app", path),
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            with open(candidate, "rb") as img_file:
                return base64.b64encode(img_file.read()).decode("utf-8")
    return ""


FAVICON_BASE64 = _get_image_64("assets/favicon.png")


def _resolve_software_version():
    try:
        return importlib_metadata.version("bilbo")
    except Exception:
        return "1.0.0"

def create_menu_item(label, close_on_click=True, style=None, on_click=None):
    return ft.MenuItemButton(
        content=ft.Text(label),
        close_on_click=close_on_click,
        style=style or ft.ButtonStyle(bgcolor={"hovered": "primary"}),
        on_click=on_click,
    )

async def mudar_tema(page):
    if page.theme_mode == "light":
        page.theme_mode = "dark"
    else:
        page.theme_mode = "light"
    page.update()

def create_menubar(page, token, container_menu_direita, container_amostras, tabela_amostras_local, atualizar_tabela, user_id):
    lang = page.session.get("lang") or "pt"
    version_value = _resolve_software_version()

    about_text = {
        "pt": {
            "title": "Versão do Software",
            "subtitle": "Bioinformatics Integration for Large-scale Biological Operations",
            "footer": "Plataforma integrada para analise RNA-Seq com pipeline reprodutivel e assistencia por IA.",
            "close": "Fechar",
        },
        "en": {
            "title": "Software Version",
            "subtitle": "Bioinformatics Integration for Large-scale Biological Operations",
            "footer": "Integrated RNA-Seq platform with reproducible pipelines and AI-assisted interpretation.",
            "close": "Close",
        },
        "es": {
            "title": "Versión del Software",
            "subtitle": "Bioinformatics Integration for Large-scale Biological Operations",
            "footer": "Plataforma integrada de RNA-Seq con pipeline reproducible y asistencia por IA.",
            "close": "Cerrar",
        },
    }.get(lang, {
        "title": "Software Version",
        "subtitle": "Bioinformatics Integration for Large-scale Biological Operations",
        "footer": "Integrated RNA-Seq platform with reproducible pipelines and AI-assisted interpretation.",
        "close": "Close",
    })

    def _open_version_modal(_):
        def _close_modal(__):
            dlg.open = False
            page.update()

        card = ft.Container(
            padding=18,
            border_radius=14,
            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.PRIMARY),
            content=ft.Column(
                tight=True,
                spacing=8,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.CENTER,
                        controls=[
                            ft.Image(src_base64=FAVICON_BASE64, width=128, height=128, fit=ft.ImageFit.CONTAIN),
                            ft.Text("BILBO", size=28, weight=ft.FontWeight.BOLD),
                        ],
                    ),
                    ft.Text(
                        f"v{version_value}",
                        text_align=ft.TextAlign.CENTER,
                        size=18,
                        weight=ft.FontWeight.W_600,
                    ),
                    ft.Text(
                        about_text["subtitle"],
                        text_align=ft.TextAlign.CENTER,
                        color=ft.Colors.with_opacity(0.9, ft.Colors.ON_SURFACE),
                        size=13,
                    ),
                    ft.Divider(height=14),
                    ft.Text(
                        about_text["footer"],
                        text_align=ft.TextAlign.CENTER,
                        size=12,
                        color=ft.Colors.with_opacity(0.8, ft.Colors.ON_SURFACE),
                    ),
                ],
            ),
        )

        dlg = ft.AlertDialog(
            title=ft.Text(about_text["title"], text_align=ft.TextAlign.CENTER),
            content=ft.Container(width=520, content=card),
            actions=[ft.TextButton(about_text["close"], on_click=_close_modal)],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        page.open(dlg)
        page.update()

    return ft.MenuBar(
        controls=[
            ft.SubmenuButton(
                content=ft.Text(t("menu_samples", lang)),
                controls=[
                    create_menu_item(
                        t("menu_add_fastq", lang),
                        on_click=lambda e: asyncio.run(show_upload_fastq_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id))
                    ),
                    create_menu_item(
                        t("menu_add_sra", lang),
                        on_click=lambda e: asyncio.run(adicionar_amostra(e, page, token, container_menu_direita, tabela_amostras_local))
                    ),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text(t("menu_quality", lang)),
                controls=[
                    create_menu_item(
                        t("menu_check_quality", lang),
                        on_click=lambda e: asyncio.run(show_quality_analysis_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id))),
                    create_menu_item(
                        t("menu_trimming", lang),
                        on_click=lambda e: asyncio.run(show_trimmagem_modal(page, token, container_menu_direita, tabela_amostras_local,  atualizar_tabela))),
                    create_menu_item(
                        t("menu_check_quality_post_trim", lang),
                        on_click=lambda e: asyncio.run(show_quality_analysis_post_trim_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id))),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text(t("menu_alignment", lang)),
                controls=[
                    create_menu_item(
                        t("menu_add_genome", lang),
                        on_click=lambda e: asyncio.run(show_genomes_modal(page, token, user_id))),
                    create_menu_item(
                        t("menu_align_genome", lang),
                        on_click=lambda e: asyncio.run(show_alignment_modal(page, token, user_id, atualizar_tabela, container_menu_direita, tabela_amostras_local))),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text(t("menu_quantification", lang)),
                controls=[
                    create_menu_item(
                        t("menu_quantify_reads", lang),
                        on_click=lambda e: asyncio.run(show_quantification_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id))),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text(t("menu_deg", lang)),
                controls=[
                    create_menu_item(
                        t("menu_define_contrasts", lang),
                        on_click=lambda e: asyncio.run(show_contrasts_modal(page, token, user_id))
                    ),
                    create_menu_item(
                        t("menu_preprocess", lang),
                        on_click=lambda e: asyncio.run(show_preprocess_modal(page, token, user_id))
                    ),
                    create_menu_item(
                        t("menu_start_deg", lang),
                        on_click=lambda e: asyncio.run(run_deg_analysis(page, token, user_id))
                    ),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text(t("menu_results", lang)),
                controls=[
                    create_menu_item(
                        t("menu_exploratory_analysis", lang),
                        on_click=lambda e: asyncio.run(show_exploratory_dropdown(page, user_id))
                    ),
                    create_menu_item(
                        t("menu_view_deg_results", lang),
                        on_click=lambda e: asyncio.run(
                            show_deg_results(page, token, user_id, container_amostras)
                        )
                    ),
                    create_menu_item(
                        t("menu_barplots", lang),
                        on_click=lambda e: asyncio.run(
                            show_barplots_table(page, token, user_id, container_amostras)
                        )
                    ),
                    create_menu_item(
                        t("menu_venn", lang),
                        on_click=lambda e: asyncio.run(
                            show_venn_table(page, token, user_id, container_amostras)
                        )
                    ),
                    create_menu_item(
                        t("menu_heatmaps", lang),
                        on_click=lambda e: asyncio.run(
                            show_heatmaps_table(page, token, user_id, container_amostras)
                        )
                    ),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text(t("menu_about", lang)),
                controls=[
                    create_menu_item(
                        t("menu_version", lang),
                        on_click=_open_version_modal,
                    ),
                ],
            ),
        ]
    )
