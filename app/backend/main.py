import os
import ollama
from pydantic import BaseModel
from fastapi import HTTPException
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import flet as ft
import logging
from .utils import manager
from .db.database import engine
from .db.models import Base
from .routes import auth, samples, quality_analysis, trimmagem, quality_analysis_post_trim, alignment, quantification, contrasts, preprocess, deg, results, upload

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("Creating FastAPI app")

app = FastAPI()


ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ollama_client = None

try:
    ollama_client = ollama.Client(host=ollama_host)
    print(f"A tentar conectar ao Ollama em {ollama_host}...")

    ollama_client.list()
    print(f"Conexão com Ollama em {ollama_host} bem-sucedida.")
except Exception as e:
    print(f"Erro ao conectar com Ollama em {ollama_host}: {e}")
    print("Ollama não estará disponível. Verifique se o serviço está a correr.")

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
app.include_router(trimmagem.router, tags=["trimmagem"])
app.include_router(quality_analysis_post_trim.router, tags=["quality_analysis_post_trim"])
app.include_router(alignment.router, tags=["alignment"])
app.include_router(quantification.router, tags=["quantification"])
app.include_router(contrasts.router, tags=["contrasts"])
app.include_router(preprocess.router, tags=["preprocess"])
app.include_router(deg.router, tags=["deg"])
app.include_router(results.router, tags=["results"])
app.include_router(upload.router, tags=["upload"])
from .routes import clustering as clustering_route
app.include_router(clustering_route.router, tags=["clustering"])


class ChatRequest(BaseModel):
    message: str
    model: str = 'gwen3:0.6b'


SYSTEM_PROMPT = """
Você é o 'Bilbo-AI', o assistente inteligente integrado na plataforma de bioinformática 'Bilbo'.
A sua persona é a de um Professor Sénior de Bioinformática e Microbiologia: paciente, extremamente técnico, mas com uma didática impecável.

**CONTEXTO DA APLICAÇÃO BILBO:**
Você opera dentro de um pipeline de RNA-Seq automatizado. Você DEVE saber que o Bilbo utiliza as seguintes ferramentas padrão:
1.  **Obtenção de Dados:** SRA Toolkit (fastq-dump) para baixar amostras do NCBI.
2.  **Controle de Qualidade (QC):** FastQC para análise inicial.
3.  **Trimmagem:** Trimmomatic para remover adaptadores e bases de baixa qualidade.
4.  **Alinhamento:** STAR (Spliced Transcripts Alignment to a Reference) para alinhar reads ao genoma.
5.  **Quantificação:** featureCounts (Subread) para contagem de genes.
6.  **Expressão Diferencial:** R (Bioconductor) usando DESeq2 e edgeR.
7.  **Visualização:** Heatmaps (ComplexHeatmap), Volcano Plots e Diagramas de Venn.

**SUA MISSÃO:**
1.  **Microbiologia e Molécula:** Explique fenómenos biológicos (ex: transcrição, regulação génica em bactérias/eucariotos) quando o utilizador tiver dúvidas teóricas.
2.  **Suporte Técnico:** Ajude a interpretar erros comuns dessas ferramentas específicas (ex: "Exit code 137 no STAR" geralmente é falta de RAM).
3.  **Interpretação de Resultados:** Ajude o utilizador a entender o que significa um "Phred Score" baixo ou um "P-value ajustado" (FDR).

**REGRAS DE RESPOSTA:**
* **Idioma:** Sempre em Português do Brasil.
* **Didática:** Explique o "Porquê" antes do "Como". Use analogias do mundo real para explicar conceitos abstratos de bioinformática.
* **Formatação:** Use Markdown agressivamente. Destaque **ferramentas** e `comandos` ou `código`. Use listas para passo-a-passo.
* **Código:** Se o utilizador pedir scripts, dê preferência a Python (para automação) ou R (para estatística), alinhado com a stack do Bilbo.
* **Proatividade:** Se o utilizador perguntar "Como faço alinhamento?", não explique apenas o conceito; explique como o STAR funciona e por que ele é bom para RNA-Seq.
"""


@app.post("/chat", tags=["ollama"])
async def handle_chat(request: ChatRequest):
    if ollama_client is None:
        logger.error("Tentativa de chat, mas o cliente Ollama não está inicializado.")
        raise HTTPException(status_code=503, detail="Serviço Ollama não está disponível.")

    try:
        print(f"A enviar para o Ollama (modelo {request.model}): {request.message}")
        messages_list = [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': request.message}
        ]

        response = ollama_client.chat(
            model=request.model,
            messages=messages_list
        )

        # 5. Retornar a resposta
        print("Resposta recebida do Ollama.")
        return response['message']

    except Exception as e:
        logger.error(f"Erro ao comunicar com Ollama: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao processar pedido: {e}")

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

flet_asgi_app = ft.app(main.main, export_asgi_app=True, assets_dir="assets")
app.mount("/frontend", flet_asgi_app)

print("Registered routes after mounting Flet:", app.routes)

Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    print("Starting Uvicorn server")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
