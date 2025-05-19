import flet as ft
import asyncio
import httpx
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_samples():
    """Fetch samples from the backend."""
    logger.info("Fetching samples from the backend.")
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/contrasts/samples")
        response.raise_for_status()
        samples = response.json()
        logger.info(f"Fetched samples: {samples}")
        return samples

async def fetch_existing_contrasts(token):
    """Fetch existing contrasts from the backend."""
    logger.info("Fetching existing contrasts from the backend.")
    headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:8000/contrasts/", headers=headers)
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
    samples = await fetch_samples()
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
        dropdown = ft.Dropdown(width=200)
        await populate_dropdown(dropdown, selected_value)
        dropdown.on_change = lambda e: used_samples.add(dropdown.value)
        logger.info(f"Dropdown created for side {side}.")
        remove_button = ft.IconButton(
            icon=ft.icons.REMOVE_CIRCLE_OUTLINE,
            icon_color=ft.colors.RED,
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
            response = await client.delete(f"http://localhost:8000/contrasts/{contrast_id}", headers=headers)
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
                                        name=ft.icons.REMOVE,
                                        size=24,
                                        color=ft.colors.BLACK38,
                                    ),
                                    right_field,
                                    ft.IconButton(
                                        icon=ft.icons.DELETE,
                                        icon_color=ft.colors.RED,
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
                    contrast_rows.controls.append(ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38))
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
        left_field = ft.Column(
            controls=[
                ft.TextField(label="Grupo 1", width=200, text_align=ft.TextAlign.CENTER),
            ],
            spacing=5,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        right_field = ft.Column(
            controls=[
                ft.TextField(label="Grupo 2", width=200, text_align=ft.TextAlign.CENTER),
            ],
            spacing=5,
            alignment=ft.MainAxisAlignment.CENTER,
        )
        left_repetition_controls = ft.Column(
            controls=[
                ft.Column(spacing=5),  # Container for repetitions
                ft.Column(
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
                                color=ft.colors.RED,
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=10,
                ),
            ],
            spacing=10,
        )
        right_repetition_controls = ft.Column(
            controls=[
                ft.Column(spacing=5),  # Container for repetitions
                ft.Column(
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
                                color=ft.colors.RED,
                            ),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=10,
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
                            name=ft.icons.REMOVE,  # Non-interactive icon
                            size=24,
                            color=ft.colors.BLACK38,
                        ),
                        right_field,
                        ft.IconButton(
                            icon=ft.icons.DELETE,
                            icon_color=ft.colors.RED,  # Make the trash icon red
                            tooltip="Excluir contraste",
                            on_click=lambda e: remove_contrast_handler(new_row),
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
        contrast_rows.controls.append(ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38))
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
    existing_contrasts = await fetch_existing_contrasts(token)
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
                                name=ft.icons.REMOVE,
                                size=24,
                                color=ft.colors.BLACK38,
                            ),
                            right_field,
                            ft.IconButton(
                                icon=ft.icons.DELETE,
                                icon_color=ft.colors.RED,
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
            contrast_rows.controls.append(ft.Divider(height=1, thickness=1, color=ft.colors.BLACK38))

    def close_modal_handler(e):
        """Handles the close button click."""
        logger.info("Close button clicked. Sending data to backend and closing modal.")

        # Prepare data to send to the backend
        contrasts_data = []
        for i in range(0, len(contrast_rows.controls), 2):  # Skip dividers
            row = contrast_rows.controls[i]
            left_group = row.controls[0].controls[0].controls[0].value  # Access TextField value for Grupo 1
            right_group = row.controls[0].controls[2].controls[0].value  # Access TextField value for Grupo 2

            left_repetitions = [
                dropdown.controls[0].value for dropdown in row.controls[1].controls[0].controls[:-1]
                if isinstance(dropdown, ft.Row) and dropdown.controls[0].value
            ]
            right_repetitions = [
                dropdown.controls[0].value for dropdown in row.controls[1].controls[1].controls[:-1]
                if isinstance(dropdown, ft.Row) and dropdown.controls[0].value
            ]

            contrasts_data.append({
                "group_1": left_group,
                "group_2": right_group,
                "repetitions_1": left_repetitions,
                "repetitions_2": right_repetitions,
            })

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
                        "http://localhost:8000/contrasts/save",
                        json={"contrasts": contrasts_data},
                        headers=headers,
                    )
                    if response.status_code == 200:
                        logger.info("Data successfully sent to backend.")
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
            width=600,
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
