"""Persist documents + chunks to Postgres. Idempotent per document via
content_sha: unchanged docs are skipped, changed docs replace their chunks."""

import hashlib

import numpy as np
import psycopg


def content_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def upsert_document(
    conn: psycopg.Connection,
    *,
    slug: str,
    doc_type: str,
    title: str,
    source_path: str,
    sha: str,
) -> tuple[int, bool]:
    """Return (document_id, changed). changed=False means same content_sha (skip)."""
    row = conn.execute(
        "SELECT id, content_sha FROM documents WHERE slug = %s", (slug,)
    ).fetchone()
    if row and row[1] == sha:
        return int(row[0]), False
    if row:
        doc_id = int(row[0])
        conn.execute(
            "UPDATE documents SET doc_type=%s, title=%s, source_path=%s, "
            "content_sha=%s, ingested_at=now() WHERE id=%s",
            (doc_type, title, source_path, sha, doc_id),
        )
        conn.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
        return doc_id, True
    new = conn.execute(
        "INSERT INTO documents (slug, doc_type, title, source_path, content_sha) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (slug, doc_type, title, source_path, sha),
    ).fetchone()
    assert new is not None
    return int(new[0]), True


def insert_chunks(conn: psycopg.Connection, document_id: int, rows: list[dict]) -> None:
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                "INSERT INTO chunks (document_id, ord, heading_path, raw_text, "
                "embed_text, char_start, char_end, embedding) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    document_id,
                    r["ord"],
                    r["heading_path"],
                    r["raw_text"],
                    r["embed_text"],
                    r["char_start"],
                    r["char_end"],
                    np.asarray(r["embedding"], dtype=np.float32),
                ),
            )
