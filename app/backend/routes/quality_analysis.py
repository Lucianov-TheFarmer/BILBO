from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel  # Import BaseModel
from ..database import get_db
from ..models import Sample, SampleStage, User, Stage
from ..utils import get_current_user, manager  # Atualizado
import subprocess

router = APIRouter()

class QualityAnalysisRequest(BaseModel):
    samples: list[str]

@router.post("/quality_analysis/")
def start_quality_analysis(request: QualityAnalysisRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    for sra_code in request.samples:
        db_sample = db.query(Sample).filter(Sample.sra_code == sra_code, Sample.user_id == user_id).first()
        if not db_sample:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sample {sra_code} not found")
        
        command = f"bash /app/backend/scripts/quality_analysis.sh {sra_code} {user_id}"
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error starting quality analysis for {sra_code}: {stderr}")
    
    return {"message": "Quality analysis started successfully"}

@router.post("/quality_analysis/update_status")
async def update_quality_analysis_status(sra_code: str = Form(...), status: str = Form(...), db: Session = Depends(get_db)):
    db_sample = db.query(Sample).filter(Sample.sra_code == sra_code).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample.status = status
    db.commit()

    # Update the sample stage
    db_sample_stage = db.query(SampleStage).filter(SampleStage.sample_id == db_sample.id, SampleStage.stage_id == 2).first()
    if db_sample_stage:
        db_sample_stage.status = status
        db.commit()

    await manager.broadcast(f"Análise de qualidade da amostra {sra_code} {status.lower()}.")
    return {"message": f"Sample {sra_code} status updated to {status}"}

@router.get("/quality_analysis/completed")
def get_completed_quality_analysis(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    samples = db.query(Sample).filter(Sample.user_id == current_user.id, Sample.status == "Completed").all()
    return samples
