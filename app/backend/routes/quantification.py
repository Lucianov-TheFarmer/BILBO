from fastapi import APIRouter, Depends, HTTPException, Form, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..database import get_db
from ..models import SampleStage, User
from ..utils import get_current_user, manager
import subprocess
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class QuantificationRequest(BaseModel):
    samples: list[str]

@router.post("/quantification/add_to_queue")
def add_to_queue(request: QuantificationRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Adiciona as amostras ao banco de dados com status 'Na fila'."""
    user_id = current_user.id
    for sample_name in request.samples:
        db_sample_stage = db.query(SampleStage).filter(
            SampleStage.name == sample_name,
            SampleStage.stage_id == 5,
            SampleStage.user_id == user_id
        ).first()

        if not db_sample_stage:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {sample_name} not found")

        # Criar um novo estágio para quantificação (stage_id=6) com extensão .txt
        new_sample_stage = SampleStage(
            sample_id=db_sample_stage.sample_id,
            stage_id=6,
            name=f"{sample_name.replace('.bam', '.txt')}",
            sra_code=db_sample_stage.sra_code,
            size=None,
            status="Na fila",  # Status inicial
            user_id=user_id,
        )
        db.add(new_sample_stage)
    db.commit()

    return {"message": "Amostras adicionadas à fila com sucesso"}

@router.post("/quantification/start_processing")
async def start_processing(request: QuantificationRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Processa as amostras de quantificação uma por uma."""
    user_id = current_user.id
    for sample_name in request.samples:
        sample_stage = db.query(SampleStage).filter(
            SampleStage.name == f"{sample_name.replace('.bam', '.txt')}",
            SampleStage.stage_id == 6,
            SampleStage.user_id == user_id
        ).first()

        if not sample_stage:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {sample_name} not found in queue")

        # Atualizar status para "counting" durante o processamento
        sample_stage.status = "counting"
        db.commit()

        # Executar o script de quantificação
        command = f"bash /app/backend/scripts/quantification.sh {sample_name} {user_id}"
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            logger.error(f"Erro ao executar quantificação para {sample_name}: {stderr}")
            sample_stage.status = "Erro"
            db.commit()
            continue

        # Calcular o tamanho do arquivo de quantificação
        quantification_path = f"../users/{user_id}/quantification/{sample_name.replace('.bam', '.txt')}"
        if os.path.exists(quantification_path):
            quantification_size = os.path.getsize(quantification_path)
            quantification_size_kb = f"{quantification_size / 1024:.2f} KB"
            sample_stage.size = quantification_size_kb

        # Atualizar o status para "completed"
        sample_stage.status = "completed"
        db.commit()

        # Emitir mensagem para o frontend
        await manager.broadcast(f"Quantificação concluída para {sample_name}")

    return {"message": "Processamento de quantificação iniciado"}

@router.get("/quantification/")
def get_quantification_samples(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Retorna as amostras disponíveis para quantificação."""
    user_id = current_user.id
    samples = db.query(SampleStage).filter(SampleStage.stage_id == 6, SampleStage.user_id == user_id).all()
    if not samples:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No quantification samples found")
    return [{"name": sample.name, "size": sample.size, "status": sample.status, "stage_id": sample.stage_id} for sample in samples]

@router.post("/quantification/update_status")
async def update_quantification_status(
    sample_name: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atualiza o status da quantificação e calcula o tamanho do arquivo .txt."""
    user_id = current_user.id
    quantification_path = f"../users/{user_id}/quantification/{sample_name}.txt"

    # Verificar se o arquivo de quantificação existe
    if not os.path.exists(quantification_path):
        raise HTTPException(status_code=404, detail=f"Arquivo de quantificação {quantification_path} não encontrado.")

    # Calcular o tamanho do arquivo de quantificação em KB
    quantification_size = os.path.getsize(quantification_path)
    quantification_size_kb = f"{quantification_size / 1024:.2f} KB"

    # Atualizar o status e o tamanho no banco de dados
    sample_stage = db.query(SampleStage).filter(
        SampleStage.name == f"{sample_name}.txt",
        SampleStage.stage_id == 6,
        SampleStage.user_id == user_id,
    ).first()

    if not sample_stage:
        raise HTTPException(status_code=404, detail="Sample not found")

    sample_stage.status = status
    sample_stage.size = quantification_size_kb
    db.commit()

    return {"message": f"Status atualizado para {sample_name}", "size": quantification_size_kb}

@router.post("/quantification/delete")
def delete_quantification_samples(
    samples: list[str],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exclui amostras de quantificação e seus arquivos associados."""
    user_id = current_user.id
    errors = []

    for sample_name in samples:
        # Garantir que o nome do arquivo não tenha duplicação de extensão
        if not sample_name.endswith(".txt"):
            sample_name += ".txt"

        quantification_path = f"../users/{user_id}/quantification/{sample_name}"

        # Remover arquivo de quantificação
        if os.path.exists(quantification_path):
            try:
                os.remove(quantification_path)
                logger.info(f"Arquivo de quantificação {quantification_path} excluído com sucesso.")
            except Exception as e:
                logger.error(f"Erro ao excluir arquivo {quantification_path}: {e}")
                errors.append(sample_name)
        else:
            logger.warning(f"Arquivo de quantificação {quantification_path} não encontrado.")

        # Remover entrada do banco de dados
        sample_stage = db.query(SampleStage).filter(
            SampleStage.name == sample_name,  # Comparar diretamente com o nome completo
            SampleStage.stage_id == 6,
            SampleStage.user_id == user_id,
        ).first()

        if sample_stage:
            try:
                db.delete(sample_stage)
                db.commit()
                logger.info(f"Amostra {sample_name} excluída do banco de dados.")
            except Exception as e:
                logger.error(f"Erro ao excluir amostra {sample_name} do banco de dados: {e}")
                errors.append(sample_name)
        else:
            logger.warning(f"Amostra {sample_name} não encontrada no banco de dados.")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao excluir as seguintes amostras: {', '.join(errors)}",
        )

    return {"message": "Amostras excluídas com sucesso."}
