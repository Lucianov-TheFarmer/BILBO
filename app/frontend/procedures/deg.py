import flet as ft
import httpx
import asyncio
import logging
import pandas as pd
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
                        expand=True,  # expandir horizontalmente
                    )
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            # width=400,
            height=400,
            expand=True,  # expandir o container para ocupar todo o modal
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

async def fetch_sheet_data(token, user_id, sheet_name):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    params = {"user_id": user_id, "sheet": sheet_name}
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/deg/sheet_data", headers=headers, params=params)
        response.raise_for_status()
        return response.json()  # {"columns": [...], "rows": [[...], ...]}

async def show_sheet_as_table(page, token, user_id, sheet_name):
    print(f"[LOG] show_sheet_as_table: sheet_name={sheet_name}")
    try:
        data = await fetch_sheet_data(token, user_id, sheet_name)
        columns = data.get("columns", [])
        rows = data.get("rows", [])
        print(f"[LOG] Columns: {columns}")
        print(f"[LOG] Number of rows: {len(rows)}")

        if not columns or not rows:
            await log_message(page, "Aba sem colunas ou dados.")
            # Atualiza o container_pre_visualizacao com mensagem amigável
            for control in page.controls:
                if isinstance(control, ft.Row):
                    for column in control.controls:
                        if isinstance(column, ft.Column):
                            for container in column.controls:
                                if (
                                    isinstance(container, ft.Container)
                                    and container.expand == 2
                                    and isinstance(container.content, ft.Column)
                                ):
                                    container.content.controls = [
                                        ft.Container(
                                            expand=True,
                                            content=ft.Text(
                                                "Nenhum dado disponível nesta aba.",
                                                color=ft.colors.RED,
                                                size=16,
                                                weight=ft.FontWeight.BOLD,
                                                text_align=ft.TextAlign.CENTER,
                                            ),
                                            alignment=ft.alignment.center,
                                            padding=ft.padding.all(10),
                                        )
                                    ]
                                    page.update()
                                    return
            return

        columns = [" " if str(col).startswith("Unnamed") else str(col) for col in columns]
        all_rows = rows.copy()
        dt_ref = ft.Ref[ft.DataTable]()
        search_ref = ft.Ref[ft.TextField]()
        notfound_ref = ft.Ref[ft.Text]()

        sort_state = {"logFC": 0}

        def format_cell(cell, col_idx):
            if col_idx == 0:
                return ft.Text(
                    str(cell),
                    selectable=True,
                    size=14,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    max_lines=1,
                )
            try:
                val = float(cell)
                return ft.Text(f"{val:.3f}", selectable=True, size=14)
            except Exception:
                return ft.Text(str(cell), selectable=True, size=14)

        def filter_rows(e=None, sorted_rows=None):
            search_value = search_ref.current.value.strip().lower()
            dt = dt_ref.current
            dt.rows.clear()
            filtered = []
            base_rows = sorted_rows if sorted_rows is not None else all_rows
            if search_value:
                filtered = [row for row in base_rows if search_value in str(row[0]).lower()]
            else:
                filtered = base_rows
            if not filtered:
                notfound_ref.current.visible = True
            else:
                notfound_ref.current.visible = False
                for row in filtered:
                    dt.rows.append(
                        ft.DataRow(
                            [ft.DataCell(format_cell(cell, col_idx)) for col_idx, cell in enumerate(row)]
                        )
                    )
            page.update()

        def sort_logfc(e=None):
            idx_logfc = 1
            current = sort_state["logFC"]
            if current == 0:
                sort_state["logFC"] = 1
            elif current == 1:
                sort_state["logFC"] = -1
            else:
                sort_state["logFC"] = 0

            if sort_state["logFC"] == 0:
                filter_rows()
            else:
                reverse = sort_state["logFC"] == -1
                try:
                    sorted_rows = sorted(
                        all_rows,
                        key=lambda row: float(row[idx_logfc]) if str(row[idx_logfc]).replace('.', '', 1).replace('-', '', 1).isdigit() else float('-inf'),
                        reverse=reverse
                    )
                except Exception:
                    sorted_rows = all_rows
                filter_rows(sorted_rows=sorted_rows)
            update_table()

        # Search bar as header for first column, agora dentro de um container com largura fixa
        search_bar = ft.Container(
            width=150,
            content=ft.TextField(
                ref=search_ref,
                label="Buscar gene",
                tooltip="Digite o nome do gene",
                value="",
                on_change=filter_rows,
                border=ft.InputBorder.OUTLINE,
                dense=True,
                filled=True,
            )
        )

        # Header da coluna logFC com botão de ordenação e ícone dinâmico, tudo em um container
        def logfc_header():
            icon = ft.icons.UNFOLD_MORE
            if sort_state["logFC"] == 1:
                icon = ft.icons.ARROW_UPWARD
            elif sort_state["logFC"] == -1:
                icon = ft.icons.ARROW_DOWNWARD
            return ft.Container(
                content=ft.Row(
                    spacing=2,
                    controls=[
                        ft.Text("logFC", weight=ft.FontWeight.BOLD, size=14),
                        ft.IconButton(
                            icon=icon,
                            icon_size=16,
                            tooltip="Ordenar logFC",
                            on_click=sort_logfc,
                            visual_density=ft.VisualDensity.COMPACT,
                            style=ft.ButtonStyle(
                                padding=0,
                                bgcolor=ft.colors.TRANSPARENT,
                                shape=ft.RoundedRectangleBorder(radius=4),
                            ),
                        ),
                    ],
                ),
                alignment=ft.alignment.center_left,
            )

        def update_table():
            table_columns = [
                ft.DataColumn(search_bar)
            ]
            if len(columns) > 1:
                table_columns.append(
                    ft.DataColumn(
                        logfc_header()
                    )
                )
                table_columns += [
                    ft.DataColumn(
                        ft.Text(str(col), weight=ft.FontWeight.BOLD, size=14)
                    ) for col in columns[2:]
                ]
            else:
                table_columns += [
                    ft.DataColumn(
                        ft.Text(str(col), weight=ft.FontWeight.BOLD, size=14)
                    ) for col in columns[1:]
                ]

            dt = dt_ref.current
            dt.columns = table_columns
            page.update()

        # Inicialmente monta os headers
        table_columns = [
            ft.DataColumn(search_bar)
        ]
        if len(columns) > 1:
            table_columns.append(
                ft.DataColumn(
                    logfc_header()
                )
            )
            table_columns += [
                ft.DataColumn(
                    ft.Text(str(col), weight=ft.FontWeight.BOLD, size=14)
                ) for col in columns[2:]
            ]
        else:
            table_columns += [
                ft.DataColumn(
                    ft.Text(str(col), weight=ft.FontWeight.BOLD, size=14)
                ) for col in columns[1:]
            ]

        excel_table = ft.DataTable(
            ref=dt_ref,
            columns=table_columns,
            rows=[
                ft.DataRow(
                    [ft.DataCell(format_cell(cell, col_idx)) for col_idx, cell in enumerate(row)]
                ) for row in rows
            ],
            column_spacing=8,
            divider_thickness=1,
            show_checkbox_column=False,
            expand=True,
            heading_row_color=ft.colors.BLACK12,
        )

        notfound_text = ft.Text(
            "Nenhum gene encontrado.",
            ref=notfound_ref,
            visible=False,
            color=ft.colors.RED,
            size=16,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )

        # Atualiza o container_pre_visualizacao para preencher toda a área disponível e permitir rolagem vertical
        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if (
                                isinstance(container, ft.Container)
                                and container.expand == 2
                                and isinstance(container.content, ft.Column)
                            ):
                                print("[LOG] Atualizando container_pre_visualizacao com tabela Excel")
                                container.content.controls = [
                                    ft.Container(
                                        expand=True,
                                        content=ft.ListView(
                                            controls=[excel_table, notfound_text],
                                            spacing=0,
                                            expand=True,
                                            auto_scroll=False,
                                            horizontal=False,
                                        ),
                                    )
                                ]
                                page.update()
                                return
        print("[LOG] container_pre_visualizacao não encontrado")
    except Exception as ex:
        print(f"[LOG] Erro ao exibir planilha: {ex}")
        await log_message(page, f"Erro ao exibir planilha: {ex}")

async def show_deg_results(page, token, user_id, container_amostras):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    params = {"user_id": user_id}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/deg/sheets", headers=headers, params=params)
            if response.status_code == 200:
                sheets = response.json().get("sheets", [])
                if not sheets:
                    await log_message(page, "Nenhuma aba encontrada em DEG.xlsx.")
                else:
                    table = ft.DataTable(
                        columns=[
                            ft.DataColumn(
                                ft.Text("Abas do DEG.xlsx", weight=ft.FontWeight.BOLD),
                            ),
                            ft.DataColumn(ft.Text(""))
                        ],
                        heading_row_color=ft.Colors.BLACK12,
                        rows=[
                            ft.DataRow(
                                cells=[
                                    ft.DataCell(
                                        ft.Container(
                                            content=ft.Text(sheet, text_align=ft.TextAlign.CENTER),
                                            width=270,
                                            alignment=ft.alignment.center_left
                                        )
                                    ),
                                    ft.DataCell(
                                        ft.Container(
                                            content=ft.Row(
                                                controls=[
                                                    ft.IconButton(
                                                        icon=ft.icons.TABLE_CHART,
                                                        icon_color=ft.colors.GREEN,
                                                        tooltip="Abrir planilha",
                                                        on_click=lambda e, s=sheet: asyncio.run(
                                                            show_sheet_as_table(page, token, user_id, s)
                                                        )
                                                    ),
                                                    ft.IconButton(
                                                        icon=ft.icons.VISIBILITY,
                                                        tooltip="Visualizar",
                                                        on_click=lambda e, s=sheet: print(f"Clicou no ícone de visualização para {s}")
                                                    ),
                                                ],
                                                spacing=5,
                                            ),
                                            alignment=ft.alignment.center_right,
                                        )
                                    ),
                                ]
                            ) for sheet in sheets
                        ],
                    )
                    container_amostras.content.controls = [table]
                    page.update()
            else:
                await log_message(page, f"Erro ao buscar abas: {response.text}")
    except Exception as ex:
        await log_message(page, f"Erro ao buscar abas do DEG.xlsx: {ex}")
