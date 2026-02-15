from __future__ import annotations

from datetime import datetime, timezone
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

    return JobStatusResponse(
        job_id=job.id,
        stage=job.stage,
        status=_as_pipeline_status(job.status),
        user_id=job.user_id,
        payload=job.payload,
        result=job.result,
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
