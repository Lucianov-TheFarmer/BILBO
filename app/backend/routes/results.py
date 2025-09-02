from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..db.models import User
from ..utils import get_current_user
import os
import openpyxl
import subprocess
import logging
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
    files = [f for f in os.listdir(deg_dir) if f.startswith("BARPLOT.MULTIPLO - ") and f.endswith(".png")]
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
    if not contrasts:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um contraste.")
    
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    deg_xlsx_path = os.path.join(deg_dir, "DEG.xlsx")
    
    if not os.path.exists(deg_xlsx_path):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")
    
    os.makedirs(deg_dir, exist_ok=True)
    
    # Script R para barplot múltiplo
    barplot_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts/barplot_multiplo.R"))
    
    if not os.path.exists(barplot_script):
        raise HTTPException(status_code=500, detail="Script barplot_multiplo.R não encontrado.")
    
    try:
        logger = logging.getLogger(__name__)
        
        # Log dos parâmetros recebidos
        logger.info(f"Gerando barplot múltiplo: user_id={user_id}, title='{title}', contrasts={contrasts}")
        logger.info(f"DEG.xlsx path: {deg_xlsx_path}")
        logger.info(f"Script R path: {barplot_script}")
        
        # Prepara argumentos para o script R
        cmd_args = ["Rscript", barplot_script, deg_xlsx_path, deg_dir, title] + contrasts
        logger.info(f"Comando R: {' '.join(cmd_args)}")
        
        process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=deg_dir  # Define diretório de trabalho
        )
        stdout, stderr = process.communicate()
        
        logger.info(f"R script stdout: {stdout}")
        if stderr:
            logger.warning(f"R script stderr: {stderr}")
        
        if process.returncode != 0:
            logger.error(f"R script failed with return code {process.returncode}")
            raise HTTPException(status_code=500, detail=f"Erro ao executar script R: {stderr}")
        
        filename = f"BARPLOT.MULTIPLO - {title}.png"
        output_file = os.path.join(deg_dir, filename)
        
        # Verifica se o arquivo foi gerado
        if not os.path.exists(output_file):
            logger.error(f"Arquivo de saída não foi gerado: {output_file}")
            raise HTTPException(status_code=500, detail="Arquivo de imagem não foi gerado pelo script R")
        
        logger.info(f"Barplot múltiplo gerado com sucesso: {filename}")
        return {"status": "ok", "file": filename, "message": "Barplot múltiplo gerado com sucesso"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar barplot múltiplo: {e}")

@router.delete("/results/delete_barplot_file")
async def delete_barplot_file(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await request.json()
    user_id = data.get("user_id", current_user.id)
    filename = data.get("filename", "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo obrigatório.")
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    file_path = os.path.join(deg_dir, filename)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"status": "ok", "message": "Arquivo deletado com sucesso"}
        else:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao deletar arquivo: {e}")

@router.get("/results/venn_files")
async def get_venn_files(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    if not os.path.exists(deg_dir):
        return {"files": []}
    files = [f for f in os.listdir(deg_dir) if f.startswith("VENN.MULTIPLO - ") and f.endswith(".txt")]
    return {"files": files}

@router.post("/results/create_venn_file")
async def create_venn_file(
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
    filename = f"VENN.MULTIPLO - {title}.txt"
    file_path = os.path.join(deg_dir, filename)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            for contrast in contrasts:
                f.write(contrast + "\n")
        return {"status": "ok", "file": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar arquivo: {e}")

@router.get("/results/heatmap_files")
async def get_heatmap_files(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    if not os.path.exists(deg_dir):
        return {"files": []}
    files = [f for f in os.listdir(deg_dir) if f.startswith("HEATMAP.MULTIPLO - ") and f.endswith(".txt")]
    return {"files": files}

@router.post("/results/create_heatmap_file")
async def create_heatmap_file(
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
    filename = f"HEATMAP.MULTIPLO - {title}.txt"
    file_path = os.path.join(deg_dir, filename)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            for contrast in contrasts:
                f.write(contrast + "\n")
        return {"status": "ok", "file": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao criar arquivo: {e}")
