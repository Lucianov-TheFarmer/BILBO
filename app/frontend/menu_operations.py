import flet as ft
from .procedures.sample_operations import adicionar_amostra  # Updated import
import asyncio

def menubar_clicar_item(e):
    print(f"{e.control.content.value}.on_click")
    e.page.show_snack_bar(ft.SnackBar(content=ft.Text(f"{e.control.content.value} was clicked!")))
    e.page.update()

def menubar_abrir_item(e):
    print(f"{e.control.content.value}.on_open")

def menubar_fechar_item(e):
    print(f"{e.control.content.value}.on_close")

def menubar_passar_por_cima_item(e):
    print(f"{e.control.content.value}.on_hover")

async def mudar_tema(page):
    if page.theme_mode == ft.ThemeMode.LIGHT:
        page.theme_mode = ft.ThemeMode.DARK
    else:
        page.theme_mode = ft.ThemeMode.LIGHT
    page.update()

def create_menubar(page, token, container_menu_direita, tabela_amostras_local):
    return ft.MenuBar(
        controls=[
            ft.SubmenuButton(
                content=ft.Text("Arquivo"),
                on_open=menubar_abrir_item,
                on_close=menubar_fechar_item,
                on_hover=menubar_passar_por_cima_item,
                controls=[
                    ft.MenuItemButton(
                        content=ft.Text("Novo"),
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Abrir"),
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.Divider(),
                    ft.MenuItemButton(
                        content=ft.Text("Salvar"),
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Salvar como"),
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.Divider(),
                    ft.MenuItemButton(
                        content=ft.Text("Fechar"),
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Sair"),
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    )
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Amostras"),
                on_open=menubar_abrir_item,
                on_close=menubar_fechar_item,
                on_hover=menubar_passar_por_cima_item,
                controls=[
                    ft.MenuItemButton(
                        content=ft.Text("Adicionar FASTQ"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Adicionar via URL"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Adicionar via SRA"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: adicionar_amostra(page, token, container_menu_direita, tabela_amostras_local)
                    )
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Qualidade"),
                on_open=menubar_abrir_item,
                on_close=menubar_fechar_item,
                on_hover=menubar_passar_por_cima_item,
                controls=[
                    ft.MenuItemButton(
                        content=ft.Text("Verificar qualidade"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Filtragem"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Alinhamento"),
                on_open=menubar_abrir_item,
                on_close=menubar_fechar_item,
                on_hover=menubar_passar_por_cima_item,
                controls=[
                    ft.MenuItemButton(
                        content=ft.Text("Adicionar genoma de referência"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Alinhar com o genoma de referência"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Quantificação"),
                on_open=menubar_abrir_item,
                on_close=menubar_fechar_item,
                on_hover=menubar_passar_por_cima_item,
                controls=[
                    ft.MenuItemButton(
                        content=ft.Text("Quantificar reads alinhadas"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    )
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Expressão diferencial"),
                on_open=menubar_abrir_item,
                on_close=menubar_fechar_item,
                on_hover=menubar_passar_por_cima_item,
                controls=[
                    ft.MenuItemButton(
                        content=ft.Text("Normalização"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Tabelas de expressão diferencial"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Obter genes diferencialmente expressos"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    )
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Identificação"),
                on_open=menubar_abrir_item,
                on_close=menubar_fechar_item,
                on_hover=menubar_passar_por_cima_item,
                controls=[
                    ft.MenuItemButton(
                        content=ft.Text("Indentificar transcritos via GFF"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Identificar transcritos via Blast"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Downstream"),
                on_open=menubar_abrir_item,
                on_close=menubar_fechar_item,
                on_hover=menubar_passar_por_cima_item,
                controls=[
                    ft.MenuItemButton(
                        content=ft.Text("Análise de enriquecimento"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Distribuição de termos GO"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Reconstrução de rotas metabólicas"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    )
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Relatórios"),
                on_open=menubar_abrir_item,
                on_close=menubar_fechar_item,
                on_hover=menubar_passar_por_cima_item,
                controls=[
                    ft.MenuItemButton(
                        content=ft.Text("Controle de qualidade"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Resultados dos alinhamentos"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Resultados da análise de expressão"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Heatmaps"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Volcano plots"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("MA plots"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Heatmaps"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Perfis de expressão"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    )
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Sobre"),
                on_open=menubar_abrir_item,
                on_close=menubar_fechar_item,
                on_hover=menubar_passar_por_cima_item,
                controls=[
                    ft.MenuItemButton(
                        content=ft.Text("Manual de utilização"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Licença de uso"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                    ft.MenuItemButton(
                        content=ft.Text("Versão do software"),
                        close_on_click=False,
                        style=ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                        on_click=lambda e: menubar_clicar_item(e)
                    ),
                ],
            ),
        ]
    )