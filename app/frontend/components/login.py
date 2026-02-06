import flet as ft
import base64
import os
from frontend.procedures.translations import t, TRADUCOES

def get_image_64(path):
    if not os.path.exists(path):
        path = os.path.join("/app/frontend", path)

    if os.path.exists(path):
        with open(path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    return ""

image_base64 = get_image_64("assets/src/favicon_white.png")
ufla_image_base64 = get_image_64("assets/src/UFLA.png")
lfmp_image_base64 = get_image_64("assets/src/LFMP.png")

async def show_login_interface(page, login, register, toggle_theme, username_input, password_input):
    lang = page.session.get("lang") or "pt"

    async def change_language(new_lang):
        page.session.set("lang", new_lang)
        page.controls.clear()
        await show_login_interface(page, login, register, toggle_theme, username_input, password_input)
        page.update()

    async def set_pt(e): await change_language("pt")
    async def set_en(e): await change_language("en")
    async def set_es(e): await change_language("es")

    username_input.label = t("user_label", lang)
    username_input.prefix_icon = "person_rounded"

    password_input.label = t("pass_label", lang)
    password_input.prefix_icon = "lock_rounded"
    password_input.password = True
    password_input.can_reveal_password = True

    page.vertical_alignment = "center"
    page.horizontal_alignment = "center"

    language_selector = ft.Row(
        controls=[
            ft.TextButton("PT", on_click=set_pt,
                          style=ft.ButtonStyle(color="primary" if lang=="pt" else "on_surface")),
            ft.TextButton("EN", on_click=set_en,
                          style=ft.ButtonStyle(color="primary" if lang=="en" else "on_surface")),
            ft.TextButton("ES", on_click=set_es,
                          style=ft.ButtonStyle(color="primary" if lang=="es" else "on_surface")),
        ],
        alignment="center",
        spacing=5
    )

    login_card = ft.Card(
        elevation=20,
        content=ft.Container(
            padding=ft.padding.symmetric(horizontal=30, vertical=40),
            width=400,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[ft.Image(src_base64=image_base64, width=100, height=100, fit="contain")],
                        alignment="center"
                    ),
                    ft.Text("BILBO", size=28, weight="bold", text_align="center"),
                    ft.Text("Bioinformatics Lab Online", size=14, text_align="center", color="on_surface_variant"),
                    ft.Divider(height=10),
                    language_selector,
                    ft.Divider(height=10),
                    username_input,
                    password_input,
                    ft.Container(height=10),
                    ft.ElevatedButton(
                        text=t("btn_login", lang),
                        on_click=login,
                        icon="login",
                        width=400,
                        height=45,
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
                    ),
                    ft.OutlinedButton(
                        text=t("btn_register", lang),
                        on_click=register,
                        icon="app_registration",
                        width=400,
                        height=45,
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
                    ),
                    ft.IconButton(
                        icon="light_mode",
                        on_click=toggle_theme,
                        tooltip=t("toggle_theme", lang)
                    ),
                ],
                horizontal_alignment="stretch",
                spacing=15
            )
        )
    )

    institution_logos = ft.Row(
        controls=[
            ft.Image(src_base64=ufla_image_base64, height=60, fit="contain"),
            ft.Image(src_base64=lfmp_image_base64, height=60, fit="contain"),
        ],
        alignment="center",
        spacing=30
    )

    page.add(
        ft.Column(
            controls=[
                login_card,
                ft.Container(height=20),
                institution_logos
            ],
            alignment="center",
            horizontal_alignment="center",
            expand=True
        )
    )

    page.update()
