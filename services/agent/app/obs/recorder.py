"""In-process per-request telemetry: a ring buffer of RequestTrace + a summary
(count, total/avg cost, p50/p95 latency, cache-hit rate, model mix, tool calls,
error rate). `Telemetry` accumulates from the SSE event stream so the endpoints
stay thin. Not durable across restarts/workers — OTel -> Langfuse is the upgrade."""

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field


@dataclass
class RequestTrace:
    ts: float
    endpoint: str  # "rag" | "agent" | "resume"
    model: str
    tokens_in: int
    tokens_out: int
    cache_read: int
    cost_usd: float
    latency_ms: int
    tools: list = field(default_factory=list)
    paused: bool = False
    ok: bool = True


def _pct(values: list[float], p: int) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((p / 100) * (len(s) - 1)))
    return s[k]


class Recorder:
    def __init__(self, maxlen: int = 500) -> None:
        self._buf: deque[RequestTrace] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def record(self, t: RequestTrace) -> None:
        with self._lock:
            self._buf.append(t)

    def recent(self, n: int = 50) -> list[dict]:
        with self._lock:
            items = list(self._buf)
        return [asdict(t) for t in items[-n:][::-1]]

    def summary(self) -> dict:
        with self._lock:
            items = list(self._buf)
        if not items:
            return {"count": 0}
        costs = [t.cost_usd for t in items]
        lats = [float(t.latency_ms) for t in items]
        models: dict[str, int] = {}
        tool_calls = 0
        cache_hits = 0
        errors = 0
        for t in items:
            models[t.model] = models.get(t.model, 0) + 1
            tool_calls += len(t.tools)
            if t.cache_read > 0:
                cache_hits += 1
            if not t.ok:
                errors += 1
        n = len(items)
        return {
            "count": n,
            "total_cost_usd": round(sum(costs), 6),
            "avg_cost_usd": round(sum(costs) / n, 6),
            "p50_latency_ms": round(_pct(lats, 50)),
            "p95_latency_ms": round(_pct(lats, 95)),
            "tokens_in": sum(t.tokens_in for t in items),
            "tokens_out": sum(t.tokens_out for t in items),
            "tool_calls": tool_calls,
            "cache_hit_rate": round(cache_hits / n, 3),
            "error_rate": round(errors / n, 3),
            "models": models,
        }


_recorder: Recorder | None = None


def get_recorder() -> Recorder:
    global _recorder
    if _recorder is None:
        _recorder = Recorder()
    return _recorder


class Telemetry:
    """Accumulate one request's telemetry from its (kind, payload) SSE events,
    then `finalize()` records a RequestTrace. Use one per request."""

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self._start = time.monotonic()
        self.model = ""
        self.tokens_in = 0
        self.tokens_out = 0
        self.cache_read = 0
        self.cost_usd = 0.0
        self.tools: list[str] = []
        self.paused = False
        self.ok = True

    def observe(self, kind: str, payload: object) -> None:
        if kind == "usage" and isinstance(payload, dict):
            self.model = str(payload.get("model", self.model))
            self.tokens_in = int(payload.get("tokens_in", 0))
            self.tokens_out = int(payload.get("tokens_out", 0))
            self.cache_read = int(payload.get("cache_read", 0))
            self.cost_usd = float(payload.get("cost_usd", 0.0))
        elif kind == "step" and isinstance(payload, dict) and payload.get("node") == "tool_exec":
            if payload.get("tool"):
                self.tools.append(str(payload["tool"]))
        elif kind == "pending_action":
            self.paused = True
        elif kind == "error":
            self.ok = False

    def finalize(self) -> None:
        get_recorder().record(
            RequestTrace(
                ts=time.time(),
                endpoint=self.endpoint,
                model=self.model or "-",
                tokens_in=self.tokens_in,
                tokens_out=self.tokens_out,
                cache_read=self.cache_read,
                cost_usd=round(self.cost_usd, 6),
                latency_ms=round((time.monotonic() - self._start) * 1000),
                tools=self.tools,
                paused=self.paused,
                ok=self.ok,
            )
        )
