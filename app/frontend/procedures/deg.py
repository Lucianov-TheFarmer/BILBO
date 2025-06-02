import flet as ft
import httpx
import asyncio
import logging
from .utils import log_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_existing_contrasts(token):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/contrasts/", headers=headers)
        response.raise_for_status()
        return response.json()

def parse_contrast_name(name):
    try:
        left, right = name.split("*")
        group_1 = left.split("(")[0].strip()
        group_2 = right.split("(")[0].strip()
        return f"{group_1} x {group_2}"
    except Exception:
        return name

async def run_deg_analysis(page, token, user_id):
    await log_message(page, "Selecione os contrastes para DEG.")
    contrasts = await fetch_existing_contrasts(token)
    selected_ids = set()
    checkboxes = []

    def on_select_all_change(e):
        checked = e.control.value
        for cb in checkboxes:
            cb.value = checked
            if checked:
                selected_ids.add(cb.data)
            else:
                selected_ids.discard(cb.data)
        page.update()

    def on_checkbox_change(e, contrast_id):
        if e.control.value:
            selected_ids.add(contrast_id)
        else:
            selected_ids.discard(contrast_id)
        all_checked = len(selected_ids) == len(checkboxes) and len(checkboxes) > 0
        select_all_checkbox.value = all_checked
        page.update()

    select_all_checkbox = ft.Checkbox(value=False, on_change=on_select_all_change)

    data_rows = []
    for contrast in contrasts:
        label = parse_contrast_name(contrast["name"])
        cb = ft.Checkbox(value=False, on_change=lambda e, cid=contrast["id"]: on_checkbox_change(e, cid), data=contrast["id"])
        checkboxes.append(cb)
        data_rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(label)),
                    ft.DataCell(cb),
                ]
            )
        )

    async def iniciar_deg(e):
        if not selected_ids:
            await log_message(page, "Selecione pelo menos um contraste para DEG!")
            return
        # Loga os contrastes selecionados
        selected_labels = [parse_contrast_name(c["name"]) for c in contrasts if c["id"] in selected_ids]
        await log_message(page, "Iniciando DEG")
        await log_message(page, f"Contrastes selecionados para DEG: {', '.join(selected_labels)}")
        dlg_modal_deg.open = False
        page.update()
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/deg/run",
                    json={"user_id": user_id, "contrast_ids": list(selected_ids)},
                    headers=headers,
                    timeout=600,
                )
                if response.status_code == 200:
                    await log_message(page, "Análise DEG concluída! O arquivo DEG.xlsx foi gerado.")
                else:
                    await log_message(page, f"Erro na análise DEG: {response.text}")
        except Exception as ex:
            logger.error(f"Erro ao executar DEG: {ex}")
            await log_message(page, f"Erro ao executar DEG: {ex}")

    dlg_modal_deg = ft.AlertDialog(
        title=ft.Text("Análise DEG"),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    ft.DataTable(
                        columns=[
                            ft.DataColumn(ft.Text("Contraste")),
                            ft.DataColumn(select_all_checkbox),
                        ],
                        rows=data_rows,
                        heading_row_height=40,
                        column_spacing=20,
                    )
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            width=400,
            height=400,
        ),
        actions=[
            ft.TextButton(
                "Iniciar DEG",
                on_click=lambda e: asyncio.run(iniciar_deg(e)),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_deg)
