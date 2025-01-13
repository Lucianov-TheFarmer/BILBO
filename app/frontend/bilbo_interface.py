import asyncio
import flet as ft
from .menu_operations import create_menubar, mudar_tema
from .sample_operations import adicionar_amostra, excluir_amostras_selecionadas, atualizar_tabela, atualizar_tabela_por_estagio, tabela_amostras
from .sample_operations import baixar_amostras
from .utils import log_message  # Updated import
import websockets  # New import
import httpx
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)  # Set to INFO level
logger = logging.getLogger(__name__)

async def show_bilbo_interface(page, logout, username, token):  # Updated function signature
    print("Entering show_bilbo_interface")
    page.controls.clear()

    menubar_principal = create_menubar(page, token)

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
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 1))
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 1))
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Análise de qualidade"),
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 2))
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 2))
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Trimmagem"),
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 3))
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 3))
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Análise de qualidade (pós trimmagem)"),
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 4))
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 4))
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Alinhamento"),
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 5))
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 5))
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Quantificação"),
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 6))
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=lambda e: asyncio.create_task(atualizar_tabela_por_estagio(page, token, 6))
                                )),
                            ],
                        ),
                    ],
                )
            ]
        )
    )

    # Call atualizar_tabela to populate the table initially
    print("Calling atualizar_tabela")
    await atualizar_tabela(page, token, container_menu_direita)

    container_amostras = ft.Container(
        expand=2,
        border=ft.border.all(1, ft.colors.BLACK),
        border_radius=ft.border_radius.all(3),
        margin=ft.margin.only(0, 5, 0, 0),
        content=ft.ListView(
            expand=1,
            spacing=10,
            controls=[
                tabela_amostras,  # Use the global tabela_amostras
                ft.TextButton("Adicionar amostra via SRA", style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=200, height=40, on_click=lambda e: asyncio.create_task(adicionar_amostra(page, token, container_menu_direita))),
                ft.TextButton("Excluir amostras selecionadas", style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), color=ft.colors.RED), width=200, height=40, on_click=lambda e: asyncio.create_task(excluir_amostras_selecionadas(page, token, container_menu_direita))),
                ft.TextButton("Baixar amostras pendentes", style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), color=ft.colors.GREEN), width=200, height=40, on_click=lambda e: asyncio.create_task(baixar_amostras(page, token, container_menu_direita))),
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
        content=ft.Container(expand=True)
    )

    print("Adding controls to the page")
    await page.add_async(
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
                                on_click=lambda e: asyncio.create_task(mudar_tema(page))
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
    await page.update_async()
    print("Exiting show_bilbo_interface")

    # Connect to WebSocket for notifications
    async with websockets.connect("ws://bioinfo-container:8000/ws") as websocket:
        while True:
            message = await websocket.recv()
            await log_message(page, message)
            await atualizar_tabela(page, token, container_menu_direita)
            await page.update_async()