"""The planner's structured output: `op: <op> ; cells: r1c2, r3c2 ; answer: <text>`.

The same grammar is used as the SFT target, parsed from neural output, and emitted by the
heuristic planner, so the verifier and the console never depend on which planner produced it.
"""
from __future__ import annotations

import re

from tabletrace.schema import AbstainReason, CellRef, Op, Program

OPS: tuple[str, ...] = ("lookup", "text", "diff", "ratio", "sum", "avg", "count", "pct_change", "abstain")
REASONS: tuple[str, ...] = ("not_in_document", "ambiguous_question", "unit_mismatch", "verification_failed",
                            "retrieval_low", "invalid_program", "timeout")
_FIELD_RE = re.compile(r"(op|cells|answer|reason)\s*:\s*")


class ProgramParseError(ValueError):
    pass


def serialize(p: Program) -> str:
    cells = ", ".join(c.cid for c in p.cells) if p.cells else "-"
    if p.op == "abstain":
        return f"op: abstain ; cells: - ; answer: - ; reason: {p.reason or 'not_in_document'}"
    if p.op == "text":
        return f"op: text ; cells: - ; answer: {p.answer if p.answer else '-'}"
    return f"op: {p.op} ; cells: {cells} ; answer: {p.answer if p.answer is not None else '-'}"


def parse(text: str, table_id: str) -> Program:
    """Strict parser. Raises ProgramParseError on anything unexpected (no partial guesses)."""
    s = (text or "").replace("<pad>", "").replace("</s>", "").strip()
    if len(s) > 400 or not s:
        raise ProgramParseError("empty or oversized output")
    fields: dict[str, str] = {}
    matches = list(_FIELD_RE.finditer(s))
    if not matches or matches[0].start() != 0:
        raise ProgramParseError("output does not start with a field")
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(s)
        val = s[m.end():end].strip().rstrip(";").strip()
        key = m.group(1)
        if key in fields:
            raise ProgramParseError(f"duplicate field {key}")
        fields[key] = val
    op = fields.get("op")
    if op not in OPS:
        raise ProgramParseError(f"unknown op {op!r}")
    if op == "abstain":
        reason = fields.get("reason", "not_in_document")
        if reason not in REASONS:
            reason = "not_in_document"
        return Program(op="abstain", cells=[], answer=None, reason=reason)  # type: ignore[arg-type]
    raw_cells = fields.get("cells", "-")
    cells: list[CellRef] = []
    if raw_cells not in ("-", ""):
        for tok in raw_cells.split(","):
            tok = tok.strip()
            if not tok:
                continue
            try:
                cells.append(CellRef.parse(table_id, tok))
            except ValueError:
                raise ProgramParseError(f"bad cell id {tok!r}") from None
    answer = fields.get("answer")
    if answer in (None, "", "-"):
        answer = None
    if op == "text":
        if not answer:
            raise ProgramParseError("text op needs an answer span")
        return Program(op="text", cells=[], answer=answer)
    if not cells:
        raise ProgramParseError("no cells for a non-abstain op")
    if len(cells) > 12:
        raise ProgramParseError("too many cells")
    return Program(op=op, cells=cells, answer=answer)  # type: ignore[arg-type]


def make_abstain(reason: AbstainReason) -> Program:
    return Program(op="abstain", cells=[], answer=None, reason=reason)


def make(op: Op, cells: list[CellRef], answer: str | None) -> Program:
    return Program(op=op, cells=cells, answer=answer)
