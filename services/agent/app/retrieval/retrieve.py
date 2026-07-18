"""Hybrid retrieval: dense pgvector kNN + Postgres FTS -> RRF -> cross-encoder
rerank. Flags let the eval compare dense-only / hybrid / hybrid+rerank."""

import time

import numpy as np
import psycopg

from ..config import get_settings
from .db import connect
from .embed import encode_query
from .fusion import reciprocal_rank_fusion
from .rerank import rerank
from .types import RetrievalTrace, RetrievedChunk


def _fetch_meta(conn: psycopg.Connection, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    rows = conn.execute(
        "SELECT c.id, c.document_id, d.slug, d.doc_type, d.title, c.heading_path, "
        "c.raw_text, c.char_start, c.char_end "
        "FROM chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE c.id = ANY(%s)",
        (ids,),
    ).fetchall()
    cols = (
        "id",
        "document_id",
        "slug",
        "doc_type",
        "title",
        "heading_path",
        "raw_text",
        "char_start",
        "char_end",
    )
    return {int(r[0]): dict(zip(cols, r, strict=False)) for r in rows}


def hybrid_search(
    query: str,
    *,
    use_sparse: bool = True,
    use_rerank: bool = True,
    conn: psycopg.Connection | None = None,
) -> tuple[list[RetrievedChunk], RetrievalTrace]:
    s = get_settings()
    own = conn is None
    conn = conn or connect()
    lat: dict[str, float] = {}

    t = time.perf_counter()
    qvec = np.asarray(encode_query(query), dtype=np.float32)
    lat["embed"] = (time.perf_counter() - t) * 1000

    conn.execute(f"SET hnsw.ef_search = {int(s.hnsw_ef_search)}")
    t = time.perf_counter()
    dense = [
        int(r[0])
        for r in conn.execute(
            "SELECT id FROM chunks ORDER BY embedding <=> %s LIMIT %s",
            (qvec, s.retrieve_fetch_k),
        ).fetchall()
    ]
    lat["dense"] = (time.perf_counter() - t) * 1000

    sparse: list[int] = []
    if use_sparse:
        t = time.perf_counter()
        sparse = [
            int(r[0])
            for r in conn.execute(
                "SELECT id FROM chunks WHERE fts @@ plainto_tsquery('english', %s) "
                "ORDER BY ts_rank(fts, plainto_tsquery('english', %s)) DESC LIMIT %s",
                (query, query, s.retrieve_fetch_k),
            ).fetchall()
        ]
        lat["sparse"] = (time.perf_counter() - t) * 1000

    arms = [dense, sparse] if use_sparse else [dense]
    fused = reciprocal_rank_fusion(arms, k=s.rrf_k)
    fused_ids = [cid for cid, _ in fused]
    rrf_by_id = dict(fused)
    dense_rank = {cid: i + 1 for i, cid in enumerate(dense)}
    sparse_rank = {cid: i + 1 for i, cid in enumerate(sparse)}

    cand_ids = fused_ids[: s.retrieve_fetch_k]
    meta = _fetch_meta(conn, cand_ids)

    rerank_score: dict[int, float] = {}
    if use_rerank and cand_ids:
        t = time.perf_counter()
        pairs = [(cid, meta[cid]["raw_text"]) for cid in cand_ids if cid in meta]
        ranked = rerank(query, pairs, top_n=s.rerank_topn)
        lat["rerank"] = (time.perf_counter() - t) * 1000
        rerank_score = dict(ranked)
        final_ids = [cid for cid, _ in ranked]
    else:
        final_ids = fused_ids[: s.rerank_topn]

    results: list[RetrievedChunk] = []
    for cid in final_ids:
        m = meta.get(cid)
        if not m:
            continue
        results.append(
            RetrievedChunk(
                chunk_id=cid,
                document_id=m["document_id"],
                slug=m["slug"],
                doc_type=m["doc_type"],
                title=m["title"],
                heading_path=m["heading_path"],
                raw_text=m["raw_text"],
                char_start=m["char_start"],
                char_end=m["char_end"],
                dense_rank=dense_rank.get(cid),
                sparse_rank=sparse_rank.get(cid),
                rrf_score=rrf_by_id.get(cid, 0.0),
                rerank_score=rerank_score.get(cid),
            )
        )

    trace = RetrievalTrace(
        query=query,
        dense_ids=dense,
        sparse_ids=sparse,
        fused_ids=fused_ids,
        reranked_ids=final_ids,
        latency_ms=lat,
    )
    if own:
        conn.close()
    return results, trace
