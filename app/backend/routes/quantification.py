from fastapi import APIRouter, Depends, HTTPException, Form, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from ..db.database import get_db
from ..db.models import SampleStage, User
from ..services.job_service import audit, create_job, normalize_status
from ..tasks.pipeline_tasks import enqueue_pipeline_job
from ..utils import get_current_user
import logging
import os
import re
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


def _normalize_selected_genome(raw_value: Optional[str]) -> Optional[str]:
    if not raw_value:
        return None

    value = raw_value.strip()
    if not value:
        return None

    # Accept formats like "GCF_..." or "Organism Name (GCF_...)".
    candidates: list[str] = [value]
    match = re.search(r"\(([^()]+)\)\s*$", value)
    if match:
        accession = match.group(1).strip()
        if accession:
            candidates.insert(0, accession)

    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate

        ref_dir = os.path.join("/users/ref_genomes", candidate)
        if os.path.isdir(ref_dir):
            return candidate

    return None

class QuantificationRequest(BaseModel):
    samples: list[str]
    feature_type: str
    id_attribute: str
    selected_genome: Optional[str] = None

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

        # Criar ou reutilizar o estágio de quantificação.
        # Evita duplicatas caso a requisição seja repetida.
        txt_name = sample_name.replace(".bam", ".txt")
        quant_stage = db.query(SampleStage).filter(
            SampleStage.name == txt_name,
            SampleStage.stage_id == 6,
            SampleStage.user_id == user_id,
        ).first()

        if quant_stage is None:
            quant_stage = SampleStage(
                stage_id=6,
                name=txt_name,
                sra_code=db_sample_stage.sra_code,
                size=None,
                status="PENDING",
                user_id=user_id,
            )
            db.add(quant_stage)
        elif quant_stage.status != "COMPLETED":
            quant_stage.sra_code = db_sample_stage.sra_code
            quant_stage.size = None
            quant_stage.status = "PENDING"

    db.commit()

    return {"message": "Amostras adicionadas à fila com sucesso"}

@router.post("/quantification/start_processing", status_code=status.HTTP_202_ACCEPTED)
async def start_processing(
    request: QuantificationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enfileira a quantificação em job assíncrono."""
    user_id = current_user.id
    selected_genome = None

    # Prefer explicit genome selected in the quantification modal.
    if request.selected_genome:
        selected_genome = _normalize_selected_genome(request.selected_genome)
        if selected_genome is None:
            raise HTTPException(
                status_code=400,
                detail="Selected reference genome is invalid or not available.",
            )

    # Backward-compatible fallback for legacy clients that do not send selected_genome.
    if selected_genome is None:
        preprocess_dir = os.path.join("/users", str(user_id), "preprocess")
        selected_genome_path = os.path.join(preprocess_dir, "selected_genome.txt")
        try:
            if os.path.exists(selected_genome_path):
                with open(selected_genome_path, "r", encoding="utf-8") as f:
                    line = f.readline().strip()
                    if line:
                        selected_genome = _normalize_selected_genome(line)
                        if selected_genome is None:
                            logger.warning(
                                "Ignoring stale selected_genome '%s' for user %s",
                                line,
                                user_id,
                            )
        except Exception:
            selected_genome = None

    for sample_name in request.samples:
        sample_stage = db.query(SampleStage).filter(
            SampleStage.name == f"{sample_name.replace('.bam', '.txt')}",
            SampleStage.stage_id == 6,
            SampleStage.user_id == user_id,
        ).first()

        if not sample_stage:
            raise HTTPException(status_code=404, detail=f"Sample {sample_name} not found in queue")

        sample_stage.status = "PENDING"
        db.commit()

    job = create_job(
        db,
        stage="quantification",
        user_id=user_id,
        payload={
            "samples": request.samples,
            "feature_type": request.feature_type,
            "id_attribute": request.id_attribute,
            "selected_genome": selected_genome,
        },
    )
    audit(
        db,
        action="quantification_enqueued",
        user_id=user_id,
        stage="quantification",
        job_id=job.id,
        metadata_json={"samples": request.samples},
    )
    enqueue_pipeline_job(job.id)
    return {"job_id": job.id, "status": "PENDING", "message": "Quantification job enqueued"}

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

    sample_stage.status = normalize_status(status)
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
