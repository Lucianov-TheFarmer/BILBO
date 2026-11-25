"""Stop active analysis jobs before removing their incomplete outputs."""

from __future__ import annotations

import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from ..core.settings import settings
from ..db.models import PipelineJob, SampleStage
from ..schemas.common import PipelineStatus
from ..tasks.celery_app import celery_app
from ..utils_paths import ensure_safe_component, safe_resolve_user_path
from .job_service import append_job_event


def _output_names(job: PipelineJob) -> tuple[int, list[str]]:
    payload = job.payload or {}
    if job.stage == "samples_download":
        return 1, [str(payload.get("sra_code") or "")]
    if job.stage == "quality_analysis":
        names = [re.sub(r"\.(?:fastq|fq)(?:\.gz)?$", ".html", str(name))
                 for name in payload.get("samples") or []]
        return 2, names
    if job.stage == "trimming":
        sample = str(payload.get("sample") or "")
        stem = re.sub(r"\.(?:fastq|fq)(?:\.gz)?$", "", sample)
        return 3, [f"{sample}_{mate}_trimmed.fastq.gz" for mate in (1, 2)] + [f"{stem}_trimmed.fastq.gz"]
    if job.stage == "quality_analysis_post_trim":
        names = [re.sub(r"_trimmed\.(?:fastq|fq)(?:\.gz)?$", "_post_trim.html", str(name))
                 for name in payload.get("samples") or []]
        return 4, names
    if job.stage == "alignment":
        return 5, [str(payload.get("sample") or "") + ".bam"]
    if job.stage == "quantification":
        return 6, [str(name).removesuffix(".bam") + ".txt" for name in payload.get("samples") or []]
    if job.stage == "clustering":
        return 9, [str(name) for name in payload.get("sheets") or []]
    if job.stage == "llm":
        return 10, [str(name) for name in payload.get("sheets") or []]
    return 0, []


def remove_partial_outputs(db: Session, job: PipelineJob) -> None:
    if job.stage == "deg":
        payload = job.payload or {}
        run_id = payload.get("run_id")
        folder = (safe_resolve_user_path(settings.users_root, job.user_id, "pipelines",
                  ensure_safe_component(str(run_id)), "DEG") if run_id else
                  safe_resolve_user_path(settings.users_root, job.user_id, "DEG"))
        if folder.is_dir():
            if run_id:
                shutil.rmtree(folder)
            elif job.started_at:
                started = job.started_at if job.started_at.tzinfo else job.started_at.replace(tzinfo=timezone.utc)
                for path in folder.iterdir():
                    if path.is_file() and path.stat().st_mtime >= started.timestamp() - 2:
                        path.unlink()
        db.commit()
        return
    stage_id, names = _output_names(job)
    if not stage_id:
        return
    names = [ensure_safe_component(name) for name in names if name]
    root = Path(settings.users_root)
    if job.stage == "samples_download":
        sample = ensure_safe_component(names[0])
        path = safe_resolve_user_path(str(root), job.user_id, "samples", sample)
        if path.is_dir():
            shutil.rmtree(path)
    elif job.stage == "alignment":
        sample = ensure_safe_component(str((job.payload or {}).get("sample") or ""))
        path = safe_resolve_user_path(str(root), job.user_id, "alignment", sample)
        if path.is_dir():
            shutil.rmtree(path)
    elif job.stage in ("clustering", "llm"):
        for name in names:
            row = db.query(SampleStage).filter_by(user_id=job.user_id,
                stage_id=stage_id, name=name).first()
            if row is not None and row.status == "COMPLETED":
                continue
            path = safe_resolve_user_path(str(root), job.user_id, job.stage, name)
            if path.is_dir():
                shutil.rmtree(path)
    else:
        folder = {"quality_analysis": "QC", "trimming": "trimmed",
                  "quality_analysis_post_trim": "QC_PostTrim", "quantification": "quantification"}[job.stage]
        for name in names:
            if job.stage.startswith("quality_analysis"):
                stem = name.removesuffix("_post_trim.html").removesuffix(".html")
                sample = re.sub(r"_R?[12]$", "", stem)
                suffix = "_trimmed_fastqc" if job.stage.endswith("post_trim") else "_fastqc"
                for ext in (".html", ".zip"):
                    path = safe_resolve_user_path(str(root), job.user_id, folder, sample,
                                                  stem + suffix + ext)
                    path.unlink(missing_ok=True)
            else:
                path = safe_resolve_user_path(str(root), job.user_id, folder, name)
                path.unlink(missing_ok=True)
    query = db.query(SampleStage).filter(
        SampleStage.user_id == job.user_id,
        SampleStage.stage_id == stage_id,
        SampleStage.status.in_(["PENDING", "RUNNING", "FAILED", "CANCELED"]),
    )
    if job.stage == "samples_download":
        query = query.filter(SampleStage.sra_code == names[0])
    else:
        query = query.filter(SampleStage.name.in_(names))
    query.delete(synchronize_session=False)
    db.commit()


def cancel_active_job(db: Session, job: PipelineJob, reason: str = "Cancelado pelo usuário.") -> bool:
    if job.status not in (PipelineStatus.PENDING.value, PipelineStatus.RUNNING.value):
        return False
    job.status = PipelineStatus.CANCELED.value
    job.error_message = reason
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    append_job_event(job.user_id, job.id, f"{job.stage}: cancelado pelo usuário; removendo saídas incompletas.")
    pid_path = safe_resolve_user_path(settings.users_root, job.user_id, "logs", "jobs",
                                      f"{job.id}.progress.pid")
    done_path = pid_path.with_suffix(".canceled")
    if pid_path.is_file():
        # The worker owns the process namespace. Give it time to observe the
        # canceled state and terminate its own tool process group.
        deadline = time.monotonic() + 12
        while not done_path.is_file() and time.monotonic() < deadline:
            time.sleep(0.2)
        if done_path.is_file():
            done_path.unlink(missing_ok=True)
            try:
                celery_app.control.revoke(job.id, terminate=False)
            except Exception:
                pass
            return True
    try:
        celery_app.control.revoke(job.id, terminate=True, signal="SIGTERM")
    except Exception:
        pass
    remove_partial_outputs(db, job)
    append_job_event(job.user_id, job.id, f"{job.stage}: cancelamento concluído.")
    return True


def cancel_jobs_for_output(db: Session, user_id: int, stage: str, name: str) -> bool:
    jobs = db.query(PipelineJob).filter(PipelineJob.user_id == user_id,
        PipelineJob.stage == stage, PipelineJob.status.in_(["PENDING", "RUNNING"])).all()
    canceled = False
    for job in jobs:
        _, outputs = _output_names(job)
        if name in outputs:
            canceled = cancel_active_job(db, job) or canceled
    return canceled
