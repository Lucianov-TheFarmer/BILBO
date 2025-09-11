import flet as ft

def create_table(columns, rows=None, toggle_select_all_handler=None):
    cols = list(columns)

    if toggle_select_all_handler:
        cols[0] = ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_handler))

    table = ft.DataTable(
        heading_row_color="primary",
        data_row_color="surface",
        border=ft.border.all(0.5, "#000000"),
        column_spacing=20,
        divider_thickness=0.5,
        columns=cols,
        rows=rows or [],
    )

    return table


def create_button(label, on_click, color="primary", width=200, height=40):
    bgcolor = color
    text_color = "#FEFEFE"

    btn = ft.ElevatedButton(
        label,
        on_click=on_click,
        width=width,
        height=height,
        style=ft.ButtonStyle(
            bgcolor=bgcolor,
            color=text_color,
            shape=ft.RoundedRectangleBorder(radius=10),
            padding=ft.padding.symmetric(12, 6),
            elevation=3,
        ),
    )

    return ft.Container(
        content=btn,
        margin=ft.margin.only(0, 6, 0, 0),
    )