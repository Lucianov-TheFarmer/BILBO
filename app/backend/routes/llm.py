import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from ..core.settings import settings
from ..db.database import get_db
from ..db.models import User, SampleStage
from ..services.job_service import audit, create_job
from ..tasks.pipeline_tasks import enqueue_pipeline_job
from ..utils import get_current_user, get_current_user_compat
from ..utils_paths import ensure_safe_component, safe_resolve_user_path

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/llm/contrasts")
def list_llm_contrasts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    uid = current_user.id
    # list SampleStage entries for stage_id=10
    stages = db.query(SampleStage).filter(SampleStage.user_id == int(uid), SampleStage.stage_id == 10).all()
    results = []
    for s in stages:
        try:
            safe_sheet = ensure_safe_component(s.name, "sheet")
        except HTTPException:
            continue
        out_dir = safe_resolve_user_path(settings.users_root, uid, "llm", safe_sheet)
        files = []
        if out_dir.exists():
            files = [f.name for f in out_dir.iterdir() if f.is_file() and f.suffix.lower() in {".md", ".json"}]
        results.append({"sheet": safe_sheet, "files": files})
    return {"contrasts": results}


@router.get("/llm/file")
def download_llm_file(
    file: str,
    sheet: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_compat),
):
    safe_sheet = ensure_safe_component(sheet, "sheet")
    safe_file = ensure_safe_component(file, "file")
    file_path = safe_resolve_user_path(settings.users_root, current_user.id, "llm", safe_sheet, safe_file)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "text/markdown" if safe_file.lower().endswith('.md') else "application/json"
    headers = {}
    if not request.headers.get("Authorization") and request.query_params.get("token"):
        headers["X-Auth-Deprecated"] = "Use Authorization: Bearer <token>; query token support will be removed."
    audit(
        db,
        action="llm_artifact_download",
        user_id=current_user.id,
        stage="llm",
        metadata_json={"sheet": safe_sheet, "file": file_path.name},
    )
    return FileResponse(path=str(file_path), filename=file_path.name, media_type=media_type, headers=headers)


@router.delete("/llm/{sheet}")
def delete_llm_sheet(sheet: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    safe_sheet = ensure_safe_component(sheet, "sheet")
    out_dir = safe_resolve_user_path(settings.users_root, current_user.id, "llm", safe_sheet)
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
        logger.warning(f"Erro ao excluir LLM files: {ex}")

    try:
        ss = db.query(SampleStage).filter(SampleStage.user_id == current_user.id, SampleStage.stage_id == 10, SampleStage.name == safe_sheet).first()
        if ss:
            db.delete(ss)
            db.commit()
    except Exception as ex:
        logger.warning(f"Erro ao remover SampleStage LLM: {ex}")

    audit(
        db,
        action="llm_deleted",
        user_id=current_user.id,
        stage="llm",
        metadata_json={"sheet": safe_sheet},
    )
    return JSONResponse(content={"message": "LLM sheet deleted"})


@router.post("/llm/run", status_code=202)
async def run_llm_route(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = await request.json()
    user_id = current_user.id
    sheets = data.get("sheets") or []
    if isinstance(sheets, str):
        sheets = [sheets]
    sheets = [ensure_safe_component(str(s), "sheet") for s in sheets]

    for sheet in sheets:
        existing = db.query(SampleStage).filter(SampleStage.user_id == int(user_id), SampleStage.stage_id == 10, SampleStage.name == sheet).first()
        if not existing:
            db.add(SampleStage(stage_id=10, name=sheet, sra_code=None, size="", status="PENDING", user_id=int(user_id)))
    db.commit()

    job = create_job(db, stage="llm", user_id=user_id, payload={"sheets": sheets})
    audit(
        db,
        action="llm_enqueued",
        user_id=user_id,
        stage="llm",
        job_id=job.id,
        metadata_json={"sheets": sheets},
    )
    enqueue_pipeline_job(job.id)
    return JSONResponse(content={"job_id": job.id, "status": "PENDING", "message": "LLM job enqueued"}, status_code=202)
