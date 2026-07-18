"""Turn reranked chunks into Anthropic document content blocks with native
citations enabled, plus a manifest mapping document_index -> absolute source
offset for UI deep-linking. Wired now; the synthesis call that uses it lands
with the LLM answer node (needs ANTHROPIC_API_KEY)."""

from .types import RetrievedChunk


def build_document_blocks(
    chunks: list[RetrievedChunk],
) -> tuple[list[dict], list[dict]]:
    blocks: list[dict] = []
    manifest: list[dict] = []
    for i, c in enumerate(chunks):
        blocks.append(
            {
                "type": "document",
                "title": f"{c['title']} ({c['slug']})",
                "source": {
                    "type": "content",
                    "content": [{"type": "text", "text": c["raw_text"]}],
                },
                "citations": {"enabled": True},
            }
        )
        manifest.append(
            {
                "document_index": i,
                "slug": c["slug"],
                "chunk_id": c["chunk_id"],
                "doc_char_start": c["char_start"],
                "doc_char_end": c["char_end"],
                "title": c["title"],
            }
        )
    return blocks, manifest
