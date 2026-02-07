import flet as ft
import asyncio
import httpx
import logging
from .utils import log_message
from .viewer import view_quantification_log

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
        heading_row_color="primary",
        columns=[
            ft.DataColumn(ft.Text("Identificação", weight="bold")),
            ft.DataColumn(ft.Text("Tamanho", weight="bold")),
            ft.DataColumn(ft.Text("Status", weight="bold")),
            ft.DataColumn(ft.Text("Log", weight="bold")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_quantification)),
        ],
        rows=[],
        column_spacing=15
    )
    return tabela_quantificacao

async def update_tabela_quantificacao(page, token, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://bioinfo-container:8000/samples/stages/6", headers=headers)
            if response.status_code == 200:
                samples = response.json()
                tabela_quantificacao.rows.clear()
                for sample in samples:
                    def view_log_handler(e, s=sample["name"]):
                        try:
                            asyncio.get_event_loop().create_task(view_quantification_log_handler(page, token, s, user_id))
                        except RuntimeError:
                            # Fallback if no running loop: run in a new loop
                            asyncio.run(view_quantification_log_handler(page, token, s, user_id))

                    log_button_disabled = sample["status"].lower() != "completed"

                    tabela_quantificacao.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(sample["name"], size=12)),
                                ft.DataCell(ft.Text(sample["size"], size=12)),
                                ft.DataCell(ft.Text(sample["status"], size=12)),
                                ft.DataCell(
                                    ft.IconButton(
                                        icon="description",
                                        tooltip="Visualizar log",
                                        on_click=view_log_handler if not log_button_disabled else None,
                                        disabled=log_button_disabled,
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

async def view_quantification_log_handler(page, token, sample_name, user_id):
    await view_quantification_log(page, token, sample_name, user_id)

async def show_quantification_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    samples = []

    feature_type_field = ft.TextField(
        label="Feature Type (-t)",
        hint_text="Exemplo: CDS, gene, exon",
        border_radius=4,
        expand=1,
    )

    id_attribute_field = ft.TextField(
        label="ID Attribute (-i)",
        hint_text="Exemplo: ID, Parent, locus_tag",
        border_radius=4,
        expand=1,
    )

    async def toggle_select_all(e):
        """Select or deselect all rows in the quantification table."""
        for row in tabela_quantificacao_modal.rows:
            row.cells[3].content.value = e.control.value
        page.update()

    tabela_quantificacao_modal = ft.DataTable(
        heading_row_color="black12",
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all)),
        ],
        rows=[],
    )

    try:
        async with httpx.AsyncClient() as client:
            response_stage_5 = await client.get("http://bioinfo-container:8000/samples/stages/5", headers=headers)
            if response_stage_5.status_code == 200:
                aligned_samples = response_stage_5.json()
            else:
                aligned_samples = []

            response_stage_6 = await client.get("http://bioinfo-container:8000/samples/stages/6", headers=headers)
            if response_stage_6.status_code == 200:
                quantified_samples = {sample["sra_code"] for sample in response_stage_6.json()}
            else:
                quantified_samples = set()

            samples = [sample for sample in aligned_samples if sample["sra_code"] not in quantified_samples]

    except Exception as e:
        logger.error(f"Erro ao buscar amostras para quantificação: {e}", exc_info=True)

    tabela_quantificacao_modal.rows.clear()
    for sample in samples:
        tabela_quantificacao_modal.rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sample["name"], size=12)),
                    ft.DataCell(ft.Text(sample["size"], size=12)),
                    ft.DataCell(ft.Text(sample["status"], size=12)),
                    ft.DataCell(ft.Checkbox()),
                ]
            )
        )

    async def start_quantification(e):
        selected_samples = [row.cells[0].content.value for row in tabela_quantificacao_modal.rows if row.cells[3].content.value]
        if not selected_samples:
            log_message(page, "Nenhuma amostra selecionada para quantificação.")
            return

        feature_type = feature_type_field.value.strip()
        id_attribute = id_attribute_field.value.strip()

        if not feature_type or not id_attribute:
            await log_message(page, "Os campos 'Feature Type' e 'ID Attribute' são obrigatórios.")
            return

        await log_message(page, f"Adicionando amostras à fila: {selected_samples}")
        dlg_modal_quantificacao.open = False
        page.update()

        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "http://bioinfo-container:8000/quantification/add_to_queue",
                    json={"samples": selected_samples, "feature_type": feature_type, "id_attribute": id_attribute},
                    headers=headers,
                )
                if response.status_code == 200:
                    await update_tabela_quantificacao(page, token, user_id)
                    page.update()
                else:
                    await log_message(page, f"Erro ao adicionar amostras à fila: {response.text}")
                    return

                for sample in selected_samples:
                    sample_txt = sample.replace(".bam", ".txt")
                    for row in tabela_quantificacao.rows:
                        if row.cells[0].content.value == sample_txt:
                            row.cells[2].content.value = "Counting"
                            page.update()
                            break

                    async with httpx.AsyncClient(timeout=300.0) as client:
                        response = await client.post(
                            "http://bioinfo-container:8000/quantification/start_processing",
                            json={"samples": [sample], "feature_type": feature_type, "id_attribute": id_attribute},
                            headers=headers,
                        )
                        if response.status_code == 200:
                            size_response = await client.post(
                                "http://bioinfo-container:8000/quantification/update_status",
                                data={"sample_name": sample_txt.replace(".txt", ""), "status": "Completed"},
                                headers=headers,
                            )
                            if size_response.status_code != 200:
                                logger.error(f"Erro ao calcular tamanho do arquivo para {sample_txt}: {size_response.status_code} - {size_response.text}")

                            await log_message(page, f"Quantificação concluída para {sample}")
                            await update_tabela_quantificacao(page, token, user_id)
                            await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                            page.update()
                        else:
                            await log_message(page, f"Erro ao processar {sample}: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Erro ao iniciar quantificação: {e}", exc_info=True)

    dlg_modal_quantificacao = ft.AlertDialog(
        title=ft.Text("Iniciar Quantificação"),
        content=ft.Container(
            content=ft.ListView(
                controls=[
                    tabela_quantificacao_modal,
                    ft.Container(height=10),
                    ft.Divider(height=1, thickness=1, color="black38"),
                    ft.Container(height=10),
                    ft.Row(
                        controls=[
                            feature_type_field,
                            id_attribute_field,
                        ],
                        alignment="space_between",
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
        actions_alignment="center",
    )

    page.open(dlg_modal_quantificacao)

async def excluir_quantificacao(page, token, user_id, selected_samples, container_menu_direita, tabela_amostras_local, atualizar_tabela):
    async def confirm_delete(e):
        if confirmation_field.value.strip().lower() != "confirmar":
            await log_message(page, "Confirmação inválida. Digite 'Confirmar' para prosseguir.")
            return

        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://bioinfo-container:8000/quantification/delete",
                    json=selected_samples,
                    headers=headers,
                )
                if response.status_code == 200:
                    await log_message(page, f"Amostras excluídas com sucesso: {selected_samples}")
                    await update_tabela_quantificacao(page, token, user_id)
                    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                else:
                    await log_message(page, f"Erro ao excluir amostras: {response.text}")
        except Exception as ex:
            await log_message(page, "Erro ao excluir amostras.")
        dlg_modal_excluir_quantificacao.open = False
        page.update()

    confirmation_field = ft.TextField(
        hint_text="Digite 'Confirmar' para excluir as amostras selecionadas.",
        border_radius=4,
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
        actions_alignment="center",
    )

    page.open(dlg_modal_excluir_quantificacao)