"""Verify the SSE plumbing (token deltas -> usage -> done) with a fake Claude
client, so the streaming path is exercised without a network call or API key.

Also covers the load-bearing retry gate in llm.py: a stream is retried ONLY
before the first token (never replay a partial stream), and an unrecoverable
failure terminates with a single ("error", ...) then ("done", None)."""

import anthropic
import httpx

from app.config import Settings
from app.llm import stream_chat


class _FakeUsage:
    input_tokens = 100
    output_tokens = 20
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class _FakeFinal:
    usage = _FakeUsage()


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    @property
    def text_stream(self):
        async def gen():
            for c in self._chunks:
                yield c

        return gen()

    async def get_final_message(self):
        return _FakeFinal()


class _FakeMessages:
    def __init__(self, chunks):
        self._chunks = chunks

    def stream(self, **_):
        return _FakeStream(self._chunks)


class _FakeClient:
    def __init__(self, chunks):
        self.messages = _FakeMessages(chunks)


async def test_stream_emits_tokens_then_usage_then_done():
    s = Settings(chat_model="claude-sonnet-5")
    client = _FakeClient(["Hel", "lo ", "world"])
    events = [(k, p) async for k, p in stream_chat("hi", s, client=client)]

    kinds = [k for k, _ in events]
    assert kinds == ["token", "token", "token", "usage", "done"]

    text = "".join(p for k, p in events if k == "token")
    assert text == "Hello world"

    usage = next(p for k, p in events if k == "usage")
    assert usage["tokens_out"] == 20
    assert usage["cost_usd"] > 0  # 100 in @ $3/Mtok + 20 out @ $15/Mtok


async def _noop_sleep(*_a, **_k):
    return None


def _conn_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com")
    )


class _RaisingStream(_FakeStream):
    """Yield `after` tokens, then raise `err` (after=0 raises before any token)."""

    def __init__(self, chunks, err, after):
        super().__init__(chunks)
        self._err = err
        self._after = after

    @property
    def text_stream(self):
        async def gen():
            n = 0
            for c in self._chunks:
                if n == self._after:
                    raise self._err
                n += 1
                yield c
            if self._after >= len(self._chunks):
                raise self._err

        return gen()


class _SeqMessages:
    """Serve a sequence of streams across retries and count stream() calls."""

    def __init__(self, streams):
        self._streams = list(streams)
        self.calls = 0

    def stream(self, **_):
        self.calls += 1
        return self._streams.pop(0)


class _SeqClient:
    def __init__(self, streams):
        self.messages = _SeqMessages(streams)


async def test_stream_retries_before_first_token(monkeypatch):
    # attempt 1 fails before emitting anything; attempt 2 succeeds -> the retry
    # is safe and the caller sees a normal token/usage/done sequence.
    monkeypatch.setattr("app.llm.backoff_sleep", _noop_sleep)
    client = _SeqClient(
        [
            _RaisingStream(["x"], _conn_error(), after=0),
            _FakeStream(["Hel", "lo"]),
        ]
    )
    s = Settings(chat_model="claude-sonnet-5")
    events = [(k, p) async for k, p in stream_chat("hi", s, client=client)]

    assert [k for k, _ in events] == ["token", "token", "usage", "done"]
    assert client.messages.calls == 2  # a retry actually happened


async def test_stream_does_not_retry_after_a_token(monkeypatch):
    # a failure AFTER the first token must NOT replay the stream — it emits a
    # single terminal ("error", ...) then ("done", None), and never re-calls stream().
    monkeypatch.setattr("app.llm.backoff_sleep", _noop_sleep)
    client = _SeqClient([_RaisingStream(["Hi"], _conn_error(), after=1)])
    s = Settings(chat_model="claude-sonnet-5")
    events = [(k, p) async for k, p in stream_chat("hi", s, client=client)]

    assert [k for k, _ in events] == ["token", "error", "done"]
    assert client.messages.calls == 1  # no replay of a partial stream
    assert isinstance(next(p for k, p in events if k == "error"), str)
