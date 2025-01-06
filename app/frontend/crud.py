# filepath: /c:/Users/vitor/Documents/Projetos/Docker server implementation/app/frontend/crud.py
import flet as ft
import requests

def show_crud_interface(page, token, logout):
    name_input = ft.TextField(label="Name")
    description_input = ft.TextField(label="Description")
    item_id_input = ft.TextField(label="Item ID")
    crud_result = ft.Text()
    items_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID")),
            ft.DataColumn(ft.Text("Name")),
            ft.DataColumn(ft.Text("Description")),
            ft.DataColumn(ft.Text("Owner ID")),
        ],
        rows=[]
    )

    def refresh_items_table():
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        response = requests.get("http://bioinfo-container:8000/items/", headers=headers)
        items = response.json()
        items_table.rows.clear()
        for item in items:
            items_table.rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(item["id"]))),
                    ft.DataCell(ft.Text(item["name"])),
                    ft.DataCell(ft.Text(item["description"])),
                    ft.DataCell(ft.Text(str(item["owner_id"]))),
                ])
            )
        page.update()

    def create_item(e):
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        response = requests.post("http://bioinfo-container:8000/items/", params={"name": name_input.value, "description": description_input.value}, headers=headers)
        crud_result.value = response.json()
        refresh_items_table()

    def read_items(e):
        refresh_items_table()

    def update_item(e):
        item_id = int(item_id_input.value)
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        response = requests.put(f"http://bioinfo-container:8000/items/{item_id}", params={"name": name_input.value, "description": description_input.value}, headers=headers)
        crud_result.value = response.json()
        refresh_items_table()

    def delete_item(e):
        item_id = int(item_id_input.value)
        headers = {"Authorization": f"Bearer {token}", "ngrok-skip-browser-warning": "true"}
        response = requests.delete(f"http://bioinfo-container:8000/items/{item_id}", headers=headers)
        crud_result.value = response.json()
        refresh_items_table()

    page.controls.clear()
    page.add(
        ft.Column(
            [
                name_input,
                description_input,
                item_id_input,
                ft.ElevatedButton("Create Item", on_click=create_item),
                ft.ElevatedButton("Read Items", on_click=read_items),
                ft.ElevatedButton("Update Item", on_click=update_item),
                ft.ElevatedButton("Delete Item", on_click=delete_item),
                items_table,
                ft.ElevatedButton("Logout", on_click=logout),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20
        )
    )
    refresh_items_table()