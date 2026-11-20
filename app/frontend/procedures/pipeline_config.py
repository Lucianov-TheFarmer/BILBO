"""Configure and monitor persistent automatic pipelines."""
from .urls import launch_public_url

import asyncio
import re

import flet as ft
import httpx

from .alignment import show_genomes_modal
from .contrasts import show_contrasts_modal
from .reference_import import show_reference_upload_modal, show_reference_url_modal
from .translations import t
from .utils import log_message

API = "http://bioinfo-container:8890"
STAR_FIELDS = ("outFilterType", "outFilterMultimapNmax", "alignSJoverhangMin",
               "alignSJDBoverhangMin", "outFilterMismatchNmax",
               "outFilterMismatchNoverReadLmax", "alignIntronMin", "alignIntronMax",
               "alignMatesGapMax")


async def show_pipeline_config_modal(page, token, user_id):
    lang = page.session.get("lang") or "pt"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        options_response, design_response = await asyncio.gather(
            client.get(f"{API}/pipeline/options", headers=headers),
            client.get(f"{API}/analysis-design", headers=headers))
    if options_response.status_code != 200:
        page.open(ft.SnackBar(ft.Text(t("pipeline_load_failed", lang))))
        return
    options = options_response.json()
    saved_design = design_response.json().get("config") if design_response.status_code == 200 else None
    design_samples = set()
    if saved_design:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                preview_response = await client.post(
                    f"{API}/analysis-design/validate", json=saved_design, headers=headers)
            if preview_response.status_code == 200:
                design_samples = set(preview_response.json().get("samples") or {})
        except Exception:
            pass
    status_text = ft.Text("")
    name_field = ft.TextField(label=t("pipeline_name", lang), value=t("pipeline_default_name", lang))
    sample_checks = {}
    sample_specs = {}
    editing_samples = {}
    sample_data = dict(options["samples"])
    sample_choices = ft.Column(spacing=2, height=170, scroll=ft.ScrollMode.AUTO)
    sample_count = ft.Text("")
    editing_label = ft.Text("")
    editing = {"id": None}

    def localized_status(value):
        key = {"COMPLETED": "pipeline_completed", "RUNNING": "pipeline_running",
               "PENDING": "pipeline_queued", "FAILED": "pipeline_failed"}.get(
                   str(value or "").upper())
        return t(key, lang) if key else str(value or "")

    def show_samples(data, select_names=None):
        selected = (set(select_names) if select_names is not None else
                    {name for name, check in sample_checks.items() if check.value})
        data = dict(data)
        for name, spec in editing_samples.items():
            data.setdefault(name, [{"name": name, "status": "PENDING",
                                    "source": spec.get("source")}])
        sample_checks.clear()
        sample_specs.clear()
        sample_choices.controls.clear()
        for name, records in sorted(data.items()):
            states = {str(item.get("status") or "").upper() for item in records}
            state = ("COMPLETED" if "COMPLETED" in states else
                     "RUNNING" if "RUNNING" in states else
                     "PENDING" if "PENDING" in states else next(iter(states), ""))
            label = f"{name} · {localized_status(state)}"
            check = ft.Checkbox(label=label, value=name in selected, on_change=lambda _: update_selection())
            sample_checks[name] = check
            sample_choices.controls.append(check)
            files = [item["name"] for item in records]
            first = any(re.search(r"(?:_1|_R1)\.(?:fastq|fq)(?:\.gz)?$", file) for file in files)
            second = any(re.search(r"(?:_2|_R2)\.(?:fastq|fq)(?:\.gz)?$", file) for file in files)
            source = ("drive" if any(item.get("source") == "drive" for item in records) else
                      "sra" if re.fullmatch(r"(?:SRR|ERR|DRR)\d+", name, re.I) and
                      state in ("PENDING", "RUNNING") else "existing")
            sample_specs[name] = {"name": name, "source": source,
                                  "paired": first or second or state != "COMPLETED"}
            if name in editing_samples:
                sample_specs[name] = dict(editing_samples[name])
        if not sample_checks:
            sample_choices.controls.append(ft.Text(t("pipeline_no_samples", lang), size=12))
        update_selection()

    def update_selection():
        count = sum(bool(check.value) for check in sample_checks.values())
        sample_count.value = t("pipeline_selected_count", lang).format(count=count)
        select_all.value = bool(sample_checks) and count == len(sample_checks)
        page.update()

    def toggle_all(_):
        for check in sample_checks.values():
            check.value = select_all.value
        update_selection()

    select_all = ft.Checkbox(label=t("pipeline_select_all", lang), on_change=toggle_all)
    show_samples(sample_data, select_names=design_samples)
    stage_checks = {stage: ft.Checkbox(label=t("pipeline_stage_" + stage, lang),
                                       value=stage in ("qc_raw", "trimming", "qc_trim", "alignment", "quantification"))
                    for stage in ("qc_raw", "trimming", "qc_trim", "alignment", "quantification", "deg", "clustering", "llm")}
    genome_field = ft.Dropdown(label=t("pipeline_genome", lang),
                               options=[ft.dropdown.Option(g["id"], f"{g['name']} ({localized_status(g['status'])})")
                                        for g in options["genomes"] if g.get("id")])
    ready_genomes = [g["id"] for g in options["genomes"] if g.get("id") and g.get("status") == "COMPLETED"]
    if len(ready_genomes) == 1:
        genome_field.value = ready_genomes[0]
    qc_raw_memory = ft.TextField(label=t("quality_memory_mb", lang), value="512", width=215,
                                 keyboard_type=ft.KeyboardType.NUMBER)
    qc_trim_memory = ft.TextField(label=t("quality_memory_mb", lang), value="512", width=215,
                                  keyboard_type=ft.KeyboardType.NUMBER)
    trim_memory = ft.TextField(label=t("trimming_memory_mb", lang), value="1024", width=215,
                               keyboard_type=ft.KeyboardType.NUMBER)
    trim_fields = {key: ft.TextField(label=t("pipeline_trim_" + key, lang), value=value, width=215)
                   for key, value in {"threads": "4", "phred": "autodetect", "adapter": "TruSeq3-PE.fa",
                                      "seed": "2", "palindrome": "30", "simple": "10", "adapter_min": "8",
                                      "window": "4", "quality": "15", "target": "40", "strictness": "0.5",
                                      "leading": "3", "trailing": "3", "crop": "", "headcrop": "",
                                      "minlen": "36", "avgqual": ""}.items()}
    trim_fields["phred"] = ft.Dropdown(label=t("pipeline_trim_phred", lang), value="autodetect",
        width=215, options=[ft.dropdown.Option(key) for key in ("autodetect", "phred33", "phred64")])
    trim_fields["adapter"] = ft.Dropdown(label=t("pipeline_trim_adapter", lang),
        value="TruSeq3-PE.fa", width=215,
        options=[ft.dropdown.Option(key) for key in ("TruSeq3-PE.fa", "TruSeq3-PE-2.fa",
                "TruSeq3-SE.fa", "TruSeq2-PE.fa", "TruSeq2-SE.fa", "NexteraPE-PE.fa",
                "Personalizado")])
    adapter_content = ft.TextField(label=t("pipeline_custom_adapter", lang), multiline=True,
                                    min_lines=2, visible=False)
    def adapter_changed(_):
        adapter_content.visible = trim_fields["adapter"].value == "Personalizado"
        page.update()
    trim_fields["adapter"].on_change = adapter_changed
    alignment_threads = ft.TextField(label=t("pipeline_threads", lang), value="8", width=200)
    diamond_threads = ft.TextField(label=t("pipeline_diamond_cpus", lang), value="8",
                                   width=200, keyboard_type=ft.KeyboardType.NUMBER)
    star_fields = {key: ft.TextField(label=key, width=200) for key in STAR_FIELDS}
    feature_type = ft.TextField(label=t("pipeline_feature_type", lang), value="gene", width=200)
    id_attribute = ft.TextField(label=t("pipeline_id_attribute", lang), value="ID", width=200)
    design_summary = ft.Text(t("pipeline_design_missing", lang) if not saved_design
                             else f"~0+group" + "".join("+" + v["name"]
                                                         for v in saved_design.get("variables") or []))
    recent = ft.Column(spacing=5, height=190, scroll=ft.ScrollMode.AUTO)
    state = {"open": True}

    def build_plan():
        samples = [sample_specs[name] for name, check in sample_checks.items() if check.value]
        trim = {"threads": trim_fields["threads"].value,
                "memory_mb": trim_memory.value,
                "phred": trim_fields["phred"].value,
                "illumina_clip": {"Arquivo adaptadores": trim_fields["adapter"].value,
                                  "Conteudo personalizado": adapter_content.value,
                                  "Seed mismatches": trim_fields["seed"].value,
                                  "Threshold palindromo": trim_fields["palindrome"].value,
                                  "Threshold simples": trim_fields["simple"].value,
                                  "Comprimento minimo adaptador": trim_fields["adapter_min"].value},
                "sliding_window": {"Tamanho janela": trim_fields["window"].value,
                                   "Qualidade minima": trim_fields["quality"].value},
                "max_info": {"Comprimento alvo": trim_fields["target"].value,
                             "Strictness": trim_fields["strictness"].value},
                "leading": trim_fields["leading"].value, "trailing": trim_fields["trailing"].value,
                "crop": trim_fields["crop"].value, "headcrop": trim_fields["headcrop"].value,
                "minlen": trim_fields["minlen"].value, "avgqual": trim_fields["avgqual"].value}
        alignment = {"threads": alignment_threads.value}
        alignment.update({key: field.value for key, field in star_fields.items() if field.value})
        return {"name": name_field.value.strip(), "samples": samples,
                "stages": {key: check.value for key, check in stage_checks.items()},
                "genome": genome_field.value,
                "quality": {"raw_memory_mb": qc_raw_memory.value,
                            "post_memory_mb": qc_trim_memory.value},
                "trimming": trim, "alignment": alignment,
                "deg": {"diamond_threads": diamond_threads.value},
                "quantification": {"feature_type": feature_type.value.strip(),
                                   "id_attribute": id_attribute.value.strip()},
                "design": saved_design if stage_checks["deg"].value else None,
                "reuse_existing": True}

    def load_draft(run):
        nonlocal saved_design
        config = run["config"]
        editing["id"] = run["id"]
        editing_samples.clear()
        editing_samples.update({sample["name"]: sample for sample in config.get("samples") or []})
        name_field.value = config.get("name") or ""
        show_samples(sample_data, select_names=editing_samples)
        for key, check in stage_checks.items():
            check.value = bool((config.get("stages") or {}).get(key))
        genome_field.value = config.get("genome")
        quality = config.get("quality") or {}
        qc_raw_memory.value = str(quality.get("raw_memory_mb", 512))
        qc_trim_memory.value = str(quality.get("post_memory_mb", 512))
        trim = config.get("trimming") or {}
        trim_memory.value = str(trim.get("memory_mb", 1024))
        adapter = trim.get("illumina_clip") or {}
        window = trim.get("sliding_window") or {}
        max_info = trim.get("max_info") or {}
        nested = {"adapter": adapter.get("Arquivo adaptadores"),
                  "seed": adapter.get("Seed mismatches"),
                  "palindrome": adapter.get("Threshold palindromo"),
                  "simple": adapter.get("Threshold simples"),
                  "adapter_min": adapter.get("Comprimento minimo adaptador"),
                  "window": window.get("Tamanho janela"),
                  "quality": window.get("Qualidade minima"),
                  "target": max_info.get("Comprimento alvo"),
                  "strictness": max_info.get("Strictness")}
        for key, field in trim_fields.items():
            value = nested.get(key) if key in nested else trim.get(key)
            if value is not None:
                field.value = str(value)
        adapter_content.value = str(adapter.get("Conteudo personalizado") or "")
        adapter_changed(None)
        alignment = config.get("alignment") or {}
        alignment_threads.value = str(alignment.get("threads", 8))
        diamond_threads.value = str((config.get("deg") or {}).get("diamond_threads", 8))
        for key, field in star_fields.items():
            field.value = str(alignment.get(key) or "")
        quant = config.get("quantification") or {}
        feature_type.value = str(quant.get("feature_type") or "gene")
        id_attribute.value = str(quant.get("id_attribute") or "ID")
        saved_design = config.get("design")
        design_summary.value = (t("pipeline_design_missing", lang) if not saved_design else
                                "~0+group" + "".join("+" + variable["name"]
                                                    for variable in saved_design.get("variables") or []))
        editing_label.value = t("pipeline_editing_draft", lang).format(name=name_field.value)
        status_text.value = t("pipeline_draft_loaded", lang)
        page.update()

    async def report_status(message, error=False):
        status_text.value = str(message)
        status_text.color = "red" if error else "green"
        page.update()
        await log_message(page, str(message))

    def response_error(response):
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        if isinstance(detail, list):
            return "; ".join(str(item.get("msg", item)) if isinstance(item, dict)
                             else str(item) for item in detail)
        return str(detail)

    async def save(start=False):
        try:
            plan = build_plan()
            if not plan["samples"]:
                await report_status(t("pipeline_choose_samples", lang), error=True)
                return
            if any(plan["stages"].get(stage) for stage in ("alignment", "quantification", "deg")) \
                    and not plan["genome"]:
                await report_status(t("pipeline_genome_required", lang), error=True)
                return
            async with httpx.AsyncClient(timeout=30) as client:
                if editing["id"]:
                    response = await client.put(f"{API}/pipeline/runs/{editing['id']}",
                                                json=plan, headers=headers)
                else:
                    response = await client.post(f"{API}/pipeline/runs", json=plan, headers=headers)
                if response.status_code not in (200, 201):
                    await report_status(response_error(response), error=True)
                    return
                run = response.json()
                editing["id"] = run["id"]
                if start:
                    response = await client.post(f"{API}/pipeline/runs/{run['id']}/start", headers=headers)
                    if response.status_code != 200:
                        await report_status(response_error(response), error=True)
                        return
                    page.pipeline_monitor_run_id = run["id"]
                    editing["id"] = None
                    editing_label.value = ""
            await report_status(t("pipeline_started", lang) if start else t("pipeline_saved", lang))
            await load_runs()
        except Exception as exc:
            await report_status(str(exc), error=True)

    async def action(run_id, endpoint):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(f"{API}/pipeline/runs/{run_id}/{endpoint}", headers=headers)
            if response.status_code == 200:
                page.pipeline_monitor_run_id = run_id
                await report_status(t("pipeline_action_done", lang))
            else:
                await report_status(response_error(response), error=True)
            await load_runs()
        except Exception as exc:
            await report_status(str(exc), error=True)

    async def delete_draft(run_id, confirm_dialog):
        page.close(confirm_dialog)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.delete(f"{API}/pipeline/runs/{run_id}", headers=headers)
        if response.status_code == 200:
            if editing["id"] == run_id:
                editing["id"] = None
                editing_label.value = ""
                editing_samples.clear()
            status_text.value = t("pipeline_draft_deleted", lang)
        else:
            status_text.value = response.json().get("detail", response.text)
        await load_runs()

    def confirm_delete(run_id):
        confirm_dialog = ft.AlertDialog(
            modal=True, title=ft.Text(t("pipeline_delete_draft", lang)),
            content=ft.Text(t("pipeline_delete_draft_hint", lang)),
            actions=[ft.TextButton(t("btn_cancel", lang),
                                   on_click=lambda _: page.close(confirm_dialog)),
                     ft.ElevatedButton(t("btn_delete", lang),
                                       on_click=lambda _: page.run_task(delete_draft, run_id, confirm_dialog))])
        page.open(confirm_dialog)

    async def load_runs():
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(f"{API}/pipeline/runs", headers=headers)
            if response.status_code != 200:
                return
            recent.controls.clear()
            for run in response.json():
                counts = {}
                for step in run["steps"]:
                    counts[step["status"]] = counts.get(step["status"], 0) + 1
                labels = {"WAITING": "pipeline_waiting", "PENDING": "pipeline_queued",
                          "RUNNING": "pipeline_running", "COMPLETED": "pipeline_completed",
                          "FAILED": "pipeline_failed", "SKIPPED": "pipeline_skipped",
                          "BLOCKED": "pipeline_blocked", "CANCELED": "pipeline_canceled",
                          "DRAFT": "pipeline_draft"}
                detail = ", ".join(f"{t(labels.get(key, key), lang)}: {value}"
                                   for key, value in sorted(counts.items()))
                run_status = t(labels.get(run["status"], run["status"]), lang)
                controls = [ft.Text(f"{run['config']['name']} · {run_status} · {detail}", expand=True)]
                if run["status"] == "DRAFT":
                    controls.append(ft.TextButton(t("pipeline_edit_draft", lang),
                        on_click=lambda _, selected=run: load_draft(selected)))
                    controls.append(ft.TextButton(t("pipeline_start", lang),
                        on_click=lambda _, rid=run["id"]: page.run_task(action, rid, "start")))
                    controls.append(ft.TextButton(t("btn_delete", lang),
                        on_click=lambda _, rid=run["id"]: confirm_delete(rid)))
                if run["status"] == "FAILED":
                    controls.append(ft.TextButton(t("pipeline_retry", lang),
                        on_click=lambda _, rid=run["id"]: page.run_task(action, rid, "retry")))
                if run["status"] == "RUNNING":
                    controls.append(ft.TextButton(t("pipeline_cancel", lang),
                        on_click=lambda _, rid=run["id"]: page.run_task(action, rid, "cancel")))
                if any(step["stage"] == "deg" and step["status"] == "COMPLETED"
                       for step in run["steps"]):
                    controls.append(ft.TextButton("DEG.xlsx", on_click=lambda _, rid=run["id"]:
                        launch_public_url(page, f"http://localhost:8890/pipeline/runs/{rid}/file/DEG.xlsx?token={token}")))
                    controls.append(ft.TextButton("DEG_full.xlsx", on_click=lambda _, rid=run["id"]:
                        launch_public_url(page, f"http://localhost:8890/pipeline/runs/{rid}/file/DEG_full.xlsx?token={token}")))
                total = len(run["steps"])
                done = sum(step["status"] in ("COMPLETED", "SKIPPED") for step in run["steps"])
                progress = ft.ProgressBar(value=done / total if total else 0, height=5)
                visible_steps = [step for step in run["steps"] if step["status"] in
                                 ("FAILED", "BLOCKED", "RUNNING")]
                step_lines = []
                for step in visible_steps[:2]:
                    stage = t("pipeline_stage_" + step["stage"], lang) if step["stage"] != "input" else t("pipeline_samples", lang)
                    label = t(labels.get(step["status"], step["status"]), lang)
                    message = f"{step['sample']} · {stage}: {label}"
                    if step.get("error_message"):
                        message += f" · {step['error_message']}"
                    step_lines.append(ft.Text(message, size=11))
                recent.controls.append(ft.Column([ft.Row(controls, wrap=True, spacing=8),
                                                  progress, *step_lines], spacing=3))
            page.update()
        except Exception:
            pass

    async def refresh_options():
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{API}/pipeline/options", headers=headers)
            if response.status_code != 200:
                return
            data = response.json()
            sample_data.clear()
            sample_data.update(data.get("samples") or {})
            show_samples(sample_data)
            current_genome = genome_field.value
            genome_field.options = [ft.dropdown.Option(g["id"], f"{g['name']} ({localized_status(g['status'])})")
                                    for g in data.get("genomes") or [] if g.get("id")]
            genome_field.value = current_genome
            page.update()
        except Exception:
            pass

    async def poll_runs():
        while state["open"]:
            await load_runs()
            await refresh_options()
            await asyncio.sleep(8)

    async def open_related(kind):
        page.close(dialog)
        async def restore_pipeline():
            nonlocal saved_design
            if kind == "contrasts":
                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        response = await client.get(f"{API}/analysis-design", headers=headers)
                    if response.status_code == 200:
                        saved_design = response.json().get("config")
                        design_summary.value = (t("pipeline_design_missing", lang) if not saved_design else
                            "~0+group" + "".join("+" + variable["name"]
                                                for variable in saved_design.get("variables") or []))
                except Exception:
                    pass
            await refresh_options()
            page.open(dialog)
        try:
            if kind == "url":
                await show_reference_url_modal(page, token, on_closed=restore_pipeline)
            elif kind == "upload":
                await show_reference_upload_modal(page, token, on_closed=restore_pipeline)
            elif kind == "ncbi":
                await show_genomes_modal(page, token, user_id, on_closed=restore_pipeline)
            elif kind == "contrasts":
                await show_contrasts_modal(page, token, user_id, on_closed=restore_pipeline)
        except Exception as exc:
            status_text.value = str(exc)
            page.open(dialog)

    def close(_):
        state["open"] = False
        page.close(dialog)

    def section(stage, controls):
        return ft.Container(
            content=ft.Column([stage_checks[stage], *controls], spacing=10),
            padding=ft.padding.all(14),
            border=ft.border.all(1, "outline"),
            border_radius=10,
        )

    genome_field.width = 415
    reference_controls = ft.Row([
        genome_field,
        ft.IconButton(icon="link", tooltip=t("menu_reference_url", lang),
                      on_click=lambda _: page.run_task(open_related, "url")),
        ft.IconButton(icon="upload_file", tooltip=t("menu_reference_upload", lang),
                      on_click=lambda _: page.run_task(open_related, "upload")),
        ft.IconButton(icon="download", tooltip=t("pipeline_reference_ncbi", lang),
                      on_click=lambda _: page.run_task(open_related, "ncbi")),
        ft.IconButton(icon="refresh", tooltip=t("pipeline_refresh", lang),
                      on_click=lambda _: page.run_task(refresh_options)),
    ], wrap=True, spacing=6)

    dialog = ft.AlertDialog(modal=True,
        title=ft.Text(t("pipeline_configure", lang)),
        content=ft.Container(width=910, height=650, content=ft.ListView(controls=[
            ft.Text(t("pipeline_intro", lang), size=12),
            name_field, editing_label, status_text,
            ft.Divider(),
            ft.Row([ft.Text(t("pipeline_samples", lang), weight=ft.FontWeight.BOLD),
                    sample_count], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            select_all,
            sample_choices,
            ft.Text(t("pipeline_import_hint", lang), size=12),
            ft.TextButton(t("pipeline_refresh", lang), icon="refresh",
                          on_click=lambda _: page.run_task(refresh_options)),
            ft.Divider(),
            ft.Container(
                content=ft.Column([
                    ft.Text(t("pipeline_genome", lang), weight=ft.FontWeight.BOLD),
                    reference_controls,
                    ft.Text(t("pipeline_reference_required_hint", lang), size=11),
                    ft.Text(t("pipeline_reference_hint", lang), size=11),
                ], spacing=10),
                padding=ft.padding.all(14),
                border=ft.border.all(1, "outline"),
                border_radius=10,
            ),
            ft.Divider(),
            ft.Text(t("pipeline_stages", lang), weight=ft.FontWeight.BOLD),
            section("qc_raw", [qc_raw_memory,
                ft.Text(t("quality_memory_hint", lang), size=11)]),
            section("trimming", [
                ft.Text(t("pipeline_trim_params", lang), size=12),
                ft.Row([trim_memory, *trim_fields.values()], wrap=True, spacing=10), adapter_content,
            ]),
            section("qc_trim", [qc_trim_memory,
                ft.Text(t("quality_memory_hint", lang), size=11)]),
            section("alignment", [
                ft.Text(t("pipeline_alignment_params", lang), size=12),
                ft.Row([alignment_threads, *star_fields.values()], wrap=True, spacing=10),
            ]),
            section("quantification", [
                ft.Text(t("pipeline_quant_params", lang), size=12),
                ft.Row([feature_type, id_attribute], wrap=True, spacing=10),
            ]),
            section("deg", [
                diamond_threads,
                design_summary,
                ft.Text(t("pipeline_deg_samples_hint", lang), size=11),
                ft.TextButton(t("pipeline_open_contrasts", lang),
                              on_click=lambda _: page.run_task(open_related, "contrasts")),
            ]),
            section("clustering", [ft.Text(t("pipeline_clustering_hint", lang), size=11)]),
            section("llm", [ft.Text(t("pipeline_llm_hint", lang), size=11)]),
            ft.Divider(),
            ft.Text(t("pipeline_recent", lang), weight=ft.FontWeight.BOLD), recent,
        ], spacing=12)),
        actions=[ft.TextButton(t("menu_close", lang), on_click=close),
                 ft.TextButton(t("pipeline_save_draft", lang), on_click=lambda _: page.run_task(save)),
                 ft.ElevatedButton(t("pipeline_start", lang), on_click=lambda _: page.run_task(save, True))],
    )
    page.open(dialog)
    page.run_task(poll_runs)
