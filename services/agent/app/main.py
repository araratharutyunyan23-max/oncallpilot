"""FastAPI entrypoint — Phase 0.

Endpoints:
  GET  /healthz  liveness (always 200 while the process is up)
  GET  /readyz   readiness — 503 until ANTHROPIC_API_KEY is configured
  POST /chat     one streamed Claude completion over SSE (edge-guarded)
"""

import json
import logging
import uuid

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .agent import resume_agent, run_agent
from .config import get_settings
from .edge_guard import enforce_edge, get_guard
from .guardrails import injection
from .llm import stream_chat
from .obs.recorder import Telemetry, get_recorder
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


class ResumeRequest(BaseModel):
    approvals: dict[str, str] = Field(default_factory=dict)  # {tool_call_id: "approved"|"denied"}


_BLOCKED_TEXT = "Blocked by the input guardrail — possible prompt injection. Please rephrase."


def _blocked_frames(reason: str):
    step = json.dumps({"node": "input_guard", "result": "blocked", "reason": reason})
    answer = json.dumps({"text": _BLOCKED_TEXT, "sources": []})
    yield {"event": "step", "data": step}
    yield {"event": "answer", "data": answer}


def _agent_sse(kind: str, payload: object, guard) -> dict:
    if kind == "usage" and isinstance(payload, dict):
        cid = payload.get("conversation_id")
        if cid:  # bill the run's cumulative cost as a per-thread delta (pause/resume safe)
            guard.charge_thread(str(cid), float(payload.get("cost_usd", 0.0)))
        else:
            guard.add_spend(float(payload.get("cost_usd", 0.0)))
    if kind == "error":
        data = json.dumps({"message": payload})
    elif kind == "done":
        data = "{}"
    else:
        data = json.dumps(payload)
    return {"event": kind, "data": data}


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
async def chat(req: ChatRequest, _: None = Depends(enforce_edge)):
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
async def rag(req: ChatRequest, _: None = Depends(enforce_edge)):
    """RAG: retrieve from the corpus, answer grounded in it with native citations."""
    s = get_settings()
    if not s.anthropic_api_key:
        return JSONResponse({"error": "ANTHROPIC_API_KEY not configured"}, status_code=503)
    guard = get_guard()
    tel = Telemetry("rag")

    async def event_gen():
        blocked, reason = injection.classify(req.query)
        if blocked:
            for frame in _blocked_frames(reason):
                yield frame
            tel.finalize()
            yield {"event": "done", "data": "{}"}
            return
        try:
            async for kind, payload in stream_rag_answer(req.query, s):
                tel.observe(kind, payload)
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
            tel.ok = False
            log.exception("rag stream crashed")
            yield {"event": "error", "data": json.dumps({"message": "internal error"})}
        finally:
            tel.finalize()

    return EventSourceResponse(event_gen())


@app.post("/agent")
async def agent(req: ChatRequest, _: None = Depends(enforce_edge)):
    """Agentic flow: retrieve -> decide -> act (MCP tools), pausing for human
    approval before any destructive action. Returns a conversation_id to /resume."""
    s = get_settings()
    if not s.anthropic_api_key:
        return JSONResponse({"error": "ANTHROPIC_API_KEY not configured"}, status_code=503)
    guard = get_guard()
    # always a fresh conversation for a new run — a client-supplied id would let
    # a new /agent call collide with (or resume) an existing thread's state.
    cid = f"conv-{uuid.uuid4().hex[:12]}"
    tel = Telemetry("agent")

    async def event_gen():
        yield {"event": "meta", "data": json.dumps({"conversation_id": cid})}
        blocked, reason = injection.classify(req.query)
        if blocked:
            for frame in _blocked_frames(reason):
                yield frame
            tel.finalize()
            yield {"event": "done", "data": "{}"}
            return
        try:
            async for kind, payload in run_agent(req.query, cid):
                tel.observe(kind, payload)
                yield _agent_sse(kind, payload, guard)
        except Exception:  # noqa: BLE001
            tel.ok = False
            log.exception("agent endpoint crashed")
            yield {"event": "error", "data": json.dumps({"message": "internal error"})}
        finally:
            tel.finalize()

    return EventSourceResponse(event_gen())


@app.post("/agent/{conversation_id}/resume")
async def agent_resume(
    conversation_id: str, req: ResumeRequest, _: None = Depends(enforce_edge)
):
    """Resume a paused agent run with the operator's approve/deny decisions."""
    s = get_settings()
    if not s.anthropic_api_key:
        return JSONResponse({"error": "ANTHROPIC_API_KEY not configured"}, status_code=503)
    guard = get_guard()
    tel = Telemetry("resume")

    async def event_gen():
        try:
            async for kind, payload in resume_agent(conversation_id, req.approvals):
                tel.observe(kind, payload)
                yield _agent_sse(kind, payload, guard)
        except Exception:  # noqa: BLE001
            tel.ok = False
            log.exception("agent resume crashed")
            yield {"event": "error", "data": json.dumps({"message": "internal error"})}
        finally:
            tel.finalize()

    return EventSourceResponse(event_gen())


@app.get("/api/metrics/summary")
async def metrics_summary() -> dict:
    return get_recorder().summary()


@app.get("/api/metrics/recent")
async def metrics_recent(limit: int = 50) -> list[dict]:
    return get_recorder().recent(min(max(1, limit), 200))
