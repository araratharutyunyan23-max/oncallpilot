"""Drive the agent graph and turn its execution into SSE events.

Emits: `sources` (retrieved), `step` (per-node trace), then either
`pending_action` (graph paused before human approval — client must POST /resume)
or `answer` + `usage` (graph finished). HITL uses a static interrupt_before on
the human_approval node; `resume_agent` injects the operator's approvals into
state and continues."""

import logging
from collections.abc import AsyncIterator

from .graph.build import get_graph, pending_payload

log = logging.getLogger("oncallpilot.agent")


async def _drive(graph, inp, cid: str) -> AsyncIterator[tuple[str, object]]:
    config = {"configurable": {"thread_id": cid}}
    try:
        async for chunk in graph.astream(inp, config, stream_mode="updates"):
            for node, update in chunk.items():
                if node == "__interrupt__" or not isinstance(update, dict):
                    continue
                if update.get("sources"):
                    yield ("sources", update["sources"])
                for t in update.get("trace", []) or []:
                    yield ("step", t)
    except Exception:  # noqa: BLE001 — surface as SSE error, never 500 mid-stream
        log.exception("agent graph crashed")
        yield ("error", "internal error")
        return

    snap = await graph.aget_state(config)
    if snap.next:  # paused before human_approval, awaiting operator decision
        yield ("pending_action", {"conversation_id": cid, **pending_payload(snap.values)})
    else:
        vals = snap.values
        yield ("answer", {"text": vals.get("final_answer"), "sources": vals.get("sources", [])})
        yield (
            "usage",
            {
                "cost_usd": round(vals.get("cost_usd", 0.0), 6),
                "tokens_in": vals.get("tokens_in", 0),
                "tokens_out": vals.get("tokens_out", 0),
            },
        )
    yield ("done", None)


async def run_agent(query: str, conversation_id: str) -> AsyncIterator[tuple[str, object]]:
    graph = get_graph()
    inp = {"query": query, "conversation_id": conversation_id}
    async for ev in _drive(graph, inp, conversation_id):
        yield ev


async def resume_agent(
    conversation_id: str, approvals: dict
) -> AsyncIterator[tuple[str, object]]:
    graph = get_graph()
    config = {"configurable": {"thread_id": conversation_id}}
    # inject the operator's decision, then continue the paused run (input=None)
    await graph.aupdate_state(config, {"approvals": approvals})
    async for ev in _drive(graph, None, conversation_id):
        yield ev
