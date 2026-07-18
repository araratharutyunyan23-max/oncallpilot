from typing import TypedDict


class RetrievedChunk(TypedDict):
    chunk_id: int
    document_id: int
    slug: str
    doc_type: str
    title: str
    heading_path: str | None
    raw_text: str
    char_start: int
    char_end: int
    dense_rank: int | None  # 1-based rank in the dense arm (None if not retrieved)
    sparse_rank: int | None  # 1-based rank in the FTS arm
    rrf_score: float
    rerank_score: float | None


class RetrievalTrace(TypedDict):
    query: str
    dense_ids: list[int]
    sparse_ids: list[int]
    fused_ids: list[int]
    reranked_ids: list[int]
    latency_ms: dict[str, float]
