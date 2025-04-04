from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models import SampleStage, User, Stage  # Remova 'Sample'
from ..utils import get_current_user, manager  # Atualizado
from pydantic import BaseModel
import subprocess
import asyncio
import sys
import threading

router = APIRouter()

class SampleCreateRequest(BaseModel):
    sra_codes: List[str]
    size: str

class SampleStageCreateRequest(BaseModel):
    stage_id: int
    status: str

def get_next_sample_id(db: Session) -> int:
    """Get the next unique sample_id for stage_id 1."""
    max_sample_id = db.query(SampleStage.sample_id).filter(SampleStage.stage_id == 1).order_by(SampleStage.sample_id.desc()).first()
    return (max_sample_id[0] + 1) if max_sample_id and max_sample_id[0] else 1

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
        # Check if the sample already exists
        existing_sample_stage = db.query(SampleStage).filter(
            SampleStage.sra_code == sra_code, SampleStage.stage_id == 1, SampleStage.user_id == current_user.id
        ).first()
        if existing_sample_stage:
            continue  # Skip existing samples

        # Generate a unique sample_id
        new_sample_id = get_next_sample_id(db)

        # Create a new sample stage for stage_id 1
        db_sample_stage = SampleStage(
            sample_id=new_sample_id,
            stage_id=1,
            name=f"{sra_code}.fastq",
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
    db_sample_stage = db.query(SampleStage).filter(SampleStage.sra_code == sra_code, SampleStage.stage_id == 1, SampleStage.user_id == current_user.id).first()
    if db_sample_stage is None:
        raise HTTPException(status_code=404, detail="Sample not found")

    user_id = current_user.id

    # Run the script to delete the file
    command = f"bash /app/backend/scripts/delete_file.sh {sra_code} {user_id}"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    if process.returncode != 0 and "not found" not in stderr:
        raise HTTPException(status_code=500, detail="Error deleting file")

    db.delete(db_sample_stage)
    db.commit()
    return {"message": "Sample and file deleted"}

@router.get("/samples/status/{sra_code}")
def get_sample_status(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample_stage = db.query(SampleStage).filter(SampleStage.sra_code == sra_code, SampleStage.stage_id == 1, SampleStage.user_id == current_user.id).first()
    if db_sample_stage is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {"status": db_sample_stage.status}

@router.post("/samples/download")
def download_pending_samples(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pending_sample = db.query(SampleStage).filter(SampleStage.status == "Pending", SampleStage.stage_id == 1).first()
    if not pending_sample:
        raise HTTPException(status_code=404, detail="No pending samples found")

    sra_code = pending_sample.sra_code
    user_id = current_user.id
    pending_sample.status = "In Progress"
    db.commit()

    command = f"bash /app/backend/scripts/download_script.sh {sra_code} {user_id}"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def update_status():
        try:
            process.wait()
            db_sample = db.query(SampleStage).filter(SampleStage.sra_code == sra_code).first()
            if process.returncode == 0:
                db_sample.status = "Completed"
                db.commit()
                asyncio.run(manager.broadcast(f"Download da amostra {sra_code} concluído."))
                return
        except Exception as e:
            db_sample.status = "Failed"
            db.commit()
        finally:
            process.terminate()

    threading.Thread(target=update_status).start()

    return {"message": f"Download started for sample {sra_code}", "sample_name": sra_code}

@router.post("/samples/update_status")
async def update_sample_status_endpoint(sra_code: str = Form(...), status: str = Form(...), db: Session = Depends(get_db)):
    db_sample_stage = update_sample_status(db, sra_code, status)

    # Update the name if the status is "Completed"
    if status == "Completed":
        db_sample_stage.name = f"{sra_code}.fastq"
        db.commit()

    await manager.broadcast(f"Download da amostra {sra_code} {status.lower()}.")
    return {"message": f"Sample {sra_code} status updated to {status}"}

@router.post("/samples/calculate_size")
async def calculate_size(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample_stage = db.query(SampleStage).filter(
        SampleStage.sra_code == sra_code, SampleStage.stage_id == 1, SampleStage.user_id == current_user.id
    ).first()
    if db_sample_stage is None or db_sample_stage.status != "Completed":
        raise HTTPException(status_code=404, detail="Sample not found or not completed")

    user_id = current_user.id

    command = f"python3 /app/backend/scripts/calculate_size.py {sra_code} {user_id}"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        print(f"Error calculating size: {stderr}", file=sys.stderr)
        raise HTTPException(status_code=500, detail="Error calculating size")

    sizes = stdout.strip().split(',')
    if len(sizes) != 2:
        print(f"Invalid size format returned by script: {stdout}", file=sys.stderr)
        raise HTTPException(status_code=500, detail="Invalid size format returned by script")

    size_1, size_2 = sizes

    # Extrair o basename do sra_code
    sra_code_basename = sra_code.split("_")[0]

    # Atualizar os registros para _1.fastq e _2.fastq com o sra_code correto
    db_sample_stage_1 = SampleStage(
        sample_id=db_sample_stage.sample_id,  # Use the same sample_id
        stage_id=1,
        name=f"{sra_code_basename}_1.fastq",
        sra_code=sra_code_basename,  # Usar apenas o basename
        size=size_1,
        status="Completed",
        user_id=current_user.id,
    )
    db_sample_stage_2 = SampleStage(
        sample_id=db_sample_stage.sample_id,  # Use the same sample_id
        stage_id=1,
        name=f"{sra_code_basename}_2.fastq",
        sra_code=sra_code_basename,  # Usar apenas o basename
        size=size_2,
        status="Completed",
        user_id=current_user.id,
    )
    db.add(db_sample_stage_1)
    db.add(db_sample_stage_2)
    db.delete(db_sample_stage)
    db.commit()

    await manager.broadcast(f"Tamanho das amostras {sra_code_basename} atualizado.")
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
        {"id": 6, "name": "quantificacao"}
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
    db_sample_stage = SampleStage(sample_id=sample_id, stage_id=request.stage_id)
    db.add(db_sample_stage)
    db.commit()
    db.refresh(db_sample_stage)
    return db_sample_stage

@router.get("/samples/{sample_id}/stages/")
def get_sample_stages(sample_id: int, db: Session = Depends(get_db)):
    sample_stages = db.query(SampleStage).filter(SampleStage.sample_id == sample_id).all()
    return sample_stages

@router.put("/samples/{sample_id}/stages/{stage_id}")
def update_sample_stage(sample_id: int, stage_id: int, status: str, db: Session = Depends(get_db)):
    db_sample_stage = db.query(SampleStage).filter(SampleStage.sample_id == sample_id, SampleStage.stage_id == stage_id).first()
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
