from fastapi import APIRouter, Depends, HTTPException, status, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from ..db.database import get_db
from ..db.models import SampleStage, User, Stage
from ..utils import get_current_user, manager
from pydantic import BaseModel
import subprocess
import asyncio
import sys
import threading
import os
import logging
from jose import jwt, JWTError
from ..utils import SECRET_KEY, ALGORITHM

router = APIRouter()
logger = logging.getLogger(__name__)

class SampleCreateRequest(BaseModel):
    sra_codes: List[str]
    size: str

class SampleStageCreateRequest(BaseModel):
    stage_id: int
    status: str

def update_sample_status(db: Session, sra_code: str, status: str):
    """Update the status of a sample."""
    db_sample_stage = db.query(SampleStage).filter(SampleStage.sra_code == sra_code, SampleStage.stage_id == 1).first()
    if not db_sample_stage:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample_stage.status = status
    db.commit()
    return db_sample_stage

@router.post("/samples/")
def create_samples(request: SampleCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    created_samples = []
    for sra_code in request.sra_codes:
        if not isinstance(sra_code, str) or not sra_code or not sra_code.upper().startswith(("SRR", "ERR", "DRR")) or not sra_code[3:].isdigit():
            raise HTTPException(status_code=400, detail=f"Código SRA inválido: {sra_code}")

        existing_sample_stage = db.query(SampleStage).filter(
            SampleStage.sra_code == sra_code, SampleStage.stage_id == 1, SampleStage.user_id == current_user.id
        ).first()
        if existing_sample_stage:
            continue

        db_sample_stage = SampleStage(
            stage_id=1,
            name=f"{sra_code}",
            sra_code=sra_code,
            size=request.size,
            status="Pending",
            user_id=current_user.id,
        )
        db.add(db_sample_stage)
        created_samples.append(db_sample_stage)
    db.commit()
    for sample_stage in created_samples:
        db.refresh(sample_stage)
    return created_samples

@router.get("/samples/")
def read_samples(skip: int = 0, limit: int = 10, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    samples = db.query(SampleStage).filter(SampleStage.user_id == current_user.id, SampleStage.stage_id == 1).offset(skip).limit(limit).all()
    return samples

@router.put("/samples/{sample_id}")
def update_sample(sample_id: int, status: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample = db.query(SampleStage).filter(SampleStage.id == sample_id).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample.status = status
    db.commit()
    db.refresh(db_sample)
    return db_sample

@router.delete("/samples/{sra_code}")
def delete_sample(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sra_code_basename = sra_code.replace("_1.fastq", "").replace("_2.fastq", "").replace(".fastq", "")

    all_samples = db.query(SampleStage).filter(
        SampleStage.sra_code == sra_code_basename,
        SampleStage.stage_id == 1,
        SampleStage.user_id == current_user.id
    ).all()

    if not all_samples:
        raise HTTPException(status_code=404, detail="Sample not found")

    user_id = current_user.id

    sample_names = [sample.name for sample in all_samples]
    is_paired_end = any("_1.fastq" in name or "_2.fastq" in name for name in sample_names)

    for sample in all_samples:
        db.delete(sample)
    db.commit()

    if is_paired_end:
        for suffix in ["_1.fastq", "_2.fastq"]:
            file_path = f"../users/{user_id}/samples/{sra_code_basename}/{sra_code_basename}{suffix}"
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Arquivo {file_path} excluído com sucesso do sistema de arquivos.")
                except Exception as e:
                    logger.error(f"Erro ao excluir arquivo {file_path} do sistema de arquivos: {e}")
            else:
                logger.warning(f"Arquivo {file_path} não encontrado para exclusão.")
    else:
        file_path = f"../users/{user_id}/samples/{sra_code_basename}/{sra_code_basename}.fastq"
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Arquivo {file_path} excluído com sucesso do sistema de arquivos.")
            except Exception as e:
                logger.error(f"Erro ao excluir arquivo {file_path} do sistema de arquivos: {e}")
        else:
            logger.warning(f"Arquivo {file_path} não encontrado para exclusão.")

    sample_dir = f"../users/{user_id}/samples/{sra_code_basename}"
    try:
        if os.path.exists(sample_dir) and not os.listdir(sample_dir):
            os.rmdir(sample_dir)
            logger.info(f"Diretório {sample_dir} removido com sucesso.")
    except Exception as e:
        logger.warning(f"Não foi possível remover diretório {sample_dir}: {e}")

    return {"message": "Sample and associated files deleted successfully"}

@router.get("/samples/status/{sra_code}")
def get_sample_status(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample_stage = db.query(SampleStage).filter(SampleStage.sra_code == sra_code, SampleStage.stage_id == 1, SampleStage.user_id == current_user.id).first()
    if db_sample_stage is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {"status": db_sample_stage.status}

@router.post("/samples/download")
def download_pending_samples(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    logger.info("Iniciando download_pending_samples endpoint")
    pending_sample = db.query(SampleStage).filter(SampleStage.status == "Pending", SampleStage.stage_id == 1).first()
    if not pending_sample:
        logger.warning("Nenhuma amostra pendente encontrada para download")
        raise HTTPException(status_code=404, detail="No pending samples found")

    sra_code = pending_sample.sra_code
    user_id = current_user.id
    logger.info(f"Marcando amostra {sra_code} como 'In Progress' para o usuário {user_id}")
    pending_sample.status = "In Progress"
    db.commit()

    command = f"bash /app/backend/scripts/download_script.sh {sra_code} {user_id}"
    logger.info(f"Executando comando: {command}")
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def update_status():
        try:
            logger.info(f"Aguardando término do processo de download para {sra_code}")
            stdout, _ = process.communicate()
            logger.info(f"Saída do script de download para {sra_code}:\n{stdout}")
            db_sample = db.query(SampleStage).filter(SampleStage.sra_code == sra_code).first()
            if process.returncode == 0:
                logger.info(f"Download da amostra {sra_code} concluído com sucesso. Atualizando status para 'Completed'.")
                db_sample.status = "Completed"
                db.commit()
                asyncio.run(manager.broadcast(f"Download da amostra {sra_code} concluído."))
                return
            else:
                logger.error(f"Download da amostra {sra_code} falhou com código {process.returncode}")
        except Exception as e:
            logger.error(f"Erro ao atualizar status da amostra {sra_code}: {e}")
            db_sample.status = "Failed"
            db.commit()
        finally:
            process.terminate()

    threading.Thread(target=update_status).start()

    return {"message": f"Download started for sample {sra_code}", "sample_name": sra_code}

@router.post("/samples/update_status")
async def update_sample_status_endpoint(sra_code: str = Form(...), status: str = Form(...), db: Session = Depends(get_db)):
    db_sample_stage = update_sample_status(db, sra_code, status)

    if status == "Completed":
        db_sample_stage.name = f"{sra_code}.fastq"
        db.commit()

    return {"message": f"Sample {sra_code} status updated to {status}"}

@router.post("/samples/calculate_size")
async def calculate_size(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    logger.info(f"Iniciando cálculo de tamanho para {sra_code}")
    db_sample_stage = db.query(SampleStage).filter(
        SampleStage.sra_code == sra_code, SampleStage.stage_id == 1, SampleStage.user_id == current_user.id
    ).first()
    if db_sample_stage is None or db_sample_stage.status != "Completed":
        logger.warning(f"Amostra {sra_code} não encontrada ou não está 'Completed'")
        raise HTTPException(status_code=404, detail="Sample not found or not completed")

    user_id = current_user.id

    command = f"python3 /app/backend/scripts/calculate_size.py {sra_code} {user_id}"
    logger.info(f"Executando comando para calcular tamanho: {command}")
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    logger.info(f"Saída do cálculo de tamanho para {sra_code}: {stdout}")
    if stderr:
        logger.error(f"Erro do cálculo de tamanho para {sra_code}: {stderr}")

    if process.returncode != 0:
        logger.error(f"Erro ao calcular tamanho: {stderr}")
        raise HTTPException(status_code=500, detail="Error calculating size")

    sizes = stdout.strip().split(',')
    if len(sizes) != 2:
        logger.error(f"Formato de tamanho inválido retornado pelo script: {stdout}")
        raise HTTPException(status_code=500, detail="Invalid size format returned by script")

    size_1, size_2 = sizes

    sra_code_basename = sra_code.split("_")[0]
    logger.info(f"Atualizando registros para {sra_code_basename}_1.fastq e {sra_code_basename}_2.fastq")

    db_sample_stage_1 = SampleStage(
        stage_id=1,
        name=f"{sra_code_basename}_1.fastq",
        sra_code=sra_code_basename,
        size=size_1,
        status="Completed",
        user_id=current_user.id,
    )
    db_sample_stage_2 = SampleStage(
        stage_id=1,
        name=f"{sra_code_basename}_2.fastq",
        sra_code=sra_code_basename,
        size=size_2,
        status="Completed",
        user_id=current_user.id,
    )
    db.add(db_sample_stage_1)
    db.add(db_sample_stage_2)
    db.delete(db_sample_stage)
    db.commit()

    logger.info(f"Tamanhos das amostras {sra_code_basename} atualizados com sucesso.")
    return {"message": "Sample sizes updated successfully"}

@router.get("/samples/pending_count")
def get_pending_samples_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pending_count = db.query(SampleStage).filter(SampleStage.status == "Pending", SampleStage.stage_id == 1, SampleStage.user_id == current_user.id).count()
    return {"pending_count": pending_count}

@router.post("/stages/")
def create_stages(db: Session = Depends(get_db)):
    stages = [
        {"id": 1, "name": "obtencao"},
        {"id": 2, "name": "qualidade1"},
        {"id": 3, "name": "trimagem"},
        {"id": 4, "name": "qualidade2"},
        {"id": 5, "name": "alinhamento"},
        {"id": 6, "name": "quantificacao"},
        {"id": 7, "name": "referencia"},
        {"id": 8, "name": "contraste"},
        {"id": 9, "name": "clustering_semantico"},
        {"id": 10, "name": "interpretacao_llm"}

    ]
    for stage in stages:
        db_stage = db.query(Stage).filter(Stage.id == stage["id"]).first()
        if not db_stage:
            db_stage = Stage(id=stage["id"], name=stage["name"])
            db.add(db_stage)
    db.commit()
    return {"message": "Stages created successfully"}

@router.post("/samples/{sample_id}/stages/")
def create_sample_stage(sample_id: int, request: SampleStageCreateRequest, db: Session = Depends(get_db)):
    db_sample_stage = SampleStage(stage_id=request.stage_id)
    db.add(db_sample_stage)
    db.commit()
    db.refresh(db_sample_stage)
    return db_sample_stage

@router.get("/samples/{sample_id}/stages/")
def get_sample_stages(sample_id: int, db: Session = Depends(get_db)):
    sample_stages = db.query(SampleStage).all()
    return sample_stages

@router.put("/samples/{sample_id}/stages/{stage_id}")
def update_sample_stage(sample_id: int, stage_id: int, status: str, db: Session = Depends(get_db)):
    db_sample_stage = db.query(SampleStage).filter(SampleStage.stage_id == stage_id).first()
    if not db_sample_stage:
        raise HTTPException(status_code=404, detail="Sample stage not found")
    db_sample_stage.status = status
    db.commit()
    db.refresh(db_sample_stage)
    return db_sample_stage

@router.get("/samples/stages/{stage_id}")
def get_samples_by_stage(stage_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sample_stages = db.query(SampleStage).filter(SampleStage.stage_id == stage_id, SampleStage.user_id == current_user.id).all()
    samples = []
    for sample_stage in sample_stages:
        samples.append({
            "id": sample_stage.id,
            "sra_code": sample_stage.sra_code,
            "size": sample_stage.size,
            "status": sample_stage.status,
            "name": sample_stage.name,
        })
    return samples

@router.get("/download/{stage_name}/{file_name}")
def download_file(stage_name: str, file_name: str, token: str = Query(...), db: Session = Depends(get_db)):
    """Download a file from any stage with token authentication."""
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    user_id = user.id

    # Get sra_code from the database
    sample_stage = db.query(SampleStage).filter(SampleStage.name == file_name, SampleStage.user_id == user_id).first()
    if not sample_stage:
        raise HTTPException(status_code=404, detail="Sample not found in database")
    
    sra_code = sample_stage.sra_code

    path_map = {
        "obtencao": f"../users/{user_id}/samples/{sra_code}/{file_name}",
        "qualidade1": f"../users/{user_id}/QC/{file_name.replace('.html', '.fastq')}/{file_name.replace('.html', '_fastqc.zip')}",
        "trimagem": f"../users/{user_id}/trimmed/{file_name}",
        "qualidade2": f"../users/{user_id}/QC_PostTrim/{file_name.replace('_post_trim.html', '_trimmed.fastq')}/{file_name.replace('_post_trim.html', '_trimmed_fastqc.zip')}",
        "alinhamento": f"../users/{user_id}/alignment/{sra_code}/{file_name}",
        "quantificacao": f"../users/{user_id}/quantification/{file_name}",
    }

    file_path = path_map.get(stage_name)

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path,
        filename=os.path.basename(file_path),
        media_type="application/octet-stream"
    )