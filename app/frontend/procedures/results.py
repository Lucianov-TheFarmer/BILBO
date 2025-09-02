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

async def delete_barplot_file(token, user_id, filename):
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            "http://localhost:8000/results/delete_barplot_file",
            json={"user_id": user_id, "filename": filename},
            headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
        )
        response.raise_for_status()
        return response.json()

async def view_barplot_file(token, user_id, filename):
    # Para arquivos .png, retornamos apenas o caminho para visualização
    return {"filename": filename}

async def fetch_venn_files(token, user_id):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/results/venn_files",
            params={"user_id": user_id},
            headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
        )
        response.raise_for_status()
        return response.json().get("files", [])

async def create_venn_file(token, user_id, title, contrasts):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/results/create_venn_file",
            json={"user_id": user_id, "title": title, "contrasts": contrasts},
            headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
        )
        response.raise_for_status()
        return response.json()

async def fetch_heatmap_files(token, user_id):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/results/heatmap_files",
            params={"user_id": user_id},
            headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
        )
        response.raise_for_status()
        return response.json().get("files", [])

async def create_heatmap_file(token, user_id, title, contrasts):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/results/create_heatmap_file",
            json={"user_id": user_id, "title": title, "contrasts": contrasts},
            headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
        )
        response.raise_for_status()
        return response.json()

async def show_barplots_table(page, token, user_id, container_amostras):
    files = await fetch_barplot_files(token, user_id)
    
    async def on_view_click(filename):
        try:
            # Visualizar imagem do barplot
            deg_dir = f"../users/{user_id}/DEG"
            img_path = f"{deg_dir}/{filename}"
            
            # Carregar e mostrar a imagem
            import os
            abs_img_path = os.path.abspath(os.path.join(os.path.dirname(__file__), img_path))
            
            if os.path.exists(abs_img_path):
                import base64
                try:
                    with open(abs_img_path, "rb") as f:
                        img_data = f.read()
                    img_base64 = base64.b64encode(img_data).decode("utf-8")
                    
                    image_control = ft.Image(src_base64=img_base64)
                    interactive_viewer = ft.InteractiveViewer(
                        min_scale=0.5,
                        max_scale=15,
                        boundary_margin=ft.margin.all(10),
                        content=image_control,
                        constrained=True
                    )
                    
                    dlg_modal = ft.AlertDialog(
                        title=ft.Text(f"Visualizar: {filename}"),
                        content=ft.Container(
                            content=interactive_viewer,
                            height=600,
                            width=800,
                        ),
                        actions=[
                            ft.TextButton(
                                "Fechar",
                                on_click=lambda e: (setattr(dlg_modal, 'open', False), page.update()),
                            ),
                        ],
                        actions_alignment=ft.MainAxisAlignment.CENTER,
                    )
                    page.open(dlg_modal)
                except Exception as e:
                    error_dlg = ft.AlertDialog(
                        title=ft.Text("Erro"),
                        content=ft.Text(f"Erro ao carregar imagem: {e}"),
                        actions=[ft.TextButton("OK", on_click=lambda e: (setattr(error_dlg, 'open', False), page.update()))],
                    )
                    page.open(error_dlg)
            else:
                error_dlg = ft.AlertDialog(
                    title=ft.Text("Erro"),
                    content=ft.Text(f"Imagem não encontrada: {filename}"),
                    actions=[ft.TextButton("OK", on_click=lambda e: (setattr(error_dlg, 'open', False), page.update()))],
                )
                page.open(error_dlg)
        except Exception as e:
            print(f"Erro ao visualizar arquivo: {e}")

    async def on_delete_click(filename):
        async def confirm_delete(e):
            try:
                await delete_barplot_file(token, user_id, filename)
                confirm_dlg.open = False
                page.update()
                await show_barplots_table(page, token, user_id, container_amostras)
            except Exception as error:
                print(f"Erro ao deletar arquivo: {error}")

        confirm_dlg = ft.AlertDialog(
            title=ft.Text("Confirmar exclusão"),
            content=ft.Text(f"Deseja realmente excluir o arquivo '{filename}'?"),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: (setattr(confirm_dlg, 'open', False), page.update())),
                ft.TextButton("Excluir", on_click=lambda e: asyncio.run(confirm_delete(e))),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        page.open(confirm_dlg)

    rows = []
    for filename in files:
        rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(filename, width=270)),
                    ft.DataCell(
                        ft.Row(
                            controls=[
                                ft.IconButton(
                                    icon=ft.icons.VISIBILITY,
                                    tooltip="Visualizar",
                                    on_click=lambda e, f=filename: asyncio.run(on_view_click(f)),
                                ),
                                ft.IconButton(
                                    icon=ft.icons.DELETE,
                                    tooltip="Excluir",
                                    icon_color=ft.colors.RED,
                                    on_click=lambda e, f=filename: asyncio.run(on_delete_click(f)),
                                ),
                            ],
                            spacing=5,
                        )
                    ),
                ]
            )
        )

    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Barplots salvos", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("")),
        ],
        rows=rows,
        heading_row_color=ft.Colors.BLACK12,
        expand=True,
    )
    btn = ft.ElevatedButton(
        "Gerar novo barplot",
        icon=ft.icons.ADD,
        on_click=lambda e: asyncio.run(show_barplots_modal(page, token, user_id, container_amostras)),
    )
    container_amostras.content.controls = [table, btn]
    page.update()

async def show_venn_table(page, token, user_id, container_amostras):
    files = await fetch_venn_files(token, user_id)
    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Diagramas de Venn salvos")),
        ],
        rows=[
            ft.DataRow([ft.DataCell(ft.Text(f))]) for f in files
        ],
        expand=True,
    )
    btn = ft.ElevatedButton(
        "Gerar novo diagrama de Venn",
        icon=ft.icons.ADD,
        on_click=lambda e: asyncio.run(show_venn_modal(page, token, user_id, container_amostras)),
    )
    container_amostras.content.controls = [table, btn]
    page.update()

async def show_heatmap_table(page, token, user_id, container_amostras):
    files = await fetch_heatmap_files(token, user_id)
    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Heatmaps salvos")),
        ],
        rows=[
            ft.DataRow([ft.DataCell(ft.Text(f))]) for f in files
        ],
        expand=True,
    )
    btn = ft.ElevatedButton(
        "Gerar novo heatmap",
        icon=ft.icons.ADD,
        on_click=lambda e: asyncio.run(show_heatmap_modal(page, token, user_id, container_amostras)),
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

async def show_venn_modal(page, token, user_id, container_amostras):
    sheets = await fetch_deg_sheets(token, user_id)
    selected = set()
    checkboxes = []
    title_field = ft.TextField(label="Título do Diagrama de Venn", width=350)
    divider = ft.Divider(height=1, thickness=1, color=ft.colors.BLACK)

    def on_checkbox_change(e, sheet):
        if e.control.value:
            if len(selected) >= 4:  # Max 4 para Venn
                e.control.value = False
                page.update()
                return
            selected.add(sheet)
        else:
            selected.discard(sheet)
        page.update()

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
        ft.DataColumn(ft.Text("Selecionar")),
    ]

    async def on_confirm(e):
        if not title_field.value.strip():
            dlg_modal.title = ft.Text("Título obrigatório!", color=ft.colors.RED)
            page.update()
            return
        await create_venn_file(token, user_id, title_field.value, list(selected))
        dlg_modal.open = False
        page.update()
        await show_venn_table(page, token, user_id, container_amostras)

    dlg_modal = ft.AlertDialog(
        title=ft.Text("Diagrama de Venn (Max: 4)"),
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
            height=400,
        ),
        actions=[
            ft.TextButton(
                "Confirmar",
                on_click=lambda e: asyncio.run(on_confirm(e)),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal)

async def show_heatmap_modal(page, token, user_id, container_amostras):
    sheets = await fetch_deg_sheets(token, user_id)
    selected = set()
    checkboxes = []
    title_field = ft.TextField(label="Título do Heatmap", width=350)
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
            selected.add(sheet)
        else:
            selected.discard(sheet)
        if select_all_checkbox is not None:
            all_checked = len(selected) == len(checkboxes) and len(checkboxes) > 0
            select_all_checkbox.value = all_checked
        page.update()

    select_all_checkbox = ft.Checkbox(value=False, on_change=on_select_all_change)

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
        ft.DataColumn(select_all_checkbox),
    ]

    async def on_confirm(e):
        if not title_field.value.strip():
            dlg_modal.title = ft.Text("Título obrigatório!", color=ft.colors.RED)
            page.update()
            return
        await create_heatmap_file(token, user_id, title_field.value, list(selected))
        dlg_modal.open = False
        page.update()
        await show_heatmap_table(page, token, user_id, container_amostras)

    dlg_modal = ft.AlertDialog(
        title=ft.Text("Heatmap"),
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
            height=400,
        ),
        actions=[
            ft.TextButton(
                "Confirmar",
                on_click=lambda e: asyncio.run(on_confirm(e)),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal)
