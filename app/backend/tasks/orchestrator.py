"""Advance independent sample jobs when their verified inputs are ready."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ..core.settings import settings
from ..db.database import SessionLocal
from ..db.models import PipelineJob, PipelineRun, PipelineStep, SampleStage
from ..services.job_service import create_job
from ..utils_paths import ensure_safe_component, safe_resolve_user_path
from .celery_app import celery_app
from .pipeline_tasks import enqueue_pipeline_job

TERMINAL = {"COMPLETED", "FAILED", "BLOCKED", "SKIPPED", "CANCELED"}
ORDER = ("input", "qc_raw", "trimming", "qc_trim", "alignment", "quantification", "deg", "clustering", "llm")
MATE_SUFFIXES = ("_1", "_2", "_R1", "_R2")
FASTQ_SUFFIXES = (".fastq.gz", ".fq.gz", ".fastq", ".fq")
# Keep in sync with the dedicated worker concurrency in docker-compose.yml.
CPU_WORKER_LIMITS = {"alignment": 4, "trimming": 2, "deg": 1}


def _root(user_id: int, *parts: str) -> Path:
    return safe_resolve_user_path(settings.users_root, user_id, *parts)


def _row(db, user_id: int, stage_id: int, name: str):
    return db.query(SampleStage).filter(SampleStage.user_id == user_id,
        SampleStage.stage_id == stage_id, SampleStage.name == name).first()


def _raw_files(db, user_id: int, sample: str, paired: bool) -> list[Path]:
    rows = db.query(SampleStage).filter(SampleStage.user_id == user_id,
        SampleStage.stage_id == 1, SampleStage.sra_code == sample,
        SampleStage.status == "COMPLETED").all()
    files = [(_root(user_id, "samples", sample, row.name), row.name) for row in rows
             if any(row.name.endswith(ext) for ext in FASTQ_SUFFIXES)]
    files = [(path, name) for path, name in files if path.is_file() and path.stat().st_size > 0]
    if not paired:
        return [path for path, _ in files[:1]]
    for left, right in (("_1", "_2"), ("_R1", "_R2")):
        for extension in FASTQ_SUFFIXES:
            names = (sample + left + extension, sample + right + extension)
            match = {name: path for path, name in files}
            if all(name in match for name in names):
                return [match[name] for name in names]
    return []


def _trimmed_files(db, user_id: int, sample: str, paired: bool) -> list[Path]:
    names = ([f"{sample}_1_trimmed.fastq.gz", f"{sample}_2_trimmed.fastq.gz"] if paired
             else [f"{sample}_trimmed.fastq.gz"])
    files = [_root(user_id, "trimmed", name) for name in names]
    return files if all(path.is_file() and path.stat().st_size > 0 and
                        (row := _row(db, user_id, 3, path.name)) is not None and
                        row.status == "COMPLETED" for path in files) else []


def _qc_ready(db, user_id: int, sample: str, files: list[Path], post: bool) -> bool:
    stage_id = 4 if post else 2
    report_dir = "QC_PostTrim" if post else "QC"
    for path in files:
        stem = path.name.removesuffix(".gz").removesuffix(".fastq").removesuffix(".fq")
        row_name = (stem.removesuffix("_trimmed") + "_post_trim.html") if post else stem + ".html"
        row = _row(db, user_id, stage_id, row_name)
        report = _root(user_id, report_dir, sample, stem + "_fastqc.html")
        if row is None or row.status != "COMPLETED" or not report.is_file():
            return False
    return bool(files)


def _ready(db, user_id: int, sample: str, stage: str, paired: bool) -> bool:
    if stage == "input":
        return bool(_raw_files(db, user_id, sample, paired))
    if stage == "qc_raw":
        return _qc_ready(db, user_id, sample, _raw_files(db, user_id, sample, paired), False)
    if stage == "trimming":
        return bool(_trimmed_files(db, user_id, sample, paired))
    if stage == "qc_trim":
        return _qc_ready(db, user_id, sample, _trimmed_files(db, user_id, sample, paired), True)
    if stage == "alignment":
        path = _root(user_id, "alignment", sample, sample + ".bam")
        row = _row(db, user_id, 5, sample + ".bam")
        return bool(row and row.status == "COMPLETED" and path.is_file() and path.stat().st_size > 0)
    if stage == "quantification":
        path = _root(user_id, "quantification", sample + ".txt")
        row = _row(db, user_id, 6, sample + ".txt")
        return bool(row and row.status == "COMPLETED" and path.is_file() and path.stat().st_size > 0)
    return False


def _reference_ready(db, user_id: int, accession: str, stage: str) -> bool:
    row = db.query(SampleStage).filter(SampleStage.user_id == user_id,
        SampleStage.stage_id == 7, SampleStage.sra_code == accession,
        SampleStage.status == "COMPLETED").first()
    if row is None:
        return False
    directory = Path(settings.users_root) / "ref_genomes" / ensure_safe_component(accession, "genome")
    if stage == "alignment":
        return (directory / "STAR_index").is_dir()
    return any((directory / name).is_file() for name in ("genomic.gff", "genomic.gff3", "genomic.gtf"))


def _active_job(db, user_id: int, stage: str, sample: str):
    jobs = db.query(PipelineJob).filter(PipelineJob.user_id == user_id,
        PipelineJob.stage == stage, PipelineJob.status.in_(["PENDING", "RUNNING"])).all()
    for job in jobs:
        payload = job.payload or {}
        selected = payload.get("samples") or []
        if payload.get("sample") == sample or payload.get("sra_code") == sample or \
                sample + ".bam" in selected or any(str(name).startswith(sample + "_") for name in selected):
            return job
    return None


def _cpu_available(db, requested: int) -> bool:
    maximum = min(os.cpu_count() or 1, 256)
    active = db.query(PipelineJob).filter(PipelineJob.stage.in_(CPU_WORKER_LIMITS),
        PipelineJob.status.in_(["PENDING", "RUNNING"])).all()
    # Queued jobs beyond a worker's concurrency cannot consume CPU yet. Counting
    # all of them blocked ready alignment samples while trimming workers were full.
    used = 0
    for stage, limit in CPU_WORKER_LIMITS.items():
        stage_jobs = [job for job in active if job.stage == stage]
        running = [job for job in stage_jobs if job.status == "RUNNING"]
        pending = [job for job in stage_jobs if job.status == "PENDING"]
        slots = max(0, limit - len(running))
        for job in running + pending[:slots]:
            used += int((job.payload or {}).get("threads") or
                        ((job.payload or {}).get("params") or {}).get("threads") or
                        (job.payload or {}).get("diamond_threads") or 1)
    return requested <= maximum and used + requested <= maximum


def _ensure_row(db, user_id: int, stage_id: int, name: str, sample: str):
    row = _row(db, user_id, stage_id, name)
    if row is None:
        row = SampleStage(user_id=user_id, stage_id=stage_id, name=name,
                          sra_code=sample, status="PENDING")
        db.add(row)
    elif row.status != "COMPLETED":
        row.status = "PENDING"
    db.commit()


def _dispatch(db, run: PipelineRun, step: PipelineStep, paired: bool) -> PipelineJob:
    user_id, sample, config = run.user_id, step.sample, run.config
    stage = step.stage
    if stage == "input":
        _ensure_row(db, user_id, 1, sample, sample)
        job_stage = "samples_download"
        payload = {"sra_code": sample}
    elif stage == "qc_raw":
        files = _raw_files(db, user_id, sample, paired)
        for path in files:
            stem = path.name.removesuffix(".gz").removesuffix(".fastq").removesuffix(".fq")
            _ensure_row(db, user_id, 2, stem + ".html", sample)
        job_stage = "quality_analysis"
        payload = {"samples": [path.name for path in files]}
    elif stage == "trimming":
        job_stage = "trimming"
        payload = {"sample": sample, "params": config["trimming"]}
    elif stage == "qc_trim":
        files = _trimmed_files(db, user_id, sample, paired)
        for path in files:
            stem = path.name.removesuffix(".gz").removesuffix(".fastq").removesuffix(".fq")
            _ensure_row(db, user_id, 4, stem.removesuffix("_trimmed") + "_post_trim.html", sample)
        job_stage = "quality_analysis_post_trim"
        payload = {"samples": [path.name for path in files]}
    elif stage == "alignment":
        _ensure_row(db, user_id, 5, sample + ".bam", sample)
        job_stage = "alignment"
        extra = [f"--{key}={value}" for key, value in config["alignment"].items()
                 if key != "threads" and value not in (None, "")]
        payload = {"sample": sample, "genome_dir": str(Path(settings.users_root) /
                   "ref_genomes" / config["genome"] / "STAR_index"),
                   "threads": config["alignment"]["threads"], "additional": extra}
    elif stage == "quantification":
        _ensure_row(db, user_id, 6, sample + ".txt", sample)
        job_stage = "quantification"
        quant = config["quantification"]
        payload = {"samples": [sample + ".bam"], "feature_type": quant.get("feature_type", "gene"),
                   "id_attribute": quant.get("id_attribute", "ID"),
                   "selected_genome": config["genome"]}
    elif stage == "deg":
        preview = config["design_snapshot"]
        root = _root(user_id, "pipelines", run.id)
        preprocess = root / "preprocess"
        preprocess.mkdir(parents=True, exist_ok=True)
        lines = ["files\tgroup\tdescription"]
        for name, group in sorted(preview["samples"].items()):
            count_file = _root(user_id, "quantification", name + ".txt")
            lines.append(f"{count_file}\t{group}\t{name}")
        (preprocess / "Targets.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (preprocess / "selected_contrasts.txt").write_text("\n".join(
            str(item["id"]) for item in preview["contrasts"]) + "\n", encoding="utf-8")
        (preprocess / "contrasts_db.txt").write_text("id\tname\n" + "\n".join(
            f"{item['id']}\t{item['name']}" for item in preview["contrasts"]) + "\n", encoding="utf-8")
        (preprocess / "selected_genome.txt").write_text(config["genome"] + "\n", encoding="utf-8")
        job_stage = "deg"
        payload = {"contrast_ids": config["design"]["contrast_ids"],
                   "genome_accession": config["genome"], "design": config["design"],
                   "design_snapshot": preview, "run_id": run.id,
                   "diamond_threads": config.get("deg", {}).get("diamond_threads", 8)}
    elif stage in ("clustering", "llm"):
        from openpyxl import load_workbook

        workbook = _root(user_id, "pipelines", run.id, "DEG", "DEG.xlsx")
        book = load_workbook(workbook, read_only=True)
        try:
            sheets = list(book.sheetnames)
        finally:
            book.close()
        if not sheets:
            raise ValueError("Differential analysis has no contrasts to process")
        for sheet in sheets:
            _ensure_row(db, user_id, 9 if stage == "clustering" else 10, sheet, "__all__")
        job_stage = stage
        payload = {"sheets": sheets, "run_id": run.id}
    else:
        raise ValueError(f"Unknown step: {stage}")
    job = create_job(db, job_stage, user_id, payload)
    enqueue_pipeline_job(job.id)
    return job


def _dependencies(run: PipelineRun, step: PipelineStep) -> list[str]:
    enabled = {name for name, selected in run.config["stages"].items() if selected}
    if step.stage == "input":
        return []
    if step.stage == "qc_raw":
        return ["input"]
    if step.stage == "trimming":
        return ["qc_raw"] if "qc_raw" in enabled else ["input"]
    if step.stage == "qc_trim":
        return ["trimming"]
    if step.stage == "alignment":
        return ["qc_trim"] if "qc_trim" in enabled else ["trimming"]
    if step.stage == "quantification":
        return ["alignment"]
    if step.stage == "deg":
        return ["quantification"]
    if step.stage == "clustering":
        return ["deg"]
    if step.stage == "llm":
        return ["clustering"]
    return []


def _advance_run(db, run: PipelineRun) -> None:
    samples = {item["name"]: item for item in run.config["samples"]}
    steps = {(step.sample, step.stage): step for step in run.steps}
    for step in sorted(run.steps, key=lambda item: ORDER.index(item.stage)):
        if step.status in TERMINAL:
            continue
        paired = samples.get(step.sample, {}).get("paired", True)
        if step.job_id:
            job = db.query(PipelineJob).filter(PipelineJob.id == step.job_id).first()
            if job is None:
                step.status, step.error_message = "FAILED", "Job record disappeared"
            elif job.status in ("FAILED", "CANCELED"):
                step.status, step.error_message = "FAILED", job.error_message or "Job failed"
            elif job.status == "COMPLETED":
                if step.stage == "deg":
                    output_ok = (_root(run.user_id, "pipelines", run.id, "DEG", "DEG.xlsx")).is_file()
                elif step.stage in ("clustering", "llm"):
                    artifact = "clusters.json" if step.stage == "clustering" else "report.md"
                    sheets = (job.payload or {}).get("sheets") or []
                    output_ok = bool(sheets) and all(
                        (_root(run.user_id, step.stage, sheet, artifact)).is_file()
                        for sheet in sheets)
                else:
                    output_ok = _ready(db, run.user_id, step.sample, step.stage, paired)
                step.status = "COMPLETED" if output_ok else "FAILED"
                step.error_message = None if output_ok else "Job finished without the expected output"
                step.finished_at = datetime.now(timezone.utc)
            else:
                step.status = job.status
            db.commit()
            continue
        if step.stage != "deg" and _ready(db, run.user_id, step.sample, step.stage, paired):
            step.status = "SKIPPED"
            step.finished_at = datetime.now(timezone.utc)
            db.commit()
            continue
        deps = _dependencies(run, step)
        dependency_steps = ([steps.get((name, deps[0])) for name in samples] if step.stage == "deg" and deps
                            else [steps.get((step.sample, name)) for name in deps])
        if any(dep and dep.status in ("FAILED", "BLOCKED", "CANCELED") for dep in dependency_steps):
            step.status, step.error_message = "BLOCKED", "Required previous step failed"
            db.commit()
            continue
        if any(dep and dep.status not in ("COMPLETED", "SKIPPED") for dep in dependency_steps):
            continue
        required_stage = {"qc_raw": "input", "trimming": "input", "qc_trim": "trimming",
                          "alignment": "trimming", "quantification": "alignment",
                          "deg": "quantification"}.get(step.stage)
        if required_stage:
            targets = samples if step.stage == "deg" else {step.sample: samples[step.sample]}
            if any(not _ready(db, run.user_id, name, required_stage, spec["paired"])
                   for name, spec in targets.items()):
                continue
        if step.stage in ("alignment", "quantification", "deg") and not _reference_ready(
            db, run.user_id, run.config["genome"], step.stage):
            continue
        if step.stage == "input" and samples[step.sample]["source"] != "sra":
            continue  # Drive and uploads are initiated in their existing dialogs.
        if step.stage in ("alignment", "trimming", "deg"):
            requested = int((run.config.get("deg", {}).get("diamond_threads", 8)
                             if step.stage == "deg" else
                             run.config[step.stage].get("threads", 1)))
            if not _cpu_available(db, requested) or shutil.disk_usage(settings.users_root).free < 20 * 1024**3:
                continue
        job_stage = {"input": "samples_download", "qc_raw": "quality_analysis",
                     "qc_trim": "quality_analysis_post_trim"}.get(step.stage, step.stage)
        existing = _active_job(db, run.user_id, job_stage, step.sample) if step.stage not in ("deg", "clustering", "llm") else None
        try:
            job = existing or _dispatch(db, run, step, paired)
        except Exception as exc:
            step.status, step.error_message = "FAILED", str(exc)[:500]
            db.commit()
            continue
        step.job_id = job.id
        step.status = job.status
        step.started_at = datetime.now(timezone.utc)
        db.commit()
    statuses = {step.status for step in run.steps}
    if statuses <= TERMINAL:
        run.status = "FAILED" if statuses & {"FAILED", "BLOCKED"} else "COMPLETED"
        run.finished_at = datetime.now(timezone.utc)
        if run.status == "FAILED":
            run.error_message = "One or more pipeline steps failed"
        db.commit()


@celery_app.task(name="pipeline.reconcile_all")
def reconcile_all():
    db = SessionLocal()
    try:
        runs = db.query(PipelineRun).filter(PipelineRun.status == "RUNNING").all()
        for run in runs:
            _advance_run(db, run)
    finally:
        db.close()
