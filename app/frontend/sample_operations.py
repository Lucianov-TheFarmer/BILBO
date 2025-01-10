import flet as ft
import httpx
import logging
import asyncio
import websockets  # New import
from .utils import log_message  # Updated import

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track the WebSocket connection
websocket_connection = None
first_check_done = False

async def adicionar_amostra(page, token):
    async def inserir_sra_na_fila(sra_code):
        sra_code = sra_code.strip()
        if not sra_code:
            logger.error("Insira um código SRA válido.")
            return
        dlg_modal_adicionar_amostra.open = False
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("http://bioinfo-container:8000/samples/", params={"sra_code": sra_code, "size": "Unknown"}, headers=headers)
            if response.status_code == 200:
                logger.info("Amostra adicionada com sucesso!")
            else:
                logger.error(f"Erro ao adicionar amostra: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        await atualizar_tabela(page, token)
        await page.update_async()

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
            ft.TextButton("Submeter", on_click=lambda e: asyncio.create_task(inserir_sra_na_fila(sra_code_field.value)), style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=200, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.dialog = dlg_modal_adicionar_amostra
    dlg_modal_adicionar_amostra.open = True
    await page.update_async()

async def excluir_amostras_selecionadas(page, token):
    async def confirmar_exclusao(e):
        amostras_selecionadas_para_exclusao = []
        dlg_modal_excluir_amostra.open = False
        for i in tabela_amostras.rows:
            if i.cells[3].content.value:
                amostras_selecionadas_para_exclusao.append(i.cells[0].content.value)
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                for sra_code in amostras_selecionadas_para_exclusao:
                    response = await client.delete(f"http://bioinfo-container:8000/samples/{sra_code}", headers=headers)
                    if response.status_code == 200:
                        logger.info(f"Amostra {sra_code} excluída com sucesso!")
                        await log_message(page, f"Amostra {sra_code} excluída com sucesso!")
                    else:
                        logger.error(f"Erro ao excluir amostra {sra_code}: {response.status_code} - {response.text}")
                        await log_message(page, f"Erro ao excluir amostra {sra_code}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            await log_message(page, f"An error occurred: {e}")
        await atualizar_tabela(page, token)
        await page.update_async()

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
            ft.TextButton("Excluir", on_click=lambda e: asyncio.create_task(confirmar_exclusao(e)) if confirm_field.value == 'Confirmar' else None, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=200, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.dialog = dlg_modal_excluir_amostra
    dlg_modal_excluir_amostra.open = True
    await page.update_async()

async def atualizar_tabela(page, token):
    global first_check_done
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    async with httpx.AsyncClient() as client:
        if not first_check_done:
            response = await client.get("http://bioinfo-container:8000/samples/", headers=headers)
            samples = response.json()
            for sample in samples:
                if sample["status"] == "In Progress":
                    sample["status"] = "Failed"
                    await client.post("http://bioinfo-container:8000/samples/update_status", data={"sra_code": sample["sra_code"], "status": "Failed"}, headers=headers)
                    logger.info(f"Sample {sample['sra_code']} status updated to Failed due to incomplete download")
            first_check_done = True
        else:
            response = await client.get("http://bioinfo-container:8000/samples/", headers=headers)
            samples = response.json()
    tabela_amostras.rows.clear()
    for sample in samples:
        tabela_amostras.rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sample["sra_code"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Checkbox()),
                ],
            )
        )
    await page.update_async()

async def baixar_amostras(page, token):
    global websocket_connection
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("http://bioinfo-container:8000/samples/download", headers=headers)
            if response.status_code == 200:
                logger.info("Download iniciado!")
                sample_name = response.json().get("sample_name", "Unknown")
                await log_message(page, f"Iniciando o download da amostra {sample_name}.")
                await atualizar_tabela(page, token)
                await page.update_async()
                if websocket_connection is None or websocket_connection.closed:
                    websocket_connection = await websockets.connect("ws://bioinfo-container:8000/ws")
                message = await websocket_connection.recv()
                await log_message(page, message)
                await atualizar_tamanho_amostras(page, token, sample_name)
                await atualizar_tabela(page, token)
                await page.update_async()
            elif response.status_code == 404:
                logger.error(f"Download error: {response.status_code} - {response.text}")
            else:
                logger.error(f"Download error: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    await atualizar_tabela(page, token)
    await page.update_async()

async def atualizar_tamanho_amostras(page, token, sra_code):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("http://bioinfo-container:8000/samples/calculate_size", params={"sra_code": sra_code}, headers=headers)
            if response.status_code == 200:
                logger.info("Tamanho das amostras atualizado com sucesso!")
            else:
                logger.error(f"Erro ao atualizar tamanho das amostras: {response.status_code} - {response.text}")
                await log_message(page, f"Erro ao atualizar tamanho das amostras: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        await log_message(page, f"An error occurred: {e}")

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