import flet as ft
import httpx
import asyncio
import logging
import pandas as pd
from .utils import log_message
from .jobs import wait_for_job
import os
from ..components.general_components import create_table

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_existing_contrasts(token):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8890/contrasts/", headers=headers)
        response.raise_for_status()
        return response.json()

async def fetch_reference_genomes(token):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8890/genomes/", headers=headers)
        response.raise_for_status()
        return response.json()  # [{"name": ..., "size": ..., "status": ...}]

def parse_contrast_name(name):
    try:
        left, right = name.split("*")
        group_1 = left.split("(")[0].strip()
        group_2 = right.split("(")[0].strip()
        return f"{group_1} x {group_2}"
    except Exception:
        return name

def extract_accession_from_name(name):
    # Espera formato: "Nome do genoma (ACESSION)"
    if "(" in name and ")" in name:
        return name.split("(")[-1].strip(")")
    return name


# Feedback incremental do job DEG
def _format_deg_progress(message, state, total_contrasts):
    """Converte mensagens técnicas do R em feedback curto para o usuário."""
    message = str(message).strip()

    # Remove o timestamp gerado pelo DEG.R.
    if message.startswith("[") and "] " in message:
        message = message.split("] ", 1)[1].strip()

    if not message:
        return None

    # Mensagens gerais do worker já chegam prontas para o usuário.
    if message.startswith("PROGRESS:"):
        return message.split(":", 1)[1].strip()

    if message == state.get("last_raw"):
        return None

    state["last_raw"] = message
    lowered = message.casefold()

    # Saída de carregamento de pacotes R que não representa progresso.
    ignored_fragments = (
        "loading required package",
        "attaching package",
        "the following object is masked",
        "gplots ",
        "use citation",
        "homepage:",
        "report issues:",
        "ask questions:",
        "suppress this message",
        "parâmetro contrast_vector",
        "executando: lrt",
        "executando: tt",
        "executando: keep_sig",
        "executando: sig_genes",
    )

    if any(fragment in lowered for fragment in ignored_fragments):
        return None

    if message == "Iniciando DEG.R":
        return "DEG — preparando o ambiente de análise."

    if "Lendo Targets.txt" in message:
        return "DEG — lendo o desenho experimental."

    if "Lendo matriz de contagem" in message:
        return "DEG — carregando a matriz de contagens."

    if message.startswith("Removed ") and "MetaTags" in message:
        return "DEG — removendo linhas técnicas da quantificação."

    if "number of genes before filter" in message:
        return "DEG — " + message.replace(
            "number of genes before filter:",
            "genes antes do filtro:",
        ).replace(
            "after >=10 filter:",
            "genes após o filtro:",
        )

    if "Obtendo contrastes" in message:
        return (
            f"DEG — preparando {total_contrasts} contraste(s) selecionado(s)."
        )

    if message.startswith("Processando contraste FULL:"):
        state["full_index"] = state.get("full_index", 0) + 1
        name = message.split(":", 1)[1].strip()

        return (
            "DEG — tabela completa "
            f"{state['full_index']}/{total_contrasts}: {name}."
        )

    if message.startswith("Processando contraste:"):
        state["contrast_index"] = state.get("contrast_index", 0) + 1
        name = message.split(":", 1)[1].strip()

        return (
            "DEG — contraste "
            f"{state['contrast_index']}/{total_contrasts}: {name}."
        )

    if message.startswith("Contraste FULL "):
        return "DEG — " + message.replace(
            " genes totais",
            " genes registrados na tabela completa",
        )

    if message.startswith("Contraste ") and "genes DEG encontrados" in message:
        return "DEG — " + message

    if "Arquivo DEG.xlsx salvo com sucesso" in message:
        return "DEG — resultados significativos salvos."

    if "Criando DEG_full.xlsx" in message:
        return "DEG — criando planilha completa de apoio."

    if "Arquivo DEG_full.xlsx salvo com sucesso" in message:
        return "DEG — planilha completa salva."

    if (
        "error" in lowered
        or "erro" in lowered
        or "execution halted" in lowered
        or "grupo(s) ausente(s)" in lowered
    ):
        return "DEG — erro: " + message

    return None


async def wait_for_deg_job_with_progress(
    page,
    token,
    job_id,
    total_contrasts,
):
    """
    Aguarda o job normalmente e, em paralelo, envia novas etapas do
    DEG_R.log para o terminal da interface.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "ngrok-skip-browser-warning": "true",
    }
    cursor = 0
    state = {
        "contrast_index": 0,
        "full_index": 0,
        "last_raw": None,
    }

    job_task = asyncio.create_task(
        wait_for_job(token, job_id)
    )

    async def fetch_progress(client):
        nonlocal cursor

        response = await client.get(
            f"http://localhost:8890/deg/jobs/{job_id}/progress",
            headers=headers,
            params={"cursor": cursor},
            timeout=20,
        )

        if response.status_code != 200:
            return

        body = response.json()
        cursor = body.get("cursor", cursor)

        for raw_line in body.get("lines", []):
            formatted = _format_deg_progress(
                raw_line,
                state,
                total_contrasts,
            )

            if formatted:
                await log_message(page, formatted)

    try:
        async with httpx.AsyncClient() as client:
            while not job_task.done():
                try:
                    await fetch_progress(client)
                except Exception as progress_error:
                    logger.debug(
                        "Falha transitória ao consultar progresso DEG: %s",
                        progress_error,
                    )

                await asyncio.sleep(1.5)

            # Última leitura para não perder mensagens gravadas junto ao fim.
            try:
                await fetch_progress(client)
            except Exception:
                logger.debug(
                    "Não foi possível realizar a leitura final do progresso DEG.",
                    exc_info=True,
                )

        return await job_task

    except Exception:
        if not job_task.done():
            job_task.cancel()
        raise


async def run_deg_analysis(page, token, user_id, refresh_callback=None):
    await log_message(page, "Selecione o genoma de referência e os contrastes para DEG.")
    # Buscar genomas de referência disponíveis
    genomes = await fetch_reference_genomes(token)
    if not genomes:
        await log_message(page, "Nenhum genoma de referência disponível.")
        return

    genome_options = [ft.dropdown.Option(genome["name"]) for genome in genomes]
    selected_genome = [genome_options[0].key]  # Usar lista mutável para manter referência

    def on_genome_change(e):
        selected_genome[0] = e.control.value

    genome_dropdown = ft.Dropdown(
        label="Genoma de referência",
        options=genome_options,
        value=genome_options[0].key,
        on_change=on_genome_change,
        width=400,
    )

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
        if not selected_genome[0]:
            await log_message(page, "Selecione um genoma de referência!")
            return
        # Extrair accession do genoma selecionado
        genome_accession = extract_accession_from_name(selected_genome[0])
        selected_labels = [parse_contrast_name(c["name"]) for c in contrasts if c["id"] in selected_ids]
        await log_message(page, "Iniciando DEG")
        await log_message(page, f"Genoma: {selected_genome[0]}")
        await log_message(page, f"Contrastes selecionados para DEG: {', '.join(selected_labels)}")
        dlg_modal_deg.open = False
        page.update()
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8890/deg/run",
                    json={
                        "contrast_ids": list(selected_ids),
                        "genome_accession": genome_accession,
                    },
                    headers=headers,
                    timeout=120,
                )
                if response.status_code in (200, 202):
                    body = response.json()
                    job_id = body.get("job_id")
                    if job_id:
                        await log_message(page, f"DEG enfileirado (job {job_id}).")
                        result = await wait_for_deg_job_with_progress(
                            page,
                            token,
                            job_id,
                            len(selected_ids),
                        )
                        status = result.get("status")
                        if status == "COMPLETED":
                            annotation = (result.get("result") or {}).get("annotation") or {}

                            await log_message(
                                page,
                                "Análise DEG e anotação funcional concluídas! "
                                "O arquivo DEG.xlsx foi gerado."
                            )

                            if annotation.get("gff") == "COMPLETED":
                                await log_message(page, "Anotação GFF concluída.")

                            if annotation.get("uniprot") == "COMPLETED":
                                await log_message(page, "Anotação UniProt concluída.")
                        else:
                            await log_message(page, f"DEG finalizado com status {status}.")
                            error_message = result.get("error_message")
                            if error_message:
                                await log_message(
                                    page,
                                    f"Detalhe: {error_message}"
                                )

                        # Atualizar tabela lateral imediatamente após
                        # o término do job.
                        if refresh_callback is not None:
                            try:
                                await refresh_callback()
                            except Exception as refresh_error:
                                logger.warning(
                                    "Erro ao atualizar contagem DEG: %s",
                                    refresh_error,
                                )
                    else:
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
                    ft.Container(height=5),
                    genome_dropdown,
                    ft.Divider(height=1, thickness=1, color="black38"),
                    ft.Row(
                        controls=[
                            ft.DataTable(
                                columns=[
                                    ft.DataColumn(ft.Text("Contraste", expand=True)),
                                    ft.DataColumn(select_all_checkbox),
                                ],
                                rows=data_rows,
                                heading_row_height=40,
                                column_spacing=20,
                                expand=True,
                            )
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        expand=True,
                    ),
                ],
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            height=400,
            expand=True,
        ),
        actions=[
            ft.TextButton(
                "Iniciar DEG",
                on_click=lambda e: asyncio.run(iniciar_deg(e)),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_deg)

async def fetch_sheet_data(token, user_id, sheet_name):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    params = {"sheet": sheet_name}
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8890/deg/sheet_data", headers=headers, params=params)
        response.raise_for_status()
        return response.json()  # {"columns": [...], "rows": [[...], ...]}

async def show_sheet_as_table(page, token, user_id, sheet_name):
    print(f"[LOG] show_sheet_as_table: sheet_name={sheet_name}")
    try:
        # Loga início da identificação para a aba
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
                                if isinstance(container, ft.Container) and container.key == "container_preview":
                                    container.content.controls = [
                                        ft.Container(
                                            expand=True,
                                            content=ft.Text(
                                                "Nenhum dado disponível nesta aba.",
                                                color="red",
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
            # Limite de largura para todas as células (exceto coluna de busca)
            max_width = 220
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
                # Para células longas, use um Container com rolagem horizontal
                return ft.Container(
                    width=max_width,
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                str(cell),
                                selectable=True,
                                size=14,
                                max_lines=3,
                                overflow=ft.TextOverflow.CLIP,
                            )
                        ],
                        scroll=ft.ScrollMode.ALWAYS,  # scroll horizontal individual
                        expand=True,
                    ),
                    alignment=ft.alignment.center_left,
                )

        def filter_rows(e=None, sorted_rows=None):
            search_value = search_ref.current.value.strip().lower()
            dt = dt_ref.current
            dt.rows.clear()
            filtered = []
            base_rows = sorted_rows if sorted_rows is not None else all_rows
            if search_value:
                # Busca em todas as colunas relevantes: nome do gene (coluna 0), Note GFF, Uniprot *
                # Descobre os índices das colunas extras
                note_gff_idx = None
                uniprot_idxs = []
                for idx, col in enumerate(columns):
                    col_l = str(col).lower()
                    if "note gff" in col_l:
                        note_gff_idx = idx
                    if col_l.startswith("uniprot"):
                        uniprot_idxs.append(idx)
                def row_matches(row):
                    # Nome do gene (coluna 0)
                    if search_value in str(row[0]).lower():
                        return True
                    # Note GFF
                    if note_gff_idx is not None and search_value in str(row[note_gff_idx]).lower():
                        return True
                    # Uniprot *
                    for idx in uniprot_idxs:
                        if search_value in str(row[idx]).lower():
                            return True
                    return False
                filtered = [row for row in base_rows if row_matches(row)]
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
            icon = "unfold_more"
            if sort_state["logFC"] == 1:
                icon = "arrow_upward"
            elif sort_state["logFC"] == -1:
                icon = "arrow_downward"
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
                                bgcolor="transparent",
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
            heading_row_color="black12",
        )

        notfound_text = ft.Text(
            "Nenhum gene encontrado.",
            ref=notfound_ref,
            visible=False,
            color="red",
            size=16,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
        )

        # Permite rolagem horizontal e vertical ao mesmo tempo
        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.key == "container_preview":
                                print("[LOG] Atualizando container_pre_visualizacao com tabela Excel")
                                container.content.controls = [
                                    ft.Column(
                                        expand=True,
                                        scroll=ft.ScrollMode.ALWAYS,  # vertical scroll
                                        controls=[
                                            ft.Row(
                                                expand=True,
                                                scroll=ft.ScrollMode.ALWAYS,  # horizontal scroll
                                                controls=[
                                                    ft.Container(
                                                        expand=True,
                                                        content=excel_table,
                                                    )
                                                ]
                                            ),
                                            notfound_text
                                        ]
                                    )
                                ]
                                page.update()
                                return
        print("[LOG] container_pre_visualizacao não encontrado")
    except Exception as ex:
        print(f"[LOG] Erro ao exibir planilha: {ex}")
        await log_message(page, f"Erro ao exibir planilha: {ex}")

async def show_deg_dropdown(page, token, user_id=None, sheet_name=None):
    # Caminho base dos gráficos DEG
    deg_dir = f"../users/{user_id}/DEG"
    # Opções do dropdown e nomes dos arquivos correspondentes
    DEG_GRAPHS = [
        ("Barplot", "BARPLOT.ISOLADO - {sheet}.png"),
        ("MA plot", "MA.ISOLADO - {sheet}.png"),
        ("Volcano plot", "VOLCANO.ISOLADO - {sheet}.png"),
        ("Frequência de termos ontológicos", "ONTO_FREQ.ISOLADO - {sheet}.png")
    ]

    # Remove qualquer dropdown ou gráfico anterior do container_pre_visualizacao
    for control in page.controls:
        if isinstance(control, ft.Row):
            for column in control.controls:
                if isinstance(column, ft.Column):
                    for container in column.controls:
                        # Prefer explicit key 'container_preview' to avoid matching the chatbot container
                        if isinstance(container, ft.Container) and getattr(container, 'key', None) == "container_preview" and isinstance(container.content, ft.Column):
                            dropdown = ft.Dropdown(
                                options=[ft.dropdown.Option(title) for title, _ in DEG_GRAPHS],
                                width=350,
                                value=DEG_GRAPHS[0][0],
                            )
                            img_placeholder = ft.Container(expand=True, alignment=ft.alignment.center)

                            current_filename = None

                            async def display_deg_graph(selected_title):
                                # Busca o arquivo correspondente ao título selecionado
                                filename = None
                                for title, fname in DEG_GRAPHS:
                                    if title == selected_title:
                                        filename = fname.format(sheet=sheet_name)
                                        break
                                if not filename:
                                    return ft.Text("Figura não encontrada.", color="red")
                                img_path = os.path.join(deg_dir, filename)
                                if not os.path.exists(img_path):
                                    return ft.Text(f"Figura não encontrada: {filename}", color="red")
                                try:
                                    with open(img_path, "rb") as f:
                                        img_data = f.read()
                                    import base64
                                    img_base64 = base64.b64encode(img_data).decode("utf-8")
                                    image_control = ft.Image(src_base64=img_base64)
                                    interactive_viewer = ft.InteractiveViewer(
                                        min_scale=0.5,
                                        max_scale=15,
                                        boundary_margin=ft.margin.all(10),
                                        content=image_control,
                                        constrained=True
                                    )
                                    # store current filename for download button
                                    nonlocal current_filename
                                    current_filename = filename
                                    return interactive_viewer
                                except Exception as e:
                                    return ft.Text(f"Erro ao carregar imagem: {e}", color="red")

                            async def on_dropdown_change(e):
                                selected_title = e.control.value
                                img = await display_deg_graph(selected_title)
                                img_placeholder.content = img
                                page.update()

                            dropdown.on_change = on_dropdown_change

                            async def download_current_image(e):
                                try:
                                    if not current_filename:
                                        await log_message(page, "Nenhuma figura selecionada para download.")
                                        return
                                    import urllib.parse
                                    fname_enc = urllib.parse.quote(current_filename, safe='')
                                    download_url = f"http://localhost:8890/results/download_image?filename={fname_enc}&token={token}"
                                    page.launch_url(download_url)
                                except Exception as ex:
                                    await log_message(page, f"Erro ao iniciar download da figura: {ex}")

                            download_icon_btn = ft.IconButton(icon="file_download", tooltip="Baixar figura", on_click=download_current_image)

                            # Exibe o primeiro gráfico por padrão
                            img_placeholder.content = await display_deg_graph(DEG_GRAPHS[0][0])

                            container.content.controls = [
                                ft.Container(
                                    expand=True,
                                    content=ft.Column(
                                        controls=[
                                            ft.Container(height=10),
                                            ft.Row([dropdown, ft.Container(width=8), download_icon_btn], alignment=ft.MainAxisAlignment.CENTER),
                                            img_placeholder
                                        ],
                                        alignment=ft.MainAxisAlignment.CENTER,
                                        spacing=0,
                                    )
                                )
                            ]
                            page.update()
                            return

async def show_deg_results(page, token, user_id, container_amostras):
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8890/deg/sheets", headers=headers)
            if response.status_code == 200:
                sheets = response.json().get("sheets", [])
                if not sheets:
                    await log_message(page, "Nenhuma aba encontrada em DEG.xlsx.")
                else:
                    # Build table with a selectable checkbox column and actions, styled like QC tables
                    async def toggle_select_all(e):
                        checked = e.control.value
                        for row in tabela.rows:
                            try:
                                if isinstance(row.cells[1].content, ft.Checkbox):
                                    row.cells[1].content.value = checked
                            except Exception:
                                continue
                        page.update()

                    tabela = ft.DataTable(
                        heading_row_color="primary",
                        data_row_color="surface",
                        border=ft.border.all(0.5, "#000000"),
                        column_spacing=12,
                        divider_thickness=0.5,
                        columns=[
                            ft.DataColumn(ft.Text("Abas do DEG.xlsx", weight=ft.FontWeight.BOLD, width=160)),
                            ft.DataColumn(ft.Checkbox(on_change=toggle_select_all)),
                            ft.DataColumn(ft.Text("Ações", weight=ft.FontWeight.BOLD)),
                        ],
                        rows=[],
                        expand=True,
                    )

                    for sheet in sheets:
                        checkbox = ft.Checkbox(data=sheet)
                        tabela.rows.append(
                            ft.DataRow(
                                cells=[
                                    ft.DataCell(ft.Text(sheet, size=12)),
                                    ft.DataCell(checkbox),
                                    ft.DataCell(
                                        ft.Row(
                                            controls=[
                                                ft.IconButton(
                                                    icon="table_chart",
                                                    icon_color="green",
                                                    tooltip="Abrir planilha",
                                                    on_click=lambda e, s=sheet: asyncio.run(
                                                        show_sheet_as_table(page, token, user_id, s)
                                                    )
                                                ),
                                                ft.IconButton(
                                                    icon="visibility",
                                                    tooltip="Visualizar",
                                                    on_click=lambda e, s=sheet: asyncio.run(
                                                        show_deg_dropdown(page, token, user_id=user_id, sheet_name=s)
                                                    )
                                                ),
                                            ],
                                            spacing=6,
                                        )
                                    ),
                                ]
                            )
                        )

                    # Scrollable wrapper for visual parity and full width
                    tabela_com_scroll = ft.Row(
                        controls=[ft.Container(content=tabela, expand=True)],
                        scroll=ft.ScrollMode.ALWAYS,
                        expand=True
                    )

                    # Download button to fetch selected sheets as a single XLSX
                    async def download_selected(e):
                        selected = []
                        for row in tabela.rows:
                            try:
                                cb = row.cells[1].content
                                if isinstance(cb, ft.Checkbox) and cb.value:
                                    # sheet name is in first cell
                                    sheet_name = row.cells[0].content.value
                                    selected.append(sheet_name)
                            except Exception:
                                continue

                        if not selected:
                            await log_message(page, "Selecione ao menos uma aba para baixar.")
                            return

                        import urllib.parse
                        sheets_param = urllib.parse.quote(",".join(selected), safe='')
                        download_url = f"http://localhost:8890/results/download_deg_sheets?sheets={sheets_param}&token={token}"
                        page.launch_url(download_url)


                    async def delete_selected(e):
                        del e
                        selected = []
                        for row in tabela.rows:
                            try:
                                checkbox = row.cells[1].content
                                if (
                                    isinstance(checkbox, ft.Checkbox)
                                    and checkbox.value
                                ):
                                    selected.append(
                                        row.cells[0].content.value
                                    )
                            except Exception:
                                continue

                        if not selected:
                            await log_message(
                                page,
                                "Selecione ao menos uma aba para excluir.",
                            )
                            return

                        async def cancel_delete(event):
                            del event
                            confirmation.open = False
                            page.update()

                        async def confirm_delete(event):
                            del event
                            try:
                                async with httpx.AsyncClient(
                                    timeout=120,
                                ) as client:
                                    delete_response = await client.request(
                                        "DELETE",
                                        "http://localhost:8890/deg/sheets",
                                        json={"sheets": selected},
                                        headers=headers,
                                    )

                                if delete_response.status_code != 200:
                                    try:
                                        detail = delete_response.json().get(
                                            "detail",
                                            delete_response.text,
                                        )
                                    except Exception:
                                        detail = delete_response.text

                                    await log_message(
                                        page,
                                        f"Erro ao excluir abas: {detail}",
                                    )
                                    return

                                result = delete_response.json()
                                confirmation.open = False
                                page.update()

                                deleted = result.get(
                                    "deleted_sheets",
                                    [],
                                )
                                await log_message(
                                    page,
                                    "Abas excluídas: "
                                    + ", ".join(deleted),
                                )

                                remaining = result.get(
                                    "remaining_sheets",
                                    [],
                                )
                                if remaining:
                                    await show_deg_results(
                                        page,
                                        token,
                                        user_id,
                                        container_amostras,
                                    )
                                else:
                                    container_amostras.content.controls = [
                                        ft.Container(
                                            padding=20,
                                            alignment=ft.alignment.center,
                                            content=ft.Text(
                                                "Todas as abas de análise "
                                                "diferencial foram excluídas.",
                                                text_align=ft.TextAlign.CENTER,
                                            ),
                                        )
                                    ]
                                    page.update()

                            except Exception as ex:
                                await log_message(
                                    page,
                                    f"Erro ao excluir abas DEG: {ex}",
                                )

                        confirmation = ft.AlertDialog(
                            modal=True,
                            title=ft.Text(
                                "Excluir abas?"
                            ),
                            content=ft.Column(
                                tight=True,
                                controls=[
                                    ft.Text(
                                        "Esta operação removerá as abas:"
                                    ),
                                    ft.Text(
                                        ", ".join(selected),
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(
                                        "Também serão removidos os gráficos, "
                                        "clusterizações e relatórios LLM/RAG "
                                        "associados a essas abas.",
                                        color="red",
                                    ),
                                ],
                            ),
                            actions=[
                                ft.TextButton(
                                    "Cancelar",
                                    on_click=cancel_delete,
                                ),
                                ft.ElevatedButton(
                                    "Excluir",
                                    icon="delete",
                                    color="white",
                                    bgcolor="red",
                                    on_click=confirm_delete,
                                ),
                            ],
                            actions_alignment=ft.MainAxisAlignment.END,
                        )

                        page.open(confirmation)
                        page.update()

                    from ..components.general_components import create_button
                    btn_download = create_button(
                        "Baixar abas",
                        download_selected,
                        color="green",
                        expand=True,
                    )
                    btn_delete = create_button(
                        "Excluir abas",
                        delete_selected,
                        color="red",
                        expand=True,
                    )

                    # Place table + centered, full-width button in the actions area
                    container_amostras.content.controls = [
                        ft.Column(
                            controls=[
                                tabela_com_scroll,
                                ft.Container(height=8),
                                ft.Row(
                                    [btn_download, btn_delete],
                                    alignment=ft.MainAxisAlignment.CENTER,
                                    expand=True,
                                ),
                            ],
                            expand=True,
                        )
                    ]

                    page.update()
            else:
                await log_message(page, f"Erro ao buscar abas: {response.text}")
    except Exception as ex:
        await log_message(page, f"Erro ao buscar abas do DEG.xlsx: {ex}")
