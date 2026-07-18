"""FastAPI entrypoint — Phase 0.

Endpoints:
  GET  /healthz  liveness (always 200 while the process is up)
  GET  /readyz   readiness — 503 until ANTHROPIC_API_KEY is configured
  POST /chat     one streamed Claude completion over SSE (edge-guarded)
"""

import json
import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .config import get_settings
from .edge_guard import enforce_edge, get_guard
from .llm import stream_chat
from .rag import stream_rag_answer

_settings = get_settings()
logging.basicConfig(level=_settings.log_level)
log = logging.getLogger("oncallpilot")

app = FastAPI(title="OncallPilot Agent", version="0.0.1-p0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz", response_model=None)
async def readyz() -> JSONResponse | dict[str, str]:
    s = get_settings()
    missing = [] if s.anthropic_api_key else ["ANTHROPIC_API_KEY"]
    if missing:
        return JSONResponse({"status": "not_ready", "missing": missing}, status_code=503)
    return {"status": "ready"}


@app.post("/chat")
async def chat(req: ChatRequest, request: Request, _: None = Depends(enforce_edge)):
    s = get_settings()
    if not s.anthropic_api_key:
        return JSONResponse({"error": "ANTHROPIC_API_KEY not configured"}, status_code=503)
    guard = get_guard()

    async def event_gen():
        try:
            async for kind, payload in stream_chat(req.query, s):
                if kind == "token":
                    yield {"event": "token", "data": json.dumps({"text": payload})}
                elif kind == "usage":
                    guard.add_spend(float(payload.get("cost_usd", 0.0)))  # type: ignore[union-attr]
                    yield {"event": "usage", "data": json.dumps(payload)}
                elif kind == "error":
                    yield {"event": "error", "data": json.dumps({"message": payload})}
                elif kind == "done":
                    yield {"event": "done", "data": "{}"}
        except Exception:  # noqa: BLE001 — surface as SSE error, never 500 mid-stream
            log.exception("chat stream crashed")
            yield {"event": "error", "data": json.dumps({"message": "internal error"})}

    return EventSourceResponse(event_gen())


@app.post("/rag")
async def rag(req: ChatRequest, request: Request, _: None = Depends(enforce_edge)):
    """RAG: retrieve from the corpus, answer grounded in it with native citations."""
    s = get_settings()
    if not s.anthropic_api_key:
        return JSONResponse({"error": "ANTHROPIC_API_KEY not configured"}, status_code=503)
    guard = get_guard()

    async def event_gen():
        try:
            async for kind, payload in stream_rag_answer(req.query, s):
                if kind == "token":
                    yield {"event": "token", "data": json.dumps({"text": payload})}
                elif kind == "sources":
                    yield {"event": "sources", "data": json.dumps(payload)}
                elif kind == "citations":
                    yield {"event": "citations", "data": json.dumps(payload)}
                elif kind == "usage":
                    guard.add_spend(float(payload.get("cost_usd", 0.0)))  # type: ignore[union-attr]
                    yield {"event": "usage", "data": json.dumps(payload)}
                elif kind == "error":
                    yield {"event": "error", "data": json.dumps({"message": payload})}
                elif kind == "done":
                    yield {"event": "done", "data": "{}"}
        except Exception:  # noqa: BLE001 — surface as SSE error, never 500 mid-stream
            log.exception("rag stream crashed")
            yield {"event": "error", "data": json.dumps({"message": "internal error"})}

    return EventSourceResponse(event_gen())
