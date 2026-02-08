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

async def delete_venn_file(token, user_id, filename):
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            "http://localhost:8000/results/delete_venn_file",
            params={"user_id": user_id, "filename": filename},
            headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
        )
        response.raise_for_status()
        return response.json()

async def delete_barplot_file(token, user_id, filename):
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            "http://localhost:8000/results/delete_barplot_file",
            params={"user_id": user_id, "filename": filename},
            headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
        )
        response.raise_for_status()
        return response.json()

async def show_barplots_table(page, token, user_id, container_amostras):
    from .viewer import view_barplot_image
    
    files = await fetch_barplot_files(token, user_id)
    
    async def delete_barplot_handler(filename):
        try:
            await delete_barplot_file(token, user_id, filename)
            # Recarrega a tabela após exclusão
            await show_barplots_table(page, token, user_id, container_amostras)
        except Exception as e:
            # Mostra erro (poderia usar um snackbar ou toast aqui)
            print(f"Erro ao excluir barplot: {e}")
    
    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Barplots salvos")),
            ft.DataColumn(ft.Text("Ações")),
        ],
        rows=[
            ft.DataRow([
                ft.DataCell(ft.Text(f)),
                ft.DataCell(ft.Row([
                    ft.IconButton(
                        icon="visibility",
                        tooltip="Ver barplot",
                        on_click=lambda e, filename=f: asyncio.run(view_barplot_image(page, token, user_id, filename))
                    ),
                    ft.IconButton(
                        icon="file_download",
                        tooltip="Baixar barplot",
                        on_click=lambda e, filename=f: page.launch_url(f"http://localhost:8000/results/download_image?user_id={user_id}&filename={__import__('urllib.parse', fromlist=['quote']).quote(filename, safe='')}&token={token}")
                    ),
                    ft.IconButton(
                        icon="delete",
                        icon_color="red",
                        tooltip="Excluir barplot",
                        on_click=lambda e, filename=f: asyncio.run(delete_barplot_handler(filename))
                    )
                ], spacing=5))
            ]) for f in files
        ],
        expand=True,
    )
    btn = ft.ElevatedButton(
        "Gerar novo barplot",
        icon="add",
        on_click=lambda e: asyncio.run(show_barplots_modal(page, token, user_id, container_amostras)),
    )
    # Replace container content entirely with the results (remove previous stage table)
    results_wrapper = ft.Container(
        content=ft.Column(controls=[table, btn]),
        padding=ft.padding.all(6),
    )

    container_amostras.content.controls = [results_wrapper]
    page.update()

async def show_venn_table(page, token, user_id, container_amostras):
    from .viewer import view_venn_image
    
    files = await fetch_venn_files(token, user_id)
    
    async def delete_venn_handler(filename):
        try:
            await delete_venn_file(token, user_id, filename)
            # Recarrega a tabela após exclusão
            await show_venn_table(page, token, user_id, container_amostras)
        except Exception as e:
            # Mostra erro (poderia usar um snackbar ou toast aqui)
            print(f"Erro ao excluir diagrama de Venn: {e}")
    
    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Diagramas de Venn salvos")),
            ft.DataColumn(ft.Text("Ações")),
        ],
        rows=[
            ft.DataRow([
                ft.DataCell(ft.Text(f)),
                ft.DataCell(ft.Row([
                    ft.IconButton(
                        icon="visibility",
                        tooltip="Ver diagrama de Venn",
                        on_click=lambda e, filename=f: asyncio.run(view_venn_image(page, token, user_id, filename))
                    ),
                    ft.IconButton(
                        icon="file_download",
                        tooltip="Baixar diagrama de Venn",
                        on_click=lambda e, filename=f: page.launch_url(f"http://localhost:8000/results/download_image?user_id={user_id}&filename={__import__('urllib.parse', fromlist=['quote']).quote(filename, safe='')}&token={token}")
                    ),
                    ft.IconButton(
                        icon="delete",
                        icon_color="red",
                        tooltip="Excluir diagrama de Venn",
                        on_click=lambda e, filename=f: asyncio.run(delete_venn_handler(filename))
                    )
                ], spacing=5))
            ]) for f in files
        ],
        expand=True,
    )
    btn = ft.ElevatedButton(
        "Gerar novo diagrama de Venn",
        icon="add",
        on_click=lambda e: asyncio.run(show_venn_modal(page, token, user_id, container_amostras)),
    )
    # Replace container content entirely with the results (remove previous stage table)
    results_wrapper = ft.Container(
        content=ft.Column(controls=[table, btn]),
        padding=ft.padding.all(6),
    )

    container_amostras.content.controls = [results_wrapper]
    page.update()

async def show_deg_modal(page, token, user_id, title, max_select=None, show_select_all=False, on_confirm=None):
    sheets = await fetch_deg_sheets(token, user_id)
    selected = set()
    checkboxes = []
    title_field = ft.TextField(label="Título do Barplot", width=350)
    divider = ft.Divider(height=1, thickness=1, color="black")

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
            dlg_modal.title = ft.Text("Título obrigatório!", color="red")
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
    async def on_confirm(title, contrasts, dlg_modal):
        if not title.strip():
            dlg_modal.title = ft.Text("Título obrigatório!", color="red")
            page.update()
            return
        if len(contrasts) < 2 or len(contrasts) > 4:
            dlg_modal.title = ft.Text("Selecione entre 2 e 4 contrastes!", color="red")
            page.update()
            return
        await create_venn_file(token, user_id, title, contrasts)
        dlg_modal.open = False
        page.update()
        await show_venn_table(page, token, user_id, container_amostras)

    await show_deg_modal(
        page,
        token,
        user_id,
        "Diagrama de Venn (2-4 contrastes)",
        max_select=4,
        show_select_all=False,
        on_confirm=on_confirm,
    )

async def show_heatmap_modal(page, token, user_id, container_amostras):
    async def on_confirm(title, selected_contrasts, dlg_modal):
        """Callback executado quando o usuário confirma a criação do heatmap"""
        try:
            # Fecha o modal primeiro
            dlg_modal.open = False
            page.update()
            
            # Chama a API para criar o heatmap
            data = {
                "title": title,
                "selected_contrasts": selected_contrasts,
                "user_id": user_id,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/results/create_heatmap_file",
                    json=data,
                    headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
                    timeout=120.0,
                )

            if response.status_code == 200:
                result = response.json()
                # Se a geração foi iniciada em background, faça polling até o arquivo aparecer
                expected = result.get("filename")
                found = False
                # timeout em segundos
                timeout = 120
                elapsed = 0
                interval = 1.0
                try:
                    while elapsed < timeout:
                        # consulta arquivos existentes
                        async with httpx.AsyncClient() as client:
                            r = await client.get(
                                "http://localhost:8000/results/heatmap_files",
                                params={"user_id": user_id},
                                headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
                                timeout=30.0,
                            )
                        if r.status_code == 200:
                            files = r.json().get("files", [])
                            if expected in files:
                                found = True
                                break
                        await asyncio.sleep(interval)
                        elapsed += interval
                except Exception as _:
                    # ignorar falhas temporárias de rede e sair para atualizar a tabela
                    pass

                # Atualiza a tabela depois que o arquivo foi detectado (ou timeout)
                await show_heatmaps_table(page, token, user_id, container_amostras)
            else:
                try:
                    error_msg = response.json().get("detail", "Erro desconhecido")
                except Exception:
                    error_msg = "Erro desconhecido"
                print(f"[frontend] Erro ao criar heatmap: {error_msg}")
        except Exception as e:
            # erro ao conectar com o servidor
            pass
    
    await show_deg_modal(
        page, 
        token, 
        user_id, 
        "Heatmap", 
        max_select=None, 
        show_select_all=True,
        on_confirm=on_confirm,
    )

async def show_heatmaps_table(page, token, user_id, container_amostras):
    """Exibe a tabela com os heatmaps criados"""
    try:
        # Busca os arquivos de heatmap
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "http://localhost:8000/results/heatmap_files",
                params={"user_id": user_id},
                headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
                timeout=30.0,
            )
        
        if response.status_code != 200:
            print(f"[frontend] Falha ao buscar heatmaps: status={response.status_code} body={response.text}")
            return
        
        files = response.json().get("files", [])
        
        # Função para visualizar heatmap
        async def view_heatmap(filename):
            from .viewer import view_heatmap_image
            await view_heatmap_image(page, token, filename, user_id)
        
        # Função para excluir heatmap (sem diálogo) - segue o padrão usado para barplot/venn
        async def delete_heatmap_request(filename):
            try:
                print(f"[frontend] Enviando DELETE /results/delete_heatmap_file user_id={user_id} filename={filename}")
                async with httpx.AsyncClient() as client:
                    response = await client.delete(
                        "http://localhost:8000/results/delete_heatmap_file",
                        params={"user_id": user_id, "filename": filename},
                        headers={"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"},
                        timeout=30.0,
                    )

                try:
                    resp_text = response.text
                except Exception:
                    resp_text = "<no body>"
                print(f"[frontend] DELETE response status={response.status_code} body={resp_text}")

                if response.status_code == 200:
                    await show_heatmaps_table(page, token, user_id, container_amostras)
                else:
                    try:
                        error_msg = response.json().get("detail", resp_text)
                    except Exception:
                        error_msg = resp_text
                    print(f"[frontend] Erro ao excluir: {error_msg}")
            except Exception as ex:
                print(f"[frontend] Erro ao conectar: {ex}")
        
        # Cria as linhas da tabela
        rows = []
        for filename in files:
            # Remove o prefixo "HEATMAP - " e a extensão ".png" para exibição
            display_name = filename
            if filename.startswith("HEATMAP - "):
                display_name = filename[10:]
            if display_name.endswith(".png"):
                display_name = display_name[:-4]
            
            # Botões de ação
            view_button = ft.IconButton(
                icon="visibility",
                tooltip="Visualizar",
                on_click=lambda e, fname=filename: asyncio.run(view_heatmap(fname))
            )
            
            # Helper sync handler to ensure the click event runs immediately and we can show debug feedback
            def on_delete_click(e, fname=filename):
                try:
                    # immediate feedback so we know the handler ran
                    print(f"[frontend] on_delete_click invoked for {fname}")
                except Exception as _:
                    pass
                # Run the async delete coroutine
                asyncio.run(delete_heatmap_request(fname))

            delete_button = ft.IconButton(
                icon="delete",
                tooltip="Excluir",
                on_click=on_delete_click
            )

            download_button = ft.IconButton(
                icon="file_download",
                tooltip="Baixar heatmap",
                on_click=lambda e, fname=filename: page.launch_url(f"http://localhost:8000/results/download_image?user_id={user_id}&filename={__import__('urllib.parse', fromlist=['quote']).quote(fname, safe='')}&token={token}")
            )
            
            row = ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(display_name)),
                    ft.DataCell(
                        ft.Row([view_button, download_button, delete_button], tight=True)
                    ),
                ]
            )
            rows.append(row)
        
        # Cria a tabela
        if rows:
            table = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("Nome do Heatmap", weight=ft.FontWeight.BOLD)),
                    ft.DataColumn(ft.Text("Ações", weight=ft.FontWeight.BOLD)),
                ],
                rows=rows,
                # border=ft.border.all(1, ft.colors.OUTLINE),
                border_radius=10,
                # vertical_lines=ft.border.BorderSide(1, ft.colors.OUTLINE),
                # horizontal_lines=ft.border.BorderSide(1, ft.colors.OUTLINE),
            )
        else:
            table = ft.Container(
                content=ft.Text(
                    "Nenhum heatmap encontrado. Clique em 'Novo Heatmap' para criar um.",
                    text_align=ft.TextAlign.CENTER,
                    size=16,
                ),
                alignment=ft.alignment.center,
                padding=ft.padding.all(20),
            )
        
        # Botão para criar novo heatmap
        btn = ft.ElevatedButton(
            "Gerar novo heatmap",
            icon="add",
            on_click=lambda e: asyncio.run(show_heatmap_modal(page, token, user_id, container_amostras)),
        )
        
        # Atualiza o container seguindo o padrão das outras funções
        container_amostras.content.controls = [table, btn]
        page.update()        

    except Exception as e:
        # Falha ao carregar heatmaps
        print(f"[frontend] Erro ao carregar heatmaps: {e}")
