import flet as ft

def create_table(columns, rows=None, toggle_select_all_handler=None, expand=True):
    cols = list(columns)

    if toggle_select_all_handler:
        cols[0] = ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_handler))

    table = ft.DataTable(
        heading_row_color="primary",
        data_row_color="surface",
        border=ft.border.all(0.5, "outline"),
        column_spacing=20,
        divider_thickness=0.5,
        columns=cols,
        rows=rows or [],
        expand=expand,
    )

    return table


def create_button(label, on_click, color="primary", width=200, height=40, expand=False):
    bgcolor = color
    text_color = "#FEFEFE"

    btn = ft.ElevatedButton(
        label,
        on_click=on_click,
        width=None if expand else width,
        height=height,
        expand=expand,
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
        expand=expand,
    )
