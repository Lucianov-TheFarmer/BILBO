# filepath: /c:/Users/vitor/Documents/Projetos/Docker server implementation/app/frontend/login.py
import flet as ft
import asyncio
import base64

# Carrega as imagens e converte para base64
with open("assets/src/favicon_white.png", "rb") as img_file:
    image_data = img_file.read()
    image_base64 = base64.b64encode(image_data).decode('utf-8')

with open("assets/src/UFLA.png", "rb") as img_file:
    ufla_image_base64 = base64.b64encode(img_file.read()).decode('utf-8')

with open("assets/src/LFMP.png", "rb") as img_file:
    lfmp_image_base64 = base64.b64encode(img_file.read()).decode('utf-8')

async def show_login_interface(page, login, register, toggle_theme, username_input, password_input, result):
    page.controls.clear()
    page.add(
        ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Image(
                                    src_base64=ufla_image_base64,
                                    width=90,
                                    height=90,
                                    fit=ft.ImageFit.CONTAIN,
                                ),
                                border_radius=ft.border_radius.all(8),
                                padding=10,
                            ),
                            ft.Container(
                                content=ft.Image(
                                    src_base64=image_base64,
                                    width=90,
                                    height=90,
                                    fit=ft.ImageFit.CONTAIN,
                                ),
                                border_radius=ft.border_radius.all(8),
                                padding=10,
                            ),
                            ft.Container(
                                content=ft.Image(
                                    src_base64=lfmp_image_base64,
                                    width=90,
                                    height=90,
                                    fit=ft.ImageFit.CONTAIN,
                                ),
                                border_radius=ft.border_radius.all(8),
                                padding=10,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                    ft.Container(height=5),
                    ft.Text("Bioinformatics and RNA-Seq LaB Online", size=30, weight=ft.FontWeight.BOLD),
                    username_input,
                    password_input,
                    ft.ElevatedButton("Register", on_click=register, width=300),
                    ft.ElevatedButton("Login", on_click=login, width=300),
                    ft.ElevatedButton("Toggle Theme", on_click=toggle_theme, width=300),
                    result
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=20
            ),
            alignment=ft.alignment.center,
            expand=True
        )
    )
    page.update()