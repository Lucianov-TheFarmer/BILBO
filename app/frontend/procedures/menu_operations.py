import flet as ft
from .sample_operations import adicionar_amostra
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

def create_menu_item(label, close_on_click=True, style=None):
    """Helper function to create a menu item button."""
    return ft.MenuItemButton(
        content=ft.Text(label),
        close_on_click=close_on_click,
        style=style or ft.ButtonStyle(bgcolor={ft.ControlState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
        on_click=lambda e: None,  # Make the button clickable but do nothing
    )

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
                    create_menu_item("Adicionar via SRA"),  # Temporarily no functionality
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Qualidade"),
                controls=[
                    create_menu_item("Verificar qualidade"),
                    create_menu_item("Filtragem"),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Alinhamento"),
                controls=[
                    create_menu_item("Adicionar genoma de referência"),
                    create_menu_item("Alinhar com o genoma de referência"),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Quantificação"),
                controls=[
                    create_menu_item("Quantificar reads alinhadas"),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Expressão diferencial"),
                controls=[
                    create_menu_item("Normalização"),
                    create_menu_item("Tabelas de expressão diferencial"),
                    create_menu_item("Obter genes diferencialmente expressos"),
                ],
            ),
            ft.SubmenuButton(
                content=ft.Text("Identificação"),
                controls=[
                    create_menu_item("Indentificar transcritos via GFF"),
                    create_menu_item("Identificar transcritos via Blast"),
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