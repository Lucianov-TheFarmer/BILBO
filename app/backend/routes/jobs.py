from __future__ import annotations
from pathlib import Path

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


def _samples_download_progress(job: PipelineJob) -> Optional[dict[str, object]]:
    payload = job.payload or {}
    if not isinstance(payload, dict):
        return None

    sra_code = str(payload.get("sra_code") or "").strip()
    if not sra_code:
        return None

    log_path = f"/app/backend/logs/{sra_code}_download.log"
    log_text = _tail_text_file(log_path)
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

    return {
        "progress_percent": percent,
        "progress_source": "samples_download_log",
    }


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
