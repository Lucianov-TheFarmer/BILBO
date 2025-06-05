from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..db.models import User, SampleStage
from ..utils import get_current_user
import subprocess
import logging
import os
import openpyxl
import pandas as pd
from fastapi.responses import JSONResponse

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/deg/run")
async def run_deg(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await request.json()
    user_id = data.get("user_id", current_user.id)
    contrast_ids = data.get("contrast_ids", [])
    logger.info(f"Iniciando DEG para user_id={user_id} com contrastes {contrast_ids}")

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "preprocess"))
    deg_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts/DEG.R"))

    if not os.path.exists(deg_script):
        logger.error("Arquivo DEG.R não encontrado.")
        raise HTTPException(status_code=500, detail="Arquivo DEG.R não encontrado.")

    if not os.path.exists(base_dir):
        logger.error(f"Diretório preprocess não encontrado: {base_dir}")
        raise HTTPException(status_code=500, detail=f"Diretório preprocess não encontrado: {base_dir}")

    # Buscar todos os contrastes do usuário e salvar contrasts_db.txt
    contrasts = db.query(SampleStage).filter(
        SampleStage.stage_id == 8,
        SampleStage.user_id == user_id,
        SampleStage.status == "Contrast"
    ).all()
    contrasts_db_path = os.path.join(base_dir, "contrasts_db.txt")
    with open(contrasts_db_path, "w", encoding="utf-8") as f:
        f.write("id\tname\n")
        for c in contrasts:
            f.write(f"{c.id}\t{c.name}\n")

    # Salvar os contrastes selecionados em um arquivo para o script R ler
    selected_contrasts_path = os.path.join(base_dir, "selected_contrasts.txt")
    with open(selected_contrasts_path, "w", encoding="utf-8") as f:
        for cid in contrast_ids:
            f.write(str(cid) + "\n")

    try:
        process = subprocess.Popen(
            ["Rscript", deg_script, base_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate()
        logger.info(f"Saída do DEG.R:\n{stdout}")
        if stderr:
            logger.error(f"Erros do DEG.R:\n{stderr}")
        if process.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Erro ao executar DEG.R: {stderr}")
    except Exception as e:
        logger.error(f"Erro ao executar DEG.R: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao executar DEG.R: {e}")

    deg_xlsx = os.path.join(base_dir, "DEG.xlsx")
    if not os.path.exists(deg_xlsx):
        raise HTTPException(status_code=500, detail="Arquivo DEG.xlsx não foi gerado.")

    logger.info("DEG.xlsx gerado com sucesso.")
    return {"message": "DEG.xlsx gerado com sucesso."}

@router.get("/deg/sheets")
async def get_deg_sheets(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "preprocess"))
    deg_xlsx = os.path.join(base_dir, "DEG.xlsx")
    if not os.path.exists(deg_xlsx):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")
    try:
        wb = openpyxl.load_workbook(deg_xlsx, read_only=True)
        sheet_names = wb.sheetnames
        wb.close()
        return {"sheets": sheet_names}
    except Exception as e:
        logger.error(f"Erro ao ler abas do DEG.xlsx: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao ler abas do DEG.xlsx: {e}")

@router.get("/deg/sheet_data")
async def get_deg_sheet_data(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    sheet_name = request.query_params.get("sheet")
    logger.info(f"[DEG] Requisição para sheet_data: user_id={user_id}, sheet_name={sheet_name}")
    
    if not sheet_name:
        raise HTTPException(status_code=400, detail="Sheet name is required.")
    
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "preprocess"))
    deg_xlsx = os.path.join(base_dir, "DEG.xlsx")
    logger.info(f"[DEG] Caminho do arquivo DEG.xlsx: {deg_xlsx}")
    
    if not os.path.exists(deg_xlsx):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")
    
    try:
        # Usando pandas para ler o arquivo Excel
        df = pd.read_excel(deg_xlsx, sheet_name=sheet_name)
        
        # Verificar se o DataFrame está vazio
        if df.empty:
            logger.info("[DEG] DataFrame vazio encontrado")
            return {"columns": [], "rows": []}
        
        # Converter NaN para strings vazias
        df = df.fillna("")
        
        # Obter colunas e linhas
        columns = df.columns.tolist()
        rows = df.values.tolist()
        
        logger.info(f"[DEG] Número de colunas: {len(columns)}")
        logger.info(f"[DEG] Número de linhas: {len(rows)}")
        
        return JSONResponse(content={
            "columns": columns,
            "rows": rows
        })
        
    except ValueError as e:
        if "Worksheet named" in str(e):
            raise HTTPException(status_code=404, detail=f"Aba '{sheet_name}' não encontrada no arquivo.")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DEG] Erro ao processar o arquivo Excel com pandas: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao processar o arquivo Excel: {e}")