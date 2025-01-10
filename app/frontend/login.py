# filepath: /c:/Users/vitor/Documents/Projetos/Docker server implementation/app/frontend/login.py
import flet as ft
import asyncio

async def show_login_interface(page, login, register, toggle_theme, username_input, password_input, result):
    page.controls.clear()
    await page.add_async(
        ft.Container(
            content=ft.Column(
                [
                    ft.Text("BIoinformatics and RNA-Seq LaB Online", size=30, weight=ft.FontWeight.BOLD),
                    username_input,
                    password_input,
                    ft.ElevatedButton("Register", on_click=lambda e: asyncio.create_task(register(e)), width=300),
                    ft.ElevatedButton("Login", on_click=lambda e: asyncio.create_task(login(e)), width=300),
                    ft.ElevatedButton("Toggle Theme", on_click=lambda e: asyncio.create_task(toggle_theme(e)), width=300),
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
    await page.update_async()