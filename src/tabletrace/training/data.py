"""Turn QA records + corpus documents into (input_text, target_text) pairs for SFT / RL / eval."""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path

from tabletrace.agent.program import serialize
from tabletrace.model.serialize import build_input, choose_context_and_rows
from tabletrace.schema import CellRef, Document, Program, Table

CONTEXT_CHARS = 300


@dataclass
class Example:
    qid: str
    question: str
    table: Table
    context: str | None
    gold: Program
    gold_answer: str | None
    source: str
    input_text: str
    target_text: str
    truncated_gold: bool   # a gold cell row was cut by the row budget
    rows_kept: int
    table_full: Table | None = None      # untruncated table (gold resolution, metrics)
    context_full: str | None = None      # untruncated passage text


def load_docs(*corpus_files: Path) -> dict[str, Document]:
    out = {}
    for corpus_file in corpus_files:
        with _open_text(corpus_file) as f:
            for line in f:
                d = Document.model_validate(json.loads(line))
                out[d.id] = d
    return out


def _open_text(path: Path):
    """Plain or gzip-compressed JSON lines (the training pool is stored as .jsonl.gz)."""
    return gzip.open(path, "rt", encoding="utf-8") if str(path).endswith(".gz") else open(path, encoding="utf-8")


def gold_program(rec: dict, table_id: str) -> Program:
    if rec["op"] == "abstain":
        return Program(op="abstain", cells=[], answer=None, reason=rec.get("reason", "not_in_document"))
    if rec["op"] == "text":
        return Program(op="text", cells=[], answer=rec["answer"])
    cells = [CellRef(table_id=table_id, row=r, col=c) for r, c in rec["gold_cells"]]
    return Program(op=rec["op"], cells=cells, answer=rec.get("answer"))


def context_for(doc: Document, rec: dict, limit: int | None = CONTEXT_CHARS) -> str | None:
    """Passage text shown to the model (first `limit` chars). For custom cases that name a passage
    (`context_passage`), that passage is used; otherwise the document's first passage."""
    text = None
    if rec.get("context"):
        text = rec["context"]
    elif rec.get("context_passage"):
        text = next((p.text for p in doc.passages if p.id == rec["context_passage"]), None)
    if text is None and doc.passages:
        text = doc.passages[0].text
    if text is None:
        return None
    return text[:limit] if limit else text


def build_examples(records: list[dict], docs: dict[str, Document], tokenizer, max_in: int = 512,
                   drop_truncated_gold: bool = False) -> list[Example]:
    out = []
    for rec in records:
        doc = docs[rec["doc_id"]]
        table = doc.table(rec["table_id"])
        ctx_full = context_for(doc, rec, limit=None)
        ctx, n = choose_context_and_rows(tokenizer, rec["question"], table, ctx_full, max_in)
        gold = gold_program(rec, table.id)
        truncated = any(c.row >= n for c in gold.cells)
        if truncated and drop_truncated_gold:
            continue
        shown = Table(**{**table.model_dump(), "rows": table.rows[:n]})
        out.append(Example(
            qid=rec["qid"], question=rec["question"], table=shown, context=ctx, gold=gold,
            gold_answer=rec.get("answer"), source=rec.get("source", "?"),
            input_text=build_input(rec["question"], table, ctx, max_rows=n), target_text=serialize(gold),
            truncated_gold=truncated, rows_kept=n, table_full=table, context_full=ctx_full,
        ))
    return out


def read_records(paths: list[Path]) -> list[dict]:
    recs = []
    for p in paths:
        with _open_text(p) as f:
            recs += [json.loads(line) for line in f if line.strip()]
    return recs
