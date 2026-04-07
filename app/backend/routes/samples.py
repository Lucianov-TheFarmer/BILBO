from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from ..core.settings import settings
from ..db.database import get_db
from ..db.models import PipelineJob, SampleStage, User, Stage
from ..services.job_service import audit, create_job, normalize_status
from ..tasks.pipeline_tasks import enqueue_pipeline_job
from ..utils import get_current_user, get_current_user_compat
from ..utils_paths import safe_resolve_user_path
from pydantic import BaseModel
import subprocess
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class SampleCreateRequest(BaseModel):
    sra_codes: List[str]
    size: str

class SampleStageCreateRequest(BaseModel):
    stage_id: int
    status: str


def _latest_samples_download_job(db: Session, user_id: int, sra_code: str) -> Optional[PipelineJob]:
    jobs = (
        db.query(PipelineJob)
        .filter(PipelineJob.user_id == user_id, PipelineJob.stage == "samples_download")
        .order_by(PipelineJob.created_at.desc())
        .limit(100)
        .all()
    )
    for job in jobs:
        payload = job.payload or {}
        if isinstance(payload, dict) and str(payload.get("sra_code")) == sra_code:
            return job
    return None


def _is_stale_pending_job(job: PipelineJob, stale_seconds: int = 300) -> bool:
    if job.status != "PENDING" or job.started_at is not None:
        return False
    if job.created_at is None:
        return True
    created = job.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - created).total_seconds() >= stale_seconds

def update_sample_status(db: Session, sra_code: str, status: str, user_id: int):
    """Update the status of a sample."""
    db_sample_stage = db.query(SampleStage).filter(
        SampleStage.sra_code == sra_code,
        SampleStage.stage_id == 1,
        SampleStage.user_id == user_id,
    ).first()
    if not db_sample_stage:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample_stage.status = normalize_status(status)
    db.commit()
    return db_sample_stage

@router.post("/samples/")
def create_samples(request: SampleCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    created_samples = []
    for sra_code in request.sra_codes:
        if not isinstance(sra_code, str) or not sra_code or not sra_code.upper().startswith(("SRR", "ERR", "DRR")) or not sra_code[3:].isdigit():
            raise HTTPException(status_code=400, detail=f"Código SRA inválido: {sra_code}")

        existing_sample_stage = db.query(SampleStage).filter(
            SampleStage.sra_code == sra_code, SampleStage.stage_id == 1, SampleStage.user_id == current_user.id
        ).first()
        if existing_sample_stage:
            continue

        db_sample_stage = SampleStage(
            stage_id=1,
            name=f"{sra_code}",
            sra_code=sra_code,
            size=request.size,
            status="PENDING",
            user_id=current_user.id,
        )
        db.add(db_sample_stage)
        created_samples.append(db_sample_stage)
    db.commit()
    for sample_stage in created_samples:
        db.refresh(sample_stage)
    return created_samples

@router.get("/samples/")
def read_samples(skip: int = 0, limit: int = 10, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    samples = db.query(SampleStage).filter(SampleStage.user_id == current_user.id, SampleStage.stage_id == 1).offset(skip).limit(limit).all()
    return samples

@router.put("/samples/{sample_id}")
def update_sample(sample_id: int, status: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample = db.query(SampleStage).filter(SampleStage.id == sample_id).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample.status = status
    db.commit()
    db.refresh(db_sample)
    return db_sample

@router.delete("/samples/{sra_code}")
def delete_sample(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sra_code_basename = sra_code.replace("_1.fastq", "").replace("_2.fastq", "").replace(".fastq", "")

    all_samples = db.query(SampleStage).filter(
        SampleStage.sra_code == sra_code_basename,
        SampleStage.stage_id == 1,
        SampleStage.user_id == current_user.id
    ).all()

    if not all_samples:
        raise HTTPException(status_code=404, detail="Sample not found")

    user_id = current_user.id

    sample_names = [sample.name for sample in all_samples]
    is_paired_end = any("_1.fastq" in name or "_2.fastq" in name for name in sample_names)

    for sample in all_samples:
        db.delete(sample)
    db.commit()

    if is_paired_end:
        for suffix in ["_1.fastq", "_2.fastq"]:
            file_path = f"../users/{user_id}/samples/{sra_code_basename}/{sra_code_basename}{suffix}"
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Arquivo {file_path} excluído com sucesso do sistema de arquivos.")
                except Exception as e:
                    logger.error(f"Erro ao excluir arquivo {file_path} do sistema de arquivos: {e}")
            else:
                logger.warning(f"Arquivo {file_path} não encontrado para exclusão.")
    else:
        file_path = f"../users/{user_id}/samples/{sra_code_basename}/{sra_code_basename}.fastq"
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Arquivo {file_path} excluído com sucesso do sistema de arquivos.")
            except Exception as e:
                logger.error(f"Erro ao excluir arquivo {file_path} do sistema de arquivos: {e}")
        else:
            logger.warning(f"Arquivo {file_path} não encontrado para exclusão.")

    sample_dir = f"../users/{user_id}/samples/{sra_code_basename}"
    try:
        if os.path.exists(sample_dir) and not os.listdir(sample_dir):
            os.rmdir(sample_dir)
            logger.info(f"Diretório {sample_dir} removido com sucesso.")
    except Exception as e:
        logger.warning(f"Não foi possível remover diretório {sample_dir}: {e}")

    audit(
        db,
        action="sample_deleted",
        user_id=current_user.id,
        stage="samples",
        metadata_json={"sra_code": sra_code_basename},
    )
    return {"message": "Sample and associated files deleted successfully"}

@router.get("/samples/status/{sra_code}")
def get_sample_status(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample_stage = db.query(SampleStage).filter(SampleStage.sra_code == sra_code, SampleStage.stage_id == 1, SampleStage.user_id == current_user.id).first()
    if db_sample_stage is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {"status": db_sample_stage.status}

@router.post("/samples/download", status_code=status.HTTP_202_ACCEPTED)
def download_pending_samples(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pending_sample = db.query(SampleStage).filter(
        SampleStage.status.in_(["PENDING", "Pending", "Na fila"]),
        SampleStage.stage_id == 1,
        SampleStage.user_id == current_user.id,
    ).first()

    if not pending_sample:
        running_sample = db.query(SampleStage).filter(
            SampleStage.status == "RUNNING",
            SampleStage.stage_id == 1,
            SampleStage.user_id == current_user.id,
        ).first()
        if not running_sample:
            raise HTTPException(status_code=404, detail="No pending samples found")

        latest_job = _latest_samples_download_job(db, current_user.id, running_sample.sra_code)
        if latest_job and latest_job.status in ["PENDING", "RUNNING"]:
            if latest_job.status == "PENDING" and _is_stale_pending_job(latest_job):
                latest_job.status = "FAILED"
                latest_job.error_message = "Marked as stale and requeued by /samples/download"
                latest_job.finished_at = datetime.now(timezone.utc)
                db.commit()
            else:
                return {
                    "job_id": latest_job.id,
                    "status": latest_job.status,
                    "message": f"Download already queued/running for sample {running_sample.sra_code}",
                    "sample_name": running_sample.sra_code,
                }

        running_sample.status = "PENDING"
        db.commit()
        pending_sample = running_sample

    sra_code = pending_sample.sra_code

    job = create_job(db, stage="samples_download", user_id=current_user.id, payload={"sra_code": sra_code})
    audit(
        db,
        action="download_enqueued",
        user_id=current_user.id,
        stage="samples_download",
        job_id=job.id,
        metadata_json={"sra_code": sra_code},
    )
    enqueue_pipeline_job(job.id)

    return {
        "job_id": job.id,
        "status": "PENDING",
        "message": f"Download job enqueued for sample {sra_code}",
        "sample_name": sra_code,
    }

@router.post("/samples/update_status")
async def update_sample_status_endpoint(
    sra_code: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_sample_stage = update_sample_status(db, sra_code, status, current_user.id)
    normalized = normalize_status(status)

    if normalized == "COMPLETED":
        db_sample_stage.name = f"{sra_code}.fastq"
        db_sample_stage.status = normalized
        db.commit()

    return {"message": f"Sample {sra_code} status updated to {normalized}"}

@router.post("/samples/calculate_size")
async def calculate_size(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    logger.info(f"Iniciando cálculo de tamanho para {sra_code}")
    db_sample_stage = db.query(SampleStage).filter(
        SampleStage.sra_code == sra_code, SampleStage.stage_id == 1, SampleStage.user_id == current_user.id
    ).first()
    if db_sample_stage is None or normalize_status(db_sample_stage.status) != "COMPLETED":
        logger.warning(f"Amostra {sra_code} não encontrada ou não está 'Completed'")
        raise HTTPException(status_code=404, detail="Sample not found or not completed")

    user_id = current_user.id

    command = ["python3", "/app/backend/scripts/calculate_size.py", sra_code, str(user_id)]
    logger.info("Executando comando para calcular tamanho: %s", " ".join(command))
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    logger.info(f"Saída do cálculo de tamanho para {sra_code}: {stdout}")
    if stderr:
        logger.error(f"Erro do cálculo de tamanho para {sra_code}: {stderr}")

    if process.returncode != 0:
        logger.error(f"Erro ao calcular tamanho: {stderr}")
        raise HTTPException(status_code=500, detail="Error calculating size")

    sizes = stdout.strip().split(',')
    if len(sizes) != 2:
        logger.error(f"Formato de tamanho inválido retornado pelo script: {stdout}")
        raise HTTPException(status_code=500, detail="Invalid size format returned by script")

    size_1, size_2 = sizes

    sra_code_basename = sra_code.split("_")[0]
    logger.info(f"Atualizando registros para {sra_code_basename}_1.fastq e {sra_code_basename}_2.fastq")

    db_sample_stage_1 = SampleStage(
        stage_id=1,
        name=f"{sra_code_basename}_1.fastq",
        sra_code=sra_code_basename,
        size=size_1,
        status="COMPLETED",
        user_id=current_user.id,
    )
    db_sample_stage_2 = SampleStage(
        stage_id=1,
        name=f"{sra_code_basename}_2.fastq",
        sra_code=sra_code_basename,
        size=size_2,
        status="COMPLETED",
        user_id=current_user.id,
    )
    db.add(db_sample_stage_1)
    db.add(db_sample_stage_2)
    db.delete(db_sample_stage)
    db.commit()

    logger.info(f"Tamanhos das amostras {sra_code_basename} atualizados com sucesso.")
    return {"message": "Sample sizes updated successfully"}

@router.get("/samples/pending_count")
def get_pending_samples_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = db.query(SampleStage).filter(
        SampleStage.stage_id == 1,
        SampleStage.user_id == current_user.id,
        SampleStage.status.in_(["PENDING", "Pending", "Na fila", "RUNNING"]),
    ).all()

    pending_count = 0
    for row in rows:
        normalized = normalize_status(row.status)
        if normalized == "PENDING":
            pending_count += 1
            continue
        if normalized == "RUNNING":
            latest_job = _latest_samples_download_job(db, current_user.id, row.sra_code)
            if latest_job is None:
                pending_count += 1
            elif latest_job.status == "PENDING" and _is_stale_pending_job(latest_job):
                pending_count += 1

    return {"pending_count": pending_count}

@router.post("/stages/")
def create_stages(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    stages = [
        {"id": 1, "name": "obtencao"},
        {"id": 2, "name": "qualidade1"},
        {"id": 3, "name": "trimagem"},
        {"id": 4, "name": "qualidade2"},
        {"id": 5, "name": "alinhamento"},
        {"id": 6, "name": "quantificacao"},
        {"id": 7, "name": "referencia"},
        {"id": 8, "name": "contraste"},
        {"id": 9, "name": "clustering_semantico"},
        {"id": 10, "name": "interpretacao_llm"}

    ]
    for stage in stages:
        db_stage = db.query(Stage).filter(Stage.id == stage["id"]).first()
        if not db_stage:
            db_stage = Stage(id=stage["id"], name=stage["name"])
            db.add(db_stage)
    db.commit()
    return {"message": "Stages created successfully"}

@router.post("/samples/{sample_id}/stages/")
def create_sample_stage(sample_id: int, request: SampleStageCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    source_sample = db.query(SampleStage).filter(SampleStage.id == sample_id, SampleStage.user_id == current_user.id).first()
    if not source_sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample_stage = SampleStage(
        stage_id=request.stage_id,
        name=source_sample.name,
        sra_code=source_sample.sra_code,
        size=source_sample.size,
        status=normalize_status(request.status),
        user_id=current_user.id,
    )
    db.add(db_sample_stage)
    db.commit()
    db.refresh(db_sample_stage)
    return db_sample_stage

@router.get("/samples/{sample_id}/stages/")
def get_sample_stages(sample_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    source_sample = db.query(SampleStage).filter(SampleStage.id == sample_id, SampleStage.user_id == current_user.id).first()
    if not source_sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    sample_stages = db.query(SampleStage).filter(
        SampleStage.user_id == current_user.id,
        SampleStage.sra_code == source_sample.sra_code,
    ).all()
    return sample_stages

@router.put("/samples/{sample_id}/stages/{stage_id}")
def update_sample_stage(sample_id: int, stage_id: int, status: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    source_sample = db.query(SampleStage).filter(SampleStage.id == sample_id, SampleStage.user_id == current_user.id).first()
    if not source_sample:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample_stage = db.query(SampleStage).filter(
        SampleStage.stage_id == stage_id,
        SampleStage.user_id == current_user.id,
        SampleStage.sra_code == source_sample.sra_code,
    ).first()
    if not db_sample_stage:
        raise HTTPException(status_code=404, detail="Sample stage not found")
    db_sample_stage.status = normalize_status(status)
    db.commit()
    db.refresh(db_sample_stage)
    return db_sample_stage

@router.get("/samples/stages/{stage_id}")
def get_samples_by_stage(stage_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sample_stages = db.query(SampleStage).filter(SampleStage.stage_id == stage_id, SampleStage.user_id == current_user.id).all()
    samples = []
    for sample_stage in sample_stages:
        samples.append({
            "id": sample_stage.id,
            "sra_code": sample_stage.sra_code,
            "size": sample_stage.size,
            "status": sample_stage.status,
            "name": sample_stage.name,
        })
    return samples

@router.get("/download/{stage_name}/{file_name}")
def download_file(
    stage_name: str,
    file_name: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_compat),
):
    """Download a file from any stage with bearer auth (legacy query token accepted)."""
    user_id = current_user.id

    sample_stage = db.query(SampleStage).filter(SampleStage.name == file_name, SampleStage.user_id == user_id).first()
    if not sample_stage:
        raise HTTPException(status_code=404, detail="Sample not found in database")

    users_root = Path(settings.users_root)
    sra_code = sample_stage.sra_code
    path_map = {
        "obtencao": safe_resolve_user_path(str(users_root), user_id, "samples", sra_code, file_name),
        "qualidade1": safe_resolve_user_path(
            str(users_root),
            user_id,
            "QC",
            file_name.replace(".html", ".fastq"),
            file_name.replace(".html", "_fastqc.zip"),
        ),
        "trimagem": safe_resolve_user_path(str(users_root), user_id, "trimmed", file_name),
        "qualidade2": safe_resolve_user_path(
            str(users_root),
            user_id,
            "QC_PostTrim",
            file_name.replace("_post_trim.html", "_trimmed.fastq"),
            file_name.replace("_post_trim.html", "_trimmed_fastqc.zip"),
        ),
        "alinhamento": safe_resolve_user_path(str(users_root), user_id, "alignment", sra_code, file_name),
        "quantificacao": safe_resolve_user_path(str(users_root), user_id, "quantification", file_name),
    }

    file_path = path_map.get(stage_name)

    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    headers = {}
    if not request.headers.get("Authorization") and request.query_params.get("token"):
        headers["X-Auth-Deprecated"] = "Use Authorization: Bearer <token>; query token support will be removed."

    audit(
        db,
        action="stage_file_download",
        user_id=current_user.id,
        stage=stage_name,
        metadata_json={"filename": file_path.name},
    )
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream",
        headers=headers,
    )
