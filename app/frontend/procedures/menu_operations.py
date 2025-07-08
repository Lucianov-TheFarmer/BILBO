import flet as ft
from .sample_operations import adicionar_amostra
from .quality_analysis import show_quality_analysis_modal
from .trimmagem import show_trimmagem_modal
from .quality_analysis_post_trim import show_quality_analysis_post_trim_modal
from .alignment import show_alignment_modal, show_genomes_modal
from .quantification import show_quantification_modal
from .contrasts import show_contrasts_modal
from .preprocess import show_preprocess_modal, show_exploratory_dropdown
from .deg import run_deg_analysis, show_deg_results
from .results import show_barplots_table, show_venn_table, show_heatmap_table
import asyncio

def create_menu_item(label, close_on_click=True, style=None, on_click=None):
    """Helper function to create a menu item button."""
    return ft.MenuItemButton(
        content=ft.Text(label),
        close_on_click=close_on_click,
        style=style or ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
        on_click=on_click,  # Pass the on_click handler
    )

async def mudar_tema(page):
    if page.theme_mode == ft.ThemeMode.LIGHT:
        page.theme_mode = ft.ThemeMode.DARK
    else:
        page.theme_mode = ft.ThemeMode.LIGHT
    page.update()

def create_menubar(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    return ft.MenuBar(
        controls=[
            ft.SubmenuButton(
                content=ft.Text("Arquivo"),
                controls=[
                    create_menu_item("Novo"),
                    create_menu_item("Abrir"),
                    ft.Divider(),
                    create_menu_item("Salvar"),
                    create_menu_item("Salvar como"),
                    ft.Divider(),
                    create_menu_item("Fechar"),
                    create_menu_item("Sair"),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Amostras"),
                controls=[
                    create_menu_item("Adicionar FASTQ"),
                    create_menu_item("Adicionar via URL"),
                    create_menu_item(
                        "Adicionar via SRA",
                        on_click=lambda e: asyncio.run(adicionar_amostra(e, page, token, container_menu_direita, tabela_amostras_local))
                    ),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Qualidade"),
                controls=[
                    create_menu_item(
                        "Verificar qualidade",
                        on_click=lambda e: asyncio.run(show_quality_analysis_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id))),
                    create_menu_item(
                        "Trimmagem",
                        on_click=lambda e: asyncio.run(show_trimmagem_modal(page, token, container_menu_direita, tabela_amostras_local,  atualizar_tabela))),
                    create_menu_item(
                        "Verificar qualidade pós-trimmagem",
                        on_click=lambda e: asyncio.run(show_quality_analysis_post_trim_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id))),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Alinhamento"),
                controls=[
                    create_menu_item(
                        "Adicionar genoma de referência",
                        on_click=lambda e: asyncio.run(show_genomes_modal(page, token, user_id))),
                    create_menu_item(
                        "Alinhar com o genoma de referência",
                        on_click=lambda e: asyncio.run(show_alignment_modal(page, token, user_id, atualizar_tabela, container_menu_direita, tabela_amostras_local))),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Quantificação"),
                controls=[
                    create_menu_item(
                        "Quantificar reads alinhadas",
                        on_click=lambda e: asyncio.run(show_quantification_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id))),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Expressão diferencial"),
                controls=[
                    create_menu_item(
                        "Definir contrastes",
                        on_click=lambda e: asyncio.run(show_contrasts_modal(page, token, user_id))
                    ),
                    create_menu_item(
                        "Pré-processamento",
                        on_click=lambda e: asyncio.run(show_preprocess_modal(page, token, user_id))
                    ),
                    create_menu_item(
                        "Iniciar DEG",
                        on_click=lambda e: asyncio.run(run_deg_analysis(page, token, user_id))
                    ),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Resultados"),
                controls=[
                    create_menu_item(
                        "Análise exploratória",
                        on_click=lambda e: asyncio.run(show_exploratory_dropdown(page, user_id))
                    ),
                    create_menu_item(
                        "Ver resultados de DEG",
                        on_click=lambda e: asyncio.run(
                            show_deg_results(page, token, user_id, page.controls[1].controls[0].controls[0])  # container_amostras
                        )
                    ),
                    create_menu_item(
                        "Barplots (Múltiplos contrastes)",
                        on_click=lambda e: asyncio.run(
                            show_barplots_table(page, token, user_id, page.controls[1].controls[0].controls[0])  # Mostra a tabela, não o modal
                        )
                    ),
                    create_menu_item(
                        "Diagrama de Venn",
                        on_click=lambda e: asyncio.run(
                            show_venn_table(page, token, user_id, page.controls[1].controls[0].controls[0])  # container_amostras
                        )
                    ),
                    create_menu_item(
                        "Heatmaps",
                        on_click=lambda e: asyncio.run(
                            show_heatmap_table(page, token, user_id, page.controls[1].controls[0].controls[0])  # container_amostras
                        )
                    ),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Downstream"),
                controls=[
                    create_menu_item("Análise de enriquecimento"),
                    create_menu_item("Distribuição de termos GO"),
                    create_menu_item("Reconstrução de rotas metabólicas"),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Relatórios"),
                controls=[
                    create_menu_item("Controle de qualidade"),
                    create_menu_item("Resultados dos alinhamentos"),
                    create_menu_item("Resultados da análise de expressão"),
                    create_menu_item("Heatmaps"),
                    create_menu_item("Volcano plots"),
                    create_menu_item("MA plots"),
                    create_menu_item("Heatmaps"),
                    create_menu_item("Perfis de expressão"),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Sobre"),
                controls=[
                    create_menu_item("Manual de utilização"),
                    create_menu_item("Licença de uso"),
                    create_menu_item("Versão do software"),
                ],
            ),
        ]
    )