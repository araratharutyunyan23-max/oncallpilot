"""Local dense embeddings via BAAI/bge-large-en-v1.5 (1024-dim, CPU).

Asymmetric: passages are embedded as-is; queries get the bge instruction prefix.
L2-normalized so cosine distance (`<=>`) is exact. The query-prefix invariant is
asserted by a unit test (silent-degradation guard)."""

from functools import lru_cache

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    from ..config import get_settings

    return SentenceTransformer(get_settings().embed_model, device="cpu")


def encode_passages(texts: list[str]) -> list[list[float]]:
    embs = _model().encode(
        texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False
    )
    return [e.tolist() for e in embs]


def encode_query(text: str) -> list[float]:
    emb = _model().encode([QUERY_PREFIX + text], normalize_embeddings=True)[0]
    return emb.tolist()
