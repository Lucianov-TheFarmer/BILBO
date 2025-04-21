from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import SampleStage, User
from ..utils import get_current_user
import subprocess
import os
import logging
import time

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter()

# ----------------------------------------
# Helper Functions
# ----------------------------------------

def calculate_directory_size(directory: str) -> str:
    """Calculate the size of a directory in MB."""
    size_in_bytes = sum(
        os.path.getsize(os.path.join(dirpath, filename))
        for dirpath, _, filenames in os.walk(directory)
        for filename in filenames
    )
    return f"{size_in_bytes / (1024 * 1024):.2f} MB"

# ----------------------------------------
# Routes for Alignment
# ----------------------------------------

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

# ----------------------------------------
# Routes for Reference Genomes
# ----------------------------------------

@router.get("/genomes/")
def get_reference_genomes(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Fetch reference genomes for the current user."""
    user_id = current_user.id
    results = db.query(SampleStage).filter(SampleStage.stage_id == 7, SampleStage.user_id == user_id).all()
    return [{"name": result.name, "size": result.size, "status": result.status} for result in results]

@router.get("/genomes/search")
def search_genomes(taxon: str = None, accession: str = None, current_user: User = Depends(get_current_user)):
    """Search for genomes using a Bash script."""
    try:
        if not (taxon or accession):
            raise HTTPException(status_code=400, detail="Either 'taxon' or 'accession' must be provided.")

        search_type = "taxon" if taxon else "accession"
        search_value = taxon or accession
        script_path = "/app/backend/scripts/search_genomes.sh"
        command = ["bash", script_path, search_type, search_value]

        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(f"Erro ao buscar genomas: {stderr.strip()}")
            raise HTTPException(status_code=500, detail=f"Erro ao buscar genomas: {stderr.strip()}")

        lines = stdout.strip().split("\n")
        headers = lines[0].split("\t")
        genomes = [dict(zip(headers, line.split("\t"))) for line in lines[1:]]
        return {"genomes": genomes}
    except Exception as e:
        logger.error(f"Erro ao buscar genomas: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar genomas: {e}")

@router.post("/genomes/download")
def download_genome(
    accession: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a genome and prepare it for indexing."""
    try:
        script_path = "/app/backend/scripts/download_genome.sh"
        download_command = ["bash", script_path, accession]
        download_process = subprocess.Popen(download_command)
        logger.info(f"Iniciando download do genoma {accession}...")

        log_file_path = "/app/backend/logs/download_genome.log"
        success_message = f"Genoma de referência {accession} baixado, descompactado, renomeado e limpo com sucesso."

        while True:
            if os.path.exists(log_file_path):
                with open(log_file_path, "r") as log_file:
                    if success_message in log_file.read():
                        logger.info(f"Download do genoma {accession} concluído com sucesso.")
                        break
            if download_process.poll() is not None and download_process.returncode != 0:
                raise HTTPException(status_code=500, detail="Erro ao baixar o genoma.")
            time.sleep(2)

        return {"message": f"Download do genoma {accession} concluído com sucesso."}
    except Exception as e:
        logger.error(f"Erro ao baixar genoma: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao baixar genoma: {e}")

@router.post("/genomes/index")
def index_genome(
    accession: str,
    organism_name: str,
    sjdb_overhang: int,
    threads: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Index a genome using STAR."""
    try:
        genome_dir = f"../users/ref_genomes/{accession}"
        # if not os.path.exists(genome_dir):
            # raise HTTPException(status_code=404, detail=f"Diretório do genoma {accession} não encontrado.")

        genome_name = f"{organism_name} ({accession})"
        initial_stage = SampleStage(
            name=genome_name,
            size=None,
            status="Indexing",
            stage_id=7,
            user_id=current_user.id,
        )
        db.add(initial_stage)
        db.commit()

        star_script_path = "/app/backend/scripts/index_genome_star.sh"
        star_command = ["bash", star_script_path, genome_dir, str(sjdb_overhang), str(threads)]
        logger.info(f"Iniciando indexação do genoma {genome_name} com STAR...")
        process = subprocess.Popen(star_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(f"Erro ao indexar genoma com STAR: {stderr.strip()}")
            raise HTTPException(status_code=500, detail=f"Erro ao indexar genoma com STAR: {stderr.strip()}")

        genome_size = calculate_directory_size(genome_dir)
        genome_stage = db.query(SampleStage).filter(
            SampleStage.name == genome_name,
            SampleStage.user_id == current_user.id,
            SampleStage.stage_id == 7,
        ).first()
        if genome_stage:
            genome_stage.status = "Completed"
            genome_stage.size = genome_size
            db.commit()

        return {"message": f"Genoma {genome_name} indexado com sucesso!"}
    except Exception as e:
        logger.error(f"Erro ao indexar genoma: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao indexar genoma: {e}")

@router.delete("/genomes/{accession}")
def delete_reference_genome(accession: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete a reference genome and its associated files."""
    try:
        user_id = current_user.id
        genome_dir = f"/users/ref_genomes/{accession}"
        genome_stage = db.query(SampleStage).filter(
            SampleStage.name.like(f"%({accession})%"),
            SampleStage.user_id == user_id,
            SampleStage.stage_id == 7,
        ).first()

        if not genome_stage:
            raise HTTPException(status_code=404, detail=f"Genoma de referência {accession} não encontrado.")

        if os.path.exists(genome_dir):
            subprocess.run(["rm", "-rf", genome_dir], check=True)
            logger.info(f"Arquivos do genoma {accession} excluídos com sucesso.")
        else:
            logger.warning(f"Diretório do genoma {accession} não encontrado.")

        db.delete(genome_stage)
        db.commit()
        logger.info(f"Genoma de referência {accession} excluído do banco de dados.")
        return {"message": f"Genoma de referência {accession} excluído com sucesso."}
    except Exception as e:
        logger.error(f"Erro ao excluir genoma de referência {accession}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao excluir genoma de referência {accession}: {e}")