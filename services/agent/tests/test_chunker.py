from app.retrieval.chunker import chunk_markdown

DOC = """# Title

Intro paragraph one.

## Section A

Step one text.

Step two text.

## Section B

Only line here.
"""


def wc(s: str) -> int:  # deterministic word-count token_len for tests
    return len(s.split())


def test_offsets_map_back_to_source():
    chunks = chunk_markdown(DOC, max_tokens=1000, overlap=0, token_len=wc)
    assert chunks
    for c in chunks:
        # the invariant citations depend on
        assert DOC[c.char_start : c.char_end] == c.raw_text


def test_heading_paths():
    paths = {c.heading_path for c in chunk_markdown(DOC, max_tokens=1000, overlap=0, token_len=wc)}
    assert "Title" in paths
    assert "Title > Section A" in paths
    assert "Title > Section B" in paths


def test_large_section_splits_and_keeps_offsets():
    big = "# T\n\n" + "\n\n".join(f"paragraph number {i} of text" for i in range(20))
    chunks = chunk_markdown(big, max_tokens=8, overlap=4, token_len=wc)
    assert len(chunks) > 1
    for c in chunks:
        assert big[c.char_start : c.char_end] == c.raw_text
        assert wc(c.raw_text) <= 8 or c.raw_text.count("\n\n") == 0
