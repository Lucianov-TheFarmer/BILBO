from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .common import PipelineStatus


class JobEnqueueResponse(BaseModel):
    job_id: str
    status: PipelineStatus
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    stage: str
    status: PipelineStatus
    user_id: int
    payload: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class JobListItem(BaseModel):
    job_id: str
    stage: str
    status: PipelineStatus
    created_at: datetime
    finished_at: Optional[datetime] = None


class JobArtifactResponse(BaseModel):
    id: int
    kind: str
    path: str
    metadata_json: Optional[dict[str, Any]] = None


class JobEnqueueRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
