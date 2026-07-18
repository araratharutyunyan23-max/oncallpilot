"""Verify the SSE plumbing (token deltas -> usage -> done) with a fake Claude
client, so the streaming path is exercised without a network call or API key."""

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
