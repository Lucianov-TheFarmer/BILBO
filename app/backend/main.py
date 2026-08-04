import asyncio
import logging
import os
from typing import Optional

import flet as ft
import ollama
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from .core.settings import settings
from .db.database import SessionLocal, engine
from .db.models import Base, PipelineJob, User
from .routes import (
    alignment,
    auth,
    contrasts,
    deg,
    preprocess,
    quality_analysis,
    quality_analysis_post_trim,
    quantification,
    results,
    samples,
    trimmagem,
    upload,
)
from .routes import clustering as clustering_route
from .routes import jobs as jobs_route
from .routes import llm as llm_route
from .utils import decode_token_user, get_current_user, manager


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

ollama_client = None
try:
    ollama_client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    ollama_client.list()
    logger.info("Connected to Ollama")
except Exception as e:  # noqa: BLE001
    logger.warning("Ollama unavailable: %s", e)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, tags=["auth"])
app.include_router(samples.router, tags=["samples"])
app.include_router(quality_analysis.router, tags=["quality_analysis"])
app.include_router(trimmagem.router, tags=["trimmagem"])
app.include_router(quality_analysis_post_trim.router, tags=["quality_analysis_post_trim"])
app.include_router(alignment.router, tags=["alignment"])
app.include_router(quantification.router, tags=["quantification"])
app.include_router(contrasts.router, tags=["contrasts"])
app.include_router(preprocess.router, tags=["preprocess"])
app.include_router(deg.router, tags=["deg"])
app.include_router(results.router, tags=["results"])
app.include_router(upload.router, tags=["upload"])
app.include_router(clustering_route.router, tags=["clustering"])
app.include_router(llm_route.router, tags=["llm"])
app.include_router(jobs_route.router, tags=["jobs"])


class ChatRequest(BaseModel):
    message: str
    model: str = settings.llm_primary_model


@app.get("/health/live")
def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Database not ready: {e}")
    return {"status": "ready"}


@app.get("/metrics/basic")
def metrics_basic():
    db = SessionLocal()
    try:
        total_jobs = db.query(PipelineJob).count()
        by_status = {}
        for status_name in ["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELED"]:
            by_status[status_name] = db.query(PipelineJob).filter(PipelineJob.status == status_name).count()
        return {"jobs_total": total_jobs, "jobs_by_status": by_status}
    finally:
        db.close()


SYSTEM_PROMPT = """
Você é o Bilbo-AI, assistente de bioinformática do pipeline RNA-seq da plataforma BILBO.
Responda sempre em Português (Brasil), com foco técnico, claro e didático.
"""


@app.post("/chat", tags=["ollama"])
async def handle_chat(request: ChatRequest, _current_user: User = Depends(get_current_user)):
    if ollama_client is None:
        raise HTTPException(status_code=503, detail="Serviço Ollama não está disponível.")

    models = [request.model] + [m for m in settings.llm_fallback_models if m != request.model]
    last_error = None
    for model in models:
        try:
            response = ollama_client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": request.message},
                ],
            )
            payload = response["message"]
            payload["model"] = model
            return payload
        except Exception as e:  # noqa: BLE001
            last_error = str(e)
            continue

    raise HTTPException(status_code=500, detail=f"Erro ao comunicar com Ollama: {last_error}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token", "").strip()
    auth_header = websocket.headers.get("Authorization", "")
    if not token and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()

    if not token:
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    try:
        username = decode_token_user(token)
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            await websocket.close(code=1008)
            return
        await manager.connect(websocket, user.id)
    except Exception:
        await websocket.close(code=1008)
        return
    finally:
        db.close()

    try:
        while True:
            data = await websocket.receive_text()
            await manager.send_personal_message(f"Message received: {data}", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


from frontend import main  # noqa: E402

flet_asgi_app = ft.app(main.main, export_asgi_app=True, assets_dir="assets")
app.mount("/frontend", flet_asgi_app)


@app.on_event("startup")
async def bootstrap_database() -> None:
    last_error: Optional[Exception] = None
    max_attempts = max(1, settings.db_startup_max_attempts)
    retry_seconds = max(0.1, settings.db_startup_retry_seconds)

    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=engine)
            logger.info("Database bootstrap completed (%s/%s).", attempt, max_attempts)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "Database bootstrap attempt %s/%s failed: %s",
                attempt,
                max_attempts,
                exc,
            )
            if attempt < max_attempts:
                await asyncio.sleep(retry_seconds)

    raise RuntimeError(
        "Database bootstrap failed after "
        f"{max_attempts} attempts. Check DATABASE_URL/POSTGRES_* in .env and PostgreSQL readiness. "
        f"Last error: {last_error}"
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8890)
