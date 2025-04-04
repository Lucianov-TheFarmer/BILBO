from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel  # Import BaseModel
from ..database import get_db
from ..models import SampleStage, User, Stage  # Substitua 'Sample' por 'SampleStage'
from ..utils import get_current_user, manager  # Atualizado
import subprocess
import os
import logging

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
            sample_id=db_sample_stage.sample_id,  # Reutilizar o sample_id da amostra original
            stage_id=2,  # ID do estágio de análise de qualidade
            name=f"{db_sample_stage.sra_code}{suffix}.html",  # Nome do arquivo de saída com sufixo
            sra_code=db_sample_stage.sra_code,  # Usar apenas o basename
            size=None,  # O tamanho permanece como NULL
            status="In Progress",  # Status inicial
            user_id=user_id,  # Associar ao usuário atual
        )
        db.add(new_sample_stage)

        # Executar o script de análise de qualidade
        command = f"bash /app/backend/scripts/quality_analysis.sh {name} {user_id}"
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error starting quality analysis for {name}: {stderr}")

        # Atualizar o status para "Completed" após a execução bem-sucedida
        new_sample_stage.status = "Completed"
        db.commit()

    return {"message": "Quality analysis started successfully"}
        
@router.post("/quality_analysis/update_status")
async def update_quality_analysis_status(sra_code: str = Form(...), status: str = Form(...), db: Session = Depends(get_db)):
    db_sample = db.query(SampleStage).filter(SampleStage.sra_code == sra_code).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample.status = status
    db.commit()

    # Update the sample stage
    db_sample_stage = db.query(SampleStage).filter(SampleStage.sample_id == db_sample.id, SampleStage.stage_id == 2).first()
    if db_sample_stage:
        db_sample_stage.name = f"{sra_code}.html"
        db.commit()

    await manager.broadcast(f"Análise de qualidade da amostra {sra_code} {status.lower()}.")
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
    if os.path.exists(output_dir):
        subprocess.run(["rm", "-rf", output_dir])

    return {"message": f"Quality analysis result {name} deleted successfully"}
