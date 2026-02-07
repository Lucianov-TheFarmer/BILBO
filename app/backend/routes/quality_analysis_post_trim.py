from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..db.database import get_db
from ..db.models import SampleStage, User
from ..utils import get_current_user, manager
import subprocess
import os
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class QualityAnalysisPostTrimRequest(BaseModel):
    samples: list[str]

@router.post("/quality_analysis_post_trim/start")
def start_quality_analysis_post_trim(request: QualityAnalysisPostTrimRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    for name in request.samples:
        db_sample_stage = db.query(SampleStage).filter(
            SampleStage.name == name,
            SampleStage.stage_id == 3,
            SampleStage.user_id == user_id
        ).first()

        if not db_sample_stage:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {name} not found")

        basename = db_sample_stage.name.replace("_trimmed.fastq", "")

        # Verificar se já existe uma entrada para evitar duplicação
        existing_entry = db.query(SampleStage).filter(
            SampleStage.name == f"{basename}_post_trim.html",
            SampleStage.stage_id == 4,
            SampleStage.user_id == user_id
        ).first()

        if existing_entry:
            logger.warning(f"Entrada já existente para {basename}_post_trim.html. Ignorando duplicação.")
            continue

        new_sample_stage = SampleStage(
            stage_id=4,
            name=f"{basename}_post_trim.html",
            sra_code=db_sample_stage.sra_code,
            size=None,
            status="In Progress",
            user_id=user_id,
        )
        db.add(new_sample_stage)
        db.commit()

        # Launch the quality analysis post-trim script in background to avoid blocking the API
        # Pass token optionally if available in env (not required)
        command = f"bash /app/backend/scripts/quality_analysis_post_trim.sh {name} {user_id}"
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            logger.info(f"Launched quality_analysis_post_trim (PID={process.pid}) for {name}")
        except Exception as e:
            logger.error(f"Failed to launch quality analysis post-trim for {name}: {e}")
            new_sample_stage.status = "Failed"
            db.commit()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error launching quality analysis post-trim for {name}: {e}")

        # Broadcast that post-trim analysis started
        try:
            asyncio.run(manager.broadcast(f"Análise de qualidade pós-trimmagem iniciada para {name}"))
        except Exception as e:
            logger.warning(f"Não foi possível enviar mensagem WebSocket de início: {e}")

    return {"message": "Quality analysis post-trimmagem started successfully"}

@router.post("/quality_analysis_post_trim/update_status")
def update_quality_analysis_post_trim_status(sra_code: str = Form(...), new_status: str = Form(...), db: Session = Depends(get_db)):
    logger.info(f"Recebendo solicitação para atualizar status: sra_code={sra_code}, status={new_status}")

    # Update any matching post-trim sample entries for any user.
    updated = False
    candidates = [f"{sra_code}_post_trim.html", f"{sra_code}_1_post_trim.html", f"{sra_code}_2_post_trim.html"]
    for name in candidates:
        db_sample_stage = db.query(SampleStage).filter(
            SampleStage.name == name,
            SampleStage.stage_id == 4
        ).first()
        if db_sample_stage:
            db_sample_stage.status = new_status
            db.commit()
            updated = True

    if not updated:
        logger.error(f"No post-trim sample found for {sra_code}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {sra_code} not found")

    # Broadcast update to frontend
    try:
        asyncio.run(manager.broadcast(f"Quality analysis post-trim {sra_code} status: {new_status}"))
    except Exception as e:
        logger.warning(f"Failed to broadcast post-trim status: {e}")

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

    # Excluir o diretório de resultados de análise de qualidade pós-trimmagem
    user_id = current_user.id
    basename = name.replace("_post_trim.html", "_trimmed.fastq")
    output_dir = f"../users/{user_id}/QC_PostTrim/{basename}"
    output_dir = output_dir.replace(".html", ".fastq")
    logger.info(f"Deleting output directory: {output_dir}")
    if os.path.exists(output_dir):
        subprocess.run(["rm", "-rf", output_dir])

    return {"message": f"Quality analysis result {name} deleted successfully"}
