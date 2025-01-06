import flet as ft
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def adicionar_amostra(page, token):
    def inserir_sra_na_fila(sra_code):
        sra_code = sra_code.strip()
        if not sra_code:
            page.show_snack_bar(ft.SnackBar(content=ft.Text("Insira um código SRA válido.")))
            return
        dlg_modal_adicionar_amostra.open = False
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        response = requests.post("http://bioinfo-container:8000/samples/", params={"sra_code": sra_code, "size": "Unknown"}, headers=headers)
        if response.status_code == 200:
            page.show_snack_bar(ft.SnackBar(content=ft.Text("Amostra adicionada com sucesso!")))
            atualizar_tabela(page, token)
        else:
            page.show_snack_bar(ft.SnackBar(content=ft.Text("Erro ao adicionar amostra.")))
        page.update()

    sra_code_field = ft.TextField(
        hint_text="Insira um código SRA",
        border_radius=ft.border_radius.all(4),
        multiline=False,
        min_lines=1,
    )

    dlg_modal_adicionar_amostra = ft.AlertDialog(
        title=ft.Text("Adicionar via SRA"),
        content=sra_code_field,
        actions=[
            ft.TextButton("Submeter", on_click=lambda e: inserir_sra_na_fila(sra_code_field.value), style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=200, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.dialog = dlg_modal_adicionar_amostra
    dlg_modal_adicionar_amostra.open = True
    page.update()

def excluir_amostras_selecionadas(page, token):
    def confirmar_exclusao(e):
        amostras_selecionadas_para_exclusao = []
        dlg_modal_excluir_amostra.open = False
        for i in tabela_amostras.rows:
            if i.cells[3].content.value:
                amostras_selecionadas_para_exclusao.append(i.cells[0].content.value)
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        for sra_code in amostras_selecionadas_para_exclusao:
            response = requests.delete(f"http://bioinfo-container:8000/samples/{sra_code}", headers=headers)
            if response.status_code == 200:
                page.show_snack_bar(ft.SnackBar(content=ft.Text(f"Amostra {sra_code} excluída com sucesso!")))
            else:
                page.show_snack_bar(ft.SnackBar(content=ft.Text(f"Erro ao excluir amostra {sra_code}.")))
        atualizar_tabela(page, token)
        page.update()

    confirm_field = ft.TextField(
        hint_text="Digite 'Confirmar' para excluir as amostras selecionadas.",
        border_radius=ft.border_radius.all(4),
        multiline=False,
        expand=1
    )

    dlg_modal_excluir_amostra = ft.AlertDialog(
        title=ft.Text("Confirmar exclusão"),
        content=confirm_field,
        actions=[
            ft.TextButton("Excluir", on_click=lambda e: confirmar_exclusao(e) if confirm_field.value == 'Confirmar' else None, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=200, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.dialog = dlg_modal_excluir_amostra
    dlg_modal_excluir_amostra.open = True
    page.update()

def atualizar_tabela(page, token):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    response = requests.get("http://bioinfo-container:8000/samples/", headers=headers)
    samples = response.json()
    tabela_amostras.rows.clear()
    for sample in samples:
        tabela_amostras.rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sample["sra_code"])),
                    ft.DataCell(ft.Text(sample["size"])),
                    ft.DataCell(ft.Text(sample["status"])),
                    ft.DataCell(ft.Checkbox()),
                ],
            )
        )
    page.update()

def baixar_amostras(page, token):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    response = requests.post("http://bioinfo-container:8000/samples/download", headers=headers)
    if response.status_code == 200:
        page.show_snack_bar(ft.SnackBar(content=ft.Text("Download iniciado!")))
        logger.info("Download iniciado!")
    else:
        logger.error(f"Download error: {response.status_code} - {response.text}")
        page.show_snack_bar(ft.SnackBar(content=ft.Text("Erro ao iniciar download.")))
    atualizar_tabela(page, token)

tabela_amostras = ft.DataTable(
    heading_row_color=ft.colors.BLACK12,
    columns=[
        ft.DataColumn(ft.Text("Identificação")),
        ft.DataColumn(ft.Text("Tamanho")),
        ft.DataColumn(ft.Text("Status")),
        ft.DataColumn(ft.Text(" ")),
    ],
    rows=[],
)