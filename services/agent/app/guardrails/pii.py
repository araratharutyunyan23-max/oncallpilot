"""Regex PII / secret redaction. Microsoft Presidio (NER-based) is the documented
upgrade; this covers the high-value structured cases that a runbook assistant is
most likely to touch: API keys, tokens, JWTs, emails, IPs.

`SECRET_TYPES` (api_key, jwt) are the leak-critical set used to scrub the model's
OUTPUT; the full set is used where broader redaction is wanted (e.g. logs)."""

import re

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("api_key", re.compile(r"\b(?:sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9\-]{10,}|AKIA[0-9A-Z]{16})\b")),  # noqa: E501
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("ipv4", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")),
]

SECRET_TYPES = {"api_key", "jwt"}  # leak-critical: always scrubbed from model output


def redact(text: str, types: set[str] | None = None) -> tuple[str, list[str]]:
    """Redact PII/secrets. `types` restricts which categories (default: all).
    Returns (redacted_text, sorted list of categories found)."""
    out = text
    found_set: set[str] = set()
    for name, rx in _PATTERNS:
        if types is not None and name not in types:
            continue
        out, n = rx.subn(f"[REDACTED_{name.upper()}]", out)
        if n:
            found_set.add(name)
    return out, sorted(found_set)


def scrub_output(text: str) -> tuple[str, list[str]]:
    """Scrub leak-critical secrets from model output (never suppress the answer,
    just redact the secret)."""
    return redact(text, types=SECRET_TYPES)
