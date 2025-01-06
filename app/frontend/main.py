# filepath: /c:/Users/vitor/Documents/Projetos/Docker server implementation/app/frontend/main.py
import requests
import flet as ft
from .login import show_login_interface
#from .crud import show_crud_interface
from .bilbo_interface import show_bilbo_interface

async def main(page: ft.Page):
    page.title = "Bioinfo Frontend"
    page.theme_mode = ft.ThemeMode.LIGHT

    result = ft.Text()
    token = None
    username = None

    def toggle_theme(e):
        page.theme_mode = ft.ThemeMode.DARK if page.theme_mode == ft.ThemeMode.LIGHT else ft.ThemeMode.LIGHT
        page.update()

    def logout(e):
        nonlocal token, username
        token = None
        username = None
        page.controls.clear()
        show_login_interface(page, login, register, toggle_theme, username_input, password_input, result)

    def login(e):
        nonlocal token, username
        headers = {"ngrok-skip-browser-warning": "true"}
        response = requests.post("http://bioinfo-container:8000/token", data={"username": username_input.value, "password": password_input.value}, headers=headers)
        if response.status_code == 200:
            token = response.json()["access_token"]
            username = username_input.value
            show_bilbo_interface(page, logout, username, token)  # Pass token as argument
        else:
            result.value = response.json()
        page.update()

    def register(e):
        headers = {"ngrok-skip-browser-warning": "true"}
        response = requests.post("http://bioinfo-container:8000/register/", params={"username": username_input.value, "password": password_input.value}, headers=headers)
        result.value = response.json()
        page.update()

    username_input = ft.TextField(label="Username", width=300)
    password_input = ft.TextField(label="Password", password=True, width=300)

    show_login_interface(page, login, register, toggle_theme, username_input, password_input, result)

# Use ft.app_async instead of ft.app to avoid calling asyncio.run()
ft.app_async(target=main)
