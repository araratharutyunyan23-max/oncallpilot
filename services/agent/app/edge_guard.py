"""Edge guard: per-key token-bucket rate limit + a global daily spend cap.

This is *operational safety* for a public, unauthenticated demo endpoint that
spends real money on Claude — not product auth. It is the P0 seed of the abuse/
spend-protection contour the plan maps to OWASP LLM04/LLM10.

P0 is single-process, so in-memory counters are sufficient. This is NOT
multi-worker safe (each uvicorn worker keeps its own counters). A shared store
(Redis) is the documented P4 upgrade.
"""

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from .config import Settings, get_settings


@dataclass
class _Bucket:
    tokens: float
    last: float


class EdgeGuard:
    def __init__(self, settings: Settings):
        self._s = settings
        self._rate_per_sec = settings.rate_limit_per_min / 60.0
        self._capacity = float(settings.rate_limit_burst)
        self._buckets: dict[str, _Bucket] = {}
        self._spend_usd = 0.0
        self._spend_day = self._today()
        self._thread_charged: dict[str, float] = {}  # cid -> cumulative $ already charged
        self._lock = threading.Lock()

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _roll_day(self) -> None:
        today = self._today()
        if today != self._spend_day:
            self._spend_day = today
            self._spend_usd = 0.0

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = _Bucket(tokens=self._capacity, last=now)
                self._buckets[key] = b
            b.tokens = min(self._capacity, b.tokens + (now - b.last) * self._rate_per_sec)
            b.last = now
            if b.tokens >= 1.0:
                b.tokens -= 1.0
                return True
            return False

    def spend_remaining(self) -> float:
        with self._lock:
            self._roll_day()
            return max(0.0, self._s.daily_spend_cap_usd - self._spend_usd)

    def spend_ok(self) -> bool:
        return self.spend_remaining() > 0.0

    def add_spend(self, usd: float) -> None:
        with self._lock:
            self._roll_day()
            self._spend_usd += max(0.0, usd)

    def charge_thread(self, cid: str, cumulative_usd: float) -> float:
        """Charge a conversation's *cumulative* cost, billing only the increment
        since it was last charged. Idempotent per (cid, total): a paused run
        charges its decide-turn cost, resume charges only the delta, and a
        re-driven completed run charges nothing. Returns the delta billed."""
        with self._lock:
            self._roll_day()
            prev = self._thread_charged.get(cid, 0.0)
            delta = max(0.0, cumulative_usd - prev)
            self._thread_charged[cid] = max(prev, cumulative_usd)
            self._spend_usd += delta
            return delta

    def spent_today(self) -> float:
        with self._lock:
            self._roll_day()
            return self._spend_usd


_guard: EdgeGuard | None = None


def get_guard() -> EdgeGuard:
    global _guard
    if _guard is None:
        _guard = EdgeGuard(get_settings())
    return _guard


def enforce_edge(request: Request) -> None:
    """FastAPI dependency: demo-key gate → rate limit → daily spend cap."""
    s = get_settings()
    guard = get_guard()

    if s.demo_api_key:
        if request.headers.get("x-demo-key") != s.demo_api_key:
            raise HTTPException(status_code=401, detail="invalid or missing x-demo-key")

    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{request.headers.get('x-demo-key', '-')}"
    if not guard.allow(key):
        raise HTTPException(status_code=429, detail="rate limit exceeded, slow down")

    if not guard.spend_ok():
        raise HTTPException(status_code=429, detail="demo daily budget reached")
