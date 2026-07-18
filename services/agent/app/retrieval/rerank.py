"""Cross-encoder reranker (BAAI/bge-reranker-v2-m3, CPU) over fused candidates."""

from functools import lru_cache


@lru_cache(maxsize=1)
def _reranker():
    from sentence_transformers import CrossEncoder

    from ..config import get_settings

    return CrossEncoder(get_settings().rerank_model, device="cpu", max_length=512)


def rerank(
    query: str, candidates: list[tuple[int, str]], top_n: int
) -> list[tuple[int, float]]:
    """candidates: (chunk_id, raw_text). Returns (chunk_id, score) best-first, top_n."""
    if not candidates:
        return []
    scores = _reranker().predict([(query, text) for _, text in candidates])
    ranked = sorted(
        ((cid, float(s)) for (cid, _), s in zip(candidates, scores, strict=False)),
        key=lambda kv: kv[1],
        reverse=True,
    )
    return ranked[:top_n]
