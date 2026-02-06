import flet as ft
import asyncio

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

def create_menubar(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    lang = page.session.get("lang") or "pt"

    return ft.MenuBar(
        controls=[
            ft.SubmenuButton(
                content=ft.Text(t("menu_file", lang)),
                controls=[
                    create_menu_item(t("menu_new", lang)),
                    create_menu_item(t("menu_open", lang)),
                    ft.Divider(),
                    create_menu_item(t("menu_save", lang)),
                    create_menu_item(t("menu_save_as", lang)),
                    ft.Divider(),
                    create_menu_item(t("menu_close", lang)),
                    create_menu_item(t("menu_exit", lang)),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text(t("menu_samples", lang)),
                controls=[
                    create_menu_item(
                        t("menu_add_fastq", lang),
                        on_click=lambda e: (print("DEBUG: Clique detectado no menu Adicionar FASTQ"), asyncio.run(show_upload_fastq_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)))[1]
                    ),
                    create_menu_item(t("menu_add_url", lang)),
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
                            show_deg_results(page, token, user_id, page.controls[1].controls[0].controls[0])
                        )
                    ),
                    create_menu_item(
                        t("menu_barplots", lang),
                        on_click=lambda e: asyncio.run(
                            show_barplots_table(page, token, user_id, page.controls[1].controls[0].controls[0])
                        )
                    ),
                    create_menu_item(
                        t("menu_venn", lang),
                        on_click=lambda e: asyncio.run(
                            show_venn_table(page, token, user_id, page.controls[1].controls[0].controls[0])
                        )
                    ),
                    create_menu_item(
                        t("menu_heatmaps", lang),
                        on_click=lambda e: asyncio.run(
                            show_heatmaps_table(page, token, user_id, page.controls[1].controls[0].controls[0])
                        )
                    ),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text(t("menu_downstream", lang)),
                controls=[
                    create_menu_item(t("menu_enrichment", lang)),
                    create_menu_item(t("menu_go_terms", lang)),
                    create_menu_item(t("menu_pathways", lang)),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text(t("menu_reports", lang)),
                controls=[
                    create_menu_item(t("menu_report_qc", lang)),
                    create_menu_item(t("menu_report_alignment", lang)),
                    create_menu_item(t("menu_report_expression", lang)),
                    create_menu_item(t("menu_report_heatmaps", lang)),
                    create_menu_item(t("menu_report_volcano", lang)),
                    create_menu_item(t("menu_report_ma", lang)),
                    create_menu_item(t("menu_report_profiles", lang)),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text(t("menu_about", lang)),
                controls=[
                    create_menu_item(t("menu_manual", lang)),
                    create_menu_item(t("menu_license", lang)),
                    create_menu_item(t("menu_version", lang)),
                ],
            ),
        ]
    )
