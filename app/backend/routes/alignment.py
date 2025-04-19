from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import SampleStage, User
from ..utils import get_current_user
import subprocess
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter()

@router.get("/alignment/")
def get_alignment_results(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Fetch alignment results for the current user."""
    user_id = current_user.id
    results = db.query(SampleStage).filter(SampleStage.stage_id == 5, SampleStage.user_id == user_id).all()
    return [{"name": result.name, "size": result.size, "status": result.status, "log": result.log} for result in results]

@router.post("/alignment/start")
def start_alignment(samples: list[str], db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Start the alignment process for selected samples."""
    user_id = current_user.id
    base_path = f"../users/{user_id}/samples"
    alignment_path = f"../users/{user_id}/alignment"
    os.makedirs(alignment_path, exist_ok=True)

    for sample in samples:
        sample_stage = db.query(SampleStage).filter(SampleStage.name == sample, SampleStage.user_id == user_id).first()
        if not sample_stage:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {sample} not found")

        command = [
            "bash",
            "/app/backend/scripts/alignment.sh",
            sample,
            alignment_path,
        ]
        logger.info(f"Executing alignment command: {' '.join(command)}")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(f"Erro no alinhamento para {sample}: {stderr.strip()}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro no alinhamento para {sample}: {stderr.strip()}")

        # Update database
        new_stage = SampleStage(
            sample_id=sample_stage.sample_id,
            stage_id=5,
            name=sample,
            size=None,
            status="Completed",
            log=stdout,
            user_id=user_id,
        )
        db.add(new_stage)
    db.commit()
    return {"message": "Alinhamento iniciado com sucesso"}

@router.delete("/alignment/{sample_name}")
def delete_alignment_result(sample_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete alignment results for a specific sample."""
    user_id = current_user.id
    alignment_path = f"../users/{user_id}/alignment/{sample_name}"
    if os.path.exists(alignment_path):
        os.remove(alignment_path)
        logger.info(f"Arquivo de alinhamento {alignment_path} excluído com sucesso.")
    else:
        logger.warning(f"Arquivo de alinhamento {alignment_path} não encontrado.")

    sample_stage = db.query(SampleStage).filter(SampleStage.name == sample_name, SampleStage.stage_id == 5, SampleStage.user_id == user_id).first()
    if sample_stage:
        db.delete(sample_stage)
        db.commit()
        logger.info(f"Resultado de alinhamento {sample_name} excluído do banco de dados.")
    else:
        logger.warning(f"Resultado de alinhamento {sample_name} não encontrado no banco de dados.")
    return {"message": f"Resultado de alinhamento {sample_name} excluído com sucesso"}


@router.get("/genomes/search")
def search_genomes(taxon: str = None, accession: str = None, current_user: User = Depends(get_current_user)):
    """Search for genomes using a Bash script."""
    try:
        if taxon:
            search_type = "taxon"
            search_value = taxon
        elif accession:
            search_type = "accession"
            search_value = accession
        else:
            raise HTTPException(status_code=400, detail="Either 'taxon' or 'accession' must be provided.")

        script_path = "/app/backend/scripts/search_genomes.sh"
        command = ["bash", script_path, search_type, search_value]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(f"Erro ao buscar genomas: {stderr.strip()}")
            raise HTTPException(status_code=500, detail=f"Erro ao buscar genomas: {stderr.strip()}")

        # Parse the output into a list of dictionaries
        lines = stdout.strip().split("\n")
        headers = lines[0].split("\t")
        genomes = [dict(zip(headers, line.split("\t"))) for line in lines[1:]]

        return {"genomes": genomes}
    except Exception as e:
        logger.error(f"Erro ao buscar genomas: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar genomas: {e}")