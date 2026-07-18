"""RAG assembly tests — document-block construction and citation->manifest
mapping — with fake message objects, so no network / API key is needed."""

from app.rag import _extract_citations, _sources
from app.retrieval.citations import build_document_blocks


def _chunk(slug: str, cid: int):
    return {
        "chunk_id": cid,
        "document_id": 1,
        "slug": slug,
        "doc_type": "runbook",
        "title": "Runbook: X",
        "heading_path": "X > Mitigation",
        "raw_text": "step body",
        "char_start": 10,
        "char_end": 19,
        "dense_rank": 1,
        "sparse_rank": None,
        "rrf_score": 0.5,
        "rerank_score": None,
    }


class _Cit:
    def __init__(self, document_index, cited_text):
        self.document_index = document_index
        self.cited_text = cited_text


class _Block:
    def __init__(self, type="text", citations=None):
        self.type = type
        self.citations = citations


class _Msg:
    def __init__(self, content):
        self.content = content


def test_build_blocks_and_manifest():
    blocks, manifest = build_document_blocks([_chunk("runbooks/redis-oom", 7)])
    assert blocks[0]["type"] == "document"
    assert blocks[0]["citations"] == {"enabled": True}
    assert blocks[0]["source"]["type"] == "content"
    assert manifest[0]["slug"] == "runbooks/redis-oom"
    assert manifest[0]["chunk_id"] == 7
    assert manifest[0]["doc_char_start"] == 10


def test_extract_citations_maps_document_index_to_slug():
    _, manifest = build_document_blocks(
        [_chunk("runbooks/redis-oom", 7), _chunk("runbooks/api-5xx", 3)]
    )
    msg = _Msg([_Block(), _Block("text", [_Cit(1, "roll back first")])])
    cits = _extract_citations(msg, manifest)
    assert len(cits) == 1
    assert cits[0]["slug"] == "runbooks/api-5xx"
    assert cits[0]["chunk_id"] == 3
    assert cits[0]["cited_text"] == "roll back first"


def test_extract_citations_dedupes():
    _, manifest = build_document_blocks([_chunk("runbooks/redis-oom", 7)])
    msg = _Msg(
        [
            _Block("text", [_Cit(0, "set allkeys-lru")]),
            _Block("text", [_Cit(0, "set allkeys-lru")]),
        ]
    )
    assert len(_extract_citations(msg, manifest)) == 1


def test_sources_shape():
    s = _sources([_chunk("runbooks/x", 1)])
    assert s[0]["slug"] == "runbooks/x"
    assert "rrf_score" in s[0]
    assert s[0]["heading_path"] == "X > Mitigation"
