import flet as ft
import asyncio

async def show_contrasts_modal(page, token, user_id):
    """Displays a modal for defining contrasts."""
    contrast_rows = ft.Column(spacing=10)  # Container for all contrast rows

    def add_repetition_handler(row, side):
        """Adds a dropdown and remove button below the specified side of the row."""
        repetition_container = row.controls[1].controls[0 if side == "left" else 1]
        dropdown = ft.Dropdown(width=200)
        remove_button = ft.IconButton(
            icon=ft.icons.REMOVE_CIRCLE_OUTLINE,
            icon_color=ft.colors.RED,  # Make the trash icon red
            tooltip="Remover repetição",
            on_click=lambda e: remove_repetition(repetition_container, dropdown, remove_button),
        )
        repetition_row = ft.Row([dropdown, remove_button], spacing=5)
        repetition_container.controls.insert(-1, repetition_row)
        page.update()

    def remove_repetition(repetition_container, dropdown, remove_button):
        """Removes a dropdown and its associated remove button."""
        repetition_row = next(
            (control for control in repetition_container.controls if dropdown in control.controls),
            None,
        )
        if repetition_row:
            repetition_container.controls.remove(repetition_row)
        page.update()

    def add_contrast_handler(e):
        """Adds a new contrast row with editable fields and repetition buttons."""
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
                            on_click=lambda e: add_repetition_handler(new_row, "left"),
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
                            on_click=lambda e: add_repetition_handler(new_row, "right"),
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
        page.update()

    def clear_repetitions(row, side):
        """Clears all repetitions for the specified side."""
        repetition_container = row.controls[1].controls[0 if side == "left" else 1]
        # Iterate over all dropdown rows and remove them
        for control in list(repetition_container.controls[:-1]):  # Exclude the buttons row
            if isinstance(control, ft.Row) and len(control.controls) > 0:
                dropdown = control.controls[0]
                remove_button = control.controls[1]
                remove_repetition(repetition_container, dropdown, remove_button)
        page.update()

    def remove_contrast_handler(row):
        """Removes a contrast row and its divider."""
        index = contrast_rows.controls.index(row)
        contrast_rows.controls.pop(index)  # Remove the row
        if index < len(contrast_rows.controls) and isinstance(contrast_rows.controls[index], ft.Divider):
            contrast_rows.controls.pop(index)  # Remove the divider below the row
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
                "Fechar",
                on_click=lambda e: dlg_modal_contrasts.open and page.update(),
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
                width=100,
                height=40,
            ),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.open(dlg_modal_contrasts)
