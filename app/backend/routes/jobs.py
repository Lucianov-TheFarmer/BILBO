from __future__ import annotations
from pathlib import Path
import csv
import json

from datetime import datetime, timezone
import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Artifact, PipelineJob, User
from ..schemas.common import PipelineStatus
from ..schemas.jobs import (
    JobArtifactResponse,
    JobEnqueueRequest,
    JobEnqueueResponse,
    JobListItem,
    JobStatusResponse,
)
from ..services.job_service import audit, create_job
from ..tasks.celery_app import celery_app
from ..tasks.pipeline_tasks import enqueue_pipeline_job
from ..utils import get_current_user

router = APIRouter()

ALLOWED_STAGES = {
    "samples_download",
    "quality_analysis",
    "quality_analysis_post_trim",
    "alignment",
    "quantification",
    "deg",
    "clustering",
    "llm",
    "results_barplot",
    "results_venn",
    "results_heatmap",
}


def _as_pipeline_status(value: str) -> PipelineStatus:
    try:
        return PipelineStatus(value)
    except ValueError:
        return PipelineStatus.PENDING


def _tail_text_file(path: str, max_bytes: int = 32768) -> str:
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes), os.SEEK_SET)
            return handle.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_progress_percent(log_text: str) -> Optional[float]:
    matches = re.findall(r"(\d{1,3}(?:\.\d+)?)%", log_text)
    if not matches:
        return None

    for value in reversed(matches):
        try:
            pct = float(value)
        except ValueError:
            continue
        if 0.0 <= pct <= 100.0:
            return pct
    return None


def _llm_progress(job: PipelineJob) -> Optional[dict[str, object]]:
    """Read atomic RAG checkpoints while an interpretation job is running."""
    if job.status != PipelineStatus.RUNNING.value or not job.started_at:
        return None
    sheets = (job.payload or {}).get("sheets") or []
    if len(sheets) != 1 or not re.fullmatch(r"[A-Za-z0-9_.-]+", str(sheets[0])):
        return None
    sheet = sheets[0]
    started = job.started_at.timestamp()
    root = Path("/users") / str(job.user_id)
    selected = root / "clustering" / sheet / "outputs" / "prioritized_genes.csv"
    checkpoint = root / "llm" / sheet / "rag_gene_evidence.json"
    try:
        if not selected.is_file() or selected.stat().st_mtime < started - 2:
            return None
        with selected.open(newline="", encoding="utf-8") as stream:
            total = sum(str(row.get("selected_for_search", "")).lower() in ("true", "1", "yes")
                        for row in csv.DictReader(stream))
        if total < 1:
            return None
        done = 0
        if checkpoint.is_file() and checkpoint.stat().st_mtime >= started - 2:
            data = json.loads(checkpoint.read_text(encoding="utf-8"))
            if isinstance(data, list):
                done = min(len(data), total)
        return {"progress_source": "rag_checkpoint", "progress_phase": "rag",
                "progress_done": done, "progress_total": total,
                "progress_percent": round(100 * done / total, 1)}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _samples_download_progress(job: PipelineJob) -> Optional[dict[str, object]]:
    payload = job.payload or {}
    if not isinstance(payload, dict):
        return None

    sra_code = str(payload.get("sra_code") or "").strip()
    if not sra_code:
        return None

    log_path = f"/app/backend/logs/{sra_code}_download.log"
    log_text = _tail_text_file(log_path, 1024 * 1024) if job.started_at else ""
    status_value = str(job.status or "")

    percent = _extract_progress_percent(log_text) if log_text else None
    if percent is None:
        if status_value == PipelineStatus.COMPLETED.value:
            percent = 100.0
        elif status_value == PipelineStatus.RUNNING.value:
            percent = 1.0

    if percent is not None and status_value == PipelineStatus.RUNNING.value and percent >= 100.0:
        # Keep running jobs below 100% until completion is confirmed.
        percent = 99.0

    progress_message = ""
    if log_text:
        lines = [line.strip() for line in log_text.replace("\r", "\n").split("\n") if line.strip()]
        if lines:
            progress_message = lines[-1]

    if status_value == PipelineStatus.COMPLETED.value and not progress_message:
        progress_message = "Download concluido"
    elif status_value == PipelineStatus.FAILED.value and not progress_message:
        progress_message = "Download falhou"

    if percent is None and not progress_message:
        return None

    phases = re.findall(r"([A-Za-z]+)\s*:\|", log_text)
    phase = phases[-1].lower() if phases else None

    return {
        "progress_percent": percent,
        "progress_phase": phase,
        "progress_message": progress_message,
        "progress_source": "samples_download_log",
    }


def _fastqc_progress(job: PipelineJob) -> Optional[dict[str, object]]:
    """Read FastQC's own periodic percentages from the shared sample log."""
    if job.status != PipelineStatus.RUNNING.value or not job.started_at:
        return None
    samples = (job.payload or {}).get("samples") or []
    if not samples:
        return None
    result = job.result or {}
    completed = min(int(result.get("completed_samples") or 0), len(samples))
    if completed >= len(samples):
        return None
    sample = str(samples[completed])
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", sample):
        return None
    if job.stage == "quality_analysis":
        stem = re.sub(r"\.(?:fastq|fq)(?:\.gz)?$", "", sample)
        base = re.sub(r"_[12]$", "", stem)
        path = Path("/users") / str(job.user_id) / "QC" / base / f"{sample}_quality_analysis.log"
    else:
        stem = re.sub(r"\.(?:fastq|fq)(?:\.gz)?$", "", sample)
        base = re.sub(r"_R?[12]_trimmed$", "", stem)
        path = Path("/users") / str(job.user_id) / "QC_PostTrim" / base / f"{stem}_quality_analysis_post_trim.log"
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        started = job.started_at if job.started_at.tzinfo else job.started_at.replace(tzinfo=timezone.utc)
        if modified < started:
            return None
    except OSError:
        return None
    text = _tail_text_file(str(path), 8192)
    matches = re.findall(r"Approx\s+(\d+(?:\.\d+)?)% complete", text)
    current = float(matches[-1]) if matches else 0.0
    if "Analysis complete for" in text:
        current = 100.0
    percent = min(99.9, round(100 * (completed + current / 100) / len(samples), 1))
    return {"progress_percent": percent, "progress_message": f"{sample}: {current:.0f}%",
            "completed_samples": completed, "total_samples": len(samples),
            "progress_source": "fastqc_log", "tool_log_path": str(path)}


def _active_tool_log(job: PipelineJob) -> Optional[Path]:
    """Find the current tool log; elapsed time alone never fails a job."""
    if not job.started_at:
        return None
    payload = job.payload or {}
    sample = str(payload.get("sample") or "")
    root = Path('/users') / str(job.user_id)
    paths = {
        'trimming': root / 'logs' / 'trimming' / f'{sample}.log',
        'alignment': root / 'alignment' / sample / f'{sample}_custom.log',
        'samples_download': Path('/app/backend/logs') / f"{payload.get('sra_code', '')}_download.log",
    }
    if job.stage == 'quantification':
        names = payload.get('samples') or []
        if len(names) == 1:
            sample = str(names[0])
            paths['quantification'] = root / 'logs' / 'quantification' / f'{sample}.log'
    path = paths.get(job.stage)
    if not path or not re.fullmatch(r'[A-Za-z0-9_.-]+', sample if job.stage != 'samples_download' else str(payload.get('sra_code') or '')):
        return None
    try:
        started = job.started_at.timestamp()
        return path if path.is_file() and path.stat().st_mtime >= started - 2 else None
    except OSError:
        return None


def _alignment_progress(job: PipelineJob) -> Optional[dict[str, object]]:
    if job.status != PipelineStatus.RUNNING.value:
        return None
    sample = str((job.payload or {}).get("sample") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}", sample):
        return None
    prefix = Path("/users") / str(job.user_id) / "alignment" / sample / sample
    log = _tail_text_file(str(prefix) + "_custom.log", 16384)
    phases = (
        ("[alignment] Completed", "completed"),
        ("[alignment] Cleanup intermediates", "cleanup"),
        ("[alignment] Marking duplicates", "mark_duplicates"),
        ("[alignment] Adding read groups", "read_groups"),
        ("[alignment] Sorting BAM", "sorting"),
        ("[alignment] Running STAR", "star"),
    )
    phase = next((name for marker, name in phases if marker in log), "starting")
    # Picard reports processed records periodically. This is a count, not an
    # estimated percentage, because multimapping makes the final count unknown.
    phase_log = log.rsplit("[alignment]", 1)[-1]
    counts = re.findall(r"(?:Read|Wrote|Processed|Written)\s+([\d,]+)\s+records", phase_log)
    processed = int(counts[-1].replace(",", "")) if counts else None
    return {"progress_phase": phase, "processed_records": processed,
            "progress_source": "alignment_log"}


@router.post("/jobs/{stage}/enqueue", status_code=status.HTTP_202_ACCEPTED, response_model=JobEnqueueResponse)
def enqueue_stage_job(
    stage: str,
    request: JobEnqueueRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if stage not in ALLOWED_STAGES:
        raise HTTPException(status_code=400, detail=f"Unknown stage: {stage}")

    job = create_job(db, stage=stage, user_id=current_user.id, payload=request.payload)
    audit(
        db,
        action="job_enqueued",
        user_id=current_user.id,
        stage=stage,
        job_id=job.id,
        metadata_json={"payload": request.payload},
    )

    enqueue_pipeline_job(job.id)

    return JobEnqueueResponse(
        job_id=job.id,
        status=PipelineStatus.PENDING,
        message=f"Job queued for stage '{stage}'",
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(PipelineJob).filter(PipelineJob.id == job_id, PipelineJob.user_id == current_user.id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    result_payload = dict(job.result or {})
    if job.stage == "samples_download":
        progress_data = _samples_download_progress(job)
        if progress_data:
            result_payload.update(progress_data)
    elif job.stage in ("quality_analysis", "quality_analysis_post_trim"):
        progress_data = _fastqc_progress(job)
        if progress_data:
            result_payload.update(progress_data)
    elif job.stage == "alignment":
        progress_data = _alignment_progress(job)
        if progress_data:
            result_payload.update(progress_data)
    elif job.stage == "llm":
        progress_data = _llm_progress(job)
        if progress_data:
            result_payload.update(progress_data)

    if job.status == PipelineStatus.RUNNING.value and not result_payload.get('progress_message'):
        tool_log = _active_tool_log(job)
        if tool_log:
            lines = _tail_text_file(str(tool_log), 4096).splitlines()
            if lines:
                result_payload['progress_message'] = lines[-1].strip()[:300]
                result_payload['progress_source'] = 'tool_log'

    # BILBO_GENERIC_JOB_PROGRESS
    try:
        progress_path = (
            Path('/users')
            / str(current_user.id)
            / 'logs'
            / 'jobs'
            / f'{job.id}.progress.log'
        )
        if progress_path.is_file():
            progress_log = _tail_text_file(str(progress_path))
            if progress_log:
                result_payload['progress_log'] = progress_log
            if job.status == PipelineStatus.RUNNING.value:
                tool_path = result_payload.get('tool_log_path')
                activity_path = Path(tool_path) if tool_path else _active_tool_log(job) or progress_path
                silent_seconds = int(datetime.now(timezone.utc).timestamp() - activity_path.stat().st_mtime)
                if silent_seconds > 300:
                    result_payload['monitor_warning'] = {
                        'code': 'no_recent_tool_output' if activity_path != progress_path else 'no_recent_events',
                        'silent_seconds': silent_seconds,
                    }
        result_payload.pop('tool_log_path', None)
    except OSError:
        pass

    return JobStatusResponse(
        job_id=job.id,
        stage=job.stage,
        status=_as_pipeline_status(job.status),
        user_id=job.user_id,
        payload=job.payload,
        result=result_payload or None,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/jobs", response_model=list[JobListItem])
def list_jobs(
    stage: Optional[str] = Query(default=None),
    status_filter: Optional[PipelineStatus] = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(PipelineJob).filter(PipelineJob.user_id == current_user.id)
    if stage:
        query = query.filter(PipelineJob.stage == stage)
    if status_filter:
        query = query.filter(PipelineJob.status == status_filter.value)

    jobs = query.order_by(PipelineJob.created_at.desc()).limit(200).all()
    return [
        JobListItem(
            job_id=j.id,
            stage=j.stage,
            status=_as_pipeline_status(j.status),
            created_at=j.created_at,
            finished_at=j.finished_at,
        )
        for j in jobs
    ]


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(PipelineJob).filter(PipelineJob.id == job_id, PipelineJob.user_id == current_user.id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status in {PipelineStatus.COMPLETED.value, PipelineStatus.FAILED.value, PipelineStatus.CANCELED.value}:
        return {"job_id": job.id, "status": job.status, "message": "Job already finished"}

    try:
        celery_app.control.revoke(job.id, terminate=True, signal="SIGTERM")
    except Exception:
        pass

    job.status = PipelineStatus.CANCELED.value
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    audit(db, action="job_canceled", user_id=current_user.id, stage=job.stage, job_id=job.id)

    return {"job_id": job.id, "status": job.status, "message": "Cancellation requested"}


@router.get("/jobs/{job_id}/artifacts", response_model=list[JobArtifactResponse])
def list_artifacts(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(PipelineJob).filter(PipelineJob.id == job_id, PipelineJob.user_id == current_user.id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    artifacts = (
        db.query(Artifact)
        .filter(Artifact.job_id == job_id, Artifact.user_id == current_user.id)
        .order_by(Artifact.created_at.asc())
        .all()
    )
    return [
        JobArtifactResponse(
            id=a.id,
            kind=a.kind,
            path=a.path,
            metadata_json=a.metadata_json,
        )
        for a in artifacts
    ]
