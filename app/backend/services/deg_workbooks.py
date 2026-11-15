"""Locate the latest completed differential analysis for a user."""

from fastapi import HTTPException

from ..core.settings import settings
from ..db.models import PipelineRun
from ..utils_paths import safe_resolve_user_path


def available_deg_workbooks(db, user_id):
    """List all retained DEG workbooks, newest first, including manual results."""
    candidates = []
    manual = safe_resolve_user_path(settings.users_root, user_id, "DEG", "DEG.xlsx")
    if manual.is_file():
        candidates.append((manual.stat().st_mtime, manual, None))
    runs = db.query(PipelineRun).filter(PipelineRun.user_id == user_id).all()
    for run in runs:
        if not any(step.stage == "deg" and step.status == "COMPLETED" for step in run.steps):
            continue
        path = safe_resolve_user_path(settings.users_root, user_id,
                                      "pipelines", run.id, "DEG", "DEG.xlsx")
        if path.is_file():
            candidates.append((path.stat().st_mtime, path, run))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [(path, run) for _, path, run in candidates]


def selected_deg_workbook(db, user_id, run_id=None):
    """Return (DEG.xlsx path, pipeline run or None), checking ownership."""
    if run_id == "manual":
        path = safe_resolve_user_path(settings.users_root, user_id, "DEG", "DEG.xlsx")
        if not path.is_file():
            raise HTTPException(404, "Arquivo DEG.xlsx não encontrado.")
        return path, None
    if run_id:
        run = db.query(PipelineRun).filter(
            PipelineRun.id == run_id, PipelineRun.user_id == user_id).first()
        if run is None or not any(step.stage == "deg" and step.status == "COMPLETED"
                                  for step in run.steps):
            raise HTTPException(404, "Pipeline DEG não encontrado.")
        path = safe_resolve_user_path(settings.users_root, user_id,
                                      "pipelines", run.id, "DEG", "DEG.xlsx")
        if not path.is_file():
            raise HTTPException(404, "Arquivo DEG.xlsx não encontrado.")
        return path, run

    candidates = available_deg_workbooks(db, user_id)
    if not candidates:
        raise HTTPException(404, "Arquivo DEG.xlsx não encontrado.")
    return candidates[0]
