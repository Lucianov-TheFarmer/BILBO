from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..db.models import User
from ..utils import get_current_user
import os
import openpyxl
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/results/deg_sheets")
async def get_deg_sheets(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    deg_xlsx = os.path.join(deg_dir, "DEG.xlsx")
    if not os.path.exists(deg_xlsx):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")
    try:
        wb = openpyxl.load_workbook(deg_xlsx, read_only=True)
        sheet_names = wb.sheetnames
        wb.close()
        return {"sheets": sheet_names}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler abas do DEG.xlsx: {e}")

@router.get("/results/barplot_files")
async def get_barplot_files(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    if not os.path.exists(deg_dir):
        return {"files": []}
    files = [f for f in os.listdir(deg_dir) if f.startswith("BARPLOT - ") and f.endswith(".txt")]
    return {"files": files}

@router.post("/results/create_barplot_file")
async def create_barplot_file(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await request.json()
    user_id = data.get("user_id", current_user.id)
    title = data.get("title", "").strip()
    contrasts = data.get("contrasts", [])
    if not title:
        raise HTTPException(status_code=400, detail="Título obrigatório.")
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    os.makedirs(deg_dir, exist_ok=True)
    filename = f"BARPLOT - {title}.txt"
    file_path = os.path.join(deg_dir, filename)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            for contrast in contrasts:
                f.write(contrast + "\n")
        return {"status": "ok", "file": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar arquivo: {e}")
