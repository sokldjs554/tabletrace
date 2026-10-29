"""Document and table indexes over a corpus store, with per-language tokenization."""
from __future__ import annotations

from dataclasses import dataclass

from tabletrace.retrieval.bm25 import BM25
from tabletrace.retrieval.tokenize import tokenize
from tabletrace.schema import Document, Passage, Table


@dataclass
class Hit:
    id: str
    doc_id: str
    kind: str          # "passage" | "table"
    score: float
    title: str
    snippet: str


def table_text(t: Table) -> str:
    cells = " ".join(" ".join(r) for r in t.rows)
    return f"{t.title} {t.caption or ''} {' '.join(t.header)} {cells}"


class CorpusIndex:
    def __init__(self, docs: list[Document], lang: str) -> None:
        self.lang = lang
        self.passages: dict[str, Passage] = {}
        self.tables: dict[str, Table] = {}
        self.docs: dict[str, Document] = {d.id: d for d in docs}
        self.passage_index = BM25()
        self.table_index = BM25()
        for d in docs:
            for p in d.passages:
                self.passages[p.id] = p
                self.passage_index.add(p.id, tokenize(f"{d.title} {p.text}", lang))
            for t in d.tables:
                self.tables[t.id] = t
                self.table_index.add(t.id, tokenize(table_text(t), lang))

    def search_passages(self, query: str, k: int = 5, doc_id: str | None = None) -> list[Hit]:
        q = tokenize(query, self.lang)
        hits = []
        for pid, s in self.passage_index.search(q, k=k * 4 if doc_id else k):
            p = self.passages[pid]
            if doc_id and p.doc_id != doc_id:
                continue
            hits.append(Hit(id=pid, doc_id=p.doc_id, kind="passage", score=round(s, 3),
                            title=self.docs[p.doc_id].title, snippet=p.text[:160]))
            if len(hits) >= k:
                break
        return hits

    def search_tables(self, query: str, k: int = 5, doc_id: str | None = None) -> list[Hit]:
        q = tokenize(query, self.lang)
        hits = []
        for tid, s in self.table_index.search(q, k=k * 4 if doc_id else k):
            t = self.tables[tid]
            if doc_id and t.doc_id != doc_id:
                continue
            hits.append(Hit(id=tid, doc_id=t.doc_id, kind="table", score=round(s, 3),
                            title=t.title, snippet=" | ".join(t.header)[:160]))
            if len(hits) >= k:
                break
        return hits
