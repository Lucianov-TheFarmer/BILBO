import httpx
import requests
import flet as ft
from .components.login import show_login_interface
from .bilbo_interface import show_bilbo_interface

async def main(page: ft.Page):
    page.title = "Bionformatics and RNA-Seq Lab Online"
    page.theme_mode = ft.ThemeMode.LIGHT

    result = ft.Text()
    token = None
    username = None

    async def toggle_theme(e):
        page.theme_mode = ft.ThemeMode.DARK if page.theme_mode == ft.ThemeMode.LIGHT else ft.ThemeMode.LIGHT
        page.update()

    async def logout(e):
        nonlocal token, username
        token = None
        username = None
        page.controls.clear()
        page.update()
        await show_login_interface(page, login, register, toggle_theme, username_input, password_input, result)

    async def login(e):
        print("Login button clicked")
        nonlocal token, username
        headers = {"ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("http://bioinfo-container:8000/token", data={"username": username_input.value, "password": password_input.value}, headers=headers, timeout=5)
            if response.status_code == 200:
                token = response.json()["access_token"]
                user_id = response.json()["user_id"]
                print(f"Token: {token}")
                username = username_input.value
                await show_bilbo_interface(page, logout, username, token, user_id)
            else:
                result.value = response.json()
        except httpx.RequestError as ex:
            result.value = f"An error occurred: {ex}"
        page.update()

    async def register(e):
        print("Register function called")
        headers = {"ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("http://bioinfo-container:8000/register/", params={"username": username_input.value, "password": password_input.value}, headers=headers, timeout=5)
            result.value = response.json()
        except httpx.RequestError as ex:
            result.value = f"An error occurred: {ex}"
        page.update()

    # Usar credenciais
    # username_input = ft.TextField(label="Username", width=300)
    # password_input = ft.TextField(label="Password", password=True, width=300)
    # await show_login_interface(page, login, register, toggle_theme, username_input, password_input, result)

    # Entrar automaticamente
    username_input = ft.TextField(label="Username", width=300)
    username_input.value = "admin"
    password_input = ft.TextField(label="Password", password=True, width=300)
    password_input.value = "admin"
    await login(e=None)
