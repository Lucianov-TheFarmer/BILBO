"""Configure and monitor persistent automatic pipelines."""

import asyncio
import re

import flet as ft
import httpx

from .analysis_design import show_analysis_design_modal
from .translations import t

API = "http://bioinfo-container:8890"
STAR_FIELDS = ("outFilterType", "outFilterMultimapNmax", "alignSJoverhangMin",
               "alignSJDBoverhangMin", "outFilterMismatchNmax",
               "outFilterMismatchNoverReadLmax", "alignIntronMin", "alignIntronMax",
               "alignMatesGapMax")


async def show_pipeline_config_modal(page, token):
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
    status_text = ft.Text("")
    name_field = ft.TextField(label=t("pipeline_name", lang), value=t("pipeline_default_name", lang))
    sample_checks = {name: ft.Checkbox(label=name, value=False) for name in sorted(options["samples"])}
    sample_pair_checks = {}
    sample_rows = []
    for name, select in sample_checks.items():
        files = [item["name"] for item in options["samples"][name]
                 if item.get("status") == "COMPLETED"]
        has_pair = (any(re.search(r"(?:_1|_R1)\.(?:fastq|fq)(?:\.gz)?$", file) for file in files)
                    and any(re.search(r"(?:_2|_R2)\.(?:fastq|fq)(?:\.gz)?$", file) for file in files))
        pair = ft.Checkbox(label="R1/R2", value=has_pair or not files)
        sample_pair_checks[name] = pair
        sample_rows.append(ft.Row([select, pair]))
    sample_choices = ft.Column(sample_rows, spacing=0)
    planned_field = ft.TextField(label=t("pipeline_planned_samples", lang),
                                 hint_text="SRR12345, A01-F_S2", multiline=True, min_lines=2)
    planned_source = ft.Dropdown(label=t("pipeline_planned_source", lang), value="sra",
                                 options=[ft.dropdown.Option("sra", "SRA"),
                                          ft.dropdown.Option("drive", "Google Drive"),
                                          ft.dropdown.Option("upload", t("pipeline_upload", lang))])
    paired = ft.Checkbox(label=t("pipeline_paired", lang), value=True)
    stage_checks = {stage: ft.Checkbox(label=t("pipeline_stage_" + stage, lang),
                                       value=stage in ("qc_raw", "trimming", "qc_trim", "alignment", "quantification"))
                    for stage in ("qc_raw", "trimming", "qc_trim", "alignment", "quantification", "deg")}
    genome_field = ft.Dropdown(label=t("pipeline_genome", lang),
                               options=[ft.dropdown.Option(g["id"], f"{g['name']} ({g['status']})")
                                        for g in options["genomes"] if g.get("id")])
    trim_fields = {key: ft.TextField(label=t("pipeline_trim_" + key, lang), value=value, width=215)
                   for key, value in {"threads": "4", "phred": "autodetect", "adapter": "TruSeq3-PE.fa",
                                      "seed": "2", "palindrome": "30", "simple": "10", "adapter_min": "8",
                                      "window": "4", "quality": "15", "target": "40", "strictness": "0.5",
                                      "leading": "3", "trailing": "3", "crop": "", "headcrop": "",
                                      "minlen": "36", "avgqual": ""}.items()}
    adapter_content = ft.TextField(label=t("pipeline_custom_adapter", lang), multiline=True,
                                    min_lines=2)
    alignment_threads = ft.TextField(label=t("pipeline_threads", lang), value="8", width=200)
    star_fields = {key: ft.TextField(label=key, width=200) for key in STAR_FIELDS}
    feature_type = ft.TextField(label=t("pipeline_feature_type", lang), value="gene", width=200)
    id_attribute = ft.TextField(label=t("pipeline_id_attribute", lang), value="ID", width=200)
    design_summary = ft.Text(t("pipeline_design_missing", lang) if not saved_design
                             else f"~0+group" + "".join("+" + v["name"]
                                                         for v in saved_design.get("variables") or []))
    recent = ft.Column(spacing=5)
    state = {"open": True}

    def planned_names():
        return [part.strip() for part in re.split(r"[,;\n]+", planned_field.value or "") if part.strip()]

    def build_plan():
        samples = [{"name": name, "source": "existing", "paired": sample_pair_checks[name].value}
                   for name, check in sample_checks.items() if check.value]
        samples.extend({"name": name, "source": planned_source.value, "paired": paired.value}
                       for name in planned_names())
        trim = {"threads": trim_fields["threads"].value,
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
                "trimming": trim, "alignment": alignment,
                "quantification": {"feature_type": feature_type.value.strip(),
                                   "id_attribute": id_attribute.value.strip()},
                "design": saved_design if stage_checks["deg"].value else None,
                "reuse_existing": True}

    async def save(start=False):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(f"{API}/pipeline/runs", json=build_plan(), headers=headers)
                if response.status_code not in (200, 201):
                    status_text.value = response.json().get("detail", response.text)
                    page.update()
                    return
                run = response.json()
                if start:
                    response = await client.post(f"{API}/pipeline/runs/{run['id']}/start", headers=headers)
                    if response.status_code != 200:
                        status_text.value = response.json().get("detail", response.text)
                        page.update()
                        return
            status_text.value = t("pipeline_started", lang) if start else t("pipeline_saved", lang)
            await load_runs()
        except Exception as exc:
            status_text.value = str(exc)
            page.update()

    async def action(run_id, endpoint):
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{API}/pipeline/runs/{run_id}/{endpoint}", headers=headers)
        status_text.value = (t("pipeline_action_done", lang) if response.status_code == 200 else
                             response.json().get("detail", response.text))
        await load_runs()

    async def load_runs():
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(f"{API}/pipeline/runs", headers=headers)
            if response.status_code != 200:
                return
            recent.controls.clear()
            for run in response.json()[:8]:
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
                    controls.append(ft.TextButton(t("pipeline_start", lang),
                        on_click=lambda _, rid=run["id"]: page.run_task(action, rid, "start")))
                if run["status"] == "FAILED":
                    controls.append(ft.TextButton(t("pipeline_retry", lang),
                        on_click=lambda _, rid=run["id"]: page.run_task(action, rid, "retry")))
                if run["status"] == "RUNNING":
                    controls.append(ft.TextButton(t("pipeline_cancel", lang),
                        on_click=lambda _, rid=run["id"]: page.run_task(action, rid, "cancel")))
                if any(step["stage"] == "deg" and step["status"] == "COMPLETED"
                       for step in run["steps"]):
                    controls.append(ft.TextButton("DEG.xlsx", on_click=lambda _, rid=run["id"]:
                        page.launch_url(f"http://localhost:8890/pipeline/runs/{rid}/file/DEG.xlsx?token={token}")))
                    controls.append(ft.TextButton("DEG_full.xlsx", on_click=lambda _, rid=run["id"]:
                        page.launch_url(f"http://localhost:8890/pipeline/runs/{rid}/file/DEG_full.xlsx?token={token}")))
                total = len(run["steps"])
                done = sum(step["status"] in ("COMPLETED", "SKIPPED") for step in run["steps"])
                progress = ft.ProgressBar(value=done / total if total else 0, height=5)
                visible_steps = [step for step in run["steps"] if step["status"] in
                                 ("FAILED", "BLOCKED", "RUNNING", "PENDING", "WAITING")]
                step_lines = []
                for step in visible_steps[:4]:
                    stage = t("pipeline_stage_" + step["stage"], lang) if step["stage"] != "input" else t("pipeline_samples", lang)
                    label = t(labels.get(step["status"], step["status"]), lang)
                    message = f"{step['sample']} · {stage}: {label}"
                    if step.get("error_message"):
                        message += f" · {step['error_message']}"
                    step_lines.append(ft.Text(message, size=11))
                recent.controls.append(ft.Column([ft.Row(controls), progress, *step_lines], spacing=3))
            page.update()
        except Exception:
            pass

    async def poll_runs():
        while state["open"]:
            await load_runs()
            await asyncio.sleep(8)

    async def edit_design(_):
        page.close(dialog)
        async def after_save(config):
            nonlocal saved_design
            saved_design = config
            design_summary.value = "~0+group" + "".join("+" + v["name"] for v in config["variables"])
            page.open(dialog)
        await show_analysis_design_modal(page, token, after_save,
                                         on_closed=lambda: page.open(dialog))

    def close(_):
        state["open"] = False
        page.close(dialog)

    dialog = ft.AlertDialog(modal=True,
        title=ft.Text(t("pipeline_configure", lang)),
        content=ft.Container(width=950, height=620, content=ft.ListView(controls=[
            ft.Text(t("pipeline_intro", lang)), name_field,
            ft.Text(t("pipeline_samples", lang), weight=ft.FontWeight.BOLD), sample_choices,
            planned_field, planned_source, paired,
            ft.Text(t("pipeline_import_hint", lang), size=12),
            ft.Text(t("pipeline_stages", lang), weight=ft.FontWeight.BOLD),
            ft.Row(list(stage_checks.values()), wrap=True), genome_field,
            ft.Text(t("pipeline_trim_params", lang), weight=ft.FontWeight.BOLD),
            ft.Row(list(trim_fields.values()), wrap=True), adapter_content,
            ft.Text(t("pipeline_alignment_params", lang), weight=ft.FontWeight.BOLD),
            alignment_threads, ft.Row(list(star_fields.values()), wrap=True),
            ft.Text(t("pipeline_quant_params", lang), weight=ft.FontWeight.BOLD),
            ft.Row([feature_type, id_attribute]),
            ft.Text(t("design_title", lang), weight=ft.FontWeight.BOLD), design_summary,
            ft.TextButton(t("pipeline_edit_design", lang), on_click=edit_design),
            status_text, ft.Text(t("pipeline_recent", lang), weight=ft.FontWeight.BOLD), recent,
        ])),
        actions=[ft.TextButton(t("menu_close", lang), on_click=close),
                 ft.TextButton(t("pipeline_save_draft", lang), on_click=lambda _: page.run_task(save)),
                 ft.ElevatedButton(t("pipeline_start", lang), on_click=lambda _: page.run_task(save, True))],
    )
    page.open(dialog)
    page.run_task(poll_runs)
