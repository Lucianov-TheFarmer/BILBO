import flet as ft

def create_table(columns, rows=None, toggle_select_all_handler=None):
    """
    Creates a reusable DataTable component.
    :param columns: List of column definitions (e.g., ft.DataColumn).
    :param rows: List of row definitions (optional).
    :param toggle_select_all_handler: Function to handle "select all" checkbox (optional).
    :return: A DataTable instance.
    """
    if toggle_select_all_handler:
        # Add a "select all" checkbox to the first column header
        columns[0] = ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_handler))

    return ft.DataTable(
        heading_row_color=ft.colors.BLACK12,
        columns=columns,
        rows=rows or [],
    )

def create_button(label, on_click, color=None, width=200, height=40):
    """
    Creates a reusable button component.
    :param label: Text to display on the button.
    :param on_click: Function to handle button clicks.
    :param color: Optional color for the button text.
    :param width: Width of the button.
    :param height: Height of the button.
    :return: A TextButton instance wrapped in a Container.
    """
    return ft.Container(
        content=ft.TextButton(
            label,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                color=color,
            ),
            width=width,
            height=height,
            on_click=on_click,
        ),
        margin=ft.margin.only(0, 5, 0, 0),
    )
