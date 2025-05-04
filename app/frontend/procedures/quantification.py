import flet as ft
import asyncio
import httpx
import logging
from .utils import log_message

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_tabela_quantificacao(page, token):
    """Creates the table for quantification."""
    global tabela_quantificacao

    async def toggle_select_all_quantification(e):
            """Select or deselect all rows in the quantification table."""
            for row in tabela_quantificacao.rows:
                row.cells[4].content.value = e.control.value
            page.update()

    tabela_quantificacao = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text("Log")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_quantification)),  # Checkbox para seleção
        ],
        rows=[],
        column_spacing=15
    )
    return tabela_quantificacao

async def update_tabela_quantificacao(page, token, user_id):
    """Atualiza a tabela de quantificação com dados do backend."""
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            # Obter amostras do estágio 6 (quantificação)
            response = await client.get("http://bioinfo-container:8000/samples/stages/6", headers=headers)
            if response.status_code == 200:
                samples = response.json()
                tabela_quantificacao.rows.clear()
                for sample in samples:
                    def view_log_handler(e, s=sample["name"]):
                        asyncio.run(view_quantification_log(page, token, s, user_id))

                    # Determinar se o botão de log deve estar ativo ou inativo
                    log_button_disabled = sample["status"].lower() != "completed"

                    tabela_quantificacao.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(sample["name"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                                ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                                ft.DataCell(
                                    ft.IconButton(
                                        icon=ft.icons.DESCRIPTION,
                                        tooltip="Visualizar log",
                                        on_click=view_log_handler if not log_button_disabled else None,
                                        disabled=log_button_disabled,  # Habilitar botão se o status for "Completed"
                                    )
                                ),
                                ft.DataCell(ft.Checkbox())
                            ]
                        )
                    )
                page.update()
            else:
                logger.error(f"Erro ao obter dados de quantificação: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Erro ao atualizar a tabela de quantificação: {e}", exc_info=True)

async def view_quantification_log(page, token, sample_name, user_id):
    """Exibe o log de quantificação para uma amostra específica."""
    page.open(ft.SnackBar(ft.Text(f"Exibindo log para {sample_name}")))

async def show_quantification_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    """Exibe o modal de quantificação com a tabela de seleção e o formulário de parâmetros."""
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    samples = []

    # Campos para o usuário inserir os parâmetros -t e -i
    feature_type_field = ft.TextField(
        label="Feature Type (-t)",
        hint_text="Exemplo: CDS, gene, exon",
        border_radius=ft.border_radius.all(4),
        expand=1,
    )

    id_attribute_field = ft.TextField(
        label="ID Attribute (-i)",
        hint_text="Exemplo: ID, Parent, locus_tag",
        border_radius=ft.border_radius.all(4),
        expand=1,
    )

    async def toggle_select_all(e):
        """Select or deselect all rows in the quantification table."""
        for row in tabela_quantificacao_modal.rows:
            row.cells[3].content.value = e.control.value  # Atualizar o valor do checkbox
        page.update()  # Atualizar a página para refletir as mudanças

    tabela_quantificacao_modal = ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all)),  # Checkbox no cabeçalho
        ],
        rows=[],
    )

    try:
        async with httpx.AsyncClient() as client:
            # Obter amostras alinhadas (stage_id=5)
            response_stage_5 = await client.get("http://bioinfo-container:8000/samples/stages/5", headers=headers)
            if response_stage_5.status_code == 200:
                aligned_samples = response_stage_5.json()
                logger.info(f"Amostras alinhadas (stage_id=5): {aligned_samples}")
            else:
                logger.error(f"Erro ao obter amostras alinhadas: {response_stage_5.status_code} - {response_stage_5.text}")
                aligned_samples = []

            # Obter amostras já quantificadas (stage_id=6)
            response_stage_6 = await client.get("http://bioinfo-container:8000/samples/stages/6", headers=headers)
            if response_stage_6.status_code == 200:
                quantified_samples = {sample["sra_code"] for sample in response_stage_6.json()}
                logger.info(f"Amostras quantificadas (stage_id=6): {quantified_samples}")
            else:
                logger.error(f"Erro ao obter amostras quantificadas: {response_stage_6.status_code} - {response_stage_6.text}")
                quantified_samples = set()

            # Filtrar amostras alinhadas que ainda não estão na etapa de quantificação
            samples = [sample for sample in aligned_samples if sample["sra_code"] not in quantified_samples]
            logger.info(f"Amostras disponíveis para quantificação: {samples}")

    except Exception as e:
        logger.error(f"Erro ao buscar amostras para quantificação: {e}", exc_info=True)

    # Atualizar a tabela no modal com as amostras disponíveis
    tabela_quantificacao_modal.rows.clear()
    for sample in samples:
        tabela_quantificacao_modal.rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sample["name"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["size"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Text(sample["status"], style=ft.TextStyle(size=12))),
                    ft.DataCell(ft.Checkbox()),  # Checkbox individual para cada linha
                ]
            )
        )

    # Função para iniciar a quantificação
    async def start_quantification(e):
        """Inicia a quantificação: adiciona as amostras à fila e processa uma por uma."""
        selected_samples = [row.cells[0].content.value for row in tabela_quantificacao_modal.rows if row.cells[3].content.value]
        if not selected_samples:
            logger.error("Nenhuma amostra selecionada para quantificação.")
            return

        await log_message(page, f"Adicionando amostras à fila: {selected_samples}")
        dlg_modal_quantificacao.open = False
        page.update()

        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            # Adicionar amostras à fila
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "http://bioinfo-container:8000/quantification/add_to_queue",
                    json={"samples": selected_samples},
                    headers=headers,
                )
                if response.status_code == 200:
                    logger.info("Amostras adicionadas à fila com sucesso")
                    await update_tabela_quantificacao(page, token, user_id)
                    page.update()
                else:
                    logger.error(f"Erro ao adicionar amostras à fila: {response.status_code} - {response.text}")
                    await log_message(page, f"Erro ao adicionar amostras à fila: {response.text}")
                    return

                # Processar amostras uma por uma
                for sample in selected_samples:
                    # Atualizar status para "Counting" no frontend
                    sample_txt = sample.replace(".bam", ".txt")  # Ajustar para buscar a amostra com extensão .txt
                    for row in tabela_quantificacao.rows:
                        if row.cells[0].content.value == sample_txt:
                            row.cells[2].content.value = "Counting"
                            page.update()
                            break

                    async with httpx.AsyncClient(timeout=300.0) as client:  # Aumentar o tempo limite para evitar ReadTimeout
                        response = await client.post(
                            "http://bioinfo-container:8000/quantification/start_processing",
                            json={"samples": [sample]},
                            headers=headers,
                        )
                        if response.status_code == 200:
                            # Calcular o tamanho do arquivo .txt
                            size_response = await client.post(
                                "http://bioinfo-container:8000/quantification/update_status",
                                data={"sample_name": sample_txt.replace(".txt", ""), "status": "Completed"},
                                headers=headers,
                            )
                            if size_response.status_code == 200:
                                size_data = size_response.json()
                                logger.info(f"Tamanho do arquivo atualizado: {size_data['size']} KB para {sample_txt}")
                            else:
                                logger.error(f"Erro ao calcular tamanho do arquivo para {sample_txt}: {size_response.status_code} - {size_response.text}")

                            logger.info(f"Processamento concluído para {sample}")
                            await update_tabela_quantificacao(page, token, user_id)
                            await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                            page.update()
                        else:
                            logger.error(f"Erro ao processar {sample}: {response.status_code} - {response.text}")
                            await log_message(page, f"Erro ao processar {sample}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Erro ao iniciar quantificação: {e}", exc_info=True)

    # Modal de quantificação
    dlg_modal_quantificacao = ft.AlertDialog(
        title=ft.Text("Iniciar Quantificação"),
        content=ft.Container(
            content=ft.ListView(
                controls=[
                    tabela_quantificacao_modal,
                    ft.Row(
                        controls=[
                            feature_type_field,
                            id_attribute_field,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
            ),
            width=600,
        ),
        actions=[
            ft.TextButton(
                "Iniciar Quantificação",
                on_click=start_quantification,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_quantificacao)

async def excluir_quantificacao(page, token, user_id, selected_samples, container_menu_direita, tabela_amostras_local, atualizar_tabela):
    """Exclui as amostras de quantificação selecionadas após confirmação."""
    async def confirm_delete(e):
        if confirmation_field.value.strip().lower() != "confirmar":
            await log_message(page, "Confirmação inválida. Digite 'Confirmar' para prosseguir.")
            return

        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://bioinfo-container:8000/quantification/delete",
                    json=selected_samples,  # Enviar a lista diretamente
                    headers=headers,
                )
                if response.status_code == 200:
                    logger.info(f"Amostras excluídas com sucesso: {selected_samples}")
                    await log_message(page, f"Amostras excluídas com sucesso: {selected_samples}")
                    await update_tabela_quantificacao(page, token, user_id)
                    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                else:
                    logger.error(f"Erro ao excluir amostras: {response.status_code} - {response.text}")
                    await log_message(page, f"Erro ao excluir amostras: {response.text}")
        except Exception as ex:
            logger.error(f"Erro ao excluir amostras: {ex}", exc_info=True)
            await log_message(page, "Erro ao excluir amostras.")
        dlg_modal_excluir_quantificacao.open = False
        page.update()

    # Modal de confirmação
    confirmation_field = ft.TextField(
        hint_text="Digite 'Confirmar' para excluir as amostras selecionadas.",
        border_radius=ft.border_radius.all(4),
        multiline=False,
        expand=1,
    )
    dlg_modal_excluir_quantificacao = ft.AlertDialog(
        title=ft.Text("Confirmar Exclusão"),
        content=confirmation_field,
        actions=[
            ft.TextButton(
                "Excluir",
                on_click=confirm_delete,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_excluir_quantificacao)
