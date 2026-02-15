from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import openpyxl
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..core.settings import settings
from ..db.database import get_db
from ..db.models import User
from ..services.job_service import audit, create_job
from ..tasks.pipeline_tasks import enqueue_pipeline_job
from ..utils import get_current_user, get_current_user_compat
from ..utils_paths import ensure_safe_component, safe_resolve_user_path

router = APIRouter()


def _deg_dir(user_id: int) -> Path:
    return safe_resolve_user_path(settings.users_root, user_id, "DEG")


@router.get("/results/deg_sheets")
async def get_deg_sheets(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    deg_dir = _deg_dir(current_user.id)
    deg_xlsx = deg_dir / "DEG.xlsx"
    if not deg_xlsx.exists():
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")
    try:
        wb = openpyxl.load_workbook(str(deg_xlsx), read_only=True)
        sheets = wb.sheetnames
        wb.close()
        return {"sheets": sheets}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Erro ao ler abas do DEG.xlsx: {e}")


@router.get("/results/barplot_files")
async def get_barplot_files(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    deg_dir = _deg_dir(current_user.id)
    if not deg_dir.exists():
        return {"files": []}
    files = [f.name for f in deg_dir.iterdir() if f.is_file() and f.name.startswith("BARPLOT.MULTIPLO - ") and f.suffix.lower() == ".png"]
    return {"files": files}


@router.post("/results/create_barplot_file", status_code=202)
async def create_barplot_file(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = await request.json()
    title = ensure_safe_component(str(data.get("title", "")).strip(), "title")
    contrasts = data.get("contrasts", [])
    if not contrasts:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um contraste.")

    deg_xlsx_path = _deg_dir(current_user.id) / "DEG.xlsx"
    if not deg_xlsx_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")

    job = create_job(
        db,
        stage="results_barplot",
        user_id=current_user.id,
        payload={"title": title, "contrasts": list(contrasts)},
    )
    audit(
        db,
        action="results_barplot_enqueued",
        user_id=current_user.id,
        stage="results",
        job_id=job.id,
        metadata_json={"title": title, "contrasts": list(contrasts)},
    )
    enqueue_pipeline_job(job.id)

    return {"job_id": job.id, "status": "PENDING", "filename": f"BARPLOT.MULTIPLO - {title}.png", "message": "Barplot job enqueued"}


@router.delete("/results/delete_barplot_file")
async def delete_barplot_file(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    filename = request.query_params.get("filename", "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo obrigatório.")
    if not filename.startswith("BARPLOT.MULTIPLO - ") or not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="Arquivo inválido.")

    file_path = safe_resolve_user_path(settings.users_root, current_user.id, "DEG", filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    file_path.unlink(missing_ok=True)
    audit(
        db,
        action="results_barplot_deleted",
        user_id=current_user.id,
        stage="results",
        metadata_json={"filename": filename},
    )
    return {"status": "ok", "message": "Arquivo excluído com sucesso"}


@router.get("/results/venn_files")
async def get_venn_files(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    deg_dir = _deg_dir(current_user.id)
    if not deg_dir.exists():
        return {"files": []}
    files = [f.name for f in deg_dir.iterdir() if f.is_file() and f.name.startswith("VENN.DIAGRAM - ") and f.suffix.lower() == ".png"]
    return {"files": files}


@router.get("/results/heatmap_files")
async def get_heatmap_files(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    deg_dir = _deg_dir(current_user.id)
    if not deg_dir.exists():
        return {"files": []}
    files = [f.name for f in deg_dir.iterdir() if f.is_file() and f.name.startswith("HEATMAP - ") and f.suffix.lower() == ".png"]
    return {"files": files}


@router.get("/results/download_deg_sheets")
def download_deg_sheets(
    request: Request,
    sheets: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_compat),
):
    deg_xlsx_path = _deg_dir(current_user.id) / "DEG.xlsx"
    if not deg_xlsx_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")

    requested = [] if not sheets else [s.strip() for s in sheets.split(",") if s.strip()]

    headers = {}
    if not request.headers.get("Authorization") and request.query_params.get("token"):
        headers["X-Auth-Deprecated"] = "Use Authorization: Bearer <token>; query token support will be removed."

    if not requested:
        audit(
            db,
            action="results_deg_sheet_download",
            user_id=current_user.id,
            stage="results",
            metadata_json={"sheets": ["*"]},
        )
        return FileResponse(
            path=str(deg_xlsx_path),
            filename=deg_xlsx_path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    with pd.ExcelWriter(str(tmp_path), engine="openpyxl") as writer:
        for sheet in requested:
            try:
                df = pd.read_excel(str(deg_xlsx_path), sheet_name=sheet)
                df.to_excel(writer, sheet_name=sheet, index=False)
            except Exception:
                continue

    audit(
        db,
        action="results_deg_sheet_download",
        user_id=current_user.id,
        stage="results",
        metadata_json={"sheets": requested},
    )

    return FileResponse(
        path=str(tmp_path),
        filename=f"DEG_selected_sheets_{current_user.id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get("/results/download_image")
def download_deg_image(
    request: Request,
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_compat),
):
    file_path = safe_resolve_user_path(settings.users_root, current_user.id, "DEG", filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    headers = {}
    if not request.headers.get("Authorization") and request.query_params.get("token"):
        headers["X-Auth-Deprecated"] = "Use Authorization: Bearer <token>; query token support will be removed."

    audit(
        db,
        action="results_image_download",
        user_id=current_user.id,
        stage="results",
        metadata_json={"filename": filename},
    )
    return FileResponse(path=str(file_path), filename=file_path.name, media_type="application/octet-stream", headers=headers)


@router.post("/results/create_venn_file", status_code=202)
async def create_venn_file(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = await request.json()
    title = ensure_safe_component(str(data.get("title", "")).strip(), "title")
    contrasts = list(data.get("contrasts", []))
    if len(contrasts) < 2 or len(contrasts) > 4:
        raise HTTPException(status_code=400, detail="Diagrama de Venn requer 2-4 contrastes.")

    deg_xlsx = _deg_dir(current_user.id) / "DEG.xlsx"
    if not deg_xlsx.exists():
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado. Execute a análise DEG primeiro.")

    job = create_job(
        db,
        stage="results_venn",
        user_id=current_user.id,
        payload={"title": title, "contrasts": contrasts},
    )
    audit(
        db,
        action="results_venn_enqueued",
        user_id=current_user.id,
        stage="results",
        job_id=job.id,
        metadata_json={"title": title, "contrasts": contrasts},
    )
    enqueue_pipeline_job(job.id)
    return {"job_id": job.id, "status": "PENDING", "filename": f"VENN.DIAGRAM - {title}.png", "message": "Venn job enqueued"}


@router.delete("/results/delete_venn_file")
async def delete_venn_file(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    filename = request.query_params.get("filename", "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo obrigatório.")
    if not filename.startswith("VENN.DIAGRAM - ") or not filename.endswith(".png"):
        raise HTTPException(status_code=400, detail="Arquivo inválido.")

    file_path = safe_resolve_user_path(settings.users_root, current_user.id, "DEG", filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    file_path.unlink(missing_ok=True)
    audit(
        db,
        action="results_venn_deleted",
        user_id=current_user.id,
        stage="results",
        metadata_json={"filename": filename},
    )
    return {"status": "ok", "message": "Arquivo excluído com sucesso"}


@router.post("/results/create_heatmap_file", status_code=202)
async def create_heatmap_file(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = await request.json()
    title = ensure_safe_component(str(data.get("title", "")).strip(), "title")
    selected_contrasts = list(data.get("selected_contrasts", []))
    if not selected_contrasts:
        raise HTTPException(status_code=400, detail="Pelo menos um contraste deve ser selecionado.")

    deg_xlsx = _deg_dir(current_user.id) / "DEG_full.xlsx"
    if not deg_xlsx.exists():
        raise HTTPException(status_code=404, detail="Arquivo DEG_full.xlsx não encontrado.")

    job = create_job(
        db,
        stage="results_heatmap",
        user_id=current_user.id,
        payload={"title": title, "selected_contrasts": selected_contrasts},
    )
    audit(
        db,
        action="results_heatmap_enqueued",
        user_id=current_user.id,
        stage="results",
        job_id=job.id,
        metadata_json={"title": title, "selected_contrasts": selected_contrasts},
    )
    enqueue_pipeline_job(job.id)
    return {"job_id": job.id, "status": "PENDING", "filename": f"HEATMAP - {title}.png", "message": "Heatmap job enqueued"}


@router.delete("/results/delete_heatmap_file")
async def delete_heatmap_file(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    filename = request.query_params.get("filename", "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Nome do arquivo obrigatório.")

    deg_dir = _deg_dir(current_user.id)
    candidates = []
    if filename.startswith("HEATMAP - ") and filename.endswith(".png"):
        candidates.append(safe_resolve_user_path(settings.users_root, current_user.id, "DEG", filename))
    else:
        candidates.extend([f for f in deg_dir.iterdir() if f.is_file() and filename in f.name and f.suffix.lower() == ".png"])

    if not candidates:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    deleted_file = candidates[0]
    deleted_file.unlink(missing_ok=True)
    audit(
        db,
        action="results_heatmap_deleted",
        user_id=current_user.id,
        stage="results",
        metadata_json={"filename": deleted_file.name},
    )
    return {"status": "ok", "message": "Arquivo excluído com sucesso"}
