"""Guard against silent degradation: bge queries MUST carry the instruction
prefix; passages must NOT. Uses a fake model so no weights are downloaded."""

import numpy as np

from app.retrieval import embed


class _FakeModel:
    def __init__(self):
        self.seen: list[str] = []

    def encode(self, texts, **_):
        self.seen.extend(texts)
        return np.zeros((len(texts), 4), dtype="float32")


def test_query_gets_prefix(monkeypatch):
    fake = _FakeModel()
    monkeypatch.setattr(embed, "_model", lambda: fake)
    embed.encode_query("redis oom")
    assert fake.seen[0].startswith(embed.QUERY_PREFIX)
    assert fake.seen[0].endswith("redis oom")


def test_passages_not_prefixed(monkeypatch):
    fake = _FakeModel()
    monkeypatch.setattr(embed, "_model", lambda: fake)
    embed.encode_passages(["a passage"])
    assert fake.seen == ["a passage"]
