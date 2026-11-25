"""Per-opening Google authorization and server-side Drive import API."""

from __future__ import annotations

import json
import os
import secrets
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import PipelineJob, SampleStage, User
from ..services.drive_service import (
    SESSION_TTL, file_metadata, parse_fastq_pair, redis_client, session_key,
    state_key, save_credentials, access_token,
)
from ..services.job_service import create_job
from ..utils import get_current_user
from ..tasks.drive_import import import_drive_pair

router = APIRouter(prefix="/drive")


def _config():
    names = ("GOOGLE_DRIVE_CLIENT_ID", "GOOGLE_DRIVE_CLIENT_SECRET", "GOOGLE_DRIVE_API_KEY", "GOOGLE_DRIVE_APP_ID")
    if any(not os.getenv(name) for name in names):
        raise HTTPException(503, "Google Drive integration is not configured")


def _redirect_uri() -> str:
    explicit = os.getenv("GOOGLE_DRIVE_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    public_base = os.getenv("BILBO_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not public_base:
        public_base = f"http://localhost:{os.getenv('BILBO_HOST_PORT', '8890')}"
    return f"{public_base}/drive/oauth/callback"


def _owned(session_id: str, user: User) -> dict:
    data = redis_client().hgetall(session_key(session_id))
    if not data or data.get("user_id") != str(user.id):
        raise HTTPException(404, "Drive session not found")
    return data


@router.post("/session")
def start_session(lang: str = "pt", user: User = Depends(get_current_user)):
    _config()
    r = redis_client()
    session_id = secrets.token_urlsafe(32)
    state = secrets.token_urlsafe(32)
    lang = lang if lang in {"pt", "en", "es"} else "pt"
    r.hset(session_key(session_id), mapping={"user_id": str(user.id), "status": "authorization_required", "lang": lang})
    r.expire(session_key(session_id), SESSION_TTL)
    r.setex(state_key(state), 600, session_id)
    params = {
        "client_id": os.environ["GOOGLE_DRIVE_CLIENT_ID"],
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/drive.file",
        "access_type": "offline",
        "prompt": "consent select_account",
        "state": state,
    }
    return {"session_id": session_id, "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)}


@router.get("/oauth/callback")
def oauth_callback(state: str, code: Optional[str] = None, error: Optional[str] = None):
    import requests
    r = redis_client()
    session_id = r.getdel(state_key(state))
    if not session_id:
        raise HTTPException(400, "Invalid or expired OAuth state")
    if error or not code:
        r.hset(session_key(session_id), "status", "authorization_failed")
        return HTMLResponse("Google Drive authorization was cancelled.", status_code=400)
    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": os.environ["GOOGLE_DRIVE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_DRIVE_CLIENT_SECRET"],
            "redirect_uri": _redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if not response.ok:
        r.hset(session_key(session_id), "status", "authorization_failed")
        raise HTTPException(400, "Google Drive authorization failed")
    try:
        save_credentials(session_id, response.json())
    except ValueError:
        r.hset(session_key(session_id), "status", "authorization_failed")
        raise HTTPException(400, "Google Drive offline access was not granted")
    r.hset(session_key(session_id), "status", "selecting")
    return RedirectResponse(f"/drive/authorized?session={session_id}", status_code=303)


@router.get("/authorized", response_class=HTMLResponse)
def authorization_complete(session: str):
    if redis_client().hget(session_key(session), "status") != "selecting":
        raise HTTPException(404, "Drive session not found")
    lang = redis_client().hget(session_key(session), "lang") or "pt"
    message = {
        "pt": "Google Drive conectado. Volte ao modal do BILBO para selecionar os arquivos.",
        "en": "Google Drive connected. Return to the BILBO dialog to select files.",
        "es": "Google Drive conectado. Vuelva al cuadro de BILBO para seleccionar archivos.",
    }.get(lang, "Google Drive connected. Return to BILBO.")
    return HTMLResponse(f"<!doctype html><html><meta charset='utf-8'><body><p>{message}</p></body></html>")


@router.get("/picker", response_class=HTMLResponse)
def picker(session: str):
    _config()
    if not redis_client().hget(session_key(session), "credentials"):
        raise HTTPException(404, "Drive session not found")
    # Session is a random, short-lived capability; the page only exposes the access token to Google's Picker.
    lang = redis_client().hget(session_key(session), "lang") or "pt"
    messages = {
        "pt": {"opening": "Abrindo Google Drive…", "sent": "Seleção enviada ao BILBO. Você pode fechar esta aba.", "failed": "Não foi possível enviar a seleção. Tente novamente."},
        "en": {"opening": "Opening Google Drive…", "sent": "Selection sent to BILBO. You can close this tab.", "failed": "Could not send selection. Please try again."},
        "es": {"opening": "Abriendo Google Drive…", "sent": "Selección enviada a BILBO. Puede cerrar esta pestaña.", "failed": "No se pudo enviar la selección. Inténtelo de nuevo."},
    }[lang if lang in {"pt", "en", "es"} else "pt"]
    config = json.dumps({"session": session, "apiKey": os.environ["GOOGLE_DRIVE_API_KEY"], "appId": os.environ["GOOGLE_DRIVE_APP_ID"], "messages": messages})
    return HTMLResponse("""<!doctype html><html><head><meta charset="utf-8"><title>Google Drive Picker</title>
<script src="https://apis.google.com/js/api.js"></script></head><body><p id="status"></p>
<script>const config = CONFIG;
document.getElementById('status').textContent = config.messages.opening;
async function openPicker() {
  const response = await fetch('/drive/picker/token?session=' + encodeURIComponent(config.session));
  if (!response.ok) throw new Error('Authorization expired');
  const {access_token} = await response.json();
  const view = new google.picker.DocsView(google.picker.ViewId.DOCS);
  const picker = new google.picker.PickerBuilder().addView(view)
    .setOAuthToken(access_token).setDeveloperKey(config.apiKey).setAppId(config.appId)
    .setOrigin(window.location.origin)
    .enableFeature(google.picker.Feature.MULTISELECT_ENABLED)
    .setCallback(async data => {
      if (data.action === google.picker.Action.PICKED) {
        const ids = data.docs.map(doc => doc.id);
        const result = await fetch('/drive/picker/selection?session=' + encodeURIComponent(config.session),
          {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})});
        document.getElementById('status').textContent = result.ok ? config.messages.sent : config.messages.failed;
        if (result.ok) window.close();
      }
    }).build();
  picker.setVisible(true);
}
gapi.load('picker', {callback: () => openPicker().catch(err => {document.getElementById('status').textContent = err.message;})});
</script></body></html>""".replace("CONFIG", config))


@router.get("/picker/token")
def picker_token(session: str):
    if not redis_client().hget(session_key(session), "credentials"):
        raise HTTPException(404, "Drive session not found")
    return {"access_token": access_token(session)}


class Selection(BaseModel):
    ids: list[str]


@router.post("/picker/selection")
def receive_selection(session: str, selection: Selection):
    r = redis_client()
    if not r.hget(session_key(session), "credentials"):
        raise HTTPException(404, "Drive session not found")
    if len(selection.ids) > 200 or len(set(selection.ids)) != len(selection.ids):
        raise HTTPException(400, "Invalid selection")
    files = []
    for file_id in selection.ids:
        metadata = file_metadata(session, file_id)
        try:
            base, mate = parse_fastq_pair(metadata["name"])
        except ValueError:
            continue
        if not metadata.get("size") or not metadata.get("md5Checksum"):
            continue
        files.append({"id": file_id, "name": metadata["name"], "base": base, "mate": mate, "size": int(metadata["size"])})
    r.hset(session_key(session), mapping={"selection": json.dumps(files), "status": "selected"})
    return {"accepted": len(files), "ignored": len(selection.ids) - len(files)}


def _selected_conflicts(db: Session, user_id: int, bases: set[str]) -> tuple[set[str], set[str]]:
    if not bases:
        return set(), set()
    existing = {
        row[0] for row in db.query(SampleStage.sra_code).filter(
            SampleStage.user_id == user_id, SampleStage.stage_id == 1,
            SampleStage.sra_code.in_(bases),
        ).all()
    }
    active_jobs = db.query(PipelineJob).filter(
        PipelineJob.user_id == user_id, PipelineJob.stage == "drive_import",
        PipelineJob.status.in_(["PENDING", "RUNNING"]),
    ).all()
    importing = {(job.payload or {}).get("base") for job in active_jobs} & bases
    return existing, importing


@router.get("/session/{session_id}")
def session_status(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = _owned(session_id, user)
    files = json.loads(data.get("selection", "[]"))
    existing, importing = _selected_conflicts(db, user.id, {file["base"] for file in files})
    return {"status": data["status"], "files": files,
            "existing_bases": sorted(existing), "importing_bases": sorted(importing)}


@router.post("/session/{session_id}/import")
def queue_import(session_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = _owned(session_id, user)
    if data.get("status") != "selected":
        raise HTTPException(409, "No Drive files selected")
    groups: dict[str, dict[int, dict]] = {}
    for file in json.loads(data.get("selection", "[]")):
        group = groups.setdefault(file["base"], {})
        if file["mate"] in group:
            raise HTTPException(400, f"Duplicate read for {file['base']}")
        group[file["mate"]] = file
    if not groups or any(set(group) != {1, 2} for group in groups.values()):
        raise HTTPException(400, "Complete R1/R2 pairs are required")
    existing, importing = _selected_conflicts(db, user.id, set(groups))
    jobs = []
    for base, group in groups.items():
        if base in existing or base in importing:
            continue
        job = create_job(db, "drive_import", user.id, {"base": base, "files": [group[1], group[2]]})
        import_drive_pair.apply_async(args=[job.id, session_id], task_id=job.id, queue="drive")
        jobs.append(job.id)
    if jobs:
        redis_client().hset(session_key(session_id), "status", "queued")
    return {"job_ids": jobs, "skipped_existing": sorted(existing),
            "skipped_importing": sorted(importing)}


@router.get("/jobs")
def recent_imports(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs = db.query(PipelineJob).filter(
        PipelineJob.user_id == user.id, PipelineJob.stage == "drive_import"
    ).order_by(PipelineJob.created_at.desc()).limit(20).all()
    r = redis_client()
    return [{
        "id": job.id,
        "base": (job.payload or {}).get("base"),
        "status": job.status,
        "size": sum(int(file.get("size", 0)) for file in (job.payload or {}).get("files", [])),
        "progress": r.hgetall(f"bilbo:drive:job:{job.id}") if job.status == "RUNNING" else {},
    } for job in jobs]


@router.get("/jobs/{job_id}")
def import_status(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.query(PipelineJob).filter(PipelineJob.id == job_id, PipelineJob.user_id == user.id, PipelineJob.stage == "drive_import").first()
    if not job:
        raise HTTPException(404, "Import job not found")
    progress = redis_client().hgetall(f"bilbo:drive:job:{job_id}")
    return {"id": job.id, "base": job.payload.get("base"), "status": job.status,
            "result": job.result, "error": job.error_message, "progress": progress,
            "files": [{"mate": file["mate"], "size": file["size"]} for file in job.payload.get("files", [])]}
