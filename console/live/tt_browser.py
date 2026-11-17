"""The demo's "run it here" path: the repository's verifier, tools and heuristic planner, called in the visitor's browser.

It runs under Pyodide (CPython compiled to WebAssembly) and imports the same modules a server would: the program
grammar, the number parser, the calculator, the cell tools and the verifier are the repository owner's own files,
unchanged. What is different from the service:

  * no LangGraph: the four steps of the graph (retrieve, propose, verify, finalize) are called in order here, and
    there is no second proposal when a proposal fails (the evaluation's setting);
  * no retrieval: the visitor has already chosen the document and the table, and the passage is the document's first
    one (or the one the stored question names), cut to the 300 characters the service and the evaluation also use;
  * no model: a proposal comes from the visitor (who edits a stored one) or from the heuristic planner;
  * Korean text is tokenized from recorded tokens (see shim/kiwipiepy.py), so only stored questions work in Korean.

tests/test_browser_path.py holds this file against the agent graph on every stored question.
"""
from __future__ import annotations

import json
import time

from tabletrace.agent.heuristic import plan as heuristic_plan
from tabletrace.agent.program import ProgramParseError, parse, serialize
from tabletrace.eval.metrics import answer_match
from tabletrace.schema import Document, TraceStep
from tabletrace.tools.numbers import parse_number
from tabletrace.verify.guard import resolve_guarded

CONTEXT_CHARS = 300      # tabletrace.training.data.CONTEXT_CHARS and the service's retrieve node


def load_tokens(tokens_json: str) -> int:
    """Hand the recorded Korean tokens to the tokenizer stand-in (a no-op where the real tokenizer is installed)."""
    import kiwipiepy

    if hasattr(kiwipiepy, "load"):
        kiwipiepy.load(json.loads(tokens_json))
    return len(json.loads(tokens_json))


def mark_of(status: str, answer: str | None, gold: dict) -> str:
    """Whether a result is right, by the evaluation's own rule (eval/run.py: the same status, and a matching answer).
    `gold` is {"status": "answered" | "abstained", "answers": [...]}."""
    if gold["status"] == "abstained":
        return "hold_ok" if status == "abstained" else "answered_unanswerable"
    if status == "abstained":
        return "hold_miss"
    return "correct" if any(answer_match(answer, g) for g in gold["answers"]) else "wrong"


def cell_values(cells, table) -> list[dict]:
    """How the number parser reads each evidence cell: raw text, parsed value, unit and where the unit came from."""
    out = []
    for c in cells:
        raw = table.rows[c.row][c.col]
        own = parse_number(raw)
        num = parse_number(raw, default_unit=table.units.get(c.col))
        out.append({"cell": c.cid, "raw": raw, "value": num.value if num else None, "unit": num.unit if num else None,
                    "unit_from": None if not num or num.unit is None else ("cell" if own and own.unit is not None else "header")})
    return out


def run(doc: Document, table_id: str, question: str, proposal: str | None = None, passage_id: str | None = None,
        entity_check: bool = False) -> dict:
    """One question on one table. `proposal` is a program in the model's output format (op ; cells ; answer); without
    it the heuristic planner proposes. Returns what the service returns for an answer, as plain data."""
    t_start = time.perf_counter()
    table = doc.table(table_id)
    passage = next((p for p in doc.passages if p.id == passage_id), None) or (doc.passages[0] if doc.passages else None)
    context, pid = (passage.text[:CONTEXT_CHARS], passage.id) if passage else (None, None)
    trace = [TraceStep(step="retrieve", tool="given", input={"query": question, "doc_id": doc.id},
                       output={"selected_table": table.id, "context_passage": pid, "note": "the visitor chose the document and the table"})]
    t0 = time.perf_counter()
    if proposal is None:
        prog = heuristic_plan(question, table, table.lang)
        raw, mode = serialize(prog), "heuristic"
    else:
        raw, mode = proposal, "visitor"
        try:
            prog = parse(proposal, table.id)
        except ProgramParseError:
            prog = None
    trace.append(TraceStep(step="propose", tool=mode, input={"question": question, "table_id": table.id, "mode": mode},
                           output={"raw": raw, "parsed": prog.model_dump() if prog else None},
                           ms=(time.perf_counter() - t0) * 1000, status="ok" if prog else "error"))
    t0 = time.perf_counter()
    res = resolve_guarded(question, table, prog, context=context, passage_id=pid or "context", entity_check=entity_check, repair=True)
    trace += res.trace
    trace.append(TraceStep(step="verify", output={"status": res.status, "reason": res.verdict.reason, "checks": [c.model_dump() for c in res.verdict.checks]},
                           ms=(time.perf_counter() - t0) * 1000))
    return {"question": question, "corpus": doc.corpus, "doc_id": doc.id, "table_id": table.id, "status": res.status, "answer": res.answer,
            "program": prog.model_dump() if prog else None, "evidence_cells": [c.model_dump() for c in res.cells],
            "evidence_spans": [s.model_dump() for s in res.spans], "calculation": res.calculation.model_dump() if res.calculation else None,
            "verdict": res.verdict.model_dump(), "planner": {"mode": mode, "model_id": None, "raw_output": raw},
            "trace": [s.model_dump() for s in trace], "elapsed_ms": (time.perf_counter() - t_start) * 1000, "error": None,
            "values": cell_values(res.cells, table), "settings": {"entity_check": entity_check, "evidence_repair": True, "fallback": False}}


def run_json(doc_json: str, table_id: str, question: str, proposal: str | None = None, passage_id: str | None = None,
             entity_check: bool = False, gold_json: str | None = None) -> str:
    """The entry point the page calls. With the gold of a stored question the result carries its mark.
    A Korean text without recorded tokens comes back as {"error": "missing_tokens"}."""
    from kiwipiepy import Kiwi  # noqa: F401  (the stand-in in the browser, the real tokenizer on a server)

    try:
        import kiwipiepy

        missing = getattr(kiwipiepy, "MissingTokens", ())
    except ImportError:
        missing = ()
    try:
        res = run(Document.model_validate_json(doc_json), table_id, question, proposal, passage_id, entity_check)
        if gold_json:
            res["mark"] = mark_of(res["status"], res["answer"], json.loads(gold_json))
        return json.dumps(res, ensure_ascii=False)
    except missing as exc:
        return json.dumps({"error": "missing_tokens", "text": str(exc.args[0])[:200]}, ensure_ascii=False)
