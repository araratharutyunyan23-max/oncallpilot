"""RAG answer node (Phase 1 user-facing deliverable).

hybrid_search -> Anthropic document content blocks with native Citations ->
streamed grounded answer. Emits the retrieved `sources` up front, streams answer
`token`s, then the resolved `citations` (mapped back to slug/chunk via the
manifest) and `usage`. Answers are grounded strictly in the retrieved docs; the
system prompt forces a plain "not in the runbooks" when the corpus doesn't cover
the question.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import anthropic
from anthropic import AsyncAnthropic

from .config import Settings
from .cost import Usage, cost_usd
from .llm import get_client
from .resilience import RETRYABLE, backoff_sleep
from .retrieval.citations import build_document_blocks
from .retrieval.retrieve import hybrid_search
from .retrieval.types import RetrievedChunk

log = logging.getLogger("oncallpilot.rag")

RAG_SYSTEM = (
    "You are OncallPilot, an assistant for SRE / on-call engineers. Answer the "
    "engineer's question using ONLY the provided documents (runbooks, ADRs, "
    "postmortems, alert docs). Cite the specific source for each claim. If the "
    "answer is not in the provided documents, say so plainly and suggest where to "
    "look — do NOT use outside knowledge or invent steps. Be concise and actionable."
)


def _sources(chunks: list[RetrievedChunk]) -> list[dict]:
    return [
        {
            "slug": c["slug"],
            "doc_type": c["doc_type"],
            "title": c["title"],
            "heading_path": c["heading_path"],
            "chunk_id": c["chunk_id"],
            "rrf_score": round(c["rrf_score"], 4),
            "rerank_score": c["rerank_score"],
        }
        for c in chunks
    ]


def _extract_citations(message: Any, manifest: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set = set()
    for block in message.content:
        cits = getattr(block, "citations", None)
        if getattr(block, "type", None) != "text" or not cits:
            continue
        for cit in cits:
            di = getattr(cit, "document_index", None)
            m = manifest[di] if isinstance(di, int) and 0 <= di < len(manifest) else {}
            cited = getattr(cit, "cited_text", "") or ""
            key = (m.get("slug"), m.get("chunk_id"), cited[:50])
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "slug": m.get("slug"),
                    "chunk_id": m.get("chunk_id"),
                    "title": m.get("title"),
                    "cited_text": cited,
                    "doc_char_start": m.get("doc_char_start"),
                    "doc_char_end": m.get("doc_char_end"),
                }
            )
    return out


async def stream_rag_answer(
    query: str,
    settings: Settings,
    *,
    client: AsyncAnthropic | None = None,
    max_retries: int = 4,
) -> AsyncIterator[tuple[str, object]]:
    cli = client or get_client()

    # retrieval is synchronous (DB + local embedding model) — keep it off the loop
    chunks, _trace = await asyncio.to_thread(hybrid_search, query)
    yield ("sources", _sources(chunks))

    blocks, manifest = build_document_blocks(chunks)
    system = [
        {
            "type": "text",
            "text": RAG_SYSTEM,
            "cache_control": {"type": "ephemeral", "ttl": settings.cache_ttl},
        }
    ]
    user_content: list[dict[str, Any]] = list(blocks)
    user_content.append({"type": "text", "text": f"Question: {query}"})
    kwargs: dict[str, Any] = {
        "model": settings.chat_model,
        "max_tokens": settings.chat_max_tokens,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": settings.chat_effort},
        "system": system,
        "messages": [{"role": "user", "content": user_content}],
    }

    attempt = 0
    while True:
        got = False
        try:
            async with cli.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    got = True
                    yield ("token", text)
                final = await stream.get_final_message()
                yield ("citations", _extract_citations(final, manifest))
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
            if got or attempt >= max_retries:
                log.warning("rag stream failed, no retry: %s", type(e).__name__)
                yield ("error", f"upstream unavailable ({type(e).__name__})")
                yield ("done", None)  # terminate on `done` like the agent endpoints
                return
            attempt += 1
            await backoff_sleep(attempt)
        except anthropic.APIStatusError as e:
            log.warning("rag api error: %s", e)
            yield ("error", f"api error {getattr(e, 'status_code', '?')}")
            yield ("done", None)
            return
