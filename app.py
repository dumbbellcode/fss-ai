#!/usr/bin/env python3
"""FastAPI chat service over the FSSAI retrieval index.

Runs the :mod:`retrieval.chat` abstraction behind a tiny HTTP API and serves a
static chat page. Configure with environment variables:

- ``OPENROUTER_API_KEY`` — required for embeddings and answer generation.
- ``QDRANT_URL``, ``QDRANT_API_KEY`` — Qdrant Cloud credentials (required).
- ``QDRANT_COLLECTION`` — Qdrant collection name (default ``fssai_regulations``).
- ``EMBEDDING_MODEL`` — embedding model id (default: ``openai/text-embedding-3-large``).
- ``CHAT_MODEL`` — chat model id (default: ``deepseek/deepseek-v4-flash``).
- ``MAX_HISTORY`` — conversation turns kept in context (default: 10).

Local dev:

    uv run uvicorn app:app --reload

Cloud Run (one command after the Dockerfile is built):

    gcloud run deploy fssai-chat --source . \
      --set-env-vars OPENROUTER_API_KEY=...,QDRANT_URL=...,QDRANT_API_KEY=...
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ingestion.config import DEFAULT_CONFIG as DEFAULT_INGESTION_CONFIG
from retrieval.chat import ChatConfig, ChatSession

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="FSSAI RAG Chat")

# Backend: "chroma" (local dev store) or "qdrant" (hosted chat product).
_backend = os.environ.get("RETRIEVAL_BACKEND", "chroma")
if _backend == "qdrant":
    _chat_kwargs: dict = dict(
        collection_name=os.environ.get("QDRANT_COLLECTION", DEFAULT_INGESTION_CONFIG.collection_name),
        backend="qdrant",
        qdrant_url=os.environ["QDRANT_URL"],
        qdrant_api_key=os.environ["QDRANT_API_KEY"],
    )
else:
    _chat_kwargs = dict(
        collection_name=os.environ.get("COLLECTION", DEFAULT_INGESTION_CONFIG.collection_name),
        persist_dir=os.environ.get("PERSIST_DIR", DEFAULT_INGESTION_CONFIG.persist_dir),
        backend="chroma",
    )

_session = ChatSession(
    chat_config=ChatConfig(
        model=os.environ.get("CHAT_MODEL", "deepseek/deepseek-v4-flash"),
        max_history_messages=int(os.environ.get("MAX_HISTORY", "10")),
    ),
    embedding_model=os.environ.get("EMBEDDING_MODEL"),
    **_chat_kwargs,
)

# Repeat-question cache: identical questions skip retrieval + LLM, making common
# repeats near-instant and free. In-memory only (per instance).
_cache: dict[str, dict] = {}


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="message must not be empty")

    cache_key = message.lower()
    cached = _cache.get(cache_key)
    if cached is not None:
        return ChatResponse(**cached)

    try:
        answer = _session.respond(message)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    response = ChatResponse(
        answer=answer,
        sources=[chunk.metadata for chunk in _session.last_chunks],
    )
    _cache[cache_key] = response.model_dump()
    return response


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


# Static files are mounted last so they never shadow API routes.
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")