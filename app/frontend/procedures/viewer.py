import flet as ft
import asyncio
import httpx
import logging
import zipfile
import os
from io import BytesIO
import base64  # New import

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Dictionary to map dropdown options to image filenames
graph_type_to_image = {
    "Per base sequence quality": "per_base_quality.png",
    "Per tile sequence quality": "per_tile_quality.png",
    "Per sequence quality scores": "per_sequence_quality.png",
    "Per base sequence content": "per_base_sequence_content.png",
    "Per sequence GC content": "per_sequence_gc_content.png",
    "Per base N content": "per_base_n_content.png",
    "Sequence Length Distribution": "sequence_length_distribution.png",
    "Sequence Duplication Levels": "duplication_levels.png",
    "Adapter Content": "adapter_content.png",
}

async def display_graph(page, token, graph_type, sample_name, user_id):
    # Extract the sample code from the sample name
    sample_code = sample_name.split('.')[0]

    # Define the path to the zip file and the image inside it
    zip_path = f"../users/{user_id}/QC/{sample_code}.fastq/{sample_code}_fastqc.zip"
    image_path = f"{sample_code}_fastqc/Images/{graph_type_to_image[graph_type]}"

    # Extract the image from the zip file
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        with zip_ref.open(image_path) as image_file:
            image_data = image_file.read()

    # Encode the image data to base64
    image_base64 = base64.b64encode(image_data).decode('utf-8')

    # Create an Image control with the extracted image data
    image_control = ft.Image(src_base64=image_base64, fit=ft.ImageFit.CONTAIN)

    # Add zoom and pan functionality
    zoom_level = 1.0
    pan_x = 0
    pan_y = 0

    def on_wheel(e):
        nonlocal zoom_level
        zoom_level += e.delta_y * 0.001
        zoom_level = max(0.1, min(zoom_level, 5.0))
        image_control.scale = zoom_level
        page.update()

    def on_drag(e):
        nonlocal pan_x, pan_y
        pan_x += e.delta_x
        pan_y += e.delta_y
        image_control.translate = ft.Offset(pan_x, pan_y)
        page.update()

    image_control.on_wheel = on_wheel
    image_control.on_drag = on_drag

    return image_control

def create_dropdown_menu(page, token, sample_name, user_id):
    async def on_change(e):
        selected_graph = e.control.value
        graph_control = await display_graph(page, token, selected_graph, sample_name, user_id)
        
        # Find the container_pre_visualizacao and update its content
        for control in page.controls:
            if isinstance(control, ft.Row):
                for column in control.controls:
                    if isinstance(column, ft.Column):
                        for container in column.controls:
                            if isinstance(container, ft.Container) and container.expand == 2 and isinstance(container.content, ft.Column):
                                container.content.controls[0].content.controls[1] = graph_control
                                await page.update_async()
                                return

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Dropdown(
                    options=[
                        ft.dropdown.Option("Per base sequence quality"),
                        ft.dropdown.Option("Per tile sequence quality"),
                        ft.dropdown.Option("Per sequence quality scores"),
                        ft.dropdown.Option("Per base sequence content"),
                        ft.dropdown.Option("Per sequence GC content"),
                        ft.dropdown.Option("Per base N content"),
                        ft.dropdown.Option("Sequence Length Distribution"),
                        ft.dropdown.Option("Sequence Duplication Levels"),
                        ft.dropdown.Option("Adapter Content"),
                    ],
                    height=50,
                    on_change=lambda e: asyncio.create_task(on_change(e)),
                    value="Per base sequence quality"  # Set the default selected value
                )
            ]
        )
    )