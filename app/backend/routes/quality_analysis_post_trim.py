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
from ..utils import get_current_user
from ..utils_paths import safe_resolve_user_path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


def _strip_trimmed_fastq_suffix(name: str) -> str:
    for suffix in (
        "_trimmed.fastq.gz",
        "_trimmed.fq.gz",
        "_trimmed.fastq",
        "_trimmed.fq",
    ):
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


class QualityAnalysisPostTrimRequest(BaseModel):
    samples: list[str]

@router.post("/quality_analysis_post_trim/start", status_code=status.HTTP_202_ACCEPTED)
def start_quality_analysis_post_trim(request: QualityAnalysisPostTrimRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    to_process: list[str] = []
    for name in request.samples:
        db_sample_stage = db.query(SampleStage).filter(
            SampleStage.name == name,
            SampleStage.stage_id == 3,
            SampleStage.user_id == user_id
        ).first()

        if not db_sample_stage:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {name} not found")

        basename = _strip_trimmed_fastq_suffix(db_sample_stage.name)

        # Verificar se já existe uma entrada para evitar duplicação
        existing_entry = db.query(SampleStage).filter(
            SampleStage.name == f"{basename}_post_trim.html",
            SampleStage.stage_id == 4,
            SampleStage.user_id == user_id
        ).first()

        if existing_entry:
            existing_entry.status = "RUNNING"
            db.add(existing_entry)
        else:
            db.add(
                SampleStage(
                    stage_id=4,
                    name=f"{basename}_post_trim.html",
                    sra_code=db_sample_stage.sra_code,
                    size=None,
                    status="RUNNING",
                    user_id=user_id,
                )
            )
        to_process.append(name)

    db.commit()

    job = create_job(db, stage="quality_analysis_post_trim", user_id=user_id, payload={"samples": to_process})
    audit(
        db,
        action="quality_analysis_post_trim_enqueued",
        user_id=user_id,
        stage="quality_analysis_post_trim",
        job_id=job.id,
        metadata_json={"samples": to_process},
    )
    enqueue_pipeline_job(job.id)
    return {"job_id": job.id, "status": "PENDING", "message": "Post-trim quality analysis job enqueued"}

@router.post("/quality_analysis_post_trim/update_status")
def update_quality_analysis_post_trim_status(
    sra_code: str = Form(...),
    new_status: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logger.info(f"Recebendo solicitação para atualizar status: sra_code={sra_code}, status={new_status}")

    # Update any matching post-trim sample entries for any user.
    updated = False
    candidates = [f"{sra_code}_post_trim.html", f"{sra_code}_1_post_trim.html", f"{sra_code}_2_post_trim.html"]
    for name in candidates:
        db_sample_stage = db.query(SampleStage).filter(
            SampleStage.name == name,
            SampleStage.stage_id == 4,
            SampleStage.user_id == current_user.id,
        ).first()
        if db_sample_stage:
            db_sample_stage.status = normalize_status(new_status)
            db.commit()
            updated = True

    if not updated:
        logger.error(f"No post-trim sample found for {sra_code}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {sra_code} not found")

    logger.info(f"Status atualizado com sucesso para {new_status} para a amostra {sra_code}")
    return {"message": f"Status atualizado para {new_status} para a amostra {sra_code}"}

@router.delete("/quality_analysis_post_trim/{name}")
def delete_quality_analysis_result(name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Encontrar o registro pelo campo 'name' e 'stage_id=4'
    db_sample_stage = db.query(SampleStage).filter(
        SampleStage.name == name,
        SampleStage.stage_id == 4,  # Corrigido para stage_id=4
        SampleStage.user_id == current_user.id
    ).first()

    if not db_sample_stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {name} not found")

    # Excluir o registro do banco de dados
    db.delete(db_sample_stage)
    db.commit()

    result_base = name
    if result_base.endswith("_post_trim.html"):
        result_base = result_base[:-len("_post_trim.html")]

    sample_base = result_base
    if sample_base.endswith("_1") or sample_base.endswith("_2"):
        sample_base = sample_base[:-2]
    elif sample_base.endswith("_R1") or sample_base.endswith("_R2"):
        sample_base = sample_base[:-3]

    output_dir = safe_resolve_user_path(
        settings.users_root,
        current_user.id,
        "QC_PostTrim",
        sample_base,
    )

    for suffix in ("_fastqc.html", "_fastqc.zip"):
        output_file = output_dir / f"{result_base}_trimmed{suffix}"
        if output_file.exists():
            output_file.unlink()

    try:
        if output_dir.exists() and not any(output_dir.iterdir()):
            output_dir.rmdir()
    except OSError:
        pass

    return {"message": f"Quality analysis result {name} deleted successfully"}
