import asyncio
import flet as ft
from .menu_operations import create_menubar, mudar_tema
from .sample_operations import adicionar_amostra, excluir_amostras_selecionadas, atualizar_tabela, tabela_amostras
from .sample_operations import baixar_amostras

async def show_bilbo_interface(page, logout, username, token):  # Updated function signature
    print("Entering show_bilbo_interface")
    page.controls.clear()

    menubar_principal = create_menubar(page, token)

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
                ft.TextButton("Adicionar amostra via SRA", style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=200, height=40, on_click=lambda e: asyncio.create_task(adicionar_amostra(page, token))),
                ft.TextButton("Excluir amostras selecionadas", style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), color=ft.colors.RED), width=200, height=40, on_click=lambda e: asyncio.create_task(excluir_amostras_selecionadas(page, token))),
                ft.TextButton("Baixar amostras pendentes", style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), color=ft.colors.GREEN), width=200, height=40, on_click=lambda e: asyncio.create_task(baixar_amostras(page, token))),
            ]
        )
    )

    # Call atualizar_tabela to populate the table initially
    print("Calling atualizar_tabela")
    await atualizar_tabela(page, token)

    container_progresso = ft.Column(
        expand=1,
        spacing=5,
        controls=[
            ft.Container(
                expand=5,
                border=ft.border.all(1, ft.colors.BLACK),
                border_radius=ft.border_radius.all(3),
                alignment=ft.alignment.center,
                padding=ft.padding.all(15),
                content=ft.Text("Tarefa atual: Aguardando", color=ft.colors.ON_PRIMARY_CONTAINER, expand=True, size=18)
            ),
            ft.Container(
                expand=1,
                border=ft.border.all(1, ft.colors.BLACK),
                border_radius=ft.border_radius.all(15),
                content=ft.ProgressBar(color=ft.colors.TERTIARY, value=0),
            )
        ]
    )

    container_pre_visualizacao = ft.Container(
        expand=2,
        border=ft.border.all(1, ft.colors.BLACK),
        border_radius=ft.border_radius.all(3),
        margin=ft.margin.only(0, 5, 0, 0),
        content=ft.Container(expand=True)
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
                                ft.DataCell(ft.Text("Obtenção de amostras")),
                                ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=ft.alignment.center)),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text("Análise de qualidade")),
                                ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=ft.alignment.center)),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text("Trimmagem")),
                                ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=ft.alignment.center)),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text("Análise de qualidade (pós trimmagem)")),
                                ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=ft.alignment.center)),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text("Alinhamento")),
                                ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=ft.alignment.center)),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text("Quantificação")),
                                ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=ft.alignment.center)),
                            ],
                        ),
                    ],
                )
            ]
        )
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
                        container_progresso
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