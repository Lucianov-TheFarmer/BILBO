from typing import List  # Add this import
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Query, status, Form, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import flet_fastapi
import requests
import sys
import os
import subprocess
from fastapi.responses import StreamingResponse
import re
import time
from fastapi.middleware.cors import CORSMiddleware
import threading
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession  # Add this import
from sqlalchemy.future import select  # Add this import
import subprocess  # Add this import
from pydantic import BaseModel  # Add this import

# Adicionar o diretório raiz ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .database import engine, get_db
from .models import Base, User, Sample, Stage, SampleStage, File

SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Configure logging
logging.basicConfig(level=logging.INFO)  # Set to INFO level
logger = logging.getLogger(__name__)

print("Creating FastAPI app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Flet app manager")
    await flet_fastapi.app_manager.start()
    yield
    print("Shutting down Flet app manager")
    await flet_fastapi.app_manager.shutdown()

app = FastAPI(lifespan=lifespan)

# Add CORS middleware to allow WebSocket connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@app.post("/register/")
def register(username: str, password: str, db: Session = Depends(get_db)):
    print("Register endpoint called")
    try:
        # Check if the username already exists
        db_user = db.query(User).filter(User.username == username).first()
        if db_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
        
        hashed_password = get_password_hash(password)
        db_user = User(username=username, hashed_password=hashed_password)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return {"message": "User registered successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error during registration: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    print("Login endpoint called")
    db_user = db.query(User).filter(User.username == form_data.username).first()
    if db_user is None or not verify_password(form_data.password, db_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": db_user.username}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    return user

class SampleCreateRequest(BaseModel):
    sra_codes: List[str]
    size: str

@app.post("/samples/")
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

@app.get("/samples/")
def read_samples(skip: int = 0, limit: int = 10, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    samples = db.query(Sample).filter(Sample.user_id == current_user.id).offset(skip).limit(limit).all()
    return samples

@app.put("/samples/{sample_id}")
def update_sample(sample_id: int, status: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample = db.query(Sample).filter(Sample.id == sample_id).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample.status = status
    db.commit()
    db.refresh(db_sample)
    return db_sample

@app.delete("/samples/{sra_code}")
def delete_sample(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample = db.query(Sample).filter(Sample.sra_code == sra_code).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    
    # Run the script to delete the file
    command = f"bash /app/backend/scripts/delete_file.sh {sra_code}"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    if process.returncode != 0 and "not found" not in stderr:
        logger.error(f"Error deleting file: {stderr}")
        raise HTTPException(status_code=500, detail="Error deleting file")

    # Delete corresponding sample stages
    db.query(SampleStage).filter(SampleStage.sample_id == db_sample.id).delete()

    db.delete(db_sample)
    db.commit()
    return {"message": "Sample and file deleted"}

@app.get("/samples/status/{sra_code}")
def get_sample_status(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_sample = db.query(Sample).filter(Sample.sra_code == sra_code, Sample.user_id == current_user.id).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    return {"status": db_sample.status}

@app.post("/samples/download")
def download_pending_samples(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pending_sample = db.query(Sample).filter(Sample.status == "Pending").first()
    if not pending_sample:
        logger.error("No pending samples found")
        raise HTTPException(status_code=404, detail="No pending samples found")

    sra_code = pending_sample.sra_code
    pending_sample.status = "In Progress"
    db.commit()
    logger.info(f"Sample {sra_code} status updated to In Progress")

    command = f"bash /app/backend/scripts/download_script.sh {sra_code} /samples"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def update_status():
        try:
            process.wait()
            db_sample = db.query(Sample).filter(Sample.sra_code == sra_code).first()
            if process.returncode == 0:
                db_sample.status = "Completed"
                db.commit()
                logger.info(f"Sample {sra_code} status updated to Completed")
                asyncio.run(manager.broadcast(f"Download da amostra {sra_code} concluído."))
                return
        except Exception as e:
            db_sample.status = "Failed"
            db.commit()
            logger.error(f"Download failed for sample {sra_code}: {e}")
        finally:
            process.terminate()

    threading.Thread(target=update_status).start()

    return {"message": f"Download started for sample {sra_code}", "sample_name": sra_code}

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.last_message: str = ""  # Track the last message sent

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        if message != self.last_message:
            self.last_message = message
            for connection in self.active_connections:
                await connection.send_text(message)

manager = ConnectionManager()

@app.post("/samples/update_status")
async def update_sample_status(sra_code: str = Form(...), status: str = Form(...), db: Session = Depends(get_db)):
    db_sample = db.query(Sample).filter(Sample.sra_code == sra_code).first()
    if db_sample is None:
        raise HTTPException(status_code=404, detail="Sample not found")
    db_sample.status = status
    db.commit()
    logger.info(f"Sample {sra_code} status updated to {status}")
    # Notify the frontend via WebSocket
    await manager.broadcast(f"Download da amostra {sra_code} {status.lower()}.")
    return {"message": f"Sample {sra_code} status updated to {status}"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.send_personal_message(f"Message received: {data}", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/samples/calculate_size")
async def calculate_size(sra_code: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check if the sample exists and has status "Completed"
    db_sample = db.query(Sample).filter(Sample.sra_code == sra_code, Sample.user_id == current_user.id).first()
    if db_sample is None or db_sample.status != "Completed":
        raise HTTPException(status_code=404, detail="Sample not found or not completed")

    # Run the script to calculate the size
    command = f"python3 /app/backend/scripts/calculate_size.py {sra_code}"
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        logger.error(f"Error calculating size: {stderr}")
        raise HTTPException(status_code=500, detail="Error calculating size")

    sizes = stdout.strip().split(',')
    if len(sizes) != 2:
        raise HTTPException(status_code=500, detail="Invalid size format returned by script")

    size_1, size_2 = sizes

    # Check if the samples already exist
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

    # Update sample_stages with new sample IDs
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

    # Notify the frontend via WebSocket
    await manager.broadcast(f"Tamanho das amostras {sra_code} atualizado.")
    return {"message": "Sample sizes updated successfully"}

@app.get("/samples/pending_count")
def get_pending_samples_count(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pending_count = db.query(Sample).filter(Sample.status == "Pending", Sample.user_id == current_user.id).count()
    return {"pending_count": pending_count}

@app.post("/stages/")
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

class SampleStageCreateRequest(BaseModel):
    stage_id: int
    status: str

@app.post("/samples/{sample_id}/stages/")
def create_sample_stage(sample_id: int, request: SampleStageCreateRequest, db: Session = Depends(get_db)):
    db_sample_stage = SampleStage(sample_id=sample_id, stage_id=request.stage_id)
    db.add(db_sample_stage)
    db.commit()
    db.refresh(db_sample_stage)
    return db_sample_stage

@app.get("/samples/{sample_id}/stages/")
def get_sample_stages(sample_id: int, db: Session = Depends(get_db)):
    sample_stages = db.query(SampleStage).filter(SampleStage.sample_id == sample_id).all()
    return sample_stages

@app.put("/samples/{sample_id}/stages/{stage_id}")
def update_sample_stage(sample_id: int, stage_id: int, status: str, db: Session = Depends(get_db)):
    db_sample_stage = db.query(SampleStage).filter(SampleStage.sample_id == sample_id, SampleStage.stage_id == stage_id).first()
    if not db_sample_stage:
        raise HTTPException(status_code=404, detail="Sample stage not found")
    db_sample_stage.status = status
    db.commit()
    db.refresh(db_sample_stage)
    return db_sample_stage

@app.get("/samples/stages/{stage_id}")
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

# Adicionar um print para verificar os endpoints registrados
print("Registered routes before mounting Flet:", app.routes)

# Montar o aplicativo Flet como um subaplicativo
print("Mounting Flet app")
from frontend import main
app.mount("/frontend", flet_fastapi.app(main.main))

# Adicionar um print para verificar os endpoints registrados após montar o Flet
print("Registered routes after mounting Flet:", app.routes)

if __name__ == "__main__":
    print("Starting Uvicorn server")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)