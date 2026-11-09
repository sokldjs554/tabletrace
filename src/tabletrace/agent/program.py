import re
from typing import cast

from tabletrace.schema import AbstainReason, CellRef, Op, Program

OPS = ("lookup", "text", "diff", "ratio", "sum", "avg", "count", "pct_change", "abstain")
REASONS = (
    "not_in_document", "ambiguous_question", "unit_mismatch", "verification_failed",
    "retrieval_low", "invalid_program", "timeout",
)


class ProgramParseError(ValueError):
    pass


def serialize(p: Program) -> str:
    if p.op == "abstain":
        return f"op: abstain ; cells: - ; answer: - ; reason: {p.reason or 'not_in_document'}"
    if p.op == "text":
        return f"op: text ; cells: - ; answer: {p.answer or '-'}"
    cells = ", ".join(cell.cid for cell in p.cells) or "-"
    answer = p.answer if p.answer is not None else "-"
    return f"op: {p.op} ; cells: {cells} ; answer: {answer}"


def parse(text: str, table_id: str) -> Program:
    cleaned = (text or "").replace("<pad>", "").replace("</s>", "").strip()
    if not cleaned or len(cleaned) > 400:
        raise ProgramParseError("invalid program length")

    matches = list(re.finditer(r"(op|cells|answer|reason)\s*:\s*", cleaned))
    if not matches or matches[0].start() != 0:
        raise ProgramParseError("program must begin with a field")
    fields: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1)
        if name in fields:
            raise ProgramParseError("duplicate field")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        fields[name] = cleaned[match.end():end].strip().rstrip(";").strip()

    op = fields.get("op")
    if op not in OPS:
        raise ProgramParseError("invalid op")
    if op == "abstain":
        reason = fields.get("reason")
        if reason not in REASONS:
            reason = "not_in_document"
        return Program(op="abstain", cells=[], answer=None, reason=cast(AbstainReason, reason))

    cells = []
    raw_cells = fields.get("cells", "")
    if raw_cells and raw_cells != "-":
        for item in raw_cells.split(","):
            if item.strip():
                try:
                    cells.append(CellRef.parse(table_id, item.strip()))
                except ValueError as exc:
                    raise ProgramParseError("invalid cell") from exc

    answer = fields.get("answer") or None
    if answer == "-":
        answer = None
    if op == "text":
        if answer is None:
            raise ProgramParseError("text requires answer")
        return Program(op="text", cells=[], answer=answer)
    if not cells or len(cells) > 12:
        raise ProgramParseError("invalid number of cells")
    return Program(op=cast(Op, op), cells=cells, answer=answer)


def make_abstain(reason: AbstainReason) -> Program:
    return Program(op="abstain", cells=[], answer=None, reason=reason)


def make(op: Op, cells: list[CellRef], answer: str | None = None) -> Program:
    return Program(op=op, cells=cells, answer=answer)
