"""Heading-aware markdown chunker.

Chunks respect heading structure and stay under a token budget measured by the
EMBEDDER's own tokenizer (see DECISIONS.md — not Anthropic count_tokens). Every
chunk records absolute char offsets so `raw_text == source[char_start:char_end]`
(the invariant citations rely on) and a heading breadcrumb.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_PARA = re.compile(r"\n\s*\n")


@dataclass
class Chunk:
    ord: int
    heading_path: str
    raw_text: str
    char_start: int
    char_end: int


@lru_cache(maxsize=1)
def _tokenizer():
    from transformers import AutoTokenizer

    from ..config import get_settings

    return AutoTokenizer.from_pretrained(get_settings().embed_model)


def default_token_len(text: str) -> int:
    return len(_tokenizer().encode(text, add_special_tokens=False))


def _sections(text: str) -> list[tuple[str, str, int]]:
    """(heading_path, body_text, body_char_start) per heading section."""
    out: list[tuple[str, str, int]] = []
    stack: list[tuple[int, str]] = []
    pos = 0
    body_start = 0
    body: list[str] = []

    def flush() -> None:
        joined = "".join(body)
        if joined.strip():
            path = " > ".join(t for _, t in stack)
            out.append((path, joined, body_start))

    for line in text.splitlines(keepends=True):
        m = _HEADING.match(line.rstrip("\n"))
        if m:
            flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            body = []
            body_start = pos + len(line)
        else:
            body.append(line)
        pos += len(line)
    flush()
    return out


def _trim(s: str, base: int) -> tuple[str, int, int]:
    start = len(s) - len(s.lstrip())
    end = len(s.rstrip())
    return s[start:end], base + start, base + end


_Para = tuple[str, int, int]  # (text, abs_char_start, abs_char_end)


def _overlap_tail(
    window: list[_Para], overlap: int, token_len: Callable[[str], int]
) -> list[_Para]:
    """Trailing paragraphs of `window` whose cumulative tokens fit in `overlap`
    (always keeps at least the last one; the caller drops it if it won't fit)."""
    if overlap <= 0:
        return []
    tail: list[_Para] = []
    total = 0
    for para in reversed(window):
        t = token_len(para[0])
        if tail and total + t > overlap:
            break
        tail.insert(0, para)
        total += t
    return tail


def chunk_markdown(
    text: str,
    *,
    max_tokens: int,
    overlap: int,
    token_len: Callable[[str], int],
) -> list[Chunk]:
    chunks: list[Chunk] = []
    ordn = 0

    def emit(path: str, window: list[_Para]) -> None:
        nonlocal ordn
        raw = text[window[0][1] : window[-1][2]]
        chunks.append(Chunk(ordn, path, raw, window[0][1], window[-1][2]))
        ordn += 1

    for path, body, base in _sections(text):
        trimmed, tstart, tend = _trim(body, base)
        if not trimmed:
            continue
        if token_len(trimmed) <= max_tokens:
            chunks.append(Chunk(ordn, path, trimmed, tstart, tend))
            ordn += 1
            continue

        # section too big — pack paragraphs, emitting BEFORE a multi-paragraph
        # window would exceed the budget. NOTE: a single paragraph larger than
        # max_tokens is still emitted whole (as its own chunk) and relies on the
        # embedder truncating it, so such a chunk can exceed max_tokens.
        paras: list[_Para] = []
        idx = 0
        for part in _PARA.split(trimmed):
            p_start = trimmed.find(part, idx)
            p_end = p_start + len(part)
            idx = p_end
            if part.strip():
                paras.append((part, tstart + p_start, tstart + p_end))

        window: list[_Para] = []
        for para in paras:
            if window and token_len(text[window[0][1] : para[2]]) > max_tokens:
                emit(path, window)
                window = _overlap_tail(window, overlap, token_len)
                if window and token_len(text[window[0][1] : para[2]]) > max_tokens:
                    window = []  # overlap tail won't fit alongside the new para — drop it
            window.append(para)
        if window:
            emit(path, window)
    return chunks
