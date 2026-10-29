"""Verification and abstention policy.

Given a question, the selected table and a proposed Program, the verifier
1. range-checks every cell,
2. for `lookup` confirms the answer is literally the evidence cell (the cell wins on conflict; if the cited
   cell is wrong but exactly one other cell holds the answer text, that cell becomes the evidence and the
   repair is recorded),
3. for calculations re-executes the restricted calculator and compares with the proposed number,
4. checks units and periods, and
5. decides answered / abstained with an explicit reason.

Everything it decides is returned as `Check` records so the console can show *why*.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from tabletrace.schema import (
    AbstainReason,
    Calculation,
    CellRef,
    Check,
    EvidenceSpan,
    Program,
    Table,
    TraceStep,
    Verdict,
)
from tabletrace.tools.cells import normalize_text
from tabletrace.tools.numbers import parse_number
from tabletrace.tools.registry import REGISTRY, ToolError

YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


@dataclass
class Resolution:
    status: str                      # answered | abstained
    answer: str | None
    cells: list[CellRef]
    calculation: Calculation | None
    verdict: Verdict
    trace: list[TraceStep] = field(default_factory=list)
    spans: list[EvidenceSpan] = field(default_factory=list)


def _years(s: str) -> set[str]:
    return set(YEAR_RE.findall(s or ""))


def _num_close(a: float, b: float) -> bool:
    if math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9):
        return True
    return math.isclose(a, b, rel_tol=0.01, abs_tol=0.051)   # proposed answers are often rounded


def find_span(answer: str, context: str, passage_id: str = "context") -> EvidenceSpan | None:
    """Locate `answer` in `context` (case/space-insensitive on a NFKC view); returns the original substring."""
    import unicodedata

    def fold(x: str) -> str:
        return unicodedata.normalize("NFKC", x).lower()

    a, c = fold(answer).strip(), fold(context)
    if not a or len(a) > 200:
        return None
    i = c.find(a)
    if i < 0:
        # tolerate whitespace differences by matching on a whitespace-stripped view
        a2, c2 = re.sub(r"\s+", "", a), re.sub(r"\s+", "", c)
        j = c2.find(a2)
        if j < 0:
            return None
        # map j back to an index in c (count non-space chars)
        k = n = 0
        while k < len(c) and n < j:
            if not c[k].isspace():
                n += 1
            k += 1
        i = k
        end = i
        n = 0
        while end < len(c) and n < len(a2):
            if not c[end].isspace():
                n += 1
            end += 1
        return EvidenceSpan(passage_id=passage_id, start=i, end=end, text=context[i:end])
    return EvidenceSpan(passage_id=passage_id, start=i, end=i + len(a), text=context[i:i + len(a)])


def resolve(question: str, table: Table | None, program: Program | None, retrieval_ok: bool = True,
            context: str | None = None, passage_id: str = "context") -> Resolution:
    checks: list[Check] = []
    trace: list[TraceStep] = []

    def abstain(reason: AbstainReason, detail: str) -> Resolution:
        checks.append(Check(name="abstain", passed=True, detail=detail))
        return Resolution("abstained", None, [], None, Verdict(status="abstained", reason=reason, checks=checks), trace)

    if table is None or not retrieval_ok:
        return abstain("retrieval_low", "관련 표를 찾지 못함 / no relevant table retrieved")
    if program is None:
        return abstain("invalid_program", "계획을 해석할 수 없음 / planner output could not be parsed")
    if program.op == "abstain":
        return abstain(program.reason or "not_in_document", "planner abstained")

    if program.op == "text":
        if not context:
            return abstain("not_in_document", "text answer proposed but no passage was available")
        span = find_span(program.answer or "", context, passage_id)
        checks.append(Check(name="answer_in_passage", passed=span is not None,
                            detail=(f"found at [{span.start}:{span.end}]" if span else f"proposed {program.answer!r} not found in the passage")))
        if span is None:
            return abstain("verification_failed", f"text answer {program.answer!r} is not in the retrieved passage")
        return Resolution("answered", span.text, [], None, Verdict(status="answered", checks=checks), trace, [span])

    # 1. cells exist
    bad = [c.cid for c in program.cells if c.row >= table.n_rows or c.col >= table.n_cols]
    checks.append(Check(name="cells_in_range", passed=not bad, detail=f"out of range: {bad}" if bad else f"{len(program.cells)} cell(s) in {table.n_rows}x{table.n_cols}"))
    if bad:
        return abstain("invalid_program", f"cells out of range: {bad}")

    # 2. period consistency (soft): question years vs. evidence row text
    q_years = _years(question)
    if q_years:
        row_years = set()
        for c in program.cells:
            row_years |= _years(" ".join(table.rows[c.row]))
        row_years |= _years(table.title)
        hit = bool(q_years & row_years)
        checks.append(Check(name="period_consistent", passed=hit or not row_years,
                            detail=f"question {sorted(q_years)} vs evidence {sorted(row_years)}"))

    if program.op == "lookup":
        if len(program.cells) != 1:
            return abstain("ambiguous_question", f"lookup with {len(program.cells)} cells")
        c = program.cells[0]
        out = REGISTRY.call("cell_lookup", table, {"row": c.row, "col": c.col}, trace)
        cell_text = out["text"]
        if not cell_text.strip():
            return abstain("not_in_document", f"cell {c.cid} is empty")
        proposed = program.answer or ""
        same = normalize_text(proposed) == normalize_text(cell_text)
        # a proposal may be a *meaningful* part of the cell ("최규하" in "최규하(崔圭夏)"), but a short numeric
        # fragment ("9" in "5,436,789") or a different number is not supported by the cell
        pn, cn = parse_number(proposed), parse_number(cell_text)
        contained = (bool(proposed) and len(normalize_text(proposed)) >= 2 and normalize_text(proposed) in normalize_text(cell_text)
                     and not (pn is not None and cn is not None and abs(pn.value - cn.value) > 1e-9))
        checks.append(Check(name="answer_matches_cell", passed=same,
                            detail=("answer equals cell" if same else
                                    f"proposed {proposed!r} != cell {cell_text!r}; cell text used")))
        if not same and not contained and proposed:
            # The cited cell does not support the answer. Before giving up, look for the answer text in
            # the table: if exactly one cell carries it, that cell is the real evidence and the citation
            # was wrong (recorded as a failed `evidence_repaired` check so the UI and metrics show it).
            found = REGISTRY.call("cell_find", table, {"text": proposed, "exact": True}, trace)
            if len(found) == 1 and len(normalize_text(proposed)) >= 2:
                c2 = found[0]
                checks.append(Check(name="evidence_repaired", passed=False,
                                    detail=f"model cited {c.cid}; the answer text is in {c2.cid} (used as evidence)"))
                return Resolution("answered", table.cell(c2.row, c2.col), [c2], None, Verdict(status="answered", checks=checks), trace)
            return abstain("verification_failed", f"proposed answer {proposed!r} is not supported by cell {c.cid}")
        # the evidence cell is the answer (exact text), even if the proposal was a substring of it
        return Resolution("answered", cell_text, [c], None, Verdict(status="answered", checks=checks), trace)

    # calculations: a program that compares a cell with itself (diff r6c4, r6c4 -> 0) is degenerate
    if len({c.cid for c in program.cells}) < len(program.cells):
        checks.append(Check(name="distinct_cells", passed=False, detail=f"repeated cells in {program.op}: {[c.cid for c in program.cells]}"))
        return abstain("invalid_program", "calculation over repeated cells")
    try:
        calc: Calculation = REGISTRY.call("calculate", table, {"op": program.op, "cells": [c.cid for c in program.cells]}, trace)
    except ToolError as e:
        msg = str(e)
        reason: AbstainReason = "unit_mismatch" if "unit mismatch" in msg else "invalid_program"
        checks.append(Check(name="calculation", passed=False, detail=msg))
        return abstain(reason, msg)
    checks.append(Check(name="calculation", passed=True, detail=f"{calc.expression} = {calc.formatted}"))
    units = {i.unit for i in calc.inputs}
    checks.append(Check(name="units_consistent", passed=len(units) == 1 or program.op in ("ratio", "count"),
                        detail=f"units {sorted(str(u) for u in units)}"))
    if program.answer:
        p = parse_number(program.answer)
        if p is None:
            checks.append(Check(name="answer_matches_calc", passed=False, detail=f"proposed {program.answer!r} is not numeric; computed value used"))
        else:
            ok = _num_close(p.value, calc.result)
            checks.append(Check(name="answer_matches_calc", passed=ok,
                                detail=f"proposed {p.value} vs computed {calc.result}" + ("" if ok else "; computed value used")))
    return Resolution("answered", calc.formatted, list(program.cells), calc, Verdict(status="answered", checks=checks), trace)
