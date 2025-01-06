import flet as ft
from flet import *
import subprocess
import os
import re
import signal

venv_python = os.path.join(os.getcwd(), 'Bilbo\\venv', 'Scripts', 'python.exe')

def main(page: ft.Page):

    page.title = "BILBO"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.window_maximized = True

    # page.client_storage.remove("myapp.current_license")
    # page.client_storage.remove("myapp.current_id")

    servidores = {"GCP": {"ip": "34.41.168.108", "usuario": "vitor_silva7"}, "LCC": {"ip": "177.105.24.9", "usuario": "chalfun"}}
    servidor_selecionado = servidores["LCC"]

    usuario_text = ft.Text("Usuário: ---------")
 
    ###### Menubar

    appbar_text_ref = ft.Ref[ft.Text]()

    def menubar_clicar_item(e):
            print(f"{e.control.content.value}.on_click")
            page.show_snack_bar(ft.SnackBar(content=ft.Text(f"{e.control.content.value} was clicked!")))
            appbar_text_ref.current.value = e.control.content.value
            page.update()

    def menubar_abrir_item(e):
            print(f"{e.control.content.value}.on_open")

    def menubar_fechar_item(e):
            print(f"{e.control.content.value}.on_close")

    def menubar_passar_por_cima_item(e):
            print(f"{e.control.content.value}.on_hover")    

    def mudar_tema(e):
        if page.theme_mode == ft.ThemeMode.LIGHT:
            page.theme_mode = ft.ThemeMode.DARK
            e.control.icon = ft.icons.LIGHT_MODE
        else:
            page.theme_mode = ft.ThemeMode.LIGHT
            e.control.icon = ft.icons.DARK_MODE
        page.update()

    ###### Verificação de licença

    def resultado_alerta_licenca(e: ft.FilePickerResultEvent):
        
        def check_user_id(user_id):
            if not re.fullmatch(r'\d{6}', user_id):
                raise ValueError("Invalid user ID")

        global current_license

        print("\nArquivo de licença selecionado:", e.files)
        if e.files is not None and len(e.files) > 0:     
            try:
               
                container_progresso.controls[0].content = ft.Text(f"Tarefa atual: Inicializando", expand=True, color=ft.colors.ON_PRIMARY_CONTAINER, size=18)
                dlg_modal_licenca.open = False
                animacao_carregamento_iniciar()

                try:
                    current_license = e.files[0].path
                    print("Licença adicionada pelo FilePicker")
                except:
                    print("Licença adicionada anteriormente")
                    current_license = e.files[0]

                result = subprocess.check_output([venv_python, f"Bilbo\\scripts\\Autorização.py", current_license, servidor_selecionado["ip"], servidor_selecionado["usuario"]])                
                id_correspondente = str(result).split(":")[1].replace(r"\r", "").replace(r"\n", "").replace(r'"', "").replace(r"'", "").strip()
                check_user_id(id_correspondente)
                print("Usuário: ", str(id_correspondente))

                page.client_storage.set("myapp.current_license", current_license)
                page.client_storage.set("myapp.current_id", id_correspondente)                
                
                usuario_text.value = f"Usuário: {id_correspondente}"
                usuario_text.update()
                page.show_snack_bar(ft.SnackBar(content=ft.Text(f"Chave autenticada! Boas análises, usuário {id_correspondente}.")))
                atualizar_tabela()
                animacao_carregamento_terminar()

            except Exception as e:
                print("Erro: ", e, "\nFalha na autenticação")
                page.client_storage.remove("myapp.current_license")
                page.client_storage.remove("myapp.current_id")
                dlg_modal_licenca.content = ft.Text("Chave inválida.\nVerifique sua licença de uso ou entre em contato com o suporte técnico.")
                container_pre_visualizacao.content = ft.Container(expand=True)
                abrir_alerta_licenca(e = None)
                page.update()

        page.update()

    def escolher_licenca(e):
        if page.client_storage.contains_key("myapp.current_license"):
            dlg_modal_licenca.open = False
            current_license = page.client_storage.get("myapp.current_license")
            print("Licença atual:", current_license)
            
        else:
            file_picker.pick_files(allow_multiple=False)

    def abrir_alerta_licenca(e):
        
        if not page.client_storage.contains_key("myapp.current_license"):
            page.dialog = dlg_modal_licenca
            dlg_modal_licenca.open = True
        else:
            license_path = page.client_storage.get("myapp.current_license")
            print("Licença atual: ", license_path)
            class MockFilePickerFile:
                def __init__(self, name, path, size):
                    self.name = "Licença adicionada"
                    self.path = path
                    self.size = 0
                    self.files = [path]
                def __repr__(self):
                    return f"FilePickerFile(name='{self.name}', path='{self.path}', size={self.size}, files={self.files})"
            
            license_list = MockFilePickerFile("Licença adicionada", license_path, 0)
            print(license_list)
            resultado_alerta_licenca(e = license_list)

    file_picker = ft.FilePicker(on_result=resultado_alerta_licenca)
    page.overlay.append(file_picker)

    dlg_modal_licenca= ft.AlertDialog(
        modal=True,
        title=ft.Text("Seja muito bem-vindo ao BILBO!"),
        content=ft.Text("Antes de começar, por favor selecione sua licença de uso."),
        actions=[
            ft.TextButton("Selecionar licença", on_click=escolher_licenca, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),width=200, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    ###### Animações

    loading_animation = ft.Lottie(src=f'https://lottie.host/7a391c77-bf50-466b-9766-0f9dd9b7ba7a/p9AHwAMJc7.json',
                        expand=True,
                        repeat=True,
                        reverse=False,
                        animate=True,
                        width=1900,
                        height=1900)

    def animacao_carregamento_iniciar():
        container_pre_visualizacao.content = ft.Container(content=loading_animation, expand=True, margin=margin.only(100,10,100,200))  
        container_amostras.disabled = True
        menubar_principal_1.disabled = True
        page.update()

    def animacao_carregamento_terminar():
        container_pre_visualizacao.content = ft.Container(expand=True)
        container_amostras.disabled = False
        menubar_principal_1.disabled = False
        page.update()

    ###### Tela de adição de amostras

    def adicionar_amostra(e):
        page.dialog = dlg_modal_adicionar_amostra
        dlg_modal_adicionar_amostra.open = True
        page.update()
    
    def Inserir_SRA_na_fila(sra_codes):
        sra_codes = sra_codes.split(',')
        sra_codes = [item for item in sra_codes if item]
        sra_codes = [sra_code.strip().replace("\r\n", "") for sra_code in sra_codes]
        print("Baixar via SRA:", ', '.join(sra_codes))
        try:
            if not sra_codes:
                page.show_snack_bar(ft.SnackBar(content=ft.Text("Insira um código SRA válido.")))
                return
            dlg_modal_adicionar_amostra.open = False
            animacao_carregamento_iniciar()

            result = subprocess.check_output([venv_python, "Bilbo\\scripts\\Inserir_SRA_na_fila.py", current_license, servidor_selecionado["ip"], servidor_selecionado["usuario"]] + sra_codes).decode("utf-8")
            print(result)

            animacao_carregamento_terminar()
            atualizar_tabela()
            
            if "já foi adicionado" in result:
                page.show_snack_bar(ft.SnackBar(content=ft.Text(f"{result.strip()}")))

        except Exception as e:
            print("Erro ao baixar amostra: ", e)

    sra_code_field = ft.TextField(
        hint_text="""Insira um ou mais códigos\n\nEx:\nSRR0000001,\nSRR0000002,\nSRR0000003""", 
        border_radius=border_radius.all(4),
        multiline=True,
        min_lines=1, 
    )

    dlg_modal_adicionar_amostra = ft.AlertDialog(
                title=ft.Text("Adicionar via SRA"),
                content=sra_code_field,
                actions=[
                    ft.TextButton("Submeter", on_click= lambda e: Inserir_SRA_na_fila(sra_code_field.value), style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),width=200, height=40),
                ],
                actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    ###### Tela de confirmação de exclusão de amostras

    def excluir_amostras_selecionadas(e):
        page.dialog = dlg_modal_excluir_amostra
        dlg_modal_excluir_amostra.open = True
        page.update()

    def confirmar_exclusao(e):
        amostras_selecionadas_para_exclusao = []
        dlg_modal_excluir_amostra.open = False
        animacao_carregamento_iniciar()

        for i in tabela_amostras.rows:
            if i.cells[3].content.value == True:
                amostras_selecionadas_para_exclusao.append(i.cells[0].content.value)  
        print("Excluindo amostras: ", amostras_selecionadas_para_exclusao)

        for i in amostras_selecionadas_para_exclusao:
            if i in downloads:
                os.kill(downloads[i], signal.SIGTERM)
                del downloads[i]

        result = subprocess.check_output([venv_python, "Bilbo\\scripts\\Excluir_amostra.py", current_license, servidor_selecionado["ip"], servidor_selecionado["usuario"]] + amostras_selecionadas_para_exclusao).decode("utf-8")
        print(result)

        atualizar_tabela()
        animacao_carregamento_terminar()
        
    confirm_field = ft.TextField(
        hint_text="Digite 'Confirmar' para excluir as amostras selecionadas.", 
        border_radius=border_radius.all(4),
        multiline=False,
        expand=1
    )

    dlg_modal_excluir_amostra = ft.AlertDialog(
        title=ft.Text("Confirmar exclusão"),
        content=confirm_field,
        actions=[
            ft.TextButton("Excluir", on_click= lambda e: confirmar_exclusao(e) if confirm_field.value == 'Confirmar' else None, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),width=200, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    ###### Tabela de amostras

    def selecionar_amostra(e: ft.ControlEvent):
        data_row = e.control
        cells = data_row.cells
        first_cell = cells[0]
        value = first_cell.content.value
        print(value)

    def atualizar_tabela():
        print("Atualizando tabelas")
        container_progresso.controls[0].content = ft.Text(f"Tarefa atual: Atualizando tabelas", expand=True, color=ft.colors.ON_PRIMARY_CONTAINER, size=18)
        try:
            result = subprocess.check_output([venv_python, "Bilbo\\scripts\\Buscar_dados.py", current_license, servidor_selecionado["ip"], servidor_selecionado["usuario"]])
            metadata_content = result.decode("utf-8").split('\r\n')
            tabela_amostras.rows.clear()

            for metadata_line in metadata_content:
                if metadata_line:  
                    if ',' in metadata_line:
                        sra_code, status, tamanho = metadata_line.split(',')    
                    else:
                        sra_code = metadata_line
                    tabela_amostras.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(sra_code)),
                                ft.DataCell(ft.Text(tamanho)),  # Tamanho do arquivo
                                ft.DataCell(ft.Text(status)),  # Status
                                ft.DataCell(ft.Checkbox()),
                            ],
                            on_select_changed=selecionar_amostra,
                        )
                    )
            progress_bar.value = 0
            container_progresso.controls[0].content = ft.Text(f"Tarefa atual: Aguardando", expand=True, color=ft.colors.ON_PRIMARY_CONTAINER, size=18)
            print("Tabelas atualizadas")
            for i in tabela_amostras.rows:
                if i.cells[2].content.value == "Em fila":
                    animacao_carregamento_terminar()
                    download_fastq_via_SRA(i.cells[0].content.value)
                    break

        except Exception as e:
            print("Erro ao buscar dados: ", e)
        
        page.update()

    tabela_amostras = ft.DataTable(        
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Identificação")),
            ft.DataColumn(ft.Text("Tamanho")),
            ft.DataColumn(ft.Text("Status")),
            ft.DataColumn(ft.Text(" ")),
        ],
        rows=[
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("--------")),
                    ft.DataCell(ft.Text("--------")),
                    ft.DataCell(ft.Text("--------")),
                    ft.DataCell(ft.Checkbox()),
                ],
            ),                            
        ],        
    )    
    
    listview_amostras = ft.ListView(expand=1, spacing=10)
    listview_amostras.controls.append(tabela_amostras)
    listview_amostras.controls.append(ft.TextButton("Adicionar amostra via SRA", style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),width=200, height=40, on_click=adicionar_amostra))
    listview_amostras.controls.append(ft.TextButton("Excluir amostras selecionadas", style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), color=colors.RED),width=200, height=40, on_click=excluir_amostras_selecionadas))

    ###### Barra de progresso dos downloads

    downloads = {}

    def download_fastq_via_SRA(sra_code):
        print("Download_fastq_via_SRA")
        progress_bar.value = 0
        container_progresso.controls[0].content = ft.Text(f"Tarefa atual: Iniciando downloads", expand=True, color=ft.colors.ON_PRIMARY_CONTAINER, size=18)
        page.update()
        process = subprocess.Popen([venv_python, "Bilbo\\scripts\\Download_fastq_via_SRA.py", current_license, servidor_selecionado["ip"], servidor_selecionado["usuario"]], stdout=subprocess.PIPE)
        downloads[sra_code] = process.pid
        current_sra_code = None
        for line in iter(process.stdout.readline, b''):
            line = line.decode().strip()
            if line == "ATUALIZAR_TABELA":
                atualizar_tabela()
            else:
                sra_code, progress = line.split(',')
                progress = float(progress)
                if sra_code != current_sra_code:
                    progress_bar.value = 0
                    current_sra_code = sra_code  
                container_progresso.controls[0].content = ft.Text(f"Tarefa atual: Baixando amostra {sra_code}", expand=True, color=ft.colors.ON_PRIMARY_CONTAINER, size=18)
                progress_bar.value = progress / 100
                page.update()

    ###### Tela de visualização de etapas

    def selecionar_etapa(e: ft.ControlEvent):
        data_row = e.control
        cells = data_row.cells
        first_cell = cells[0]
        value = first_cell.content.value
        print("Etapa atual: ", value)

    def carregar_etapas():
        print("Verificando etapas")
        container_progresso.controls[0].content = ft.Text(f"Tarefa atual: Atualizando tabelas", expand=True, color=ft.colors.ON_PRIMARY_CONTAINER, size=18)
        try:
            result = subprocess.check_output([venv_python, "Bilbo\\scripts\\Buscar_dados_etapas.py", current_license, servidor_selecionado["ip"], servidor_selecionado["usuario"]])
            metadata_content = result.decode("utf-8").split('\r\n')
            tabela_etapas.rows.clear()

            for metadata_line in metadata_content:
                if metadata_line:  
                    if ',' in metadata_line:
                        sra_code, status, tamanho = metadata_line.split(',')    
                    else:
                        sra_code = metadata_line
                    tabela_etapas.rows.append(
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(sra_code)),
                                ft.DataCell(ft.Text(tamanho)),  # Tamanho do arquivo
                                # ft.DataCell(ft.Text(status)),  # Status
                                # ft.DataCell(ft.Checkbox()),
                            ],
                            on_select_changed=selecionar_amostra,
                        )
                    )
            progress_bar.value = 0
            container_progresso.controls[0].content = ft.Text(f"Tarefa atual: Aguardando", expand=True, color=ft.colors.ON_PRIMARY_CONTAINER, size=18)
            print("Etapas verificadas")
            for i in tabela_amostras.rows:
                if i.cells[2].content.value == "Em fila":
                    animacao_carregamento_terminar()
                    download_fastq_via_SRA(i.cells[0].content.value)
                    break

        except Exception as e:
            print("Erro ao buscar dados: ", e)
        
        page.update()

    tabela_etapas = ft.DataTable(        
        heading_row_color=ft.colors.BLACK12,
        columns=[
            ft.DataColumn(ft.Text("Procedimento")),
            ft.DataColumn(ft.Text("Quantidade")),
            # ft.DataColumn(ft.Text(" ")),
            # ft.DataColumn(ft.Text(" ")),
        ],
        rows=[
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Obtenção de amostras")),
                    ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=alignment.center)),
                ],
                on_select_changed=selecionar_etapa,
            ),
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Análise de qualidade")),
                    ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=alignment.center)),
                ],
                on_select_changed=selecionar_etapa,
            ),
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Trimmagem")),
                    ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=alignment.center)),
                ],
                on_select_changed=selecionar_etapa,
            ),
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Análise de qualidade (pós trimmagem)")),
                    ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=alignment.center)),
                ],
                on_select_changed=selecionar_etapa,
            ),
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Alinhamento")),
                    ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=alignment.center)),
                ],
                on_select_changed=selecionar_etapa,
            ),
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text("Quantificação")),
                    ft.DataCell(ft.Container(ft.Text("0"), width=80, alignment=alignment.center)),
                ],
                on_select_changed=selecionar_etapa,            
            ),                            
        ],        
    )    
    
    listview_etapas = ft.ListView(expand=1, spacing=10)
    listview_etapas.controls.append(tabela_etapas)

    ###### Página principal

    menubar_principal_1 = ft.MenuBar(
                controls=[                    
                    ft.SubmenuButton(
                        content=ft.Text("Arquivo"),
                        on_open=menubar_abrir_item,
                        on_close=menubar_fechar_item,
                        on_hover=menubar_passar_por_cima_item,
                        controls=[
                            ft.MenuItemButton(
                                content=ft.Text("Novo"),
                                style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                on_click=menubar_clicar_item
                            ),
                            ft.MenuItemButton(
                                content=ft.Text("Abrir"),
                                style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                on_click=menubar_clicar_item
                            ),
                            ft.Divider(),
                            ft.MenuItemButton(
                                content=ft.Text("Salvar"),
                                style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                on_click=menubar_clicar_item
                            ),
                            ft.MenuItemButton(
                                content=ft.Text("Salvar como"),
                                style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                on_click=menubar_clicar_item
                            ),
                            ft.Divider(),
                            ft.MenuItemButton(
                                content=ft.Text("Fechar"),
                                style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                on_click=menubar_clicar_item
                            ),
                            ft.MenuItemButton(
                                content=ft.Text("Sair"),
                                style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                on_click=menubar_clicar_item
                            )
                        ],
                    ),
                    ft.SubmenuButton(
                        content=ft.Text("Amostras"),
                        on_open=menubar_abrir_item,
                        on_close=menubar_fechar_item,
                        on_hover=menubar_passar_por_cima_item,
                        controls=[
                                ft.MenuItemButton(
                                    content=ft.Text("Adicionar FASTQ"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Adicionar via URL"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Adicionar via SRA"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=adicionar_amostra
                                )
                            ],
                    ),
                    ft.SubmenuButton(
                        content=ft.Text("Qualidade"),
                        on_open=menubar_abrir_item,
                        on_close=menubar_fechar_item,
                        on_hover=menubar_passar_por_cima_item,
                        controls=[
                                ft.MenuItemButton(
                                    content=ft.Text("Verificar qualidade"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Filtragem"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                            ],
                    ),
                    ft.SubmenuButton(
                        content=ft.Text("Alinhamento"),
                        on_open=menubar_abrir_item,
                        on_close=menubar_fechar_item,
                        on_hover=menubar_passar_por_cima_item,
                        controls=[
                                ft.MenuItemButton(
                                    content=ft.Text("Adicionar genoma de referência"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Alinhar com o genoma de referência"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),                                
                            ],
                    ),
                    ft.SubmenuButton(
                        content=ft.Text("Quantificação"),
                        on_open=menubar_abrir_item,
                        on_close=menubar_fechar_item,
                        on_hover=menubar_passar_por_cima_item,
                        controls=[
                                ft.MenuItemButton(
                                    content=ft.Text("Quantificar reads alinhadas"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                )
                            ],
                    ),
                    ft.SubmenuButton(
                        content=ft.Text("Expressão diferencial"),
                        on_open=menubar_abrir_item,
                        on_close=menubar_fechar_item,
                        on_hover=menubar_passar_por_cima_item,
                        controls=[
                                ft.MenuItemButton(
                                    content=ft.Text("Normalização"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Tabelas de expressão diferencial"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Obter genes diferencialmente expressos"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                )
                            ],
                    ),
                    ft.SubmenuButton(
                        content=ft.Text("Identificação"),
                        on_open=menubar_abrir_item,
                        on_close=menubar_fechar_item,
                        on_hover=menubar_passar_por_cima_item,
                        controls=[
                                ft.MenuItemButton(
                                    content=ft.Text("Indentificar transcritos via GFF"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Identificar transcritos via Blast"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),                                
                            ],
                    ),
                    ft.SubmenuButton(
                        content=ft.Text("Downstream"),
                        on_open=menubar_abrir_item,
                        on_close=menubar_fechar_item,
                        on_hover=menubar_passar_por_cima_item,
                        controls=[
                                ft.MenuItemButton(
                                    content=ft.Text("Análise de enriquecimento"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Distribuição de termos GO"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Reconstrução de rotas metabólicas"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                )
                            ],
                    ),
                    ft.SubmenuButton(
                        content=ft.Text("Relatórios"),
                        on_open=menubar_abrir_item,
                        on_close=menubar_fechar_item,
                        on_hover=menubar_passar_por_cima_item,
                        controls=[
                                ft.MenuItemButton(
                                    content=ft.Text("Controle de qualidade"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Resultados dos alinhamentos"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Resultados da análise de expressão"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Heatmaps"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Volcano plots"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("MA plots"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Heatmaps"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Perfis de expressão"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                )
                            ],
                    ),
                    ft.SubmenuButton(
                        content=ft.Text("Sobre"),
                        on_open=menubar_abrir_item,
                        on_close=menubar_fechar_item,
                        on_hover=menubar_passar_por_cima_item,
                        controls=[
                                ft.MenuItemButton(
                                    content=ft.Text("Manual de utilização"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Licença de uso"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),
                                ft.MenuItemButton(
                                    content=ft.Text("Versão do software"),
                                    close_on_click=False,
                                    style=ft.ButtonStyle(bgcolor={ft.MaterialState.HOVERED: ft.colors.PRIMARY_CONTAINER}),
                                    on_click=menubar_clicar_item
                                ),                                
                            ],
                    ),                    
                ]
            )
 
    menubar_principal_2 = ft.MenuBar(
                controls=[
                    ft.Row(
                        controls=(
                            ft.Container(
                                expand=1,
                                width=10,
                            ),
                            ft.Container(
                                expand=3,
                                content=usuario_text
                            ),
                            ft.Container(
                                expand=2,
                                content=ft.IconButton(
                                    icon=ft.icons.LIGHT_MODE,
                                    on_click=mudar_tema)
                            )
                        ),
                        alignment=ft.MainAxisAlignment.END
                    )        
                ]
    )

    container_amostras = ft.Container(  
                            expand=2,                             
                            border=border.all(1, ft.colors.BLACK),
                            border_radius=border_radius.all(3),
                            margin=margin.only(0,5,0,0),
                            content=listview_amostras)

    progress_bar = ft.ProgressBar(color=ft.colors.TERTIARY, value=0)

    container_progresso = ft.Column(
        expand=1,
        spacing=5,
        controls=[
            ft.Container(
            expand=5,
            border=border.all(1, ft.colors.BLACK),
            border_radius=border_radius.all(3),
            alignment = alignment.center,
            padding = padding.all(15),
            content=ft.Text("Tarefa atual: Aguardando", color=ft.colors.ON_PRIMARY_CONTAINER, expand=True, size=18)
            ),
            ft.Container(
            expand=1,
            border=border.all(1, ft.colors.BLACK),
            border_radius=border_radius.all(15),
            content=progress_bar,
            )
        ]
    )

    container_pre_visualizacao = ft.Container(
                            expand=2,
                            # width=600,
                            # height=500,
                            border=border.all(1, ft.colors.BLACK),
                            border_radius=border_radius.all(3),
                            margin=margin.only(0,5,0,0),
                            content=ft.Container(expand=True))

    container_menu_direita = ft.Container(  
                            expand=2,                             
                            border=border.all(1, ft.colors.BLACK),
                            border_radius=border_radius.all(3),
                            margin=margin.only(0,5,0,0),
                            content=listview_etapas)

    page.add(

        # Menubar
        ft.Row(
            expand=1,
            controls = [
                ft.Container(
                    margin=ft.Margin(-9, -11, 0, -9),
                    expand=30,
                    content=menubar_principal_1
                ),
                ft.Container(
                    expand=1,
                ),
                ft.Container(
                    alignment=ft.alignment.center_right,
                    margin=ft.Margin(0,-11,-9,-9),
                    expand=6,
                    content=menubar_principal_2
                )
            ]
        ),

        # Conteúdo
        ft.Row(
            expand=34,
            controls=[
                ft.Column(
                    expand=1,
                    controls=[
                        container_amostras,
                        container_progresso
                    ]
                ),
                ft.Column(
                    expand=1,
                    controls=[
                        container_pre_visualizacao,    
                        ft.Container(
                            # bgcolor=ft.colors.GREEN,
                            expand = 1,
                            # width=600,
                            # height=230,
                            border=border.all(1, ft.colors.BLACK),
                            border_radius=border_radius.all(3),
                        ),    
                    ],
                ),
                ft.Column(
                    expand=1,
                    controls=[
                        container_menu_direita,    
                        ft.Container(
                            # bgcolor=ft.colors.RED,
                            expand=1,
                            # width=450,
                            # height=230,
                            border=border.all(1, ft.colors.BLACK),
                            border_radius=border_radius.all(3),
                        ),    
                    ],
                )
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
            ))

    abrir_alerta_licenca(e=None)
    page.update()

ft.app(main, assets_dir=f"assets")

# Arrumar a tabela de etapas