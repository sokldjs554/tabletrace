"""Loads processed corpora (data/<corpus>/documents.jsonl) and exposes typed Documents."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from tabletrace.schema import Corpus, Document, Table

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
CORPUS_FILES: dict[str, Path] = {
    "ko_tables": DATA_DIR / "ko" / "documents.jsonl",
    "chem_docs": DATA_DIR / "chem" / "documents.jsonl",
}


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@lru_cache(maxsize=4)
def load_corpus(corpus: Corpus, path: Path | None = None) -> list[Document]:
    p = path or CORPUS_FILES[corpus]
    if not p.exists():
        return []
    return [Document.model_validate(r) for r in read_jsonl(p)]


class CorpusStore:
    def __init__(self, corpora: dict[str, list[Document]]) -> None:
        self.corpora = corpora
        self.docs: dict[str, Document] = {}
        self.tables: dict[str, Table] = {}
        for docs in corpora.values():
            for d in docs:
                self.docs[d.id] = d
                for t in d.tables:
                    self.tables[t.id] = t

    @classmethod
    def from_disk(cls) -> CorpusStore:
        return cls({c: load_corpus(c) for c in CORPUS_FILES})  # type: ignore[arg-type]

    def doc(self, doc_id: str) -> Document:
        return self.docs[doc_id]

    def table(self, table_id: str) -> Table:
        return self.tables[table_id]
