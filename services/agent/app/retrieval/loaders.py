"""Load the on-disk SRE corpus into typed docs. doc_type is inferred from the
top-level directory; title from the first H1; slug from the relative path."""

from dataclasses import dataclass
from pathlib import Path

_DOC_TYPE_BY_DIR = {
    "runbooks": "runbook",
    "adrs": "adr",
    "postmortems": "postmortem",
    "alerts": "alert_doc",
}


@dataclass
class LoadedDoc:
    slug: str
    doc_type: str
    title: str
    source_path: str
    text: str


def _first_h1(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def load_corpus(corpus_dir: Path) -> list[LoadedDoc]:
    docs: list[LoadedDoc] = []
    for path in sorted(corpus_dir.rglob("*.md")):
        rel = path.relative_to(corpus_dir)
        doc_type = _DOC_TYPE_BY_DIR.get(rel.parts[0], "runbook")
        text = path.read_text(encoding="utf-8")
        docs.append(
            LoadedDoc(
                slug=str(rel.with_suffix("")),
                doc_type=doc_type,
                title=_first_h1(text) or path.stem,
                source_path=str(path),
                text=text,
            )
        )
    return docs
