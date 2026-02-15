import logging
import shutil

from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..core.settings import settings
from ..db.database import get_db
from ..db.models import SampleStage, User
from ..services.job_service import audit, create_job, normalize_status
from ..tasks.pipeline_tasks import enqueue_pipeline_job
from ..utils import get_current_user, manager
from ..utils_paths import safe_resolve_user_path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class QualityAnalysisRequest(BaseModel):
    samples: list[str]

@router.post("/quality_analysis/", status_code=status.HTTP_202_ACCEPTED)  # Iniciar análise de qualidade
def start_quality_analysis(request: QualityAnalysisRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    to_process: list[str] = []
    for name in request.samples:  # Usar 'name' em vez de 'sra_code'
        # Garantir que o 'name' seja o nome completo da amostra (ex.: SRR31951083_1.fastq ou SRR31951083_2.fastq)
        db_sample_stage = db.query(SampleStage).filter(
            SampleStage.name == name,  # Verificar pelo nome completo da amostra
            SampleStage.stage_id == 1,
            SampleStage.user_id == user_id
        ).first()

        if not db_sample_stage:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {name} not found")

        suffix = "_1" if "_1.fastq" in name else "_2"

        output_name = f"{db_sample_stage.sra_code}{suffix}.html"
        exists = db.query(SampleStage).filter(
            SampleStage.name == output_name,
            SampleStage.stage_id == 2,
            SampleStage.user_id == user_id,
        ).first()
        if not exists:
            db.add(
                SampleStage(
                    stage_id=2,
                    name=output_name,
                    sra_code=db_sample_stage.sra_code,
                    size=None,
                    status="RUNNING",
                    user_id=user_id,
                )
            )
        else:
            exists.status = "RUNNING"
            db.add(exists)
        to_process.append(name)

    db.commit()

    job = create_job(db, stage="quality_analysis", user_id=user_id, payload={"samples": to_process})
    audit(
        db,
        action="quality_analysis_enqueued",
        user_id=user_id,
        stage="quality_analysis",
        job_id=job.id,
        metadata_json={"samples": to_process},
    )
    enqueue_pipeline_job(job.id)
    return {"job_id": job.id, "status": "PENDING", "message": "Quality analysis job enqueued"}
        
@router.post("/quality_analysis/update_status")
async def update_quality_analysis_status(
    sra_code: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Atualize apenas o registro correto, sem sobrescrever o nome
    updated = False
    for suffix in ["_1", "_2"]:
        name = f"{sra_code}{suffix}.html"
        db_sample_stage = db.query(SampleStage).filter(
            SampleStage.name == name,
            SampleStage.stage_id == 2,
            SampleStage.user_id == current_user.id,
        ).first()
        if db_sample_stage:
            db_sample_stage.status = normalize_status(status)
            db.commit()
            updated = True
    if not updated:
        raise HTTPException(status_code=404, detail="Sample not found")
    # Notify frontend via WebSocket about the status change
    try:
        await manager.broadcast(f"Quality analysis {sra_code} status: {status}", user_id=current_user.id)
    except Exception as e:
        logger.warning(f"Failed to broadcast quality analysis status: {e}")

    return {"message": f"Sample {sra_code} status updated to {status}"}

@router.get("/quality_analysis/completed")
def get_completed_quality_analysis(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    logger.info("Fetching completed quality analysis results...")
    sample_stages = db.query(SampleStage).filter(SampleStage.stage_id == 2, SampleStage.user_id == current_user.id).all()
    logger.info(f"Raw sample stages fetched: {sample_stages}")

    samples = []
    for sample_stage in sample_stages:
        sample_data = {
            "id": sample_stage.id,
            "sra_code": sample_stage.sra_code,
            "size": sample_stage.size,
            "status": sample_stage.status,
            "name": sample_stage.name  # Include the name field
        }
        samples.append(sample_data)
        logger.info(f"Processed sample data: {sample_data}")

    logger.info(f"Final response being sent to frontend: {samples}")
    return samples

@router.delete("/quality_analysis/{name}")
def delete_quality_analysis_result(name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Encontrar o registro pelo campo 'name' e 'stage_id=2'
    db_sample_stage = db.query(SampleStage).filter(
        SampleStage.name == name,
        SampleStage.stage_id == 2,
        SampleStage.user_id == current_user.id
    ).first()

    if not db_sample_stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {name} not found")

    # Excluir o registro do banco de dados
    db.delete(db_sample_stage)
    db.commit()

    output_dir = safe_resolve_user_path(
        settings.users_root,
        current_user.id,
        "QC",
        name.replace(".html", ".fastq"),
    )
    if output_dir.exists():
        shutil.rmtree(output_dir, ignore_errors=True)

    return {"message": f"Quality analysis result {name} deleted successfully"}
