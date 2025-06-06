import flet as ft
import httpx
import asyncio

async def fetch_deg_sheets(token, user_id):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    params = {"user_id": user_id}
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/results/deg_sheets", headers=headers, params=params)
        response.raise_for_status()
        return response.json().get("sheets", [])

async def fetch_barplot_files(token, user_id):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/results/barplot_files",
            params={"user_id": user_id},
            headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
        )
        response.raise_for_status()
        return response.json().get("files", [])

async def create_barplot_file(token, user_id, title, contrasts):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/results/create_barplot_file",
            json={"user_id": user_id, "title": title, "contrasts": contrasts},
            headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
        )
        response.raise_for_status()
        return response.json()

async def show_barplots_table(page, token, user_id, container_amostras):
    files = await fetch_barplot_files(token, user_id)
    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Barplots salvos")),
        ],
        rows=[
            ft.DataRow([ft.DataCell(ft.Text(f))]) for f in files
        ],
        expand=True,
    )
    btn = ft.ElevatedButton(
        "Gerar novo barplot",
        icon=ft.icons.ADD,
        on_click=lambda e: asyncio.run(show_barplots_modal(page, token, user_id, container_amostras)),
    )
    container_amostras.content.controls = [table, btn]
    page.update()

async def show_deg_modal(page, token, user_id, title, max_select=None, show_select_all=False, on_confirm=None):
    sheets = await fetch_deg_sheets(token, user_id)
    selected = set()
    checkboxes = []
    title_field = ft.TextField(label="Título do Barplot", width=350)
    divider = ft.Divider(height=1, thickness=1, color=ft.colors.BLACK)

    def on_select_all_change(e):
        checked = e.control.value
        for cb in checkboxes:
            cb.value = checked
            if checked:
                selected.add(cb.data)
            else:
                selected.discard(cb.data)
        page.update()

    def on_checkbox_change(e, sheet):
        if e.control.value:
            if max_select is not None and len(selected) >= max_select:
                e.control.value = False
                page.update()
                return
            selected.add(sheet)
        else:
            selected.discard(sheet)
        if show_select_all and select_all_checkbox is not None:
            all_checked = len(selected) == len(checkboxes) and len(checkboxes) > 0
            select_all_checkbox.value = all_checked
        page.update()

    select_all_checkbox = ft.Checkbox(value=False, on_change=on_select_all_change) if show_select_all else None

    data_rows = []
    for sheet in sheets:
        cb = ft.Checkbox(
            value=False,
            on_change=lambda e, s=sheet: on_checkbox_change(e, s),
            data=sheet
        )
        checkboxes.append(cb)
        data_rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(sheet)),
                    ft.DataCell(cb),
                ]
            )
        )

    columns = [
        ft.DataColumn(ft.Text("Aba")),
        ft.DataColumn(select_all_checkbox if show_select_all else ft.Text("Selecionar")),
    ]

    dlg_modal = ft.AlertDialog(
        title=ft.Text(title),
        content=ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(height=5),
                    title_field,
                    divider,
                    ft.DataTable(
                        columns=columns,
                        rows=data_rows,
                        heading_row_height=40,
                        column_spacing=20,
                        expand=True,
                    )
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            # width=400,
            height=400,
        ),
        actions=[
            ft.TextButton(
                "Confirmar",
                # Use asyncio.run para garantir execução correta no handler do Flet
                on_click=lambda e: asyncio.run(on_confirm(title_field.value, list(selected), dlg_modal)),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal)

async def show_barplots_modal(page, token, user_id, container_amostras):
    async def on_confirm(title, contrasts, dlg_modal):
        if not title.strip():
            dlg_modal.title = ft.Text("Título obrigatório!", color=ft.colors.RED)
            page.update()
            return
        await create_barplot_file(token, user_id, title, contrasts)
        dlg_modal.open = False
        page.update()
        await show_barplots_table(page, token, user_id, container_amostras)

    await show_deg_modal(
        page,
        token,
        user_id,
        "Barplots",
        max_select=None,
        show_select_all=True,
        on_confirm=on_confirm,
    )

async def show_venn_modal(page, token, user_id):
    await show_deg_modal(page, token, user_id, "Diagrama de Venn (Max: 4)", max_select=4, show_select_all=False)

async def show_heatmap_modal(page, token, user_id):
    await show_deg_modal(page, token, user_id, "Heatmap", max_select=None, show_select_all=True)
