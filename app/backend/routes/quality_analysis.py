from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel  # Import BaseModel
from ..db.database import get_db
from ..db.models import SampleStage, User, Stage  # Substitua 'Sample' por 'SampleStage'
from ..utils import get_current_user, manager  # Atualizado
import subprocess
import os
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class QualityAnalysisRequest(BaseModel):
    samples: list[str]

@router.post("/quality_analysis/")  # Iniciar análise de qualidade
def start_quality_analysis(request: QualityAnalysisRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    for name in request.samples:  # Usar 'name' em vez de 'sra_code'
        # Garantir que o 'name' seja o nome completo da amostra (ex.: SRR31951083_1.fastq ou SRR31951083_2.fastq)
        db_sample_stage = db.query(SampleStage).filter(
            SampleStage.name == name,  # Verificar pelo nome completo da amostra
            SampleStage.stage_id == 1,
            SampleStage.user_id == user_id
        ).first()

        if not db_sample_stage:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {name} not found")

        # Determinar o sufixo (_1 ou _2) com base no nome da amostra
        suffix = "_1" if "_1.fastq" in name else "_2"

        # Criar um novo estágio para análise de qualidade (stage_id=2)
        new_sample_stage = SampleStage(
            stage_id=2,  # ID do estágio de análise de qualidade
            name=f"{db_sample_stage.sra_code}{suffix}.html",  # Nome do arquivo de saída com sufixo
            sra_code=db_sample_stage.sra_code,  # Usar apenas o basename
            size=None,  # O tamanho permanece como NULL
            status="In Progress",  # Status inicial
            user_id=user_id,  # Associar ao usuário atual
        )
        db.add(new_sample_stage)
        db.commit()

        # Executar o script de análise de qualidade em background (não bloquear a rota)
        command = f"bash /app/backend/scripts/quality_analysis.sh {name} {user_id}"
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            logger.info(f"Launched quality analysis (PID={process.pid}) for {name}")
        except Exception as e:
            logger.error(f"Failed to launch quality analysis for {name}: {e}")
            new_sample_stage.status = "Failed"
            db.commit()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error launching quality analysis for {name}: {e}")

        # Optionally notify frontend that analysis started
        try:
            asyncio.run(manager.broadcast(f"Análise de qualidade iniciada para {name}"))
        except Exception as e:
            logger.warning(f"Não foi possível enviar mensagem WebSocket: {e}")

    return {"message": "Quality analysis started successfully"}
        
@router.post("/quality_analysis/update_status")
async def update_quality_analysis_status(
    sra_code: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    # Atualize apenas o registro correto, sem sobrescrever o nome
    updated = False
    for suffix in ["_1", "_2"]:
        name = f"{sra_code}{suffix}.html"
        db_sample_stage = db.query(SampleStage).filter(
            SampleStage.name == name,
            SampleStage.stage_id == 2
        ).first()
        if db_sample_stage:
            db_sample_stage.status = status
            db.commit()
            updated = True
    if not updated:
        raise HTTPException(status_code=404, detail="Sample not found")
    # Notify frontend via WebSocket about the status change
    try:
        await manager.broadcast(f"Quality analysis {sra_code} status: {status}")
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

    # Excluir o diretório de resultados de análise de qualidade
    user_id = current_user.id
    output_dir = f"../users/{user_id}/QC/{name}"
    output_dir = output_dir.replace(".html", ".fastq")
    logger.info(f"Deleting output directory: {output_dir}")
    if os.path.exists(output_dir):
        subprocess.run(["rm", "-rf", output_dir])

    return {"message": f"Quality analysis result {name} deleted successfully"}
