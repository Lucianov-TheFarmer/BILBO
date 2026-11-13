"""Contrast and edgeR model editor with per-sample metadata values."""

import asyncio
import inspect
import re
import uuid

import flet as ft
import httpx

from .translations import t

API = "http://bioinfo-container:8890"
CONTRAST_NAME = re.compile(r"^([^()]+)\(([^()]*)\)\*([^()]+)\(([^()]*)\)$")


async def show_contrasts_modal(page, token, user_id=None, on_closed=None):
    del user_id
    lang = page.session.get("lang") or "pt"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        options_response, contrasts_response, design_response = await asyncio.gather(
            client.get(f"{API}/pipeline/options", headers=headers),
            client.get(f"{API}/contrasts/", headers=headers),
            client.get(f"{API}/analysis-design", headers=headers))
    if options_response.status_code != 200 or contrasts_response.status_code != 200:
        page.open(ft.SnackBar(ft.Text(t("contrast_load_failed", lang))))
        if on_closed:
            result = on_closed()
            if inspect.isawaitable(result):
                await result
        return

    samples = options_response.json().get("samples") or {}
    saved_rows = contrasts_response.json()
    saved = (design_response.json().get("config") or {}) if design_response.status_code == 200 else {}
    saved_variables = saved.get("variables") or []
    known_ids = [item["id"] for item in saved_rows]
    status = ft.Text("")
    contrast_column = ft.Column(spacing=14,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    variable_column = ft.Column(spacing=8,
                                horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    contrast_entries = []
    variable_entries = []
    repetition_entries = []

    async def refresh_samples():
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"{API}/pipeline/options", headers=headers)
            response.raise_for_status()
            samples.clear()
            samples.update(response.json().get("samples") or {})
            for repetition in repetition_entries:
                repetition["sample"].options = sample_options()
            page.update()
        except Exception as exc:
            status.value = str(exc)
            page.update()

    def sample_options():
        result = []
        for name, records in sorted(samples.items()):
            states = {str(item.get("status") or "").upper() for item in records}
            state = ("COMPLETED" if "COMPLETED" in states else
                     "RUNNING" if "RUNNING" in states else
                     "PENDING" if "PENDING" in states else next(iter(states), ""))
            key = {"COMPLETED": "pipeline_completed", "RUNNING": "pipeline_running",
                   "PENDING": "pipeline_queued", "FAILED": "pipeline_failed"}.get(state)
            label = f"{name} · {t(key, lang) if key else state}"
            result.append(ft.dropdown.Option(name, label))
        return result

    def variable_options():
        return [ft.dropdown.Option(entry["id"], entry["name"].value.strip() or
                                   t("design_variable_name", lang)) for entry in variable_entries]

    def refresh_variable_options(_=None):
        for repetition in repetition_entries:
            for assignment in repetition["assignments"]:
                assignment["variable"].options = variable_options()
        page.update()

    def add_assignment(repetition, variable_id=None, value=""):
        if not variable_entries:
            status.value = t("design_add_variable_first", lang)
            page.update()
            return
        variable_id = variable_id or variable_entries[0]["id"]
        variable = ft.Dropdown(label=t("design_variable_name", lang), width=175,
                               value=variable_id, options=variable_options())
        field = ft.TextField(label=t("design_variable_value", lang), value=str(value), width=165)
        row = ft.Row([variable, field], spacing=8,
                     alignment=ft.MainAxisAlignment.CENTER)
        assignment = {"variable": variable, "value": field, "row": row}
        remove = ft.IconButton(icon="close", tooltip=t("design_remove_variable", lang),
                               on_click=lambda _: remove_assignment(repetition, assignment))
        row.controls.append(remove)
        repetition["assignments"].append(assignment)
        repetition["assignment_column"].controls.append(row)
        page.update()

    def remove_assignment(repetition, assignment):
        repetition["assignments"].remove(assignment)
        repetition["assignment_column"].controls.remove(assignment["row"])
        page.update()

    def add_variable(item=None):
        item = item or {}
        identifier = uuid.uuid4().hex
        name = ft.TextField(label=t("design_variable_name", lang), value=item.get("name", ""),
                            width=205, on_change=refresh_variable_options)
        kind = ft.Dropdown(label=t("design_variable_type", lang), width=155,
                           value=item.get("kind", "categorical"),
                           options=[ft.dropdown.Option("categorical", t("design_categorical", lang)),
                                    ft.dropdown.Option("numeric", t("design_numeric", lang))])
        row = ft.Row([name, kind], spacing=8)
        entry = {"id": identifier, "name": name, "kind": kind, "row": row}
        remove = ft.IconButton(icon="delete_outline", tooltip=t("design_remove_variable", lang),
                               on_click=lambda _: remove_variable(entry))
        row.controls.append(remove)
        variable_entries.append(entry)
        variable_column.controls.append(row)
        for repetition in repetition_entries:
            sample = repetition["sample"].value
            value = (item.get("values") or {}).get(sample, "") if sample else ""
            add_assignment(repetition, identifier, value)
        refresh_variable_options()

    def remove_variable(entry):
        variable_entries.remove(entry)
        variable_column.controls.remove(entry["row"])
        for repetition in repetition_entries:
            for assignment in list(repetition["assignments"]):
                if assignment["variable"].value == entry["id"]:
                    remove_assignment(repetition, assignment)
        refresh_variable_options()

    def add_repetition(side, sample=None):
        dropdown = ft.Dropdown(label=t("pipeline_samples", lang), width=240,
                               value=sample, options=sample_options())
        assignment_column = ft.Column(spacing=4)
        repetition = {"sample": dropdown, "assignments": [],
                      "assignment_column": assignment_column}

        def sample_changed(_):
            for assignment in repetition["assignments"]:
                definition = next((v for v in variable_entries
                                   if v["id"] == assignment["variable"].value), None)
                saved_value = (next((v for v in saved_variables
                                     if definition and v["name"] == definition["name"].value.strip()), {})
                               .get("values") or {}).get(dropdown.value, "")
                assignment["value"].value = str(saved_value)
            page.update()

        dropdown.on_change = sample_changed
        remove = ft.IconButton(icon="remove_circle_outline", icon_color="red",
                               tooltip=t("contrast_remove_rep", lang),
                               on_click=lambda _: remove_repetition(side, repetition))
        card = ft.Container(
            width=400,
            content=ft.Column([ft.Row([dropdown, remove],
                                      alignment=ft.MainAxisAlignment.CENTER), assignment_column,
                               ft.TextButton(t("design_add_value", lang),
                                             on_click=lambda _: add_assignment(repetition))],
                              spacing=4, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=8, border=ft.border.all(1, "outline"), border_radius=8)
        repetition["card"] = card
        side["repetitions"].append(repetition)
        side["column"].controls.append(card)
        repetition_entries.append(repetition)
        for variable in variable_entries:
            match = next((v for v in saved_variables
                          if v["name"] == variable["name"].value.strip()), {})
            add_assignment(repetition, variable["id"], (match.get("values") or {}).get(sample, ""))
        page.update()

    def remove_repetition(side, repetition):
        side["repetitions"].remove(repetition)
        side["column"].controls.remove(repetition["card"])
        repetition_entries.remove(repetition)
        page.update()

    def add_contrast(item=None):
        item = item or {}
        sides = []
        for number in (1, 2):
            group = ft.TextField(label=t("group_one" if number == 1 else "group_two", lang),
                                 value=item.get(f"group_{number}", ""), width=220)
            repeats = ft.Column(spacing=7, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            sides.append({"group": group, "column": repeats, "repetitions": []})
        entry = {"id": item.get("id"), "sides": sides}
        remove = ft.IconButton(icon="delete_outline", icon_color="red",
                               tooltip=t("contrast_remove", lang),
                               on_click=lambda _: remove_contrast(entry))
        card = ft.Container(
            width=860,
            content=ft.Column([
                ft.Row([sides[0]["group"], ft.Text("×"), sides[1]["group"], remove],
                       spacing=12, alignment=ft.MainAxisAlignment.CENTER),
                ft.Row([ft.Column([sides[0]["column"],
                                   ft.TextButton(t("contrast_add_rep", lang),
                                                 on_click=lambda _: add_repetition(sides[0]))],
                                  width=400, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Column([sides[1]["column"],
                                   ft.TextButton(t("contrast_add_rep", lang),
                                                 on_click=lambda _: add_repetition(sides[1]))],
                                  width=400, horizontal_alignment=ft.CrossAxisAlignment.CENTER)],
                       spacing=16, alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=14, border=ft.border.all(1, "outline"), border_radius=10)
        entry["card"] = card
        contrast_entries.append(entry)
        contrast_column.controls.append(card)
        for number in (1, 2):
            for sample in item.get(f"repetitions_{number}") or []:
                add_repetition(sides[number - 1], sample)
        page.update()

    def remove_contrast(entry):
        contrast_entries.remove(entry)
        contrast_column.controls.remove(entry["card"])
        for side in entry["sides"]:
            for repetition in list(side["repetitions"]):
                remove_repetition(side, repetition)
        page.update()

    for item in saved_rows:
        match = CONTRAST_NAME.fullmatch(item["name"])
        if match:
            left, left_samples, right, right_samples = match.groups()
            add_contrast({"id": item["id"], "group_1": left.strip(), "group_2": right.strip(),
                          "repetitions_1": left_samples.split(";"),
                          "repetitions_2": right_samples.split(";")})
    for variable in saved_variables:
        add_variable(variable)

    def payload():
        contrasts = []
        for entry in contrast_entries:
            item = {"id": entry["id"]}
            for number, side in enumerate(entry["sides"], 1):
                item[f"group_{number}"] = (side["group"].value or "").strip()
                item[f"repetitions_{number}"] = [rep["sample"].value for rep in side["repetitions"]]
            contrasts.append(item)
        variables = []
        for definition in variable_entries:
            values = {}
            for repetition in repetition_entries:
                sample = repetition["sample"].value
                for assignment in repetition["assignments"]:
                    if assignment["variable"].value != definition["id"] or not sample:
                        continue
                    if sample in values:
                        if values[sample] != assignment["value"].value:
                            raise ValueError(t("design_duplicate_value", lang).format(sample=sample))
                    values[sample] = assignment["value"].value
            variables.append({"name": (definition["name"].value or "").strip(),
                              "kind": definition["kind"].value, "values": values})
        return {"known_ids": known_ids, "contrasts": contrasts, "variables": variables}

    async def submit(save=False):
        try:
            body = payload()
            if not body["contrasts"] and not save:
                status.value = t("design_need_contrasts", lang)
                page.update()
                return
            endpoint = f"{API}/contrasts/configure" + ("" if save else "/validate")
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(endpoint, json=body, headers=headers)
            if response.status_code != 200:
                detail = response.json().get("detail", response.text)
                if isinstance(detail, list):
                    detail = "; ".join(str(item.get("msg", item)) for item in detail)
                status.value = str(detail)
                page.update()
                return
            preview = response.json().get("preview") if save else response.json()
            status.value = (f"{preview['formula']} · {t('design_residual_df', lang)}: "
                            f"{preview['residual_df']}" if preview else t("contrast_saved", lang))
            page.update()
            if save:
                page.close(dialog)
                if on_closed:
                    result = on_closed()
                    if asyncio.iscoroutine(result):
                        await result
        except Exception as exc:
            status.value = str(exc)
            page.update()

    async def close():
        page.close(dialog)
        if on_closed:
            result = on_closed()
            if inspect.isawaitable(result):
                await result

    dialog = ft.AlertDialog(
        modal=True, title=ft.Text(t("contrast_define", lang)),
        content=ft.Container(width=930, height=620, content=ft.ListView(controls=[
            ft.Text(t("contrast_intro", lang), size=12),
            ft.TextButton(t("pipeline_refresh", lang), icon="refresh",
                          on_click=lambda _: page.run_task(refresh_samples)),
            ft.Text(t("design_variables", lang), weight=ft.FontWeight.BOLD),
            variable_column,
            ft.TextButton(t("design_add_variable", lang), on_click=lambda _: add_variable()),
            ft.Divider(),
            ft.Text(t("contrast_define", lang), weight=ft.FontWeight.BOLD),
            contrast_column,
            ft.TextButton(t("contrast_add", lang), on_click=lambda _: add_contrast()),
            status,
        ], spacing=14)),
        actions=[ft.TextButton(t("menu_close", lang), on_click=lambda _: page.run_task(close)),
                 ft.TextButton(t("design_validate", lang),
                               on_click=lambda _: page.run_task(submit)),
                 ft.ElevatedButton(t("menu_save", lang),
                                   on_click=lambda _: page.run_task(submit, True))],
    )
    page.open(dialog)
