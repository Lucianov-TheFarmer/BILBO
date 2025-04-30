from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import SampleStage, User
from ..utils import get_current_user, manager  # Atualizado para incluir manager
import subprocess
import os
import logging
import time
import json
import shutil
from pydantic import BaseModel, Field
from typing import Optional
import asyncio

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
# Pydantic Models
# ----------------------------------------

class AdditionalParams(BaseModel):
    threads: int = Field(..., description="Número de threads para o STAR")
    outFilterType: Optional[str] = Field(None, description="Reduz junções espúrias (Opcional)")
    outFilterMultimapNmax: Optional[str] = Field(None, description="Máximo de alinhamentos múltiplos permitidos (Opcional)")
    alignSJoverhangMin: Optional[str] = Field(None, description="Sobreposição mínima para junções não anotadas (Opcional)")
    alignSJDBoverhangMin: Optional[str] = Field(None, description="Sobreposição mínima para junções anotadas (Opcional)")
    outFilterMismatchNmax: Optional[str] = Field(None, description="Máximo de mismatches por par (Opcional)")
    outFilterMismatchNoverReadLmax: Optional[str] = Field(None, description="Máximo de mismatches relativo ao comprimento da leitura (Opcional)")
    alignIntronMin: Optional[str] = Field(None, description="Comprimento mínimo do intron (Opcional)")
    alignIntronMax: Optional[str] = Field(None, description="Comprimento máximo do intron (Opcional)")
    alignMatesGapMax: Optional[str] = Field(None, description="Distância máxima entre mates (Opcional)")

# ----------------------------------------
# Routes for Alignment
# ----------------------------------------

@router.get("/alignment/")
def get_alignment_results(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Fetch alignment results for the current user."""
    user_id = current_user.id
    results = db.query(SampleStage).filter(SampleStage.stage_id == 5, SampleStage.user_id == user_id).all()
    return [{"name": result.name, "size": result.size, "status": result.status} for result in results]

@router.post("/alignment/add_samples")
def add_samples(
    samples: str = Form(...),  # Receber como string JSON
    genome: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add all samples to the database with status 'Pending'."""
    user_id = current_user.id
    base_path = f"../users/{user_id}/trimmed"

    # Decodificar JSON de samples
    try:
        samples_list = json.loads(samples)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON format for samples.")

    # Validate genome format
    if "(" in genome and ")" in genome:
        accession = genome.split("(")[-1].strip(")")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid genome format. Accession not found.")

    # Extrair basenames únicos das amostras
    basenames = list({sample.split('_')[0] for sample in samples_list})
    logger.info(f"Basenames identificados: {basenames}")

    # Adicionar basenames ao banco de dados
    for basename in basenames:
        sample_path_1 = os.path.join(base_path, f"{basename}_1_trimmed.fastq")
        sample_path_2 = os.path.join(base_path, f"{basename}_2_trimmed.fastq")

        if not os.path.exists(sample_path_1) or not os.path.exists(sample_path_2):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sample files not found: [{sample_path_1}, {sample_path_2}]",
            )

        # Adicionar basename ao banco de dados com status 'Pending'
        new_stage = SampleStage(
            stage_id=5,
            name=f"{basename}.bam",
            sra_code=basename,
            status="Pending",
            user_id=user_id,
        )
        db.add(new_stage)

    db.commit()
    return {"message": "Samples added successfully."}

@router.post("/alignment/start")
async def start_alignment(
    sample: str = Form(...),
    genome: str = Form(...),
    threads: int = Query(..., description="Número de threads para o STAR"),
    additional_params: AdditionalParams = Depends(),
    token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start the alignment process for a single sample."""
    user_id = current_user.id
    base_path = f"../users/{user_id}/trimmed"
    alignment_path = f"../users/{user_id}/alignment"
    os.makedirs(alignment_path, exist_ok=True)

    # Validate genome format
    if "(" in genome and ")" in genome:
        accession = genome.split("(")[-1].strip(")")
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid genome format. Accession not found.")

    genome_dir = f"../users/ref_genomes/{accession}/STAR_index"
    if not os.path.exists(genome_dir):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Genome index not found at {genome_dir}. Ensure the genome is indexed correctly.",
        )

    basename = sample.split('_')[0]
    sample_path_1 = os.path.join(base_path, f"{basename}_1_trimmed.fastq")
    sample_path_2 = os.path.join(base_path, f"{basename}_2_trimmed.fastq")

    if not os.path.exists(sample_path_1) or not os.path.exists(sample_path_2):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sample files not found: [{sample_path_1}, {sample_path_2}]",
        )

    # Update sample status to 'Aligning'
    sample_stage = db.query(SampleStage).filter(
        SampleStage.sra_code == basename,
        SampleStage.stage_id == 5,
        SampleStage.user_id == user_id,
    ).first()

    if not sample_stage:
        raise HTTPException(status_code=404, detail="Sample not found")

    if sample_stage.status != "Pending":
        raise HTTPException(status_code=400, detail="Sample is already being processed or completed")

    sample_stage.status = "Aligning"
    db.commit()

    # Prepare command for alignment
    command = [
        "bash",
        "/app/backend/scripts/alignment.sh",
        basename,
        str(user_id),
        alignment_path,
        genome_dir,
        str(threads),
        token,
    ]

    if additional_params:
        for key, value in additional_params.dict().items():
            if value is not None and key != "threads":
                command.append(f"--{key}={value}")

    # Execute alignment
    logger.info(f"Executing alignment command: {' '.join(command)}")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    return {"message": f"Alignment started for {basename}"}

@router.post("/alignment/update_status")
async def update_alignment_status(
    sra_code: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atualiza o status e o tamanho do arquivo BAM no banco de dados."""
    user_id = current_user.id
    alignment_path = f"../users/{user_id}/alignment/{sra_code}/{sra_code}.bam"

    # Verificar se o arquivo BAM existe
    if not os.path.exists(alignment_path):
        raise HTTPException(status_code=404, detail=f"Arquivo BAM {alignment_path} não encontrado.")

    # Calcular o tamanho do arquivo BAM
    bam_size = os.path.getsize(alignment_path)
    bam_size_mb = f"{bam_size / (1024 * 1024):.2f} MB"

    # Atualizar o status e o tamanho no banco de dados
    sample_stage = db.query(SampleStage).filter(
        SampleStage.sra_code == sra_code,
        SampleStage.stage_id == 5,
        SampleStage.user_id == user_id,
    ).first()

    if not sample_stage:
        raise HTTPException(status_code=404, detail="Sample not found")

    sample_stage.status = status
    sample_stage.size = bam_size_mb
    db.commit()

    # Emitir mensagem para o frontend
    await manager.broadcast(f"Alinhamento concluído para {sra_code}")

    return {"message": f"Status atualizado para {sra_code}", "size": bam_size_mb}

@router.delete("/alignment/{sample_name}")
def delete_alignment_result(sample_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete alignment results for a specific sample."""
    user_id = current_user.id
    alignment_dir = f"../users/{user_id}/alignment/{sample_name}".replace(".bam", "")

    # Excluir o diretório de alinhamento associado
    if os.path.exists(alignment_dir):
        try:
            shutil.rmtree(alignment_dir)
            logger.info(f"Diretório de alinhamento {alignment_dir} excluído com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao excluir o diretório {alignment_dir}: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao excluir o diretório {alignment_dir}.")
    else:
        logger.warning(f"Diretório de alinhamento {alignment_dir} não encontrado.")

    # Remover a entrada correspondente no banco de dados
    sample_stage = db.query(SampleStage).filter(
        SampleStage.name == sample_name,
        SampleStage.stage_id == 5,
        SampleStage.user_id == user_id,
    ).first()

    if not sample_stage:
        logger.warning(f"Alinhamento {sample_name} não encontrado no banco de dados.")
        return {"message": f"Alinhamento {sample_name} já foi excluído ou não existe."}

    try:
        db.delete(sample_stage)
        db.commit()
        logger.info(f"Alinhamento {sample_name} excluído com sucesso do banco de dados.")
        return {"message": f"Alinhamento {sample_name} excluído com sucesso."}
    except Exception as e:
        logger.error(f"Erro ao excluir alinhamento {sample_name} do banco de dados: {e}")
        raise HTTPException(status_code=500, detail="Erro ao excluir alinhamento do banco de dados.")

@router.post("/ws/")
async def broadcast_message(message: str = Form(...)):
    """Broadcast a message to all WebSocket clients."""
    try:
        await manager.broadcast(message)
        return {"message": "Broadcast sent successfully"}
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem de broadcast: {e}")
        raise HTTPException(status_code=500, detail="Erro ao enviar mensagem de broadcast")

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
        genome_dir = f"/users/ref_genomes/{accession}"

        # Verificar se o diretório do genoma existe
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