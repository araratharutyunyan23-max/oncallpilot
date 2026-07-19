"""Observability (Phase 4): per-request telemetry (cost / latency / tokens /
tools / model). First cut is an in-process ring buffer; OTel -> Langfuse export
is the documented durability/tracing upgrade (see DECISIONS.md)."""
