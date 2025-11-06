import asyncio
import flet as ft
from functools import partial
from .procedures.menu_operations import create_menubar, mudar_tema
from .procedures.sample_operations import adicionar_amostra, excluir_amostras_selecionadas, atualizar_tabela, atualizar_tabela_por_estagio, baixar_amostras
from .procedures.quality_analysis import show_quality_analysis_modal, create_tabela_amostras_qc, update_quality_analysis_table, delete_quality_analysis_results
from .procedures.trimmagem import show_trimmagem_modal, create_tabela_amostras_trimmadas, update_trimmagem_table, delete_trimmed_samples
from .procedures.quality_analysis_post_trim import show_quality_analysis_post_trim_modal, create_tabela_amostras_pos_trimmagem, update_tabela_amostras_pos_trimmagem, delete_quality_analysis_post_trim_results
from .procedures.alignment import show_alignment_modal, show_genomes_modal, create_tabela_alinhamento, update_tabela_alinhamento, excluir_alinhamento
from .procedures.quantification import show_quantification_modal, update_tabela_quantificacao, create_tabela_quantificacao, excluir_quantificacao
from .procedures.utils import log_message
from .components.general_components import create_table, create_button
import websockets
import httpx
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Disable httpx logs
httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)

# Disable FastAPI access logs
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.setLevel(logging.WARNING)

async def show_bilbo_interface(page, logout, username, token, user_id):
    print("Entering show_bilbo_interface")
    page.controls.clear()

    # Definição da tabela principal que será usada para diferentes estágios
    tabela_amostras_local = create_table(
        columns=[
            ft.DataColumn(ft.Text("Identificação", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Tamanho", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Status",  weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text(" ")),
            ft.DataColumn(ft.Text("Ações", weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )
    
    # Criação das tabelas específicas para cada estágio
    tabela_amostras_qc = create_tabela_amostras_qc(page, token)
    tabela_amostras_trimmadas = create_tabela_amostras_trimmadas(page, token)
    tabela_amostras_pos_trimmagem = create_tabela_amostras_pos_trimmagem(page, token)
    tabela_alinhamento = create_tabela_alinhamento(page, token)
    tabela_quantificacao = create_tabela_quantificacao(page, token)

    # --- Container principal para a área de amostras ---

    container_amostras = ft.Container(
        expand=2,
        bgcolor="surface",
        border_radius=ft.border_radius.all(12),
        shadow=ft.BoxShadow(blur_radius=6, color="rgba(0, 0, 0, 0.01)"),
        padding=ft.padding.all(12),
        margin=ft.margin.only(0, 5, 0, 0),
        content=ft.ListView(
            expand=True,
            spacing=15,
            controls=[]
        )
    )

    # Função para alternar a tabela e os botões exibidos no container
    async def toggle_buttons(tabela, controls):
        tabela_com_scroll = ft.Row(
            controls=[tabela],     
            scroll=ft.ScrollMode.ALWAYS,
            expand=True
        )
        container_amostras.content.controls = [tabela_com_scroll] + controls
        page.update()

    # --- Handlers para os botões ---
    async def adicionar_amostra_handler(e):
        await adicionar_amostra(e, page, token, container_menu_direita, tabela_amostras_local)

    async def excluir_amostras_selecionadas_handler(e):
        await excluir_amostras_selecionadas(e, page, token, container_menu_direita, tabela_amostras_local)

    async def baixar_amostras_handler(e):
        await baixar_amostras(e, page, token, container_menu_direita, tabela_amostras_local)

    async def show_quality_analysis_modal_handler(e):
        await show_quality_analysis_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)

    async def excluir_qualidade_handler(e):
        await delete_quality_analysis_results(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)

    async def show_trimmagem_modal_handler(e):
        await show_trimmagem_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela)

    async def excluir_amostras_trimmadas_handler(e):
        await delete_trimmed_samples(page, token, tabela_amostras_trimmadas, container_menu_direita, tabela_amostras_local, atualizar_tabela)

    async def show_quality_analysis_post_trim_modal_handler(e):
        await show_quality_analysis_post_trim_modal(page, token, container_menu_direita, tabela_amostras_trimmadas, atualizar_tabela, user_id)

    async def excluir_qualidade_post_trim_handler(e):
        await delete_quality_analysis_post_trim_results(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)

    async def iniciar_alinhamento_handler(e):
        await show_alignment_modal(page, token, user_id, atualizar_tabela, container_menu_direita, tabela_amostras_local)

    async def excluir_alinhamento_handler(e):
        selected_samples = [row.cells[0].content.value for row in tabela_alinhamento.rows if row.cells[4].content.value]
        if not selected_samples:
            await log_message(page, "Nenhuma amostra selecionada para exclusão.")
            return
        await excluir_alinhamento(page, token, user_id, selected_samples, container_menu_direita, tabela_amostras_local, atualizar_tabela)

    async def ver_genomas_referencia_handler(e):
        await show_genomes_modal(page, token, user_id)

    async def iniciar_quantificacao_handler(e):
        await show_quantification_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)

    async def excluir_quantificacao_handler(e):
        selected_samples = [row.cells[0].content.value for row in tabela_quantificacao.rows if row.cells[4].content.value]
        if not selected_samples:
            await log_message(page, "Nenhuma amostra selecionada para exclusão.")
            return
        await excluir_quantificacao(page, token, user_id, selected_samples, container_menu_direita, tabela_amostras_local, atualizar_tabela)
    
    # --- Lógica para atualizar a interface com base no estágio selecionado ---
    async def atualizar_tabela_por_estagio_handler(e, stage_id):
        logger.info(f"Alterando para o estágio: {stage_id}")
        await atualizar_tabela_por_estagio(e, page, token, stage_id, tabela_amostras_local, user_id)
        if stage_id == 1:
            await toggle_buttons(
                tabela=tabela_amostras_local,
                controls=[
                    create_button("Adicionar amostra via SRA", adicionar_amostra_handler, expand=True),
                    create_button("Excluir amostras selecionadas", excluir_amostras_selecionadas_handler, color="red", expand=True),
                    create_button("Baixar amostras pendentes", baixar_amostras_handler, color="green", expand=True),
                ]
            )
        elif stage_id == 2:
            await toggle_buttons(
                tabela=tabela_amostras_qc,
                controls=[
                    create_button("Analisar qualidade", show_quality_analysis_modal_handler, color="green", expand=True),
                    create_button("Excluir resultados de qualidade", excluir_qualidade_handler, color="red", expand=True),
                ]
            )
        elif stage_id == 3:
            await update_trimmagem_table(page, token)
            await toggle_buttons(
                tabela=tabela_amostras_trimmadas,
                controls=[
                    create_button("Iniciar trimmagem", show_trimmagem_modal_handler, expand=True),
                    create_button("Excluir amostras trimmadas", excluir_amostras_trimmadas_handler, color="red", expand=True),
                ]
            )
        elif stage_id == 4:
            await update_tabela_amostras_pos_trimmagem(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)
            await toggle_buttons(
                tabela=tabela_amostras_pos_trimmagem,
                controls=[
                    create_button("Analisar qualidade (pós trimmagem)", show_quality_analysis_post_trim_modal_handler, color="green", expand=True),
                    create_button("Excluir resultados de qualidade", excluir_qualidade_post_trim_handler, color="red", expand=True),
                ]
            )
        elif stage_id == 5:
            await update_tabela_alinhamento(page, token, user_id)
            await toggle_buttons(
                tabela=tabela_alinhamento,
                controls=[
                    create_button("Iniciar alinhamento", iniciar_alinhamento_handler, expand=True),
                    create_button("Excluir alinhamento", excluir_alinhamento_handler, color="red", expand=True),
                    create_button("Ver genomas de referência", ver_genomas_referencia_handler, color="orange", expand=True),
                ]
            )
        elif stage_id == 6:
            await update_tabela_quantificacao(page, token, user_id)
            await toggle_buttons(
                tabela=tabela_quantificacao,
                controls=[
                    create_button("Iniciar quantificação", iniciar_quantificacao_handler, color="green", expand=True),
                    create_button("Excluir quantificação", excluir_quantificacao_handler, color="red", expand=True),
                ]
            )
    
    # --- O restante da sua interface (menus, etc.) ---
    container_menu_direita = ft.Container(
        expand=2,
        bgcolor="surface",
        border_radius=ft.border_radius.all(12),
        shadow=ft.BoxShadow(blur_radius=6, color="rgba(0, 0, 0, 0.01)"),
        padding=ft.padding.all(12),
        margin=ft.margin.only(0, 5, 0, 0),
        content=ft.ListView(
            expand=1,
            spacing=15,
            controls=[
                ft.DataTable(
                    heading_row_color="primary",
                    data_row_color="surface",
                    border=ft.border.all(0.5,"#000000"),
                    columns=[
                        ft.DataColumn(ft.Text("Procedimento", weight=ft.FontWeight.BOLD)),
                        ft.DataColumn(ft.Text("Quantidade", weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)),
                    ],
                    rows=[
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Obtenção de amostras"),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=1)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=1)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Análise de qualidade"),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=2)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=2)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Trimmagem"),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=3)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=3)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Análise de qualidade (pós trimmagem)"),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=4)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=4)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Alinhamento"),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=5)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=5)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Quantificação"),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=6)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=6)
                                )),
                            ],
                        ),
                    ],
                )
            ]
        )
    )

    menubar_principal = create_menubar(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)
    
    container_terminal = ft.Container(
        expand=1,
        bgcolor="surface",
        border_radius=ft.border_radius.all(12),
        shadow=ft.BoxShadow(blur_radius=6, color="rgba(0, 0, 0, 0.01)"),
        alignment=ft.alignment.top_left,
        padding=ft.padding.all(15),
        content=ft.ListView(
            expand=True,
            spacing=8,
            controls=[]
        )
    )
    page.container_terminal = container_terminal

    container_pre_visualizacao = ft.Container(
        expand=2,
        bgcolor="surface",
        border_radius=ft.border_radius.all(12),
        shadow=ft.BoxShadow(blur_radius=6, color="rgba(0, 0, 0, 0.01)"),
        margin=ft.margin.only(0, 5, 0, 0),
        padding=ft.padding.all(12),
        alignment=ft.alignment.center,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    expand=True
                )
            ]
        )
    )

    async def toggle_theme_handler(e):
        await mudar_tema(page)

    page.add(
        ft.Row(
            controls=[
                ft.Container(
                    margin=ft.Margin(-5, -5, 0, 0),
                    expand=30,
                    content=menubar_principal
                ),
                ft.Container(
                    expand=1,
                ),
                ft.Container(
                    alignment=ft.alignment.center_right,
                    margin=ft.Margin(0, -7, -7, -7),
                    expand=6,
                    content=ft.Row(
                        controls=[
                            ft.Text(f"Logged in as: {username}"),
                            ft.IconButton(
                                icon="light_mode",
                                on_click=toggle_theme_handler
                            ),
                            ft.IconButton(
                                icon="logout",
                                on_click=logout
                            )
                        ]
                    )
                )
            ]
        ),
        ft.Row(
            expand=34,
            controls=[
                ft.Column(
                    expand=2,
                    controls=[
                        container_menu_direita
                    ]
                ),
                ft.Column(
                    expand=4,
                    controls=[
                        container_pre_visualizacao,
                    ],
                ),
                ft.Column(
                    expand=2,
                    controls=[
                        container_amostras,
                        container_terminal
                    ],
                )
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )
    
    # Exibir o estado inicial (Estágio 1)
    await atualizar_tabela_por_estagio_handler(None, 1)
    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)

    async def connect_websocket():
        async with websockets.connect("ws://bioinfo-container:8000/ws") as websocket:
            while True:
                message = await websocket.recv()
                await log_message(page, message, container_terminal=container_terminal)
                await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                await update_quality_analysis_table(page, token, user_id)
                page.update()

    page.run_task(connect_websocket)