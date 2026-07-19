"""The agent graph: retrieve -> decide -> (respond | tool_exec | human_approval).

decide_action runs a manual Anthropic tool-use turn (Claude sees the 3 MCP tools
and the retrieved context); the GRAPH — not the model — decides whether a
destructive tool needs human approval, gating it with interrupt() BEFORE the
tool executes. tool_call_id doubles as the idempotency key so a replay/retry
never double-creates a ticket. Checkpointer is an in-process MemorySaver so the
interrupt survives across the /agent -> /resume HTTP boundary (single worker);
PostgresSaver is the documented durability upgrade (see DECISIONS.md)."""

import asyncio
import json
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from ..config import get_settings
from ..cost import Usage, cost_usd
from ..llm import get_client
from ..retrieval.retrieve import hybrid_search
from ..tools.mcp_client import call_tool, list_tool_defs
from ..tools.policy import is_destructive
from .state import AgentState

AGENT_SYSTEM = (
    "You are OncallPilot, an assistant for SRE / on-call engineers. You have "
    "runbook/ADR/postmortem context and these tools: get_ci_status and "
    "query_monitoring_alerts (read-only), and create_jira_ticket (destructive). "
    "When the user explicitly asks to file/create/open a ticket or incident, first "
    "gather the relevant facts with the read-only tools, then DO call "
    "create_jira_ticket — a human approves it before it actually runs, so proposing "
    "it is the correct action, not overstepping. For other questions, answer from the "
    "documents and tool results. Ground everything in the provided context. Be concise."
)


def _context_blocks(chunks: list[Any]) -> list[dict]:
    # plain document blocks (no citations here — the /rag endpoint owns cited answers)
    return [
        {
            "type": "document",
            "title": f"{c['title']} ({c['slug']})",
            "source": {"type": "content", "content": [{"type": "text", "text": c["raw_text"]}]},
        }
        for c in chunks
    ]


def _usage_update(model: str, u: Any, cache_ttl: str) -> dict:
    usage = Usage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )
    return {
        "cost_usd": cost_usd(model, usage, cache_ttl),
        "tokens_in": usage.input_tokens,
        "tokens_out": usage.output_tokens,
    }


def _preview(call: dict) -> str:
    a = call["input"]
    if call["name"] == "create_jira_ticket":
        return (
            f"Create {a.get('project_key')} {a.get('priority', 'P2')} "
            f"{a.get('issue_type', 'Incident')}: {a.get('summary', '')}"
        )
    return f"{call['name']}({json.dumps(a)[:120]})"


async def _retrieve(state: AgentState) -> dict:
    chunks, _ = await asyncio.to_thread(hybrid_search, state["query"])
    sources = [
        {
            "slug": c["slug"],
            "title": c["title"],
            "heading_path": c["heading_path"],
            "chunk_id": c["chunk_id"],
        }
        for c in chunks
    ]
    return {
        "doc_blocks": _context_blocks(chunks),
        "sources": sources,
        "trace": [{"node": "retrieve", "sources": [s["slug"] for s in sources]}],
    }


async def _decide(state: AgentState) -> dict:
    s = get_settings()
    tool_defs = await list_tool_defs()
    msgs = state.get("anthropic_messages") or []
    if not msgs:
        content = list(state["doc_blocks"]) + [
            {"type": "text", "text": f"Question: {state['query']}"}
        ]
        msgs = [{"role": "user", "content": content}]

    kwargs: dict[str, Any] = {
        "model": s.agent_model,
        "max_tokens": s.chat_max_tokens,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": s.agent_effort},
        "system": [
            {
                "type": "text",
                "text": AGENT_SYSTEM,
                "cache_control": {"type": "ephemeral", "ttl": s.cache_ttl},
            }
        ],
        "tools": tool_defs,
        "messages": msgs,
    }
    resp = await get_client().messages.create(**kwargs)
    new_msgs = msgs + [{"role": "assistant", "content": resp.content}]
    upd = _usage_update(s.agent_model, resp.usage, s.cache_ttl)
    step = state.get("step", 0) + 1

    tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
    text = "".join(
        getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
    )

    if not tool_uses or step >= s.max_agent_steps:
        return {
            "anthropic_messages": new_msgs,
            "final_answer": text or "(no answer produced)",
            "route": "respond",
            "step": step,
            "trace": [{"node": "decide", "action": "answer"}],
            **upd,
        }

    pending = [
        {"id": b.id, "name": b.name, "input": dict(b.input), "destructive": is_destructive(b.name)}
        for b in tool_uses
    ]
    return {
        "anthropic_messages": new_msgs,
        "pending_calls": pending,
        "step": step,
        "route": "approve" if any(p["destructive"] for p in pending) else "act",
        "trace": [{"node": "decide", "action": "tools", "calls": [p["name"] for p in pending]}],
        **upd,
    }


async def _tool_exec(state: AgentState) -> dict:
    approvals = state.get("approvals", {})
    results: list[dict] = []
    trace: list[dict] = []
    for call in state.get("pending_calls", []):
        if call["destructive"] and approvals.get(call["id"]) != "approved":
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": json.dumps({"status": "denied", "message": "operator denied"}),
                }
            )
            trace.append({"node": "tool_exec", "tool": call["name"], "result": "denied"})
            continue
        args = dict(call["input"])
        if call["name"] == "create_jira_ticket":
            args["idempotency_key"] = call["id"]  # tool_call_id == idempotency key
        try:
            out = await call_tool(call["name"], args)
        except Exception as e:  # noqa: BLE001 — surface tool failure back to the model
            out = json.dumps({"error": str(e)[:200]})
        results.append({"type": "tool_result", "tool_use_id": call["id"], "content": out})
        trace.append({"node": "tool_exec", "tool": call["name"], "result": "executed"})

    return {
        "anthropic_messages": state["anthropic_messages"] + [{"role": "user", "content": results}],
        "pending_calls": [],
        "approvals": {},
        "trace": trace,
    }


def pending_payload(values: dict) -> dict:
    """Build the pending-action payload from a paused graph's state (the
    destructive calls awaiting approval)."""
    destructive = [c for c in values.get("pending_calls", []) if c.get("destructive")]
    return {
        "pending_actions": [
            {"tool_call_id": c["id"], "name": c["name"], "args": c["input"], "preview": _preview(c)}
            for c in destructive
        ]
    }


async def _human_approval(state: AgentState) -> dict:
    # Pause point: the graph is compiled with interrupt_before=["human_approval"],
    # so execution stops BEFORE this node. The operator's approvals are injected
    # into state (via update_state) before the graph is resumed; this node only
    # records the trace. (Static interrupt is used because langgraph 1.2.9's
    # dynamic interrupt() fails to resolve the run config in async nodes.)
    return {"trace": [{"node": "human_approval", "decided": state.get("approvals", {})}]}


def _respond(state: AgentState) -> dict:
    return {"trace": [{"node": "respond"}]}


def _route_after_decide(state: AgentState) -> str:
    r = state.get("route")
    if r == "respond":
        return "respond"
    if r == "approve":
        return "human_approval"
    return "tool_exec"


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("retrieve", _retrieve)
    g.add_node("decide", _decide)
    g.add_node("tool_exec", _tool_exec)
    g.add_node("human_approval", _human_approval)
    g.add_node("respond", _respond)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "decide")
    g.add_conditional_edges(
        "decide", _route_after_decide, ["respond", "tool_exec", "human_approval"]
    )
    g.add_edge("human_approval", "tool_exec")
    g.add_edge("tool_exec", "decide")
    g.add_edge("respond", END)
    # static interrupt: pause BEFORE human_approval (reached only for destructive
    # actions via routing) — see _human_approval for why not dynamic interrupt().
    return g.compile(checkpointer=MemorySaver(), interrupt_before=["human_approval"])


_graph = None


def get_graph():
    """Compiled graph singleton — its MemorySaver must persist across /agent and
    /resume requests (single uvicorn worker)."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
