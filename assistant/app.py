"""E5-05: usługa HTTP asystenta (FastAPI).

    uvicorn app:app --app-dir assistant --port 8000
    http://localhost:8000/ask?q=dlaczego%20linia%20stanęła%20o%2010:23
    http://localhost:8000/docs                       (Swagger – formularz do testów)

Model embeddingów i połączenie z bazą ładujemy raz przy starcie, nie przy każdym pytaniu (ok. 3 s i 470 MB).
"""
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException

from kb import Embedder, connect
from llm import LLMUnavailable
from rag import answer

state = {}


@asynccontextmanager
async def lifespan(app):
    state["emb"], state["conn"] = Embedder(), connect()
    yield
    state["conn"].close()


app = FastAPI(title="LineSight – asystent postojów", lifespan=lifespan)


@app.get("/ask")
def ask(q: str, stop: Optional[datetime] = None, backend: Optional[str] = None):
    """q – pytanie; stop – t_start postoju (ISO, z linku w Grafanie); backend – ollama | gemini."""
    if backend not in (None, "ollama", "gemini"):
        raise HTTPException(400, "backend: ollama | gemini")
    try:
        return answer(state["conn"], state["emb"], q, stop_t=stop, backend=backend)
    except LLMUnavailable as e:
        raise HTTPException(503, str(e))


@app.get("/health")
def health():
    return {"ok": state["conn"].execute("SELECT 1").fetchone()[0] == 1}
