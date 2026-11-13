"""Guided edgeR model editor using the existing contrast assignments."""

import inspect

import flet as ft
import httpx

from .translations import t

API = "http://bioinfo-container:8890"


async def show_analysis_design_modal(page, token, on_saved=None, on_closed=None):
    lang = page.session.get("lang") or "pt"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        context_response = await client.get(f"{API}/analysis-design/context", headers=headers)
        saved_response = await client.get(f"{API}/analysis-design", headers=headers)
    if context_response.status_code != 200:
        page.open(ft.SnackBar(ft.Text(t("design_need_contrasts", lang))))
        if on_closed:
            result = on_closed()
            if inspect.isawaitable(result):
                await result
        return
    context = context_response.json()
    saved = (saved_response.json().get("config") or {}) if saved_response.status_code == 200 else {}
    all_samples = sorted(context["samples"])
    selected_ids = set(saved.get("contrast_ids") or [item["id"] for item in context["contrasts"]])
    contrast_controls = []
    for item in context["contrasts"]:
        checkbox = ft.Checkbox(label=item["name"], value=item["id"] in selected_ids)
        contrast_controls.append((item["id"], checkbox, item))
    variables = []
    variable_column = ft.Column(spacing=12)
    feedback = ft.Text("")

    def add_variable(item=None):
        item = item or {}
        name_field = ft.TextField(label=t("design_variable_name", lang),
                                  value=item.get("name", ""), width=180)
        kind_field = ft.Dropdown(label=t("design_variable_type", lang), width=180,
                                 value=item.get("kind", "categorical"),
                                 options=[ft.dropdown.Option("categorical", t("design_categorical", lang)),
                                          ft.dropdown.Option("numeric", t("design_numeric", lang))])
        values = item.get("values") or {}
        value_fields = {sample: ft.TextField(label=f"{sample} · {context['samples'][sample]}",
                                             value=str(values.get(sample, "")), width=220)
                        for sample in all_samples}
        block = ft.Column(controls=[ft.Row([name_field, kind_field]),
                                    ft.Row(list(value_fields.values()), wrap=True)])
        remove_button = ft.TextButton(t("design_remove_variable", lang))
        block.controls[0].controls.append(remove_button)
        entry = {"name": name_field, "kind": kind_field, "values": value_fields, "block": block}
        remove_button.on_click = lambda _: (variables.remove(entry), variable_column.controls.remove(block), page.update())
        variables.append(entry)
        variable_column.controls.append(block)
        page.update()

    for variable in saved.get("variables") or []:
        add_variable(variable)

    def payload():
        ids = [item_id for item_id, checkbox, _ in contrast_controls if checkbox.value]
        samples = set()
        for item_id, checkbox, item in contrast_controls:
            if checkbox.value:
                samples.update(item["positive"]["samples"])
                samples.update(item["negative"]["samples"])
        return {"contrast_ids": ids, "variables": [
            {"name": entry["name"].value.strip(), "kind": entry["kind"].value,
             "values": {sample: entry["values"][sample].value for sample in samples}}
            for entry in variables]}

    async def check(save=False):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = (await client.put(f"{API}/analysis-design", json=payload(), headers=headers)
                            if save else await client.post(f"{API}/analysis-design/validate",
                                                      json=payload(), headers=headers))
            if response.status_code not in (200, 201):
                feedback.value = response.json().get("detail", response.text)
                page.update()
                return
            preview = response.json().get("preview") if save else response.json()
            feedback.value = (f"{preview['formula']} · {t('design_residual_df', lang)}: "
                              f"{preview['residual_df']}")
            page.update()
            if save:
                page.close(dialog)
                if on_saved:
                    result = on_saved(response.json()["config"])
                    if inspect.isawaitable(result):
                        await result
        except Exception as exc:
            feedback.value = str(exc)
            page.update()

    async def close():
        page.close(dialog)
        if on_closed:
            result = on_closed()
            if inspect.isawaitable(result):
                await result

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(t("design_title", lang)),
        content=ft.Container(width=860, height=540, content=ft.ListView(controls=[
            ft.Text(t("design_intro", lang)),
            ft.Text(t("design_group_auto", lang)),
            ft.Column([checkbox for _, checkbox, _ in contrast_controls]),
            ft.Text(t("design_variables", lang), weight=ft.FontWeight.BOLD),
            ft.TextButton(t("design_add_variable", lang), on_click=lambda _: add_variable()),
            variable_column, feedback,
        ])),
        actions=[ft.TextButton(t("menu_close", lang), on_click=lambda _: page.run_task(close)),
                 ft.TextButton(t("design_validate", lang), on_click=lambda _: page.run_task(check)),
                 ft.ElevatedButton(t("menu_save", lang), on_click=lambda _: page.run_task(check, True))],
    )
    page.open(dialog)
