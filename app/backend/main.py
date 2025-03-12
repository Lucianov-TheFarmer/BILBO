from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import flet_fastapi
import logging
from .utils import manager  # Atualizado
from .database import engine
from .models import Base

# Importar as rotas
from .routes import auth, samples, quality_analysis  # Atualizado

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("Creating FastAPI app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting Flet app manager")
    await flet_fastapi.app_manager.start()
    yield
    print("Shutting down Flet app manager")
    await flet_fastapi.app_manager.shutdown()

app = FastAPI(lifespan=lifespan)

# Add CORS middleware to allow WebSocket connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir as rotas sem prefixos
app.include_router(auth.router, tags=["auth"])
app.include_router(samples.router, tags=["samples"])
app.include_router(quality_analysis.router, tags=["quality_analysis"])  # Atualizado

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.send_personal_message(f"Message received: {data}", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Adicionar um print para verificar os endpoints registrados
print("Registered routes before mounting Flet:", app.routes)

# Montar o aplicativo Flet como um subaplicativo
print("Mounting Flet app")
from frontend import main
app.mount("/frontend", flet_fastapi.app(main.main))

# Adicionar um print para verificar os endpoints registrados após montar o Flet
print("Registered routes after mounting Flet:", app.routes)

# Create tables if they do not exist
Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    print("Starting Uvicorn server")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)