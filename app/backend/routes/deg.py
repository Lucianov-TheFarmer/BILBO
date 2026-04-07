from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import logging
import os

import openpyxl
import pandas as pd

from ..db.database import get_db
from ..db.models import SampleStage, User
from ..services.job_service import audit, create_job
from ..tasks.pipeline_tasks import enqueue_pipeline_job
from ..utils import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/deg/run", status_code=202)
async def run_deg(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await request.json()
    user_id = current_user.id
    contrast_ids = data.get("contrast_ids", [])
    genome_accession = data.get("genome_accession")
    logger.info(f"Iniciando DEG para user_id={user_id} com contrastes {contrast_ids} e genoma {genome_accession}")

    preprocess_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "preprocess"))
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    os.makedirs(deg_dir, exist_ok=True)

    if not os.path.exists(preprocess_dir):
        logger.error(f"Diretório preprocess não encontrado: {preprocess_dir}")
        raise HTTPException(status_code=500, detail=f"Diretório preprocess não encontrado: {preprocess_dir}")

    # Buscar todos os contrastes do usuário e salvar contrasts_db.txt
    contrasts = db.query(SampleStage).filter(
        SampleStage.stage_id == 8,
        SampleStage.user_id == user_id,
        SampleStage.status == "Contrast"
    ).all()
    contrasts_db_path = os.path.join(preprocess_dir, "contrasts_db.txt")
    with open(contrasts_db_path, "w", encoding="utf-8") as f:
        f.write("id\tname\n")
        for c in contrasts:
            f.write(f"{c.id}\t{c.name}\n")

    # Salvar os contrastes selecionados em um arquivo para o script R ler
    selected_contrasts_path = os.path.join(preprocess_dir, "selected_contrasts.txt")
    with open(selected_contrasts_path, "w", encoding="utf-8") as f:
        for cid in contrast_ids:
            f.write(str(cid) + "\n")

    # Salvar o accession do genoma selecionado
    if genome_accession:
        genome_file_path = os.path.join(preprocess_dir, "selected_genome.txt")
        with open(genome_file_path, "w", encoding="utf-8") as f:
            f.write(str(genome_accession) + "\n")

    job = create_job(
        db,
        stage="deg",
        user_id=user_id,
        payload={"contrast_ids": contrast_ids, "genome_accession": genome_accession},
    )
    audit(
        db,
        action="deg_enqueued",
        user_id=user_id,
        stage="deg",
        job_id=job.id,
        metadata_json={"contrast_ids": contrast_ids, "genome_accession": genome_accession},
    )
    enqueue_pipeline_job(job.id)
    return {"job_id": job.id, "status": "PENDING", "message": "DEG job enqueued"}

@router.get("/deg/sheets")
async def get_deg_sheets(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
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
        logger.error(f"Erro ao ler abas do DEG.xlsx: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao ler abas do DEG.xlsx: {e}")

@router.get("/deg/sheet_data")
async def get_deg_sheet_data(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = current_user.id
    sheet_name = request.query_params.get("sheet")
    page = max(1, int(request.query_params.get("page", "1")))
    page_size = min(500, max(1, int(request.query_params.get("page_size", "100"))))
    logger.info(f"[DEG] Requisição para sheet_data: user_id={user_id}, sheet_name={sheet_name}")
    
    if not sheet_name:
        raise HTTPException(status_code=400, detail="Sheet name is required.")
    
    deg_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../users", str(user_id), "DEG"))
    deg_xlsx = os.path.join(deg_dir, "DEG.xlsx")
    logger.info(f"[DEG] Caminho do arquivo DEG.xlsx: {deg_xlsx}")
    
    if not os.path.exists(deg_xlsx):
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")
    
    try:
        df = pd.read_excel(deg_xlsx, sheet_name=sheet_name)
        if df.empty:
            return {"columns": [], "rows": [], "page": page, "page_size": page_size, "total_rows": 0}

        df = df.fillna("")

        total_rows = len(df)
        start = (page - 1) * page_size
        end = start + page_size
        paged_df = df.iloc[start:end]

        columns = df.columns.tolist()
        rows = paged_df.values.tolist()

        return JSONResponse(content={
            "columns": columns,
            "rows": rows,
            "page": page,
            "page_size": page_size,
            "total_rows": total_rows,
        })
        
    except ValueError as e:
        if "Worksheet named" in str(e):
            raise HTTPException(status_code=404, detail=f"Aba '{sheet_name}' não encontrada no arquivo.")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[DEG] Erro ao processar o arquivo Excel com pandas: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao processar o arquivo Excel: {e}")
