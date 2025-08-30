import flet as ft

def create_table(columns, rows=None, toggle_select_all_handler=None):
    """
    Cria um ft.DataTable com estilo mais agradável.
    Mantém a mesma assinatura original para não quebrar código que chama esta função.
    """
    # clone das colunas para não alterar a lista original externamente
    cols = list(columns)

    # se o caller pediu um "select all" no header, substitui a primeira coluna pelo checkbox
    if toggle_select_all_handler:
        cols[0] = ft.DataColumn(ft.Checkbox(on_change=toggle_select_all_handler))

    # DataTable estilizado — retorno continua sendo um ft.DataTable (compatível com o resto do código)
    table = ft.DataTable(
        # cabeçalho com azul forte e alta opacidade (como você pediu antes)
        heading_row_color=ft.colors.with_opacity(0.75, ft.colors.PRIMARY),

        # linhas com leve fundo para leitura (alternativa visual discreta)
        data_row_color=ft.colors.with_opacity(0.02, ft.colors.PRIMARY),

        # borda sutil azulada ao redor da tabela
        border=ft.border.all(0.6, ft.colors.with_opacity(0.12, ft.colors.PRIMARY)),

        # espaçamento entre colunas (melhora legibilidade)
        column_spacing=20,

        divider_thickness=0.5,

        columns=cols,
        rows=rows or [],
    )

    return table


def create_button(label, on_click, color=None, width=200, height=40):

    bgcolor = color if color is not None else ft.colors.PRIMARY
    text_color = ft.colors.WHITE if bgcolor != ft.colors.WHITE else ft.colors.BLACK

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
