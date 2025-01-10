import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Query, status
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
logging.basicConfig(level=logging.INFO)
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

@app.post("/samples/")
def create_sample(sra_code: str, size: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    existing_sample = db.query(Sample).filter(Sample.sra_code == sra_code, Sample.user_id == current_user.id).first()
    if existing_sample:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sample with this SRA code already exists")
    
    db_sample = Sample(sra_code=sra_code, size=size, status="Pending", user_id=current_user.id)
    db.add(db_sample)
    db.commit()
    db.refresh(db_sample)
    return db_sample

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
    db.delete(db_sample)
    db.commit()
    return {"message": "Sample deleted"}

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
    subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    return {"message": f"Download started for sample {sra_code}"}

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