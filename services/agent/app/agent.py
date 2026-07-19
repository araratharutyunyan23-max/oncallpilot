"""Drive the agent graph and turn its execution into SSE events.

Emits: `sources` (retrieved), `step` (per-node trace), then either
`pending_action` (paused before human approval — client must POST /resume) or
`answer` (finished), and always a `usage` event (carrying conversation_id so the
edge guard can bill the run's cumulative cost as a per-thread delta — a paused
run's decide-turn cost is charged at the pause, resume charges only the
increment, and a re-driven completed run charges nothing). HITL uses a static
interrupt_before; `resume_agent` injects approvals and continues."""

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
        yield ("done", None)
        return

    snap = await graph.aget_state(config)
    vals = snap.values
    usage = {
        "conversation_id": cid,
        "cost_usd": round(vals.get("cost_usd", 0.0), 6),
        "tokens_in": vals.get("tokens_in", 0),
        "tokens_out": vals.get("tokens_out", 0),
    }
    if snap.next:  # paused before human_approval, awaiting operator decision
        yield ("pending_action", {"conversation_id": cid, **pending_payload(vals)})
    else:
        yield ("answer", {"text": vals.get("final_answer"), "sources": vals.get("sources", [])})
    yield ("usage", usage)  # both paths; billed as a per-thread delta (see charge_thread)
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
    snap = await graph.aget_state(config)
    if not snap.next:
        # not paused (already finished, or unknown/expired cid) — don't re-drive
        yield ("error", "no pending action to resume for this conversation")
        yield ("done", None)
        return
    await graph.aupdate_state(config, {"approvals": approvals})
    async for ev in _drive(graph, None, conversation_id):
        yield ev
