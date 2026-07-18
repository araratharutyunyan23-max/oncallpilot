"""Retry/backoff primitives for Claude calls.

Claude calls are wrapped in exponential backoff with jitter on 429 / 529
(overloaded) / connection errors. For streaming, retries are only safe *before
the first token* — a partial stream cannot be replayed; that gating lives in
llm.py, this module just supplies the classification and the sleep.
"""

import asyncio
import random

import anthropic

RETRYABLE = (
    anthropic.RateLimitError,  # 429
    anthropic.InternalServerError,  # 5xx incl. 529 overloaded
    anthropic.APIConnectionError,  # network failure before a response
)


async def backoff_sleep(attempt: int, base: float = 0.5, cap: float = 30.0) -> None:
    """Sleep for exponential backoff with jitter. `attempt` is 1-based."""
    delay = min(cap, base * (2 ** (attempt - 1)))
    delay = delay * (0.5 + random.random() / 2.0)  # 50–100% jitter
    await asyncio.sleep(delay)
