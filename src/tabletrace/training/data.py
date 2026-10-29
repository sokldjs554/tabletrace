"""Turn QA records + corpus documents into (input_text, target_text) pairs for SFT / RL / eval."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tabletrace.agent.program import serialize
from tabletrace.model.serialize import build_input, fit_rows
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


def load_docs(*corpus_files: Path) -> dict[str, Document]:
    out = {}
    for corpus_file in corpus_files:
        with open(corpus_file, encoding="utf-8") as f:
            for line in f:
                d = Document.model_validate(json.loads(line))
                out[d.id] = d
    return out


def gold_program(rec: dict, table_id: str) -> Program:
    if rec["op"] == "abstain":
        return Program(op="abstain", cells=[], answer=None, reason=rec.get("reason", "not_in_document"))
    if rec["op"] == "text":
        return Program(op="text", cells=[], answer=rec["answer"])
    cells = [CellRef(table_id=table_id, row=r, col=c) for r, c in rec["gold_cells"]]
    return Program(op=rec["op"], cells=cells, answer=rec.get("answer"))


def context_for(doc: Document, rec: dict) -> str | None:
    if rec.get("context"):
        return rec["context"][:CONTEXT_CHARS]
    if doc.passages:
        return doc.passages[0].text[:CONTEXT_CHARS]
    return None


def build_examples(records: list[dict], docs: dict[str, Document], tokenizer, max_in: int = 512,
                   drop_truncated_gold: bool = False) -> list[Example]:
    out = []
    for rec in records:
        doc = docs[rec["doc_id"]]
        table = doc.table(rec["table_id"])
        ctx = context_for(doc, rec)
        n = fit_rows(tokenizer, rec["question"], table, ctx, max_in)
        if n < table.n_rows and n < 2 and ctx:
            ctx = None
            n = fit_rows(tokenizer, rec["question"], table, None, max_in)
        gold = gold_program(rec, table.id)
        truncated = any(c.row >= n for c in gold.cells)
        if truncated and drop_truncated_gold:
            continue
        shown = Table(**{**table.model_dump(), "rows": table.rows[:n]})
        out.append(Example(
            qid=rec["qid"], question=rec["question"], table=shown, context=ctx, gold=gold,
            gold_answer=rec.get("answer"), source=rec.get("source", "?"),
            input_text=build_input(rec["question"], table, ctx, max_rows=n), target_text=serialize(gold),
            truncated_gold=truncated, rows_kept=n,
        ))
    return out


def read_records(paths: list[Path]) -> list[dict]:
    recs = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            recs += [json.loads(line) for line in f if line.strip()]
    return recs
