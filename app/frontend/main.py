import httpx
import flet as ft
from .components.login import show_login_interface
from .bilbo_interface import show_bilbo_interface

async def main(page: ft.Page):
    page.title = "Bionformatics and RNA-Seq Lab Online"
    page.theme_mode = ft.ThemeMode.LIGHT

    page.snack_bar = ft.SnackBar(content=ft.Text(""), open=False)
    page.overlay.append(page.snack_bar)

    async def show_snackbar(message):
        page.snack_bar.content = ft.Text(message)
        page.snack_bar.open = True
        await page.update_async()

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
        await show_login_interface(page, login, register, toggle_theme, username_input, password_input)
        page.update()

    async def show_snackbar(message):
        page.snack_bar.content = ft.Text(message)
        page.snack_bar.open = True
        page.update()

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
                error_message = response.json().get("detail", "An unknown error occurred.")
                await show_snackbar(error_message)
        except httpx.RequestError as ex:
            await show_snackbar(f"An error occurred: {ex}")

    async def register(e):
        print("Register function called")
        headers = {"ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("http://bioinfo-container:8000/register/", params={"username": username_input.value, "password": password_input.value}, headers=headers, timeout=5)
            
            if response.status_code == 200:
                await show_snackbar("Registration successful! Please log in.")
            else:
                error_message = response.json().get("detail", "An unknown error occurred.")
                await show_snackbar(error_message)
        except httpx.RequestError as ex:
            await show_snackbar(f"An error occurred: {ex}")

    username_input = ft.TextField(label="Username", width=300)
    password_input = ft.TextField(label="Password", password=True, width=300)
    await show_login_interface(page, login, register, toggle_theme, username_input, password_input)