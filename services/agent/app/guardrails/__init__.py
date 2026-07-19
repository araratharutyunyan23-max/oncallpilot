"""Guardrails (Phase 4): input prompt-injection screening, PII/secret redaction,
datamarking of untrusted content (retrieved docs + tool output), and output leak
scanning. First cut uses heuristics + regex; a haiku jailbreak classifier and
Microsoft Presidio are the documented upgrades (see DECISIONS.md OWASP mapping).
The structural defenses (HITL gate, document-block separation) are code-enforced
and do NOT depend on these classifiers."""
