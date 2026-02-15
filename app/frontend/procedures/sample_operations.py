import flet as ft
import httpx
import logging
import asyncio
from .jobs import wait_for_job
from .utils import log_message
from .quality_analysis import update_quality_analysis_table
from ..components.general_components import create_table  # Import reusable table

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track the WebSocket connection
first_check_done = False

tabela_amostras = create_table(
    columns=[
        ft.DataColumn(ft.Text("Identificação")),
        ft.DataColumn(ft.Text("Tamanho")),
        ft.DataColumn(ft.Text("Status")),
        ft.DataColumn(ft.Checkbox()),  # Add checkbox to the column header
    ],
    rows=[],
)

async def adicionar_amostra(e, page, token, container_menu_direita, tabela_amostras_local):
    async def inserir_sra_na_fila(sra_codes):
        sra_codes = [code.strip() for code in sra_codes.split(",") if code.strip()]
        if not sra_codes:
            logger.error("Insira um ou mais códigos SRA válidos.")
            return
        dlg_modal_adicionar_amostra.open = False
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://bioinfo-container:8000/samples/",
                    json={"sra_codes": sra_codes, "size": "Unknown"},
                    headers=headers,
                )
                if response.status_code == 200:
                    samples = response.json()
                    for sample in samples:
                        logger.info(f"Amostra {sample['sra_code']} adicionada com sucesso!")
                elif response.status_code == 400:
                    try:
                        detail = response.json().get("detail", "")
                    except Exception:
                        detail = response.text
                    logger.error(f"Erro ao adicionar amostras: {detail}")
                    await log_message(page, f"Erro ao adicionar amostras: {detail}")
                else:
                    logger.error(f"Erro ao adicionar amostras: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
        page.update()

    sra_code_field = ft.TextField(
        hint_text="Insira um ou mais códigos SRA separados por vírgulas",
        border_radius=ft.border_radius.all(4),
        multiline=False,
        min_lines=1,
    )

    async def inserir_sra_na_fila_handler(e):
        await inserir_sra_na_fila(sra_code_field.value)

    dlg_modal_adicionar_amostra = ft.AlertDialog(
        title=ft.Text("Adicionar via SRA"),
        content=sra_code_field,
        actions=[
            ft.TextButton("Submeter", on_click=inserir_sra_na_fila_handler, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=500, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER
    )
    
    page.open(dlg_modal_adicionar_amostra)

async def excluir_amostras_selecionadas(e, page, token, container_menu_direita, tabela_amostras_local):
    async def confirmar_exclusao():
        amostras_selecionadas_para_exclusao = []
        dlg_modal_excluir_amostra.open = False
        for row in tabela_amostras_local.rows:
            if isinstance(row.cells[3].content, ft.Checkbox) and row.cells[3].content.value:
                sample_name = row.cells[0].content.value
                if isinstance(sample_name, str):
                    amostras_selecionadas_para_exclusao.append(sample_name)

        if not amostras_selecionadas_para_exclusao:
            logger.error("Nenhuma amostra selecionada para exclusão.")
            return

        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                for sra_code in amostras_selecionadas_para_exclusao:
                    response = await client.delete(f"http://bioinfo-container:8000/samples/{sra_code}", headers=headers)
                    if response.status_code == 200:
                        logger.info(f"Amostra {sra_code} excluída com sucesso!")
                        await log_message(page, f"Amostra {sra_code} excluída com sucesso!")
                        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                        page.update()
                    else:
                        logger.error(f"Erro ao excluir amostra {sra_code}: {response.status_code} - {response.text}")
                        await log_message(page, f"Erro ao excluir amostra {sra_code}: {response.status_code} - {response.text}")
                        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                        page.update()
            
        except Exception as e:
            logger.error(f"Erro ao excluir amostras: {e}", exc_info=True)

    confirm_field = ft.TextField(
        hint_text="Digite 'Confirmar' para excluir as amostras selecionadas.",
        border_radius=ft.border_radius.all(4),
        multiline=False,
        expand=1
    )

    async def confirmar_exclusao_handler(e):
        if confirm_field.value == 'Confirmar':
            await confirmar_exclusao()

    dlg_modal_excluir_amostra = ft.AlertDialog(
        title=ft.Text("Confirmar exclusão"),
        content=confirm_field,
        actions=[
            ft.TextButton("Excluir", on_click=confirmar_exclusao_handler, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=200, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_excluir_amostra)

async def make_request(method, url, headers=None, json=None, params=None):
    """Helper function to make HTTP requests."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=headers, json=json, params=params)
            response.raise_for_status()
            return response
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise

async def atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local):
    global first_check_done
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    if not first_check_done:
        await make_request("POST", "http://bioinfo-container:8000/stages/", headers=headers)
        first_check_done = True

    response = await make_request("GET", "http://bioinfo-container:8000/samples/", headers=headers)
    samples = response.json()

    async def toggle_select_all(e):
        for row in tabela_amostras_local.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    tabela_amostras_local.rows.clear()
    tabela_amostras_local.columns[3] = ft.DataColumn(ft.Checkbox(on_change=toggle_select_all))
    for sample in samples:
        
        async def download_sample_file(e, sample_name=sample["name"]):
            try:
                download_url = f"http://localhost:8000/download/obtencao/{sample_name}?token={token}"
                page.launch_url(download_url)
                await log_message(page, f"Download iniciado para {sample_name}")
                
            except Exception as e:
                logger.error(f"Erro no download de {sample_name}: {e}")
                await log_message(page, f"Erro no download de {sample_name}: {str(e)}")
        
        # Show download button only when sample status is Completed
        actions = []
        try:
            status = (sample.get("status") or "").lower()
        except Exception:
            status = ""

        if status == "completed":
            actions.append(ft.IconButton(
                icon="download",
                tooltip="Baixar arquivo da amostra",
                on_click=download_sample_file
            ))

        tabela_amostras_local.rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sample["name"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Checkbox()),
                    ft.DataCell(ft.Row(actions)),
                ],
            )
        )

    stage_counts = {}
    # Fetch counts for stages 1..10
    for stage_id in range(1, 11):
        try:
            response = await make_request("GET", f"http://bioinfo-container:8000/samples/stages/{stage_id}", headers=headers)
            stage_counts[stage_id] = len(response.json())
        except Exception:
            stage_counts[stage_id] = 0

    # Fetch contrasts count to represent DEG results (stage_id 8)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://bioinfo-container:8000/contrasts/", headers=headers)
            if resp.status_code == 200:
                contrasts = resp.json()
                # DEG results are represented at stage_id 7 in the UI
                stage_counts[7] = len(contrasts)
            else:
                stage_counts[7] = 0
    except Exception:
        stage_counts[7] = 0

    # Map table rows order to corresponding stage ids. If UI order changes, update this map accordingly.
    stage_map = [1, 2, 3, 4, 5, 6, 7, 9, 10]
    for i, row in enumerate(container_menu_direita.content.controls[0].rows):
        mapped_stage = stage_map[i] if i < len(stage_map) else (i + 1)
        # update the quantity cell (row.cells[1].content.content holds the Text)
        try:
            row.cells[1].content.content.value = str(stage_counts.get(mapped_stage, 0))
        except Exception:
            # fallback if structure differs
            try:
                row.cells[1].content.value = str(stage_counts.get(mapped_stage, 0))
            except Exception:
                pass

    page.update()

async def atualizar_tabela_por_estagio(e, page, token, stage_id, tabela_amostras_local, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://bioinfo-container:8000/samples/stages/{stage_id}", headers=headers)
        if response.status_code == 200:
            samples = response.json()
            tabela_amostras_local.rows.clear()
            for sample in samples:
                
                async def download_sample_file(e, sample_name=sample["name"]):
                    try:
                        download_url = f"http://localhost:8000/download/obtencao/{sample_name}?token={token}"
                        page.launch_url(download_url)
                        await log_message(page, f"Download iniciado para {sample_name}")
                        
                    except Exception as e:
                        logger.error(f"Erro no download de {sample_name}: {e}")
                        await log_message(page, f"Erro no download de {sample_name}: {str(e)}")
                
                tabela_amostras_local.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(sample["name"] or sample["sra_code"], style=ft.TextStyle(size=12))),
                            ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                            ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                            ft.DataCell(ft.Checkbox()),
                            # Show download button only when sample status is Completed
                            (ft.DataCell(ft.Row([ft.IconButton(icon="download", tooltip="Baixar arquivo da amostra", on_click=download_sample_file)])) if ((sample.get("status") or "").lower() == "completed") else ft.DataCell(ft.Row([]))),
                        ],
                    )
                )
            page.update()
            if stage_id == 2:
                await update_quality_analysis_table(page, token, user_id)
        else:
            logger.error(f"Erro ao atualizar tabela por estágio: {response.status_code} - {response.text}")

async def baixar_amostras(e, page, token, container_menu_direita, tabela_amostras_local):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://bioinfo-container:8000/samples/pending_count", headers=headers)
            if response.status_code == 200:
                pending_count = response.json().get("pending_count", 0)
                if pending_count == 0:
                    logger.info("No pending samples to download.")
                    await log_message(page, "No pending samples to download.")
                    return
                for _ in range(pending_count):
                    response = await client.post("http://bioinfo-container:8000/samples/download", headers=headers)
                    if response.status_code in (200, 202):
                        logger.info("Download enfileirado!")
                        body = response.json()
                        sample_name = body.get("sample_name", "Unknown")
                        job_id = body.get("job_id")
                        await log_message(page, f"Iniciando o download da amostra {sample_name}.")
                        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                        page.update()
                        if job_id:
                            result = await wait_for_job(token, job_id)
                            final_status = result.get("status")
                            await log_message(page, f"Download da amostra {sample_name} finalizado com status {final_status}.")
                            if final_status == "COMPLETED":
                                await atualizar_tamanho_amostras(page, token, sample_name, container_menu_direita)

                        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                        page.update()
                    elif response.status_code == 404:
                        logger.error(f"Download error: {response.status_code} - {response.text}")
                    else:
                        logger.error(f"Download error: {response.status_code} - {response.text}")
            else:
                logger.error(f"Failed to get pending samples count: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
    page.update()

async def atualizar_tamanho_amostras(page, token, sra_code, container_menu_direita):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post("http://bioinfo-container:8000/samples/calculate_size", params={"sra_code": sra_code}, headers=headers)
            if response.status_code == 200:
                logger.info("Tamanho das amostras atualizado com sucesso!")
                await atualizar_tabela(page, token, container_menu_direita, tabela_amostras)
            else:
                logger.error(f"Erro ao atualizar tamanho das amostras: {response.status_code} - {response.text}")
                await log_message(page, f"Erro ao atualizar tamanho das amostras: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        await log_message(page, f"An error occurred: {e}")
