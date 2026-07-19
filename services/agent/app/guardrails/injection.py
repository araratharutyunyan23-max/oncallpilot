"""Prompt-injection screening + datamarking.

`classify` is a cheap, deterministic first line against obvious jailbreak /
override attempts (a haiku classifier is the upgrade). It is defense-in-depth,
NOT the primary control: the human-in-the-loop gate and document-block channel
separation are structural and hold even if this misses. `datamark` wraps
untrusted content (retrieved docs, tool output) so the model treats it as data,
not instructions."""

import re

_PATTERNS = [
    r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?|rules)",
    r"disregard\s+(the|your|all|any)\s+(above|previous|prior|system|earlier)",
    r"forget\s+(everything|all|your)\s+(above|previous|instructions)",
    r"reveal\s+(your|the)\s+(system\s+prompt|instructions|prompt)",
    r"(print|show|repeat)\s+(your|the)\s+(system\s+prompt|instructions)",
    r"you\s+are\s+now\s+(a|an|DAN|in\s+developer)",
    r"\bdeveloper\s+mode\b",
    r"override\s+(your|the|all)\s+(instructions|rules|guardrails|safety)",
    r"\bDAN\b.*\b(mode|prompt)\b",
]
_RE = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def classify(text: str) -> tuple[bool, str]:
    """(blocked, reason). blocked=True on an obvious injection/override attempt."""
    for rx in _RE:
        m = rx.search(text)
        if m:
            return True, f"injection pattern: {m.group(0)[:60].strip()}"
    return False, ""


def datamark(text: str, kind: str = "tool_output") -> str:
    return f"<untrusted_{kind}>\n{text}\n</untrusted_{kind}>"
