import flet as ft
import base64

with open("assets/src/favicon_white.png", "rb") as img_file:
    image_data = img_file.read()
    image_base64 = base64.b64encode(image_data).decode('utf-8')

with open("assets/src/UFLA.png", "rb") as img_file:
    ufla_image_base64 = base64.b64encode(img_file.read()).decode('utf-8')

with open("assets/src/LFMP.png", "rb") as img_file:
    lfmp_image_base64 = base64.b64encode(img_file.read()).decode('utf-8')

async def show_login_interface(page, login, register, toggle_theme, username_input, password_input):
    page.controls.clear()
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    username_input.prefix_icon = ft.icons.PERSON_ROUNDED
    password_input.prefix_icon = ft.icons.LOCK_ROUNDED

    login_card = ft.Card(
        elevation=20,
        content=ft.Container(
            padding=ft.padding.symmetric(horizontal=30, vertical=40),
            width=400,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Image(src_base64=image_base64, width=100, height=100, fit=ft.ImageFit.CONTAIN),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER
                    ),
                    ft.Text(
                        "BILBO",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER
                    ),
                    ft.Text(
                        "Bioinformatics and RNA-Seq Lab Online",
                        size=14,
                        text_align=ft.TextAlign.CENTER,
                        color=ft.colors.ON_SURFACE_VARIANT
                    ),
                    ft.Divider(height=20),
                    username_input,
                    password_input,
                    ft.Container(height=5),
                    ft.ElevatedButton(
                        text="Login",
                        on_click=login,
                        icon=ft.icons.LOGIN,
                        bgcolor=ft.colors.PRIMARY,
                        color=ft.colors.WHITE,
                        height=45,
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
                    ),
                    ft.OutlinedButton(
                        text="Register",
                        on_click=register,
                        icon=ft.icons.APP_REGISTRATION,
                        height=45,
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
                    ),
                    ft.IconButton(
                        icon=ft.icons.LIGHT_MODE,
                        on_click=toggle_theme,
                        tooltip="Alternar Tema",
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                spacing=15
            )
        )
    )

    # Logos das instituições na parte inferior
    institution_logos = ft.Row(
        controls=[
            ft.Image(src_base64=ufla_image_base64, height=100, fit=ft.ImageFit.CONTAIN, tooltip="Universidade Federal de Lavras"),
            ft.Image(src_base64=lfmp_image_base64, height=100, fit=ft.ImageFit.CONTAIN, tooltip="Laboratório de Fisiologia Molecular de Plantas"),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        spacing=30
    )

    page.add(
        ft.Stack(
            [
                ft.Column(
                    controls=[
                        login_card,
                        ft.Container(height=30),
                        institution_logos
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True
                )
            ]
        )
    )
    page.update()