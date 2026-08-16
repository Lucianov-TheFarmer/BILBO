import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from ..core.settings import settings
from ..db.database import get_db
from ..db.models import User, SampleStage
from ..services.job_service import audit, create_job
from ..services.rag_bootstrap import rag_status
from ..tasks.pipeline_tasks import enqueue_pipeline_job
from ..utils import get_current_user, get_current_user_compat
from ..utils_paths import ensure_safe_component, safe_resolve_user_path

router = APIRouter()
logger = logging.getLogger(__name__)



@router.get("/llm/rag/status")
def get_rag_status(current_user: User = Depends(get_current_user)):
    del current_user
    return rag_status()


@router.post("/llm/rag/initialize", status_code=202)
def initialize_rag(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    status = rag_status()
    if status["ready"]:
        return JSONResponse(
            content={
                "status": "COMPLETED",
                "message": "RAG database is already initialized.",
                "rag": status,
            },
            status_code=200,
        )

    job = create_job(
        db,
        stage="rag_bootstrap",
        user_id=current_user.id,
        payload={"source": "zenodo", "shared": True},
    )
    audit(
        db,
        action="rag_bootstrap_enqueued",
        user_id=current_user.id,
        stage="rag_bootstrap",
        job_id=job.id,
        metadata_json={"snapshot_url": status["snapshot_url"]},
    )
    enqueue_pipeline_job(job.id)
    return JSONResponse(
        content={
            "job_id": job.id,
            "status": "PENDING",
            "message": "RAG database initialization enqueued.",
        },
        status_code=202,
    )


@router.get("/llm/contrasts")
def list_llm_contrasts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import json as json_module

    uid = int(current_user.id)

    stages = (
        db.query(SampleStage)
        .filter(
            SampleStage.user_id == uid,
            SampleStage.stage_id == 10,
        )
        .all()
    )

    results = []
    seen_sheets = set()

    for stage in stages:
        if str(stage.status or "").upper() != "COMPLETED":
            continue

        try:
            safe_sheet = ensure_safe_component(
                stage.name,
                "sheet",
            )
        except HTTPException:
            continue

        if safe_sheet in seen_sheets:
            continue

        out_dir = safe_resolve_user_path(
            settings.users_root,
            uid,
            "llm",
            safe_sheet,
        )

        required = {
            "report.md": out_dir / "report.md",
            "report.html": out_dir / "report.html",
            "data.json": out_dir / "data.json",
        }

        if not all(
            path.is_file() and path.stat().st_size > 0
            for path in required.values()
        ):
            continue

        try:
            json_module.loads(
                required["data.json"].read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            UnicodeDecodeError,
            json_module.JSONDecodeError,
        ):
            continue

        files = sorted(
            path.name
            for path in out_dir.iterdir()
            if (
                path.is_file()
                and path.stat().st_size > 0
                and path.suffix.lower()
                in {".md", ".json", ".html"}
            )
        )

        results.append({
            "sheet": safe_sheet,
            "files": files,
        })
        seen_sheets.add(safe_sheet)

    return {"contrasts": results}


@router.get("/llm/file")
def download_llm_file(
    file: str,
    sheet: str,
    request: Request,
    inline: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_compat),
):
    safe_sheet = ensure_safe_component(sheet, "sheet")
    safe_file = ensure_safe_component(file, "file")
    file_path = safe_resolve_user_path(settings.users_root, current_user.id, "llm", safe_sheet, safe_file)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    suffix = file_path.suffix.lower()
    media_type = {
        ".md": "text/markdown; charset=utf-8",
        ".json": "application/json",
        ".html": "text/html; charset=utf-8",
    }.get(suffix, "application/octet-stream")
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
    if suffix == ".html" and inline:
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            headers=headers,
        )
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type,
        headers=headers,
    )


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
    sheets = [
        ensure_safe_component(
            str(sheet),
            "sheet",
        )
        for sheet in sheets
    ]

    # BILBO_LLM_REJECT_ACTIVE_DUPLICATES
    active_stages = (
        db.query(SampleStage)
        .filter(
            SampleStage.user_id == int(user_id),
            SampleStage.stage_id == 10,
            SampleStage.name.in_(sheets),
            SampleStage.status.in_(
                ["PENDING", "RUNNING"]
            ),
        )
        .all()
    )

    active_sheets = sorted(
        {
            str(stage.name)
            for stage in active_stages
        }
    )

    if active_sheets:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Já existe interpretação LLM "
                    "em andamento para um ou mais contrastes."
                ),
                "active_sheets": active_sheets,
            },
        )

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
