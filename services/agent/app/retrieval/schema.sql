-- OncallPilot retrieval schema (Postgres 16 + pgvector).
-- Applied automatically on first container init (mounted into
-- /docker-entrypoint-initdb.d) and idempotent, so `make ingest` can re-run.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id          BIGSERIAL PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,          -- e.g. "runbooks/redis-oom"
    doc_type    TEXT NOT NULL,                 -- runbook | adr | postmortem | alert_doc
    title       TEXT NOT NULL,
    source_path TEXT NOT NULL,
    content_sha TEXT NOT NULL,                 -- idempotent re-ingest guard
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL PRIMARY KEY,
    document_id  BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ord          INT NOT NULL,                 -- chunk order within the document
    heading_path TEXT,                         -- e.g. "Redis OOM > Immediate mitigation"
    raw_text     TEXT NOT NULL,                -- clean span, used for citations
    embed_text   TEXT NOT NULL,                -- breadcrumb-prefixed, used for embedding only
    char_start   INT NOT NULL,
    char_end     INT NOT NULL,
    embedding    vector(1024),
    -- lexical arm: Postgres FTS (ts_rank), honestly NOT BM25 (see DECISIONS.md)
    fts          tsvector GENERATED ALWAYS AS (to_tsvector('english', raw_text)) STORED,
    UNIQUE (document_id, ord)
);

-- dense arm: HNSW over cosine distance (bge embeddings are L2-normalized)
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- sparse arm: GIN over the generated tsvector
CREATE INDEX IF NOT EXISTS chunks_fts_gin
    ON chunks USING gin (fts);
