from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import timedelta
from ..db.database import get_db
from ..db.models import User
from ..utils import pwd_context, create_access_token, get_password_hash, verify_password, get_current_user
import re

router = APIRouter()

@router.post("/register/")
def register(username: str, password: str, db: Session = Depends(get_db)):
    # 1. Validação de campos vazios
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O nome de usuário e a senha não podem estar vazios."
        )

    # 2. Validação de nome de usuário duplicado
    db_user = db.query(User).filter(User.username == username).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nome de usuário já registrado."
        )

    # 3. Validação do comprimento da senha
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A senha deve ter pelo menos 8 caracteres."
        )

    # 4. Validação de complexidade da senha (pelo menos uma letra e um número)
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A senha deve conter pelo menos uma letra e um número."
        )

    try:
        hashed_password = get_password_hash(password)
        db_user = User(username=username, hashed_password=hashed_password)
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return {"message": "Usuário registrado com sucesso"}
    except Exception as e:
        # Captura outras exceções que podem ocorrer durante a transação com o banco
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro interno do servidor.")


@router.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == form_data.username).first()
    if db_user is None or not verify_password(form_data.password, db_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    access_token_expires = timedelta(minutes=1440)
    access_token = create_access_token(data={"sub": db_user.username}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer", "user_id": db_user.id}