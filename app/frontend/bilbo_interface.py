import asyncio
import flet as ft
from functools import partial
from .procedures.menu_operations import create_menubar, mudar_tema
from .procedures.sample_operations import adicionar_amostra, excluir_amostras_selecionadas, atualizar_tabela, atualizar_tabela_por_estagio, baixar_amostras
from .procedures.quality_analysis import show_quality_analysis_modal, create_tabela_amostras_qc, update_quality_analysis_table, delete_quality_analysis_results
from .procedures.trimmagem import show_trimmagem_modal, create_tabela_amostras_trimmadas, show_trimmagem_table, delete_trimmed_samples  # Import the trimmagem modal and table
from .procedures.viewer import create_dropdown_menu, display_graph  # Updated import
from .procedures.utils import log_message  # Updated import
from .components.general_components import create_table, create_button  # Updated import
import websockets  # New import
import httpx
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)  # Set to DEBUG level
logger = logging.getLogger(__name__)

async def show_bilbo_interface(page, logout, username, token, user_id):  # Updated function signature
    print("Entering show_bilbo_interface")
    page.controls.clear()

    # Create a new instance of tabela_amostras
    tabela_amostras_local = create_table(
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text(" ")),
        ],
        rows=[],
    )

    tabela_amostras_qc = create_tabela_amostras_qc(page, token)  # Pass token as argument

    tabela_amostras_trimmadas = create_tabela_amostras_trimmadas(page, token)  # Pass token as argument

    # Function to toggle buttons
    async def toggle_buttons(controls, tabela):
        container_amostras.content.controls = [tabela] + controls
        page.update()

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

    async def atualizar_tabela_por_estagio_handler(e, stage_id):
        await atualizar_tabela_por_estagio(e, page, token, stage_id, tabela_amostras_local, user_id)
        if stage_id == 1:
            await toggle_buttons([
                create_button("Adicionar amostra via SRA", adicionar_amostra_handler),
                create_button("Excluir amostras selecionadas", excluir_amostras_selecionadas_handler, color=ft.colors.RED),
                create_button("Baixar amostras pendentes", baixar_amostras_handler, color=ft.colors.GREEN),
            ], tabela_amostras_local)
        elif stage_id == 2:
            await toggle_buttons([
                analisar_qualidade_button,
                excluir_qualidade_button,
            ], tabela_amostras_qc)
        elif stage_id == 3:  # Trimmagem stage
            await show_trimmagem_table(page, token, tabela_amostras_local)  # Atualiza apenas o container_amostras
            await toggle_buttons([
                iniciar_trimmagem_button,
                excluir_trimmagem_button,
            ], tabela_amostras_local)

    # Define the "Analisar qualidade" button
    analisar_qualidade_button = create_button(
        label="Analisar qualidade",
        on_click=show_quality_analysis_modal_handler,
    )

    # Define the "Excluir resultados de qualidade" button
    excluir_qualidade_button = create_button(
        label="Excluir resultados de qualidade",
        on_click=excluir_qualidade_handler,
        color=ft.colors.RED,
    )

    # Define the "Iniciar trimmagem" button
    iniciar_trimmagem_button = create_button(
        label="Iniciar trimmagem",
        on_click=show_trimmagem_modal_handler,  # Call the trimmagem modal
    )

    # Define the "Excluir amostras trimmadas" button
    excluir_trimmagem_button = create_button(
        label="Excluir amostras trimmadas",
        on_click=excluir_amostras_trimmadas_handler,
        color=ft.colors.RED,
    )

    container_menu_direita = ft.Container(
        expand=2,
        border=ft.border.all(1, ft.colors.BLACK),
        border_radius=ft.border_radius.all(3),
        margin=ft.margin.only(0, 5, 0, 0),
        content=ft.ListView(
            expand=1,
            spacing=10,
            controls=[
                ft.DataTable(
                    heading_row_color=ft.colors.BLACK12,
                    columns=[
                        ft.DataColumn(ft.Text("Procedimento")),
                        ft.DataColumn(ft.Text("Quantidade")),
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

    menubar_principal = create_menubar(page, token, container_menu_direita, tabela_amostras_local)

    # Call atualizar_tabela to populate the table initially
    print("Calling atualizar_tabela")
    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)

    container_amostras = ft.Container(
        expand=2,
        border=ft.border.all(1, ft.colors.BLACK),
        border_radius=ft.border_radius.all(3),
        margin=ft.margin.only(0, 5, 0, 0),
        content=ft.ListView(
            expand=1,
            spacing=10,
            controls=[
                tabela_amostras_local,  # Use the local tabela_amostras
                create_button("Adicionar amostra via SRA", adicionar_amostra_handler),
                create_button("Excluir amostras selecionadas", excluir_amostras_selecionadas_handler, color=ft.colors.RED),
                create_button("Baixar amostras pendentes", baixar_amostras_handler, color=ft.colors.GREEN),
            ]
        )
    )

    container_terminal = ft.Container(
        expand=1,
        border=ft.border.all(1, ft.colors.BLACK),
        border_radius=ft.border_radius.all(3),
        alignment=ft.alignment.center,
        padding=ft.padding.all(15),
        content=ft.ListView(
            expand=True,
            spacing=10,
            controls=[]
        )
    )

    container_pre_visualizacao = ft.Container(
        expand=2,
        border=ft.border.all(1, ft.colors.BLACK),
        border_radius=ft.border_radius.all(3),
        margin=ft.margin.only(0, 5, 0, 0),
        content=ft.Column(
            controls=[
                ft.Container(
                    expand=True,
                    content=None  # Placeholder to maintain size
                )
            ]
        )
    )

    print("Adding controls to the page")

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
                                icon=ft.icons.LIGHT_MODE,
                                on_click=toggle_theme_handler
                            ),
                            ft.IconButton(
                                icon=ft.icons.LOGOUT,
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
                    expand=1,
                    controls=[
                        container_amostras,
                        container_terminal
                    ]
                ),
                ft.Column(
                    expand=1,
                    controls=[
                        container_pre_visualizacao,
                        ft.Container(
                            expand=1,
                            border=ft.border.all(1, ft.colors.BLACK),
                            border_radius=ft.border_radius.all(3),
                        ),
                    ],
                ),
                ft.Column(
                    expand=1,
                    controls=[
                        container_menu_direita,
                        ft.Container(
                            expand=1,
                            border=ft.border.all(1, ft.colors.BLACK),
                            border_radius=ft.border_radius.all(3),
                        ),
                    ],
                )
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )
    print("Updating the page")
    page.update()
    print("Exiting show_bilbo_interface")

    # Connect to WebSocket for notifications
    async def connect_websocket():
        async with websockets.connect("ws://bioinfo-container:8000/ws") as websocket:
            while True:
                message = await websocket.recv()
                await log_message(page, message)
                await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                await update_quality_analysis_table(page, token, user_id)
                page.update()

    # Inicie a tarefa WebSocket em segundo plano
    page.run_task(connect_websocket)
