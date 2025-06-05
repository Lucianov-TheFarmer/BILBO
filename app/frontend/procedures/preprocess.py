import flet as ft
import httpx
import asyncio
import logging
import os
import base64
from .utils import log_message  # Adicione esta linha

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

async def show_preprocess_modal(page, token, user_id):
    logging.info("Opening preprocess modal.")
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

    async def iniciar_preprocessamento(e):
        if not selected_ids:
            await log_message(page, "Selecione pelo menos um contraste!")
            return
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/preprocess/start",
                    json={"contrast_ids": list(selected_ids)},
                    headers=headers,
                )
                if response.status_code == 200:
                    await log_message(page, "Pré-processamento iniciado com sucesso!")
                else:
                    await log_message(page, f"Erro: {response.text}")
        except Exception as ex:
            await log_message(page, f"Erro: {ex}")
        dlg_modal.open = False
        page.update()

    dlg_modal = ft.AlertDialog(
        title=ft.Text("Pré-processamento"),
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
            # width=400,
            height=400,
        ),
        actions=[
            ft.TextButton(
                "Iniciar pré-processamento",
                on_click=lambda e: asyncio.run(iniciar_preprocessamento(e)),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=200,
                height=40,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal)

EXPLORATORY_GRAPHS = [
    ("Tamanho das bibliotecas", "libraries_sizes.png"),
    ("BCV (Biological Coefficient of Variation)", "edgeR_BCV.png"),
    ("MDS (Multidimensional Scaling)", "edgeR_MDS.png"),
    ("Clusterização de amostras", "sampleClustering.png"),
    ("Densidade - Counts brutos", "Densities_input.png"),
    ("Densidade - Counts filtrados", "Densities_low_expression_filter.png"),
    ("Densidade - CPM normalizado", "Densities_normalization.png"),
    ("Densidade - CPM ajustado", "Densities_log_cpm_fitted_norm.png"),
    ("Histograma log10(CPM+1)", "Log10_histogram_normalized.png"),
    ("Histograma log2(CPM+1)", "Log2_histogram_normalized.png"),
    ("Histograma CPM", "histogram_normalized.png"),
    ("Heatmap de correlação", "sampleClusteringHeatmap.png"),
]

def get_preprocess_image_path(user_id, filename):
    return os.path.abspath(os.path.join("..", "users", str(user_id), "preprocess", filename))

async def show_exploratory_dropdown(page, user_id):
    # Remove qualquer dropdown ou imagem anterior do container_pre_visualizacao
    for control in page.controls:
        if isinstance(control, ft.Row):
            for column in control.controls:
                if isinstance(column, ft.Column):
                    for container in column.controls:
                        if isinstance(container, ft.Container) and container.expand == 2 and isinstance(container.content, ft.Column):
                            # Cria o dropdown e armazena referência para atualização
                            dropdown = ft.Dropdown(
                                options=[ft.dropdown.Option(title, data=filename) for title, filename in EXPLORATORY_GRAPHS],
                                width=350,
                                value=EXPLORATORY_GRAPHS[0][0],
                            )

                            # Placeholder para imagem, será atualizado dinamicamente
                            img_placeholder = ft.Container(expand=True, alignment=ft.alignment.center)

                            # Função para atualizar o gráfico exibido sem remover o dropdown
                            async def on_dropdown_change(e):
                                selected_title = e.control.value
                                img = await display_exploratory_graph(page, user_id, selected_title)
                                img_placeholder.content = img
                                page.update()

                            dropdown.on_change = on_dropdown_change

                            # Exibe o primeiro gráfico por padrão
                            img_placeholder.content = await display_exploratory_graph(page, user_id, EXPLORATORY_GRAPHS[0][0])

                            container.content.controls = [
                                ft.Container(
                                    expand=True,
                                    content=ft.Column(
                                        controls=[
                                            ft.Container(height=10),
                                            ft.Row(
                                                [dropdown],
                                                alignment=ft.MainAxisAlignment.CENTER
                                            ),
                                            img_placeholder
                                        ],
                                        alignment=ft.MainAxisAlignment.CENTER,
                                        spacing=0,
                                    )
                                )
                            ]
                            page.update()
                            return

async def display_exploratory_graph(page, user_id, selected_title):
    # Busca o arquivo correspondente ao título selecionado
    filename = None
    for title, fname in EXPLORATORY_GRAPHS:
        if title == selected_title:
            filename = fname
            break
    if not filename:
        return ft.Text("Figura não encontrada.", color=ft.colors.RED)
    img_path = get_preprocess_image_path(user_id, filename)
    if not os.path.exists(img_path):
        return ft.Text(f"Figura não encontrada: {filename}", color=ft.colors.RED)
    try:
        with open(img_path, "rb") as f:
            img_data = f.read()
        img_base64 = base64.b64encode(img_data).decode("utf-8")
        # Ajusta a imagem para caber no container e permitir pan mesmo no zoom mínimo
        image_control = ft.Image(
            src_base64=img_base64,
            # fit=ft.ImageFit.NONE,
            # width=800,   # Reduzido para garantir que caiba no container
            # height=450,
        )
        interactive_viewer = ft.InteractiveViewer(
            min_scale=0.5,  # Permite pan mesmo no zoom mínimo
            max_scale=15,
            boundary_margin=ft.margin.all(10),  # Aumenta a margem para facilitar o pan
            content=image_control,
            constrained=True  # Permite pan livre mesmo se a imagem for menor que o container
        )
        return interactive_viewer
    except Exception as e:
        return ft.Text(f"Erro ao carregar imagem: {e}", color=ft.colors.RED)
