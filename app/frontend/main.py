import httpx
import flet as ft
from .components.login import show_login_interface
from .bilbo_interface import show_bilbo_interface
from frontend.procedures.translations import t

async def main(page: ft.Page):
    page.title = "Bionformatics and RNA-Seq Lab Online"
    page.dark_theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary="#3C5E86",
            on_primary="#F3F7FC",
            secondary="#9CB2CC",
            on_secondary="#0E1726",
            background="#0C1320",
            on_background="#E6EEF8",
            surface="#111B2A",
            on_surface="#E6EEF8",
            outline="#314357",
        )
    )
    page.theme_mode = "light"
    page.bgcolor = "background"

    page.snack_bar = ft.SnackBar(content=ft.Text(""), open=False)
    page.overlay.append(page.snack_bar)

    if not page.session.get("lang"):
        page.session.set("lang", "pt")

    # page.title = t("login_title", page.session.get("lang"))

    async def show_snackbar(message):
        page.snack_bar.content = ft.Text(message)
        page.snack_bar.open = True
        page.update()

    token = None
    username = None

    async def toggle_theme(e):
        page.theme_mode = "dark" if page.theme_mode == "light" else "light"
        page.update()
        # Se ainda não há token (está na tela de login), recarrega a interface de login
        if token is None:
            await show_login_interface(page, login, register, toggle_theme, username_input, password_input)

    async def logout(e):
        nonlocal token, username
        token = None
        username = None
        page.controls.clear()
        await show_login_interface(page, login, register, toggle_theme, username_input, password_input)
        page.update()

    async def login(e):
        print("Login button clicked")
        nonlocal token, username
        headers = {"ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("http://bioinfo-container:8890/token", data={"username": username_input.value, "password": password_input.value}, headers=headers, timeout=5)
            if response.status_code == 200:
                data = None
                try:
                    data = response.json()
                except Exception:
                    pass
                if data:
                    token = data.get("access_token")
                    user_id = data.get("user_id")
                else:
                    await show_snackbar("Login succeeded but server returned unexpected response.")
                    return
                username = username_input.value
                await show_bilbo_interface(page, logout, username, token, user_id)
            else:
                try:
                    err = response.json()
                    error_message = err.get("detail", "An unknown error occurred.")
                except Exception:
                    txt = response.text
                    error_message = txt if txt else f"Server returned status {response.status_code}"
                await show_snackbar(error_message)
        except httpx.RequestError as ex:
            await show_snackbar(f"An error occurred: {ex}")

    async def register(e):
        print("Register function called")
        headers = {"ngrok-skip-browser-warning": "true"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post("http://bioinfo-container:8890/register/", params={"username": username_input.value, "password": password_input.value}, headers=headers, timeout=5)

            if response.status_code == 200:
                await show_snackbar("Registration successful! Please log in.")
            else:
                try:
                    err = response.json()
                    error_message = err.get("detail", "An unknown error occurred.")
                except Exception:
                    txt = response.text
                    error_message = txt if txt else f"Server returned status {response.status_code}"
                await show_snackbar(error_message)
        except httpx.RequestError as ex:
            await show_snackbar(f"An error occurred: {ex}")

    username_input = ft.TextField(label="Username", width=300)
    password_input = ft.TextField(label="Password", password=True, width=300)
    await show_login_interface(page, login, register, toggle_theme, username_input, password_input)
