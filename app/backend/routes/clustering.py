import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from ..core.settings import settings
from ..db.database import get_db
from ..db.models import SampleStage, User
from ..services.job_service import audit, create_job
from ..tasks.pipeline_tasks import enqueue_pipeline_job
from ..utils import get_current_user, get_current_user_compat
from ..utils_paths import ensure_safe_component, safe_resolve_user_path
import openpyxl

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/clustering/contrasts")
async def list_contrasts(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user_id = current_user.id
    deg_dir = safe_resolve_user_path(settings.users_root, user_id, "DEG")
    deg_xlsx = deg_dir / "DEG.xlsx"
    if not deg_xlsx.exists():
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")

    try:
        wb = openpyxl.load_workbook(str(deg_xlsx), read_only=True)
        sheet_names = wb.sheetnames
        wb.close()
    except Exception as e:
        logger.error(f"Erro ao ler abas do DEG.xlsx: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao ler abas do DEG.xlsx: {e}")

    results = []
    for sheet in sheet_names:
        try:
            safe_sheet = ensure_safe_component(sheet, "sheet")
        except HTTPException:
            continue
        cluster_dir = safe_resolve_user_path(settings.users_root, user_id, "clustering", safe_sheet)
        clustered = False
        files = []
        if cluster_dir.exists():
            files = [f.name for f in cluster_dir.iterdir() if f.is_file() and f.suffix.lower() in {'.png', '.jpg', '.jpeg'}]
            clustered = len(files) > 0
        results.append({"sheet": safe_sheet, "clustered": clustered, "files": files})

    return {"contrasts": results}

@router.post("/clustering/run", status_code=202)
async def run_clustering(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = await request.json()
    user_id = current_user.id
    sheets = data.get("sheets") or []
    if isinstance(sheets, str):
        sheets = [sheets]
    sheets = [ensure_safe_component(str(s), "sheet") for s in sheets]

    deg_dir = safe_resolve_user_path(settings.users_root, user_id, "DEG")
    deg_xlsx = deg_dir / "DEG.xlsx"
    if not deg_xlsx.exists():
        raise HTTPException(status_code=404, detail="Arquivo DEG.xlsx não encontrado.")

    for sheet in sheets:
        out_dir = safe_resolve_user_path(settings.users_root, user_id, "clustering", sheet)
        out_dir.mkdir(parents=True, exist_ok=True)
        existing = db.query(SampleStage).filter(SampleStage.user_id == int(user_id), SampleStage.stage_id == 9, SampleStage.name == sheet).first()
        if not existing:
            db.add(SampleStage(stage_id=9, name=sheet, sra_code=None, size="", status="PENDING", user_id=int(user_id)))
    db.commit()

    job = create_job(db, stage="clustering", user_id=user_id, payload={"sheets": sheets})
    audit(
        db,
        action="clustering_enqueued",
        user_id=user_id,
        stage="clustering",
        job_id=job.id,
        metadata_json={"sheets": sheets},
    )
    enqueue_pipeline_job(job.id)
    return JSONResponse(content={"job_id": job.id, "status": "PENDING", "message": "Clustering job enqueued"}, status_code=202)


@router.get("/clustering/file")
def download_clustering_file(
    file: str,
    sheet: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_compat),
):
    """Serve a clustering image file after validating bearer token."""
    safe_sheet = ensure_safe_component(sheet, "sheet")
    safe_file = ensure_safe_component(file, "file")
    file_path = safe_resolve_user_path(settings.users_root, current_user.id, "clustering", safe_sheet, safe_file)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    headers = {}
    if not request.headers.get("Authorization") and request.query_params.get("token"):
        headers["X-Auth-Deprecated"] = "Use Authorization: Bearer <token>; query token support will be removed."
    audit(
        db,
        action="clustering_artifact_download",
        user_id=current_user.id,
        stage="clustering",
        metadata_json={"sheet": safe_sheet, "file": file_path.name},
    )
    return FileResponse(path=str(file_path), filename=file_path.name, media_type="image/png", headers=headers)


@router.delete("/clustering/{sheet}")
def delete_clustering_sheet(sheet: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Delete clustering files and the corresponding SampleStage entry."""
    safe_sheet = ensure_safe_component(sheet, "sheet")
    out_dir = safe_resolve_user_path(settings.users_root, current_user.id, "clustering", safe_sheet)
    # remove files and directory
    try:
        if out_dir.exists():
            for f in out_dir.iterdir():
                try:
                    if f.is_file():
                        f.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                out_dir.rmdir()
            except Exception:
                pass
    except Exception as ex:
        logger.warning(f"Erro ao excluir arquivos de clustering: {ex}")

    # remove DB entry
    try:
        ss = db.query(SampleStage).filter(SampleStage.user_id == current_user.id, SampleStage.stage_id == 9, SampleStage.name == safe_sheet).first()
        if ss:
            db.delete(ss)
            db.commit()
    except Exception as ex:
        logger.warning(f"Erro ao remover SampleStage de clustering: {ex}")

    audit(
        db,
        action="clustering_deleted",
        user_id=current_user.id,
        stage="clustering",
        metadata_json={"sheet": safe_sheet},
    )
    return JSONResponse(content={"message": "Clustering deleted"})
