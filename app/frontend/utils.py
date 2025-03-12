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
        await page.update_async()

async def create_confirmation_modal(page, title, hint_text, confirm_action):
    confirm_field = ft.TextField(
        hint_text=hint_text,
        border_radius=ft.border_radius.all(4),
        multiline=False,
        expand=1
    )

    async def on_confirm(e):
        if confirm_field.value == 'Confirmar':
            dlg_modal_confirm.open = False  # Close the modal
            await page.update_async()
            await confirm_action(e)

    dlg_modal_confirm = ft.AlertDialog(
        title=ft.Text(title),
        content=confirm_field,
        actions=[
            ft.TextButton("Excluir", on_click=lambda e: asyncio.create_task(on_confirm(e)), style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), width=200, height=40),
        ],
        actions_alignment=ft.MainAxisAlignment.CENTER,
    )

    page.dialog = dlg_modal_confirm
    dlg_modal_confirm.open = True
    await page.update_async()
