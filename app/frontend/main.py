import httpx
import requests
import flet as ft
from .login import show_login_interface
from .bilbo_interface import show_bilbo_interface

async def main(page: ft.Page):
    page.title = "Bioinfo Frontend"
    page.theme_mode = ft.ThemeMode.LIGHT

    result = ft.Text()
    token = None
    username = None

    async def toggle_theme(e):
        page.theme_mode = ft.ThemeMode.DARK if page.theme_mode == ft.ThemeMode.LIGHT else ft.ThemeMode.LIGHT
        await page.update_async()

    async def logout(e):
        nonlocal token, username
        token = None
        username = None
        page.controls.clear()
        await page.update_async()
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
                user_id = response.json()["user_id"]  # Assuming the user_id is returned in the response
                print(f"Token: {token}")
                username = username_input.value
                await show_bilbo_interface(page, logout, username, token, user_id)  # Pass user_id as argument
            else:
                result.value = response.json()
        except httpx.RequestError as ex:
            result.value = f"An error occurred: {ex}"
        await page.update_async()

    async def register(e):
        print("Register function called")
        headers = {"ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("http://bioinfo-container:8000/register/", params={"username": username_input.value, "password": password_input.value}, headers=headers, timeout=5)
            result.value = response.json()
        except httpx.RequestError as ex:
            result.value = f"An error occurred: {ex}"
        await page.update_async()

    username_input = ft.TextField(label="Username", width=300)
    password_input = ft.TextField(label="Password", password=True, width=300)

    await show_login_interface(page, login, register, toggle_theme, username_input, password_input, result)
