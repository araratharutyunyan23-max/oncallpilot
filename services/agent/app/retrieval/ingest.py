"""Ingest the SRE corpus: load -> chunk (heading-aware) -> embed (bge) -> store.
Idempotent per document (content_sha). Run: `python -m app.retrieval.ingest`."""

from pathlib import Path

from ..config import get_settings
from .chunker import chunk_markdown, default_token_len
from .db import connect
from .embed import encode_passages
from .loaders import load_corpus
from .store import content_sha, insert_chunks, upsert_document

REPO_ROOT = Path(__file__).resolve().parents[4]
CORPUS_DIR = REPO_ROOT / "docs" / "corpus"


def run_ingest(corpus_dir: Path | None = None) -> dict:
    s = get_settings()
    corpus = Path(corpus_dir or CORPUS_DIR)
    docs = load_corpus(corpus)
    conn = connect()
    stats = {"documents": 0, "chunks": 0, "skipped": 0}
    try:
        for doc in docs:
            sha = content_sha(doc.text)
            doc_id, changed = upsert_document(
                conn,
                slug=doc.slug,
                doc_type=doc.doc_type,
                title=doc.title,
                source_path=doc.source_path,
                sha=sha,
            )
            if not changed:
                stats["skipped"] += 1
                continue
            chunks = chunk_markdown(
                doc.text,
                max_tokens=s.chunk_tokens,
                overlap=s.chunk_overlap,
                token_len=default_token_len,
            )
            embed_texts = [
                f"[{doc.doc_type}] {c.heading_path}\n\n{c.raw_text}"
                if c.heading_path
                else c.raw_text
                for c in chunks
            ]
            embeddings = encode_passages(embed_texts)
            rows = [
                {
                    "ord": c.ord,
                    "heading_path": c.heading_path or None,
                    "raw_text": c.raw_text,
                    "embed_text": et,
                    "char_start": c.char_start,
                    "char_end": c.char_end,
                    "embedding": e,
                }
                for c, et, e in zip(chunks, embed_texts, embeddings, strict=False)
            ]
            insert_chunks(conn, doc_id, rows)
            stats["documents"] += 1
            stats["chunks"] += len(rows)
            print(f"  {doc.slug:40s} {len(rows):3d} chunks")
    finally:
        conn.close()
    return stats


if __name__ == "__main__":
    print("Ingesting corpus…")
    result = run_ingest()
    print(f"done: {result}")
