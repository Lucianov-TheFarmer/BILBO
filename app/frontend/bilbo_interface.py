import asyncio
import flet as ft
from functools import partial
from frontend.procedures.translations import t  # Importação das traduções
from .procedures.menu_operations import create_menubar, mudar_tema
from .procedures.sample_operations import adicionar_amostra, excluir_amostras_selecionadas, atualizar_tabela, atualizar_tabela_por_estagio, baixar_amostras
from .procedures.quality_analysis import show_quality_analysis_modal, create_tabela_amostras_qc, update_quality_analysis_table, delete_quality_analysis_results
from .procedures.trimmagem import show_trimmagem_modal, create_tabela_amostras_trimmadas, update_trimmagem_table, delete_trimmed_samples
from .procedures.quality_analysis_post_trim import show_quality_analysis_post_trim_modal, create_tabela_amostras_pos_trimmagem, update_tabela_amostras_pos_trimmagem, delete_quality_analysis_post_trim_results
from .procedures.alignment import show_alignment_modal, show_genomes_modal, create_tabela_alinhamento, update_tabela_alinhamento, excluir_alinhamento
from .procedures.quantification import show_quantification_modal, update_tabela_quantificacao, create_tabela_quantificacao, excluir_quantificacao
from .procedures.contrasts import show_contrasts_modal
from .procedures.utils import log_message
from .components.general_components import create_table, create_button
from .procedures.deg import show_deg_results
from .procedures.clustering import show_clustering
from .procedures.llm import show_llm
import websockets
import httpx
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)

uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.setLevel(logging.WARNING)

async def show_bilbo_interface(page, logout, username, token, user_id):
    logger.debug("Initializing interface for user_id=%s", user_id)

    lang = page.session.get("lang") or "pt"

    async def change_language(new_lang):
        page.session.set("lang", new_lang)
        page.controls.clear()
        await show_bilbo_interface(page, logout, username, token, user_id)
        page.update()

    async def set_pt(e): await change_language("pt")
    async def set_en(e): await change_language("en")
    async def set_es(e): await change_language("es")

    page.controls.clear()

    tabela_amostras_local = create_table(
        columns=[
            ft.DataColumn(ft.Text("ID / Name", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Size", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Status",  weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text(" ")),
            ft.DataColumn(ft.Text(t("menu_results", lang), weight=ft.FontWeight.BOLD)),
        ],
        rows=[],
    )

    tabela_amostras_qc = create_tabela_amostras_qc(page, token)
    tabela_amostras_trimmadas = create_tabela_amostras_trimmadas(page, token)
    tabela_amostras_pos_trimmagem = create_tabela_amostras_pos_trimmagem(page, token)
    tabela_alinhamento = create_tabela_alinhamento(page, token)
    tabela_quantificacao = create_tabela_quantificacao(page, token)

    container_amostras = ft.Container(
        expand=2,
        bgcolor="surface",
        border_radius=ft.border_radius.all(12),
        shadow=ft.BoxShadow(blur_radius=6, color="rgba(0, 0, 0, 0.01)"),
        padding=ft.padding.all(12),
        margin=ft.margin.only(0, 5, 0, 0),
        content=ft.ListView(
            expand=True,
            spacing=15,
            controls=[]
        )
    )

    async def toggle_buttons(tabela, controls):
        tabela_com_scroll = ft.Row(
            controls=[tabela],
            scroll=ft.ScrollMode.ALWAYS,
            expand=True
        )
        container_amostras.content.controls = [tabela_com_scroll] + controls
        page.update()

    async def adicionar_amostra_handler(e):
        await adicionar_amostra(e, page, token, container_menu_direita, tabela_amostras_local)

    async def excluir_amostras_selecionadas_handler(e):
        await excluir_amostras_selecionadas(e, page, token, container_menu_direita, tabela_amostras_local)

    async def baixar_amostras_handler(e):
        await baixar_amostras(e, page, token, container_menu_direita, tabela_amostras_local)

    async def show_quality_analysis_modal_handler(e):
        await show_quality_analysis_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)

    async def excluir_qualidade_handler(e):
        await delete_quality_analysis_results(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)

    async def show_trimmagem_modal_handler(e):
        await show_trimmagem_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela)

    async def excluir_amostras_trimmadas_handler(e):
        await delete_trimmed_samples(page, token, tabela_amostras_trimmadas, container_menu_direita, tabela_amostras_local, atualizar_tabela)

    async def show_quality_analysis_post_trim_modal_handler(e):
        await show_quality_analysis_post_trim_modal(page, token, container_menu_direita, tabela_amostras_trimmadas, atualizar_tabela, user_id)

    async def excluir_qualidade_post_trim_handler(e):
        await delete_quality_analysis_post_trim_results(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)

    async def iniciar_alinhamento_handler(e):
        await show_alignment_modal(page, token, user_id, atualizar_tabela, container_menu_direita, tabela_amostras_local)

    async def excluir_alinhamento_handler(e):
        selected_samples = [row.cells[0].content.value for row in tabela_alinhamento.rows if row.cells[4].content.value]
        if not selected_samples:
            await log_message(page, t("no_data", lang))
            return
        await excluir_alinhamento(page, token, user_id, selected_samples, container_menu_direita, tabela_amostras_local, atualizar_tabela)

    async def ver_genomas_referencia_handler(e):
        await show_genomes_modal(page, token, user_id)

    async def iniciar_quantificacao_handler(e):
        await show_quantification_modal(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)

    async def show_contrasts_modal_handler(e):
        await show_contrasts_modal(page, token, user_id)


    async def show_deg_results_handler(e):
        await show_deg_results(page, token, user_id, container_amostras)

    async def excluir_quantificacao_handler(e):
        selected_samples = [row.cells[0].content.value for row in tabela_quantificacao.rows if row.cells[4].content.value]
        if not selected_samples:
            await log_message(page, t("no_data", lang))
            return
        await excluir_quantificacao(page, token, user_id, selected_samples, container_menu_direita, tabela_amostras_local, atualizar_tabela)

    async def refresh_stage_counts():
        await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)

    async def atualizar_tabela_por_estagio_handler(e, stage_id):
        logger.info(f"Alterando para o estágio: {stage_id}")
        await atualizar_tabela_por_estagio(e, page, token, stage_id, tabela_amostras_local, user_id)

        if stage_id == 1:
            await toggle_buttons(
                tabela=tabela_amostras_local,
                controls=[
                    create_button(t("menu_add_sra", lang), adicionar_amostra_handler, expand=True),
                    create_button(t("btn_delete", lang), excluir_amostras_selecionadas_handler, color="red", expand=True),
                    create_button("Baixar Amostras", baixar_amostras_handler, color="green", expand=True), # Chave faltando, mantido texto fixo ou crie "btn_download"
                ]
            )
        elif stage_id == 2:
            await toggle_buttons(
                tabela=tabela_amostras_qc,
                controls=[
                    create_button(t("menu_check_quality", lang), show_quality_analysis_modal_handler, color="green", expand=True),
                    create_button(t("btn_delete", lang), excluir_qualidade_handler, color="red", expand=True),
                ]
            )
        elif stage_id == 3:
            await update_trimmagem_table(page, token)
            await toggle_buttons(
                tabela=tabela_amostras_trimmadas,
                controls=[
                    create_button(t("menu_trimming", lang), show_trimmagem_modal_handler, expand=True),
                    create_button(t("btn_delete", lang), excluir_amostras_trimmadas_handler, color="red", expand=True),
                ]
            )
        elif stage_id == 4:
            await update_tabela_amostras_pos_trimmagem(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)
            await toggle_buttons(
                tabela=tabela_amostras_pos_trimmagem,
                controls=[
                    create_button(t("menu_check_quality_post_trim", lang), show_quality_analysis_post_trim_modal_handler, color="green", expand=True),
                    create_button(t("btn_delete", lang), excluir_qualidade_post_trim_handler, color="red", expand=True),
                ]
            )
        elif stage_id == 5:
            await update_tabela_alinhamento(page, token, user_id)
            await toggle_buttons(
                tabela=tabela_alinhamento,
                controls=[
                    create_button(t("menu_align_genome", lang), iniciar_alinhamento_handler, expand=True),
                    create_button(t("btn_delete", lang), excluir_alinhamento_handler, color="red", expand=True),
                    create_button(t("menu_add_genome", lang), ver_genomas_referencia_handler, color="orange", expand=True),
                ]
            )
        elif stage_id == 6:
            await update_tabela_quantificacao(page, token, user_id)
            await toggle_buttons(
                tabela=tabela_quantificacao,
                controls=[
                    create_button(t("menu_quantify_reads", lang), iniciar_quantificacao_handler, color="green", expand=True),
                    create_button(t("btn_delete", lang), excluir_quantificacao_handler, color="red", expand=True),
                ]
            )
        elif stage_id == 7:
            # DEG stage: show DEG results in the actions area (container_amostras)
            await show_deg_results(page, token, user_id, container_amostras)
        elif stage_id == 9:
            await show_clustering(page, token, user_id, container_amostras, container_pre_visualizacao, refresh_stage_counts)
        elif stage_id == 10:
            await show_llm(page, token, user_id, container_amostras, container_pre_visualizacao, refresh_stage_counts)

    container_menu_direita = ft.Container(
        expand=1 ,
        bgcolor="surface",
        border_radius=ft.border_radius.all(12),
        shadow=ft.BoxShadow(blur_radius=6, color="rgba(0, 0, 0, 0.01)"),
        padding=ft.padding.all(12),
        margin=ft.margin.only(0, 5, 0, 0),
        content=ft.ListView(
            expand=1,
            spacing=15,
            controls=[
                ft.DataTable(
                    heading_row_color="primary",
                    data_row_color="surface",
                    border=ft.border.all(0.5, "outline"),
                    columns=[
                        ft.DataColumn(ft.Text("Stage", weight=ft.FontWeight.BOLD)),
                        ft.DataColumn(ft.Text("Qty", weight=ft.FontWeight.BOLD, text_align=ft.TextAlign.CENTER)),
                    ],
                    rows=[
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text(t("menu_samples", lang)),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=1)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=1)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text(t("menu_quality", lang)),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=2)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=2)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text(t("menu_trimming", lang)),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=3)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=3)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text(t("menu_check_quality_post_trim", lang)),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=4)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=4)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text(t("menu_alignment", lang)),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=5)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=5)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text(t("menu_quantification", lang)),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=6)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("0"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=6)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(
                                    ft.Container(
                                        content=ft.Text("Contrastes"),
                                        on_click=show_contrasts_modal_handler,
                                    )
                                ),
                                ft.DataCell(
                                    ft.Container(
                                        content=ft.Text("0"),
                                        alignment=ft.alignment.center,
                                        on_click=show_contrasts_modal_handler,
                                    )
                                ),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                            content=ft.Text(t("menu_deg", lang)),
                                            on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=7)
                                        )),
                                        ft.DataCell(ft.Container(
                                            content=ft.Text("0"),
                                            alignment=ft.alignment.center,
                                            on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=7)
                                        )),
                            ],
                        ),
                        # New pipeline stages (placeholders)
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Clusterização Semântica"),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=9)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("-"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=9)
                                )),
                            ],
                        ),
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Container(
                                    content=ft.Text("Interpretação por LLM"),
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=10)
                                )),
                                ft.DataCell(ft.Container(
                                    content=ft.Text("-"),
                                    alignment=ft.alignment.center,
                                    on_click=partial(atualizar_tabela_por_estagio_handler, stage_id=10)
                                )),
                            ],
                        ),
                    ],
                )
            ]
        )
    )

    # Chatbot UI temporarily disabled. If you want to re-enable it,
    # uncomment the block below and its inclusion in the layout.
    #
    # chat_log = ft.ListView(
    #     expand=True,
    #     spacing=10,
    #     controls=[ft.Text("Hello! How can I help you?" if lang=="en" else "Olá! Como posso ajudar?")]
    # )
    #
    # async def enviar_mensagem_chat(e: ft.ControlEvent):
    #     page = e.page
    #     texto_usuario = e.control.value
    #     if not texto_usuario:
    #         return
    #
    #     chat_log.controls.append(ft.Text(f"User: {texto_usuario}", italic=True, weight=ft.FontWeight.BOLD))
    #     e.control.value = ""
    #
    #     thinking_text = ft.Text("BILBO: Thinking..." if lang=="en" else "BILBO: Pensando...", selectable=True)
    #     chat_log.controls.append(thinking_text)
    #
    #     page.update()
    #
    #     try:
    #         headers = {
    #             "Authorization": f"Bearer {token}",
    #             "ngrok-skip-browser-warning": "true"
    #         }
    #         async with httpx.AsyncClient(timeout=60.0) as client:
    #             response = await client.post(
    #                 "http://localhost:8890/chat",
    #                 json={"message": texto_usuario, "model": "qwen3:0.6b"},
    #                 headers=headers
    #             )
    #
    #         if response.status_code == 200:
    #             data = response.json()
    #             full_reply = data.get("content", "Error: Empty response.")
    #             thinking_text.value = f"BILBO: {full_reply}"
    #         else:
    #             try:
    #                 error_data = response.json()
    #                 error_msg = error_data.get("error", response.text)
    #                 thinking_text.value = f"BILBO: Backend Error ({response.status_code}): {error_msg}"
    #             except Exception:
    #                  thinking_text.value = f"BILBO: Error ({response.status_code}): {response.text}"
    #             thinking_text.color = "red"
    #
    #     except httpx.RequestError as ex:
    #         thinking_text.value = f"BILBO: Connection error. {ex}"
    #         thinking_text.color = "red"
    #     except Exception as ex:
    #         thinking_text.value = f"BILBO: Unexpected error. {ex}"
    #         thinking_text.color = "red"
    #
    #     page.update()
    #
    # chat_input = ft.TextField(
    #     label=t("menu_about", lang) + " (Ask...)",
    #     expand=True,
    #     border_radius=ft.border_radius.all(20),
    #     border_color="outline",
    #     on_submit=enviar_mensagem_chat
    # )
    #
    # container_chatbot = ft.Container(
    #     expand=2,
    #     bgcolor="surface",
    #     border_radius=ft.border_radius.all(12),
    #     shadow=ft.BoxShadow(blur_radius=6, color="rgba(0, 0, 0, 0.01)"),
    #     padding=ft.padding.all(12),
    #     margin=ft.margin.only(0, 5, 0, 0),
    #     content=ft.Column(
    #         expand=True,
    #         controls=[
    #             ft.Text("BILBO AI Assistant", style=ft.TextThemeStyle.TITLE_MEDIUM, weight=ft.FontWeight.BOLD),
    #             chat_log,
    #             ft.Row(controls=[chat_input])
    #         ]
    #     )
    # )

    menubar_principal = create_menubar(page, token, container_menu_direita, container_amostras, tabela_amostras_local, atualizar_tabela, user_id)

    container_terminal = ft.Container(
        expand=2,
        bgcolor="surface",
        border_radius=ft.border_radius.all(12),
        shadow=ft.BoxShadow(blur_radius=6, color="rgba(0, 0, 0, 0.01)"),
        alignment=ft.alignment.top_left,
        padding=ft.padding.all(15),
        content=ft.ListView(
            expand=True,
            spacing=8,
            controls=[]
        )
    )
    page.container_terminal = container_terminal

    container_pre_visualizacao = ft.Container(
        expand=1,
        key="container_preview",
        bgcolor="surface",
        border_radius=ft.border_radius.all(12),
        shadow=ft.BoxShadow(blur_radius=6, color="rgba(0, 0, 0, 0.01)"),
        margin=ft.margin.only(0, 5, 0, 0),
        padding=ft.padding.all(12),
        alignment=ft.alignment.top_center,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.START,
            controls=[
                ft.Container(expand=True)
            ]
        )
    )

    async def toggle_theme_handler(e):
        await mudar_tema(page)

    page.add(
        ft.Row(
            controls=[
                ft.Container(
                    margin=ft.Margin(-5, -5, 0, 0),
                    expand=24,
                    content=menubar_principal
                ),
                ft.Container(
                    expand=1,
                ),

                ft.Container(
                    alignment=ft.alignment.center_right,
                    margin=ft.Margin(0, -7, -7, -7),
                    expand=16,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.END,
                        controls=[
                            ft.Text(f"{username}"),
                            ft.TextButton("PT", on_click=set_pt, style=ft.ButtonStyle(padding=5, color="primary" if lang=="pt" else "secondary")),
                            ft.TextButton("EN", on_click=set_en, style=ft.ButtonStyle(padding=5, color="primary" if lang=="en" else "secondary")),
                            ft.TextButton("ES", on_click=set_es, style=ft.ButtonStyle(padding=5, color="primary" if lang=="es" else "secondary")),

                            ft.IconButton(
                                icon="light_mode",
                                on_click=toggle_theme_handler,
                                tooltip=t("toggle_theme", lang)
                            ),
                            ft.IconButton(
                                icon="logout",
                                on_click=logout,
                                tooltip=t("menu_logout", lang)
                            )
                        ]
                    )
                )
            ]
        ),
        ft.Row(
            expand=34,
            controls=[
                ft.Column(
                    expand=2,
                    controls=[
                        container_menu_direita,
                    ]
                ),
                ft.Column(
                    expand=4,
                    controls=[
                        container_pre_visualizacao,
                    ],
                ),
                ft.Column(
                    expand=2,
                    controls=[
                        container_amostras,
                        container_terminal
                    ],
                )
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    )

    await atualizar_tabela_por_estagio_handler(None, 1)
    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)

    async def connect_websocket():
        async with websockets.connect(f"ws://bioinfo-container:8890/ws?token={token}") as websocket:
            while True:
                message = await websocket.recv()
                await log_message(page, message, container_terminal=container_terminal)
                # Update main tables when backend broadcasts events (start/completion)
                try:
                    await atualizar_tabela(page, token, container_menu_direita, tabela_amostras_local)
                except Exception as e:
                    logger.warning(f"Failed to atualizar_tabela from websocket event: {e}")
                try:
                    await update_quality_analysis_table(page, token, user_id)
                except Exception as e:
                    logger.warning(f"Failed to update_quality_analysis_table from websocket event: {e}")
                try:
                    await update_trimmagem_table(page, token)
                except Exception as e:
                    logger.warning(f"Failed to update_trimmagem_table from websocket event: {e}")
                try:
                    await update_tabela_amostras_pos_trimmagem(page, token, container_menu_direita, tabela_amostras_local, atualizar_tabela, user_id)
                except Exception as e:
                    logger.warning(f"Failed to update post-trim quality table from websocket event: {e}")
                try:
                    # If clustering finished, refresh clustering table when user is on that stage
                    if isinstance(message, str) and "Clustering completed" in message:
                        try:
                            await show_clustering(page, token, user_id, container_amostras, container_pre_visualizacao, refresh_stage_counts)
                        except Exception as ex:
                            logger.warning(f"Failed to refresh clustering UI: {ex}")
                except Exception:
                    pass
                page.update()

    page.run_task(connect_websocket)
