"""Faithfulness LLM-judge via Anthropic structured outputs — a pinned model +
fixed prompt + json_schema for deterministic-ish grading (see DECISIONS.md:
structured outputs for graders; no majority-of-N since sampling params are
unavailable)."""

import json
from typing import Any

from ..config import get_settings
from ..llm import get_client

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "grounded_fraction": {"type": "number"},
        "faithful": {"type": "boolean"},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["grounded_fraction", "faithful", "unsupported_claims"],
}


async def judge_faithfulness(
    question: str, context: str, answer: str, *, client: Any = None
) -> dict:
    cli = client or get_client()
    model = get_settings().chat_model
    prompt = (
        "You are a strict grader. Decide whether every factual claim in ANSWER is "
        "supported by CONTEXT (retrieved runbook excerpts). Judge grounding only, not "
        "fluency.\n\n"
        f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nANSWER:\n{answer}\n\n"
        "grounded_fraction = fraction of ANSWER's claims supported by CONTEXT (1.0 = "
        "fully grounded). faithful = grounded_fraction >= 0.9. List any unsupported_claims."
    )
    try:
        resp = await cli.messages.create(
            model=model,
            max_tokens=1024,
            thinking={"type": "disabled"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        txt = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
        )
        return json.loads(txt)
    except Exception as e:  # noqa: BLE001 — a judge failure shouldn't crash the suite
        return {
            "grounded_fraction": 0.0,
            "faithful": False,
            "unsupported_claims": [f"judge error: {e}"],
        }
