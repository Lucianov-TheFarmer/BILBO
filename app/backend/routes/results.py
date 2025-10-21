from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..db.database import get_db
from ..db.models import User
from ..utils import get_current_user
import os
import openpyxl
import subprocess
import tempfile
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
    files = [f for f in os.listdir(deg_dir) if f.startswith("VENN.DIAGRAM - ") and f.endswith(".png")]
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
        raise HTTPException(status_code=400, detail="Pelo menos um contraste deve ser selecionado.")
        
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    os.makedirs(deg_dir, exist_ok=True)
    
    # Caminhos dos arquivos
    deg_xlsx = os.path.join(deg_dir, "DEG.xlsx")
    png_filename = f"BARPLOT.MULTIPLO - {title}.png"
    png_path = os.path.join(deg_dir, png_filename)
    
    # Verifica se DEG.xlsx existe
    if not os.path.exists(deg_xlsx):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado. Execute a análise DEG primeiro.")
    
    try:
        # Cria arquivo temporário com contrastes
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as temp_file:
            for contrast in contrasts:
                temp_file.write(contrast + "\n")
            temp_contrasts_path = temp_file.name
        
        # Executa script de geração do barplot múltiplo
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts/multiple_barplot.py"))
        
        if not os.path.exists(script_path):
            raise HTTPException(status_code=500, detail="Script multiple_barplot.py não encontrado.")
        
        result = subprocess.run(
            ["python", script_path, temp_contrasts_path, deg_xlsx, png_path, title],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Remove arquivo temporário
        os.unlink(temp_contrasts_path)
        
        if result.returncode != 0:
            logging.error(f"Erro ao executar multiple_barplot.py: {result.stderr}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar barplot: {result.stderr}")
        
        logging.info(f"Barplot múltiplo gerado: {png_filename}")
        return {"status": "ok", "file": png_filename}
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Timeout na geração do barplot.")
    except Exception as e:
        logging.error(f"Erro ao criar barplot múltiplo: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao criar barplot: {e}")

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
    if not contrasts:
        raise HTTPException(status_code=400, detail="Pelo menos um contraste deve ser selecionado.")
    if len(contrasts) < 2 or len(contrasts) > 4:
        raise HTTPException(status_code=400, detail="Diagrama de Venn requer 2-4 contrastes.")
        
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    os.makedirs(deg_dir, exist_ok=True)
    
    # Caminhos dos arquivos
    deg_xlsx = os.path.join(deg_dir, "DEG.xlsx")
    png_filename = f"VENN.DIAGRAM - {title}.png"
    png_path = os.path.join(deg_dir, png_filename)
    
    # Verifica se DEG.xlsx existe
    if not os.path.exists(deg_xlsx):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado. Execute a análise DEG primeiro.")
    
    try:
        # Cria arquivo temporário com contrastes
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as temp_file:
            for contrast in contrasts:
                temp_file.write(contrast + "\n")
            temp_contrasts_path = temp_file.name
        
        # Executa script de geração do diagrama de Venn
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts/venn_diagram.py"))
        
        if not os.path.exists(script_path):
            raise HTTPException(status_code=500, detail="Script venn_diagram.py não encontrado.")
        
        result = subprocess.run(
            ["python", script_path, temp_contrasts_path, deg_xlsx, png_path, title],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Remove arquivo temporário
        os.unlink(temp_contrasts_path)
        
        if result.returncode != 0:
            logging.error(f"Erro ao executar venn_diagram.py: {result.stderr}")
            raise HTTPException(status_code=500, detail=f"Erro ao gerar diagrama de Venn: {result.stderr}")
        
        logging.info(f"Diagrama de Venn gerado: {png_filename}")
        return {"status": "ok", "file": png_filename}
        
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Timeout na geração do diagrama de Venn.")
    except Exception as e:
        logging.error(f"Erro ao criar diagrama de Venn: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao criar diagrama de Venn: {e}")

@router.delete("/results/delete_barplot_file")
async def delete_barplot_file(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    filename = request.query_params.get("filename", "").strip()
    
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo obrigatório.")
    
    # Verifica se é um arquivo de barplot múltiplo válido
    if not filename.startswith("BARPLOT.MULTIPLO - ") or not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="Arquivo inválido.")
    
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    file_path = os.path.join(deg_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    
    try:
        os.remove(file_path)
        logging.info(f"Barplot excluído: {filename}")
        return {"status": "ok", "message": "Arquivo excluído com sucesso"}
    except Exception as e:
        logging.error(f"Erro ao excluir barplot: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao excluir arquivo: {e}")

@router.delete("/results/delete_venn_file")
async def delete_venn_file(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = request.query_params.get("user_id", current_user.id)
    filename = request.query_params.get("filename", "").strip()
    
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo obrigatório.")
    
    # Verifica se é um arquivo de diagrama de Venn válido
    if not filename.startswith("VENN.DIAGRAM - ") or not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="Arquivo inválido.")
    
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    file_path = os.path.join(deg_dir, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    
    try:
        os.remove(file_path)
        logging.info(f"Diagrama de Venn excluído: {filename}")
        return {"status": "ok", "message": "Arquivo excluído com sucesso"}
    except Exception as e:
        logging.error(f"Erro ao excluir diagrama de Venn: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao excluir arquivo: {e}")
