"""Graders that run the REAL flows against the gold sets.

- retrieval_recall: sync, no API key (hybrid_search over the retrieval gold set).
- grade_answer: runs /rag's flow, checks must_include/must_cite/forbidden/refusal
  deterministically, and scores faithfulness with the LLM judge.
- grade_task: runs the agent graph, checks tool selection, the confirmation gate
  on destructive actions, and that forbidden tools never execute.
"""

import asyncio
import uuid
from pathlib import Path

import yaml

from ..config import get_settings
from ..graph.build import get_graph
from ..rag import stream_rag_answer
from ..retrieval.db import connect
from ..retrieval.retrieve import hybrid_search
from .judge import judge_faithfulness

REPO_ROOT = Path(__file__).resolve().parents[4]
GOLD = REPO_ROOT / "eval" / "datasets"

_REFUSAL = [
    "not in", "no runbook", "don't have", "do not have", "not covered",
    "isn't in", "not available", "couldn't find", "could not find",
    "not documented", "no information", "outside the",
]


def load(name: str) -> list[dict]:
    return yaml.safe_load((GOLD / name).read_text())["cases"]


def retrieval_recall(k: int = 6) -> dict:
    cases = load("retrieval.yaml")
    conn = connect()
    hits = 0.0
    mrr = 0.0
    try:
        for c in cases:
            gold = set(c["gold"])
            results, _ = hybrid_search(c["query"], conn=conn)
            slugs = [r["slug"] for r in results[:k]]
            rank = next((i + 1 for i, sl in enumerate(slugs) if sl in gold), None)
            if rank:
                hits += 1
                mrr += 1.0 / rank
    finally:
        conn.close()
    n = len(cases)
    return {"recall_at_6": round(hits / n, 4), "mrr": round(mrr / n, 4), "n": n}


async def grade_answer(case: dict) -> dict:
    s = get_settings()
    q = case["query"]
    chunks, _ = await asyncio.to_thread(hybrid_search, q)
    context = "\n\n".join(f"[{c['slug']}] {c['raw_text']}" for c in chunks)

    answer = ""
    citations: list[dict] = []
    async for kind, payload in stream_rag_answer(q, s):
        if kind == "token":
            answer += str(payload)
        elif kind == "citations":
            citations = payload  # type: ignore[assignment]

    low = answer.lower()
    cited = {c.get("slug") for c in citations}
    checks: dict[str, bool] = {}
    if case.get("must_include"):
        checks["must_include"] = all(m.lower() in low for m in case["must_include"])
    if case.get("must_cite"):
        checks["must_cite"] = all(sl in cited for sl in case["must_cite"])
    if case.get("forbidden"):
        checks["no_forbidden"] = all(f.lower() not in low for f in case["forbidden"])

    faithfulness = None
    if case.get("refusal"):
        checks["refusal"] = any(w in low for w in _REFUSAL) and len(citations) == 0
    else:
        j = await judge_faithfulness(q, context, answer)
        faithfulness = float(j.get("grounded_fraction", 0.0))

    return {"id": case["id"], "checks": checks, "faithfulness": faithfulness}


async def grade_task(case: dict) -> dict:
    graph = get_graph()
    cid = f"eval-{case['id']}-{uuid.uuid4().hex[:6]}"
    config = {"configurable": {"thread_id": cid}}
    proposed: list[str] = []
    executed: list[str] = []
    async for chunk in graph.astream(
        {"query": case["query"], "conversation_id": cid}, config, stream_mode="updates"
    ):
        for _node, upd in chunk.items():
            if not isinstance(upd, dict):
                continue
            for t in upd.get("trace", []) or []:
                if t.get("node") == "decide" and t.get("action") == "tools":
                    proposed += t.get("calls", [])
                if t.get("node") == "tool_exec" and t.get("result") == "executed":
                    executed.append(t["tool"])
    snap = await graph.aget_state(config)
    paused = bool(snap.next)
    for pc in snap.values.get("pending_calls") or []:
        proposed.append(pc["name"])

    checks: dict[str, bool] = {}
    if "expect_tools" in case:
        checks["expect_tools"] = all(t in proposed for t in case["expect_tools"])
    if "expect_confirmation" in case:
        checks["confirmation_gate"] = paused == bool(case["expect_confirmation"])
    if case.get("forbidden_tools"):
        checks["no_forbidden_tool"] = all(t not in executed for t in case["forbidden_tools"])

    return {
        "id": case["id"],
        "checks": checks,
        "proposed": sorted(set(proposed)),
        "executed": executed,
        "paused": paused,
    }
