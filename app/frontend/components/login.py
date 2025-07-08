# filepath: /c:/Users/vitor/Documents/Projetos/Docker server implementation/app/frontend/login.py
import flet as ft
import asyncio
import base64

# Carrega as imagens do tema claro e converte para base64
with open("assets/src/favicon_white.png", "rb") as img_file:
    favicon_light_base64 = base64.b64encode(img_file.read()).decode('utf-8')

with open("assets/src/UFLA.png", "rb") as img_file:
    ufla_light_base64 = base64.b64encode(img_file.read()).decode('utf-8')

with open("assets/src/LFMP.png", "rb") as img_file:
    lfmp_light_base64 = base64.b64encode(img_file.read()).decode('utf-8')

# Carrega as imagens do tema escuro e converte para base64
with open("assets/src/favicon_black.png", "rb") as img_file:
    favicon_dark_base64 = base64.b64encode(img_file.read()).decode('utf-8')

with open("assets/src/UFLA_dark.png", "rb") as img_file:
    ufla_dark_base64 = base64.b64encode(img_file.read()).decode('utf-8')

with open("assets/src/LFMP_dark.png", "rb") as img_file:
    lfmp_dark_base64 = base64.b64encode(img_file.read()).decode('utf-8')

def get_theme_images(page):
    """Retorna as imagens apropriadas baseadas no tema da página"""
    if page.theme_mode == ft.ThemeMode.DARK:
        return {
            'favicon': favicon_dark_base64,
            'ufla': ufla_dark_base64,
            'lfmp': lfmp_dark_base64
        }
    else:
        return {
            'favicon': favicon_light_base64,
            'ufla': ufla_light_base64,
            'lfmp': lfmp_light_base64
        }

async def show_login_interface(page, login, register, toggle_theme, username_input, password_input, result):
    # Obtém as imagens baseadas no tema atual
    theme_images = get_theme_images(page)
    
    page.controls.clear()
    page.add(
        ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=ft.Image(
                                    src_base64=theme_images['ufla'],
                                    width=90,
                                    height=90,
                                    fit=ft.ImageFit.CONTAIN,
                                ),
                                border_radius=ft.border_radius.all(8),
                                padding=10,
                            ),
                            ft.Container(
                                content=ft.Image(
                                    src_base64=theme_images['favicon'],
                                    width=90,
                                    height=90,
                                    fit=ft.ImageFit.CONTAIN,
                                ),
                                border_radius=ft.border_radius.all(8),
                                padding=10,
                            ),
                            ft.Container(
                                content=ft.Image(
                                    src_base64=theme_images['lfmp'],
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