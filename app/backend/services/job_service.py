from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..core.settings import settings
from ..db.models import Artifact, AuditLog, PipelineJob
from ..schemas.common import PipelineStatus


STATUS_NORMALIZATION = {
    "pending": PipelineStatus.PENDING.value,
    "in progress": PipelineStatus.RUNNING.value,
    "running": PipelineStatus.RUNNING.value,
    "aligning": PipelineStatus.RUNNING.value,
    "counting": PipelineStatus.RUNNING.value,
    "na fila": PipelineStatus.PENDING.value,
    "completed": PipelineStatus.COMPLETED.value,
    "done": PipelineStatus.COMPLETED.value,
    "clustered": PipelineStatus.COMPLETED.value,
    "interpreted": PipelineStatus.COMPLETED.value,
    "failed": PipelineStatus.FAILED.value,
    "erro": PipelineStatus.FAILED.value,
    "error": PipelineStatus.FAILED.value,
    "canceled": PipelineStatus.CANCELED.value,
    "cancelled": PipelineStatus.CANCELED.value,
}


def normalize_status(raw: Optional[str]) -> str:
    if raw is None:
        return PipelineStatus.PENDING.value
    key = raw.strip().lower()
    return STATUS_NORMALIZATION.get(key, raw.upper())


def create_job(db: Session, stage: str, user_id: int, payload: Optional[dict[str, Any]] = None) -> PipelineJob:
    job = PipelineJob(
        id=uuid.uuid4().hex,
        stage=stage,
        status=PipelineStatus.PENDING.value,
        user_id=user_id,
        payload=payload or {},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def set_job_running(db: Session, job_id: str) -> PipelineJob:
    job = db.query(PipelineJob).filter(
        PipelineJob.id == job_id
    ).first()

    if job is None:
        raise ValueError(f"Job {job_id} not found")

    terminal_statuses = {
        PipelineStatus.COMPLETED.value,
        PipelineStatus.FAILED.value,
        PipelineStatus.CANCELED.value,
    }

    if job.status in terminal_statuses or job.finished_at is not None:
        return job

    job.status = PipelineStatus.RUNNING.value
    job.started_at = datetime.now(timezone.utc)
    job.error_message = None

    db.commit()
    db.refresh(job)
    return job


def set_job_finished(
    db: Session,
    job_id: str,
    status: PipelineStatus,
    *,
    result: Optional[dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> PipelineJob:
    job = db.query(PipelineJob).filter(PipelineJob.id == job_id).first()
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    job.status = status.value
    job.result = result or {}
    job.error_message = error_message
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job


def add_artifact(
    db: Session,
    *,
    job_id: str,
    user_id: int,
    kind: str,
    path: str,
    metadata_json: Optional[dict[str, Any]] = None,
) -> Artifact:
    users_root = Path(settings.users_root).resolve()
    owner_root = (users_root / str(user_id)).resolve()
    candidate = Path(path).resolve()
    try:
        candidate.relative_to(owner_root)
    except ValueError as exc:
        raise ValueError("Artifact path must stay under the owner directory") from exc

    artifact = Artifact(
        job_id=job_id,
        user_id=user_id,
        kind=kind,
        path=str(candidate),
        metadata_json=metadata_json or {},
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def audit(
    db: Session,
    *,
    action: str,
    user_id: int,
    stage: Optional[str] = None,
    job_id: Optional[str] = None,
    metadata_json: Optional[dict[str, Any]] = None,
) -> AuditLog:
    log = AuditLog(
        action=action,
        user_id=user_id,
        stage=stage,
        job_id=job_id,
        metadata_json=metadata_json or {},
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
