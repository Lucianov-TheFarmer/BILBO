"""Import a genomic assembly and its annotation from local files or public URLs."""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.settings import settings
from ..db.database import get_db
from ..db.models import PipelineJob, SampleStage, User
from ..services.job_service import create_job
from ..services.reference_import import MAX_TRANSFER, source_format, validate_public_url
from ..tasks.reference_import import import_reference
from ..utils import get_current_user

router = APIRouter(prefix="/genomes/import")


class UrlReference(BaseModel):
    label: str = Field(min_length=2, max_length=100)
    fasta_url: str
    annotation_url: str
    threads: int = Field(default=8, ge=1, le=64)
    sjdb_overhang: int = Field(default=100, ge=1, le=1000)


def _queue(db: Session, user: User, label: str, source: dict, threads: int, overhang: int):
    clean = label.strip()
    if not clean or not re.fullmatch(r"[\w .()\-]+", clean, re.UNICODE):
        raise HTTPException(422, "Invalid reference name")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", clean).strip("_")[:32] or "reference"
    accession = f"USR{user.id}_{slug}_{uuid.uuid4().hex[:8]}"
    row = SampleStage(stage_id=7, name=f"{clean} ({accession})", sra_code=accession,
                      size=None, status="PENDING", user_id=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    job = create_job(db, "reference_import", user.id,
                     {"accession": accession, "row_id": row.id, "label": clean,
                      "source": source, "threads": threads, "sjdb_overhang": overhang})
    try:
        import_reference.delay(job.id)
    except Exception:
        row.status = "FAILED"
        db.commit()
        raise HTTPException(503, "Reference worker unavailable")
    return {"job_id": job.id, "accession": accession, "status": "PENDING"}


@router.post("/url", status_code=202)
def import_url(request: UrlReference, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        fasta = validate_public_url(request.fasta_url, "fasta")
        annotation = validate_public_url(request.annotation_url, "annotation")
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return _queue(db, user, request.label,
                  {"type": "url", "fasta": fasta, "annotation": annotation},
                  request.threads, request.sjdb_overhang)


@router.post("/upload", status_code=202)
async def import_upload(label: str = Form(...), fasta: UploadFile = File(...),
                        annotation: UploadFile = File(...), threads: int = Form(8),
                        sjdb_overhang: int = Form(100), user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    if not 1 <= threads <= 64 or not 1 <= sjdb_overhang <= 1000:
        raise HTTPException(422, "Invalid indexing settings")
    try:
        source_format(fasta.filename or "", "fasta")
        source_format(annotation.filename or "", "annotation")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    incoming = Path(settings.users_root) / "ref_genomes" / "_incoming" / uuid.uuid4().hex
    incoming.mkdir(parents=True, exist_ok=False)
    try:
        for upload, kind in ((fasta, "fasta"), (annotation, "annotation")):
            target = incoming / f"{kind}{''.join(Path(upload.filename).suffixes)}"
            total = 0
            with target.open("wb") as output:
                while chunk := await upload.read(8 * 1024 * 1024):
                    total += len(chunk)
                    if total > MAX_TRANSFER:
                        raise ValueError("Reference upload exceeds the 12 GiB file limit")
                    output.write(chunk)
        return _queue(db, user, label,
                      {"type": "upload", "directory": str(incoming),
                       "fasta": next(str(p) for p in incoming.iterdir() if p.name.startswith("fasta")),
                       "annotation": next(str(p) for p in incoming.iterdir() if p.name.startswith("annotation"))},
                      threads, sjdb_overhang)
    except Exception:
        shutil.rmtree(incoming, ignore_errors=True)
        raise


@router.get("/jobs/{job_id}")
def import_status(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(PipelineJob).filter(PipelineJob.id == job_id,
                                       PipelineJob.user_id == user.id,
                                       PipelineJob.stage == "reference_import").first()
    if not job:
        raise HTTPException(404, "Reference job not found")
    return {"job_id": job.id, "status": job.status, "result": job.result or {},
            "error_message": job.error_message}


@router.get("/jobs")
def recent_imports(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs = (db.query(PipelineJob)
            .filter(PipelineJob.user_id == user.id, PipelineJob.stage == "reference_import")
            .order_by(PipelineJob.created_at.desc()).limit(10).all())
    return [{"job_id": job.id, "label": (job.payload or {}).get("label"),
             "accession": (job.payload or {}).get("accession"),
             "status": job.status, "phase": (job.result or {}).get("phase"),
             "error_message": job.error_message} for job in jobs]
