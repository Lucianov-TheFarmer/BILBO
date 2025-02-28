from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models import Sample, SampleStage, User, Stage
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

@router.post("/samples/")
def create_samples(request: SampleCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    created_samples = []
    for sra_code in request.sra_codes:
        # Verifique se a amostra já existe, considerando o código SRA original e os sufixos _1.fastq e _2.fastq
        existing_sample = db.query(Sample).filter(Sample.sra_code == sra_code, Sample.user_id == current_user.id).first()
        existing_sample_1 = db.query(Sample).filter(Sample.sra_code == f"{sra_code}_1.fastq", Sample.user_id == current_user.id).first()
        existing_sample_2 = db.query(Sample).filter(Sample.sra_code == f"{sra_code}_2.fastq", Sample.user_id == current_user.id).first()
        if existing_sample or existing_sample_1 or existing_sample_2:
            continue  # Skip existing samples
        db_sample = Sample(sra_code=sra_code, size=request.size, status="Pending", user_id=current_user.id)
        db.add(db_sample)
        created_samples.append(db_sample)
    db.commit()
    for sample in created_samples:
        db.refresh(sample)
    return created_samples

@router.get("/samples/")
def read_samples(skip: int = 0, limit: int = 10, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    samples = db.query(Sample).filter(Sample.user_id == current_user.id).offset(skip).limit(limit).all()
    return samples

@router.put("/samples/{sample_id}")
def update_sample(sample_id: int, status: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample.status = status
    db.commit()
    db.refresh(db_sample)
    return db_sample

@router.delete("/samples/{sra_code}")
def delete_sample(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample = db.query(Sample).filter(Sample.sra_code == sra_code).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    
    user_id = current_user.id

    # Run the script to delete the file
    command = f"bash /app/backend/scripts/delete_file.sh {sra_code} {user_id}"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    if process.returncode != 0 and "not found" not in stderr:
        raise HTTPException(status_code=500, detail="Error deleting file")

    # Delete corresponding sample stages
    db.query(SampleStage).filter(SampleStage.sample_id == db_sample.id).delete()

    db.delete(db_sample)
    db.commit()
    return {"message": "Sample and file deleted"}

@router.get("/samples/status/{sra_code}")
def get_sample_status(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample = db.query(Sample).filter(Sample.sra_code == sra_code, Sample.user_id == current_user.id).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {"status": db_sample.status}

@router.post("/samples/download")
def download_pending_samples(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pending_sample = db.query(Sample).filter(Sample.status == "Pending").first()
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
            db_sample = db.query(Sample).filter(Sample.sra_code == sra_code).first()
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
async def update_sample_status(sra_code: str = Form(...), status: str = Form(...), db: Session = Depends(get_db)):
    db_sample = db.query(Sample).filter(Sample.sra_code == sra_code).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample.status = status
    db.commit()
    await manager.broadcast(f"Download da amostra {sra_code} {status.lower()}.")
    return {"message": f"Sample {sra_code} status updated to {status}"}

@router.post("/samples/calculate_size")
async def calculate_size(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample = db.query(Sample).filter(Sample.sra_code == sra_code, Sample.user_id == current_user.id).first()
    if db_sample is None or db_sample.status != "Completed":
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

    db_sample_1 = db.query(Sample).filter(Sample.sra_code == f"{sra_code}_1.fastq", Sample.user_id == current_user.id).first()
    db_sample_2 = db.query(Sample).filter(Sample.sra_code == f"{sra_code}_2.fastq", Sample.user_id == current_user.id).first()

    if db_sample_1 is None:
        db_sample_1 = Sample(sra_code=f"{sra_code}_1.fastq", size=size_1, status="Completed", user_id=current_user.id)
        db.add(db_sample_1)
    else:
        db_sample_1.size = size_1
        db_sample_1.status = "Completed"

    if db_sample_2 is None:
        db_sample_2 = Sample(sra_code=f"{sra_code}_2.fastq", size=size_2, status="Completed", user_id=current_user.id)
        db.add(db_sample_2)
    else:
        db_sample_2.size = size_2
        db_sample_2.status = "Completed"

    db.commit()
    db.refresh(db_sample_1)
    db.refresh(db_sample_2)

    db_sample_stage = db.query(SampleStage).filter(SampleStage.sample_id == db_sample.id).first()
    if db_sample_stage:
        db_sample_stage_1 = SampleStage(sample_id=db_sample_1.id, stage_id=db_sample_stage.stage_id)
        db_sample_stage_2 = SampleStage(sample_id=db_sample_2.id, stage_id=db_sample_stage.stage_id)
        db.add(db_sample_stage_1)
        db.add(db_sample_stage_2)
        db.delete(db_sample_stage)

    db.commit()

    db.delete(db_sample)
    db.commit()

    await manager.broadcast(f"Tamanho das amostras {sra_code} atualizado.")
    return {"message": "Sample sizes updated successfully"}

@router.get("/samples/pending_count")
def get_pending_samples_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pending_count = db.query(Sample).filter(Sample.status == "Pending", Sample.user_id == current_user.id).count()
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
    sample_stages = db.query(SampleStage).filter(SampleStage.stage_id == stage_id).all()
    samples = []
    for sample_stage in sample_stages:
        sample = db.query(Sample).filter(Sample.id == sample_stage.sample_id, Sample.user_id == current_user.id).first()
        if sample:
            samples.append({
                "id": sample.id,
                "sra_code": sample.sra_code,
                "size": sample.size,
                "status": sample.status
            })
    return samples
