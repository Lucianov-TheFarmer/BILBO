import flet as ft
import asyncio
import httpx
import logging
from .utils import log_message  # Import log_message

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_samples(token):
    """Fetch samples from the backend."""
    logger.info("Fetching samples from the backend.")
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8890/contrasts/samples", headers=headers)
            response.raise_for_status()
            samples = response.json()
            logger.info(f"Fetched samples: {samples}")
            return samples
        except httpx.HTTPStatusError as ex:
            if ex.response.status_code == 404:
                logger.warning("No samples found (404).")
                return None
            else:
                logger.error(f"Error fetching samples: {ex}")
                raise

async def fetch_existing_contrasts(token):
    """Fetch existing contrasts from the backend."""
    logger.info("Fetching existing contrasts from the backend.")
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8890/contrasts/", headers=headers)
        response.raise_for_status()
        contrasts = response.json()
        logger.info(f"Fetched existing contrasts: {contrasts}")
        return contrasts

async def show_contrasts_modal(page, token, user_id):
    """Displays a modal for defining contrasts."""
    logger.info("Opening contrasts modal.")
    contrast_rows = ft.Column(spacing=10)  # Container for all contrast rows
    used_samples = set()  # Track used sample IDs

    # Fetch samples and build sra_code -> id mapping
    try:
        samples = await fetch_samples(token)
    except httpx.HTTPStatusError as ex:
        if ex.response.status_code == 401:
            await log_message(page, "Sessão expirada ou inválida. Faça login novamente para definir contrastes.")
            return
        await log_message(page, f"Erro ao buscar amostras para contrastes: HTTP {ex.response.status_code}.")
        return
    except Exception as ex:
        logger.error(f"Error fetching samples: {ex}", exc_info=True)
        await log_message(page, "Erro ao buscar amostras para contrastes.")
        return

    if samples is None or len(samples) == 0:
        await log_message(page, "Nenhuma amostra disponível para definição de contrastes.")
        return

    sra_code_to_id = {}
    for sample in samples:
        # Remove .txt if present for mapping
        sra_code = sample["name"].replace(".txt", "")
        sra_code_to_id[sra_code] = sample["id"]

    async def populate_dropdown(dropdown, selected_value=None):
        """Populate dropdown with available samples."""
        logger.info("Populating dropdown with available samples.")
        dropdown.options = [
            ft.dropdown.Option(sample["id"], sample["name"])
            for sample in samples if (sample["id"] not in used_samples) or (selected_value is not None and sample["id"] == selected_value)
        ]
        if selected_value is not None:
            dropdown.value = selected_value
            used_samples.add(selected_value)
        logger.info(f"Dropdown options populated: {dropdown.options}")
        page.update()

    async def add_repetition_handler(row, side, selected_value=None):
        """Adds a dropdown and remove button below the specified side of the row."""
        logger.info(f"Adding repetition handler for side: {side}")
        repetition_container = row.controls[1].controls[0 if side == "left" else 1]
        dropdown = ft.Dropdown()
        await populate_dropdown(dropdown, selected_value)
        # Corrigir: garantir que o valor do dropdown seja atualizado no objeto Python
        def on_dropdown_change(e):
            dropdown.value = e.control.value  # Sincroniza valor do objeto Python
            used_samples.add(dropdown.value)
            logger.info(f"Dropdown changed: {dropdown.value}")
        dropdown.on_change = on_dropdown_change
        logger.info(f"Dropdown created for side {side}.")
        remove_button = ft.IconButton(
            icon="remove_circle_outline",
            icon_color="red",
            tooltip="Remover repetição",
            on_click=lambda e: remove_repetition(repetition_container, dropdown, remove_button),
        )
        repetition_row = ft.Row([dropdown, remove_button], spacing=5)
        repetition_container.controls.insert(-1, repetition_row)
        logger.info(f"Repetition row added for side {side}.")
        page.update()

    def remove_repetition(repetition_container, dropdown, remove_button):
        """Removes a dropdown and its associated remove button."""
        logger.info("Removing repetition.")
        repetition_row = next(
            (control for control in repetition_container.controls if dropdown in control.controls),
            None,
        )
        if repetition_row:
            repetition_container.controls.remove(repetition_row)
            logger.info("Repetition removed.")
        page.update()

    def clear_repetitions(row, side):
        """Clears all repetitions for the specified side."""
        logger.info(f"Clearing repetitions for side: {side}")
        repetition_container = row.controls[1].controls[0 if side == "left" else 1]
        for control in list(repetition_container.controls[:-1]):
            if isinstance(control, ft.Row) and len(control.controls) > 0:
                dropdown = control.controls[0]
                remove_button = control.controls[1]
                remove_repetition(repetition_container, dropdown, remove_button)
        logger.info(f"Repetitions cleared for side: {side}")
        page.update()

    async def delete_contrast_backend(contrast_id):
        """Delete a contrast from the backend."""
        logger.info(f"Deleting contrast {contrast_id} from backend.")
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        async with httpx.AsyncClient() as client:
            response = await client.delete(f"http://localhost:8890/contrasts/{contrast_id}", headers=headers)
            if response.status_code == 200:
                logger.info(f"Contrast {contrast_id} deleted from backend.")
            else:
                logger.error(f"Failed to delete contrast {contrast_id} from backend: {response.status_code} - {response.text}")

    def remove_contrast_handler(row, contrast_id=None):
        """Removes a contrast row and its divider, and optionally from backend."""
        logger.info("Removing a contrast row.")
        try:
            index = contrast_rows.controls.index(row)
            contrast_rows.controls.pop(index)
            if index < len(contrast_rows.controls) and isinstance(contrast_rows.controls[index], ft.Divider):
                contrast_rows.controls.pop(index)
            logger.info("Contrast row removed.")
            page.update()
        except ValueError:
            logger.warning("Tried to remove a row that is not in the list (already removed).")
        if contrast_id is not None:
            async def after_delete():
                await delete_contrast_backend(contrast_id)
                # Atualiza a lista de contrastes do frontend após exclusão
                # Remove todos os controles e reconstrói a lista
                contrast_rows.controls.clear()
                # Recarrega os contrastes do backend
                existing_contrasts = await fetch_existing_contrasts(token)
                for contrast in existing_contrasts:
                    group_1, reps_1, group_2, reps_2 = parse_contrast_name(contrast["name"])
                    reps_1_ids = [sra_code_to_id.get(rep, None) for rep in reps_1 if rep in sra_code_to_id]
                    reps_2_ids = [sra_code_to_id.get(rep, None) for rep in reps_2 if rep in sra_code_to_id]

                    left_field = ft.Column(
                        controls=[
                            ft.TextField(label="Grupo 1", value=group_1, width=200, text_align=ft.TextAlign.CENTER, read_only=True),
                        ],
                        spacing=5,
                        alignment=ft.MainAxisAlignment.CENTER,
                    )
                    right_field = ft.Column(
                        controls=[
                            ft.TextField(label="Grupo 2", value=group_2, width=200, text_align=ft.TextAlign.CENTER, read_only=True),
                        ],
                        spacing=5,
                        alignment=ft.MainAxisAlignment.CENTER,
                    )
                    left_repetition_controls = ft.Column(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text("; ".join([str(rep) for rep in reps_1]), width=200) if reps_1 else ft.Text("-", width=200)
                                ],
                                spacing=5,
                            ),
                        ],
                        spacing=10,
                    )
                    right_repetition_controls = ft.Column(
                        controls=[
                            ft.Column(
                                controls=[
                                    ft.Text("; ".join([str(rep) for rep in reps_2]), width=200) if reps_2 else ft.Text("-", width=200)
                                ],
                                spacing=5,
                            ),
                        ],
                        spacing=10,
                    )
                    new_row = ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    left_field,
                                    ft.Icon(
                                        name="remove",
                                        size=24,
                                        color="black38",
                                    ),
                                    right_field,
                                    ft.IconButton(
                                        icon="delete",
                                        icon_color="red",
                                        tooltip="Excluir contraste",
                                        on_click=lambda e, row_ref=None, cid=contrast["id"]: remove_contrast_handler(new_row, contrast_id=cid),
                                    ),
                                ],
                                spacing=20,
                                alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                            ),
                            ft.Row(
                                controls=[
                                    left_repetition_controls,
                                    right_repetition_controls,
                                ],
                                spacing=20,
                                alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                            ),
                        ],
                        spacing=10,
                    )
                    contrast_rows.controls.append(new_row)
                    contrast_rows.controls.append(ft.Divider(height=1, thickness=1, color="black38"))
                page.update()
            run_async(after_delete())

    def parse_contrast_name(name):
        """Parses the contrast name to extract groups and repetitions."""
        try:
            left, right = name.split("*")
            group_1, reps_1 = left.split("(", 1)
            group_2, reps_2 = right.split("(", 1)
            group_1 = group_1.strip()
            group_2 = group_2.strip()
            reps_1 = reps_1.rstrip(")").split(";") if "(" in left else []
            reps_2 = reps_2.rstrip(")").split(";") if "(" in right else []
            return group_1, reps_1, group_2, reps_2
        except Exception as ex:
            logger.error(f"Error parsing contrast: {name} - {ex}")
            return name, [], "", []

    def add_contrast_handler(e):
        """Adds a new contrast row with editable fields and repetition buttons."""
        logger.info("Adding a new contrast row.")
        # Coluna esquerda: Grupo 1
        left_field = ft.TextField(
            label="Grupo 1",
            width=200,
            text_align=ft.TextAlign.CENTER,
            max_length=10  # Limita a 10 caracteres
        )
        left_repetition_column = ft.Column(spacing=5)
        left_buttons_row = ft.Row(
            controls=[
                ft.TextButton(
                    "Adicionar repetição",
                    on_click=lambda e: run_async(add_repetition_handler(new_row, "left")),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                ),
                ft.TextButton(
                    "Limpar repetições",
                    on_click=lambda e: clear_repetitions(new_row, "left"),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=10),
                        color="red",
                    ),
                ),
            ],
            spacing=10,
            alignment=ft.MainAxisAlignment.START,
        )
        left_column = ft.Column(
            controls=[
                left_field,
                left_repetition_column,
                left_buttons_row,
            ],
            spacing=10,
            alignment=ft.MainAxisAlignment.START,
        )

        # Coluna direita: Grupo 2
        right_field = ft.TextField(
            label="Grupo 2",
            width=200,
            text_align=ft.TextAlign.CENTER,
            max_length=10  # Limita a 10 caracteres
        )
        right_repetition_column = ft.Column(spacing=5)
        right_buttons_row = ft.Row(
            controls=[
                ft.TextButton(
                    "Adicionar repetição",
                    on_click=lambda e: run_async(add_repetition_handler(new_row, "right")),
                    style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                ),
                ft.TextButton(
                    "Limpar repetições",
                    on_click=lambda e: clear_repetitions(new_row, "right"),
                    style=ft.ButtonStyle(
                        shape=ft.RoundedRectangleBorder(radius=10),
                        color="red",
                    ),
                ),
            ],
            spacing=10,
            alignment=ft.MainAxisAlignment.START,
        )
        right_column = ft.Column(
            controls=[
                right_field,
                right_repetition_column,
                right_buttons_row,
            ],
            spacing=10,
            alignment=ft.MainAxisAlignment.START,
        )

        # Linha dos campos de grupo e lixeira
        group_row = ft.Row(
            controls=[
                left_field,
                ft.Icon(
                    name="remove",  # Non-interactive icon
                    size=24,
                    color="black38",
                ),
                right_field,
                ft.IconButton(
                    icon="delete",
                    icon_color="red",  # Make the trash icon red
                    tooltip="Excluir contraste",
                    on_click=lambda e: remove_contrast_handler(new_row),
                ),
            ],
            spacing=20,
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        )

        # Linha das repetições e botões, alinhadas verticalmente
        repetitions_row = ft.Row(
            controls=[
                ft.Column(
                    controls=[
                        left_repetition_column,
                        left_buttons_row,
                    ],
                    spacing=10,
                    alignment=ft.MainAxisAlignment.START,
                ),
                ft.Column(
                    controls=[
                        right_repetition_column,
                        right_buttons_row,
                    ],
                    spacing=10,
                    alignment=ft.MainAxisAlignment.START,
                ),
            ],
            spacing=40,
            alignment=ft.MainAxisAlignment.START,
        )

        new_row = ft.Column(
            controls=[
                group_row,
                repetitions_row,
            ],
            spacing=10,
        )
        contrast_rows.controls.append(new_row)
        contrast_rows.controls.append(ft.Divider(height=1, thickness=1, color="black38"))
        logger.info("New contrast row added.")
        page.update()

    # Helper to run async code in both contexts (button click and modal build)
    def run_async(coro):
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(coro)
            return task
        except RuntimeError:
            return asyncio.run(coro)

    # --- Build existing contrasts visually ---
    try:
        existing_contrasts = await fetch_existing_contrasts(token)
    except httpx.HTTPStatusError as ex:
        if ex.response.status_code == 401:
            await log_message(page, "Sessão expirada ou inválida. Faça login novamente para carregar contrastes.")
            return
        await log_message(page, f"Erro ao carregar contrastes existentes: HTTP {ex.response.status_code}.")
        return
    except Exception as ex:
        logger.error(f"Error fetching existing contrasts: {ex}", exc_info=True)
        await log_message(page, "Erro ao carregar contrastes existentes.")
        return

    if existing_contrasts:
        for contrast in existing_contrasts:
            group_1, reps_1, group_2, reps_2 = parse_contrast_name(contrast["name"])
            reps_1_ids = [sra_code_to_id.get(rep, None) for rep in reps_1 if rep in sra_code_to_id]
            reps_2_ids = [sra_code_to_id.get(rep, None) for rep in reps_2 if rep in sra_code_to_id]

            left_field = ft.Column(
                controls=[
                    ft.TextField(label="Grupo 1", value=group_1, width=200, text_align=ft.TextAlign.CENTER, read_only=True),
                ],
                spacing=5,
                alignment=ft.MainAxisAlignment.CENTER,
            )
            right_field = ft.Column(
                controls=[
                    ft.TextField(label="Grupo 2", value=group_2, width=200, text_align=ft.TextAlign.CENTER, read_only=True),
                ],
                spacing=5,
                alignment=ft.MainAxisAlignment.CENTER,
            )
            # Show repetitions as text, not dropdowns, and no add/clear/remove buttons
            left_repetition_controls = ft.Column(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text("\n".join([str(rep) for rep in reps_1]), width=200) if reps_1 else ft.Text("-", width=200)
                        ],
                        spacing=5,
                    ),
                ],
                spacing=10,
            )
            right_repetition_controls = ft.Column(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text("\n".join([str(rep) for rep in reps_2]), width=200) if reps_2 else ft.Text("-", width=200)
                        ],
                        spacing=5,
                    ),
                ],
                spacing=10,
            )
            new_row = ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            left_field,
                            ft.Icon(
                                name="remove",
                                size=24,
                                color="black38",
                            ),
                            right_field,
                            ft.IconButton(
                                icon="delete",
                                icon_color="red",
                                tooltip="Excluir contraste",
                                on_click=lambda e, row_ref=None, cid=contrast["id"]: remove_contrast_handler(new_row, contrast_id=cid),
                            ),
                        ],
                        spacing=20,
                        alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                    ),
                    ft.Row(
                        controls=[
                            left_repetition_controls,
                            right_repetition_controls,
                        ],
                        spacing=20,
                        alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                    ),
                ],
                spacing=10,
            )
            contrast_rows.controls.append(new_row)
            contrast_rows.controls.append(ft.Divider(height=1, thickness=1, color="black38"))

    def close_modal_handler(e):
        """Handles the close button click."""
        logger.info("Close button clicked. Sending data to backend and closing modal.")

        contrasts_data = []
        logger.info(f"contrast_rows.controls: {contrast_rows.controls}")
        for i in range(0, len(contrast_rows.controls), 2):  # Skip dividers
            row = contrast_rows.controls[i]
            logger.info(f"Processing row {i}: {row}")
            group_row = row.controls[0]  # ft.Row: [left_field, icon, right_field, delete_button]

            # Corrigir: pode ser ft.TextField ou ft.Column (quando já salvo)
            def get_group_value(field):
                # Se for TextField, retorna .value
                if hasattr(field, "value"):
                    return field.value
                # Se for Column, pega o primeiro controle e retorna .value se for TextField
                if isinstance(field, ft.Column) and field.controls:
                    ctrl = field.controls[0]
                    if hasattr(ctrl, "value"):
                        return ctrl.value
                # fallback
                return ""

            left_field = group_row.controls[0]
            right_field = group_row.controls[2]
            left_group = get_group_value(left_field)
            right_group = get_group_value(right_field)
            logger.info(f"left_group: {left_group}, right_group: {right_group}")

            repetitions_row = row.controls[1]  # ft.Row: [left_column, right_column]
            left_column = repetitions_row.controls[0]  # ft.Column
            right_column = repetitions_row.controls[1]  # ft.Column

            logger.info(f"left_column.controls: {getattr(left_column, 'controls', None)}")
            logger.info(f"right_column.controls: {getattr(right_column, 'controls', None)}")

            left_repetition_rows = left_column.controls[1:-1]
            right_repetition_rows = right_column.controls[1:-1]
            logger.info(f"left_repetition_rows: {left_repetition_rows}, right_repetition_rows: {right_repetition_rows}")

            def extract_repetitions(repetition_rows):
                reps = []
                logger.info(f"extract_repetitions: repetition_rows = {repetition_rows}")
                for idx, row in enumerate(repetition_rows):
                    logger.info(f"extract_repetitions: row[{idx}] = {row}, type={type(row)}")
                    if isinstance(row, ft.Row) and len(row.controls) > 0:
                        dropdown = row.controls[0]
                        logger.info(f"extract_repetitions: row[{idx}].dropdown = {dropdown}, value={getattr(dropdown, 'value', None)}")
                        if hasattr(dropdown, "value") and dropdown.value:
                            reps.append(dropdown.value)
                logger.info(f"Extracted repetitions: {reps}")
                return reps

            left_repetitions = extract_repetitions(left_repetition_rows)
            right_repetitions = extract_repetitions(right_repetition_rows)
            logger.info(f"left_repetitions: {left_repetitions}, right_repetitions: {right_repetitions}")

            if left_group and right_group and left_repetitions and right_repetitions:
                contrasts_data.append({
                    "group_1": left_group,
                    "group_2": right_group,
                    "repetitions_1": left_repetitions,
                    "repetitions_2": right_repetitions,
                })
            else:
                logger.info(f"Contrast not added: left_group={left_group}, right_group={right_group}, left_repetitions={left_repetitions}, right_repetitions={right_repetitions}")

        logger.info(f"Prepared contrasts data: {contrasts_data}")

        # Send data to the backend
        async def send_data():
            try:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "ngrok-skip-browser-warning": "true"
                }
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://localhost:8890/contrasts/save",
                        json={"contrasts": contrasts_data},
                        headers=headers,
                    )
                    if response.status_code == 200:
                        logger.info("Data successfully sent to backend.")
                        # Formatação aprimorada da mensagem de múltiplos contrastes
                        contrast_names_list = [f"{c['group_1']} x {c['group_2']}" for c in contrasts_data]
                        if len(contrast_names_list) == 1:
                            msg = f"Contraste {contrast_names_list[0]} salvo com sucesso."
                        else:
                            msg = "Contrastes "
                            msg += ", ".join(contrast_names_list[:-1])
                            msg += f" e {contrast_names_list[-1]} salvo com sucesso."
                        await log_message(page, msg)
                    else:
                        logger.error(f"Failed to send data to backend: {response.status_code} - {response.text}")
            except Exception as ex:
                logger.error(f"Error while sending data to backend: {ex}", exc_info=True)

        asyncio.run(send_data())

        dlg_modal_contrasts.open = False
        page.update()

    dlg_modal_contrasts = ft.AlertDialog(
        title=ft.Text("Definir Contrastes"),
        content=ft.Container(
            content=ft.ListView(
                controls=[
                    ft.Container(height=3),
                    contrast_rows,
                    ft.Container(
                        content=ft.TextButton(
                            "Adicionar contraste",
                            on_click=add_contrast_handler,
                            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                        ),
                        alignment=ft.alignment.center,
                    ),
                ],                
                spacing=20,
            ),
            width=700,
            height=500,  # Set height to enable scrolling
        ),
        actions=[
            ft.TextButton(
                "Salvar",
                on_click=close_modal_handler,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=100,
                height=40,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    logger.info("Opening modal dialog.")
    page.open(dlg_modal_contrasts)
