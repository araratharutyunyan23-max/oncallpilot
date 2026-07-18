"""Reciprocal Rank Fusion — rank-based, so no normalization between the
unbounded ts_rank score and cosine distance is needed. Pure + unit-tested."""


def reciprocal_rank_fusion(
    ranked_lists: list[list[int]], k: int = 60
) -> list[tuple[int, float]]:
    """Fuse several ranked id lists into one. `ranked_lists` are ordered best-first.

    Returns (id, score) sorted best-first. Score for an id is the sum over lists
    of 1 / (k + rank), rank being 1-based within each list.
    """
    scores: dict[int, float] = {}
    for lst in ranked_lists:
        for rank0, cid in enumerate(lst):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank0 + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
