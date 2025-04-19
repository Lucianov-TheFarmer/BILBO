from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import flet as ft
import logging
from .utils import manager
from .database import engine
from .models import Base
from .routes import auth, samples, quality_analysis, trimmagem, quality_analysis_post_trim, alignment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("Creating FastAPI app")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, tags=["auth"])
app.include_router(samples.router, tags=["samples"])
app.include_router(quality_analysis.router, tags=["quality_analysis"])
app.include_router(trimmagem.router, tags=["trimmagem"])  # Register the trimmagem route
app.include_router(quality_analysis_post_trim.router, tags=["quality_analysis_post_trim"])
app.include_router(alignment.router, tags=["alignment"])

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.send_personal_message(f"Message received: {data}", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

print("Registered routes before mounting Flet:", app.routes)

print("Mounting Flet app")
from frontend import main

flet_asgi_app = ft.app(main.main, export_asgi_app=True)
app.mount("/frontend", flet_asgi_app)

print("Registered routes after mounting Flet:", app.routes)

Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    print("Starting Uvicorn server")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)