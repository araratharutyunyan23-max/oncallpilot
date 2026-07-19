"""The single Claude call for Phase 0: one streamed completion.

Uses the current (2026) Claude API surface:
  - adaptive thinking (`thinking={"type": "adaptive"}`), never `budget_tokens`
  - depth via `output_config={"effort": ...}` (NOT sampling params — those 400)
  - a frozen system prefix marked with `cache_control` (ephemeral, 1h ttl)
  - streaming (required for large max_tokens)

Retries (429/529/connection) happen only before the first token; a partial
stream is never replayed.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from .config import Settings, get_settings
from .cost import Usage, cost_usd
from .resilience import RETRYABLE, backoff_sleep

log = logging.getLogger("oncallpilot.llm")

_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        # take the key from our own config (single source of truth: .env or OS env),
        # not the SDK's implicit os.environ lookup — the latter is empty under local
        # dev where the key lives only in the pydantic-loaded .env.
        _client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _client


async def stream_chat(
    query: str,
    settings: Settings,
    *,
    client: AsyncAnthropic | None = None,
    max_retries: int = 4,
) -> AsyncIterator[tuple[str, object]]:
    """Yield ("token", str)* then ("usage", dict) then ("done", None).

    On unrecoverable failure yields ("error", str) instead of raising, so the
    caller can surface it as an SSE frame rather than a 500 mid-stream.
    """
    cli = client or get_client()
    system = [
        {
            "type": "text",
            "text": settings.system_prompt,
            "cache_control": {"type": "ephemeral", "ttl": settings.cache_ttl},
        }
    ]
    kwargs: dict[str, Any] = {
        "model": settings.chat_model,
        "max_tokens": settings.chat_max_tokens,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": settings.chat_effort},
        "system": system,
        "messages": [{"role": "user", "content": query}],
    }

    attempt = 0
    while True:
        got_token = False
        try:
            async with cli.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    got_token = True
                    yield ("token", text)
                final = await stream.get_final_message()
                usage = Usage.from_response(final.usage)
                cost = cost_usd(settings.chat_model, usage, settings.cache_ttl)
                yield (
                    "usage",
                    {
                        "model": settings.chat_model,
                        "tokens_in": usage.input_tokens,
                        "tokens_out": usage.output_tokens,
                        "cache_read": usage.cache_read_input_tokens,
                        "cost_usd": round(cost, 6),
                    },
                )
                yield ("done", None)
                return
        except RETRYABLE as e:
            if got_token or attempt >= max_retries:
                log.warning("stream failed, no retry: %s", type(e).__name__)
                yield ("error", f"upstream unavailable ({type(e).__name__})")
                yield ("done", None)  # terminate on `done` like the agent endpoints
                return
            attempt += 1
            log.info("retry %d after %s", attempt, type(e).__name__)
            await backoff_sleep(attempt)
        except anthropic.APIStatusError as e:
            log.warning("api error: %s", e)
            yield ("error", f"api error {getattr(e, 'status_code', '?')}")
            yield ("done", None)
            return
