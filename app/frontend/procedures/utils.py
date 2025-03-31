import flet as ft
import asyncio

# Track the last message sent
last_message = ""

async def log_message(page, message):
    global last_message
    if message != last_message:
        last_message = message
        container_terminal = page.controls[1].controls[0].controls[1]
        container_terminal.content.controls.append(ft.Text(message))
        page.update()