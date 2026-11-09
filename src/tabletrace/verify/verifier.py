import math
import re
import unicodedata
from dataclasses import dataclass, field

from tabletrace.retrieval.tokenize import entity_tokens, tokenize
from tabletrace.schema import Calculation, CellRef, Check, EvidenceSpan, TraceStep, Verdict
from tabletrace.tools.cells import normalize_text
from tabletrace.tools.numbers import parse_number
from tabletrace.tools.registry import REGISTRY, ToolError


@dataclass
class Resolution:
    status: str
    answer: str | None
    cells: list[CellRef]
    calculation: Calculation | None
    verdict: Verdict
    trace: list[TraceStep] = field(default_factory=list)
    spans: list[EvidenceSpan] = field(default_factory=list)


def _years(text):
    return set(re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", text))


def _close(a, b):
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9) or math.isclose(a, b, rel_tol=0.01, abs_tol=0.051)


def _compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or "")).lower()


def find_span(answer, context, passage_id="context"):
    needle = unicodedata.normalize("NFKC", answer or "").lower().strip()
    haystack = unicodedata.normalize("NFKC", context or "").lower()
    if not needle or len(needle) > 200:
        return None
    start = haystack.find(needle)
    if start >= 0:
        end = start + len(needle)
        return EvidenceSpan(passage_id=passage_id, start=start, end=end, text=context[start:end])
    positions = [i for i, c in enumerate(haystack) if not c.isspace()]
    compact_needle = re.sub(r"\s+", "", needle)
    compact_haystack = "".join(haystack[i] for i in positions)
    index = compact_haystack.find(compact_needle)
    if index < 0 or not compact_needle:
        return None
    start = positions[index - 1] + 1 if index else 0
    end = positions[index + len(compact_needle) - 1] + 1
    return EvidenceSpan(passage_id=passage_id, start=start, end=end, text=context[start:end])


def _mentions(text, entity):
    if entity in text:
        return True
    pairs = {entity[i:i + 2] for i in range(len(entity) - 1)}
    return len(pairs) >= 2 and sum(pair in text for pair in pairs) / len(pairs) >= 0.5


def subject_check(question, table, cells, context=None):
    entities = entity_tokens(question, table.lang)
    if not entities or not cells:
        return None, None
    title = _compact(" ".join([table.title, table.caption or "", *table.header]))
    subjects = [_compact(e) for e in entities if _compact(e) not in title]
    if not subjects:
        return None, None
    rows = sorted({c.row for c in cells})
    evidence = _compact(" ".join(" ".join(table.rows[r]) for r in rows if 0 <= r < len(table.rows)) + " " + (context or ""))
    if any(_mentions(evidence, subject) for subject in subjects):
        return Check(name="subject_in_evidence", passed=True, detail="질문 대상이 근거에 있습니다."), None
    all_rows = _compact(" ".join(" ".join(row) for row in table.rows))
    in_table = any(_mentions(all_rows, subject) for subject in subjects)
    reason = "verification_failed" if in_table else "not_in_document"
    location = "다른 행에는 있음" if in_table else "표에 없음"
    return Check(name="subject_in_evidence", passed=False, detail=f"질문 대상 {', '.join(subjects)}: 인용 행 {rows}에서 찾지 못함 ({location})."), reason


def header_column(question, table, cited):
    query = _compact(question)
    query_tokens = set(tokenize(question, table.lang))
    scores = {}
    for col, header in enumerate(table.header):
        name = _compact(header)
        if not name:
            continue
        if len(name) >= 2 and name in query:
            scores[col] = 1.0
        else:
            tokens = set(tokenize(header, table.lang))
            if tokens:
                ratio = len(tokens & query_tokens) / len(tokens)
                if ratio >= 0.5:
                    scores[col] = ratio
    if not scores or cited in scores:
        return None
    best = max(scores.values())
    columns = [col for col, score in scores.items() if score == best]
    return columns[0] if len(columns) == 1 else None


def resolve(question, table, program, retrieval_ok=True, context=None, passage_id="context", entity_check=True, column_check=False):
    checks = []
    trace = []

    def check(name, passed, detail):
        checks.append(Check(name=name, passed=passed, detail=detail))

    def abstain(reason):
        reasons = {
            "retrieval_low": "표가 없거나 검색 결과가 충분하지 않아 보류합니다.",
            "invalid_program": "프로그램 또는 근거 셀이 유효하지 않아 보류합니다.",
            "not_in_document": "필요한 답이나 근거를 문서에서 찾지 못해 보류합니다.",
            "ambiguous_question": "근거를 하나로 정할 수 없어 보류합니다.",
            "verification_failed": "제안한 답이나 근거를 확인하지 못해 보류합니다.",
            "unit_mismatch": "입력 단위가 서로 달라 계산을 보류합니다.",
            "timeout": "처리 시간이 초과되어 보류합니다.",
        }
        check("abstain", True, reasons.get(reason, f"사유 {reason}으로 보류합니다."))
        return Resolution("abstained", None, [], None, Verdict(status="abstained", reason=reason, checks=checks), trace)

    def answered(answer, cells=None, calculation=None, spans=None):
        return Resolution("answered", answer, cells or [], calculation, Verdict(status="answered", checks=checks), trace, spans or [])

    def decide():
        if table is None or not retrieval_ok:
            return abstain("retrieval_low")
        if program is None:
            return abstain("invalid_program")
        if program.op == "abstain":
            return abstain(program.reason or "not_in_document")
        if program.op == "text":
            if not context:
                return abstain("not_in_document")
            span = find_span(program.answer or "", context, passage_id)
            check("answer_in_passage", span is not None, "본문에서 답을 확인합니다.")
            if span is None:
                return abstain("verification_failed")
            return answered(span.text, spans=[span])

        cells = program.cells
        outside = [c.cid for c in cells if c.row >= len(table.rows) or c.col >= len(table.header)]
        valid = not outside
        detail = f"범위 밖 셀: {', '.join(outside)}" if outside else f"셀 {len(cells)}개, 표 크기 {len(table.rows)}×{len(table.header)}"
        check("cells_in_range", valid, detail)
        if not valid:
            return abstain("invalid_program")
        question_years = _years(question)
        if question_years:
            evidence_years = _years(table.title + " " + " ".join(" ".join(table.rows[c.row]) for c in cells))
            check("period_consistent", not evidence_years or bool(question_years & evidence_years),
                  f"질문 연도: {sorted(question_years)}, 근거 연도: {sorted(evidence_years)}")

        if program.op == "lookup":
            if len(cells) != 1:
                return abstain("ambiguous_question")
            ref = cells[0]
            value = REGISTRY.call("cell_lookup", table, {"row": ref.row, "col": ref.col}, trace)["text"]
            if not value.strip():
                return abstain("not_in_document")
            if column_check:
                column = header_column(question, table, ref.col)
                if column is not None and table.cell(ref.row, column).strip():
                    corrected = CellRef(table_id=table.id, row=ref.row, col=column)
                    check("column_repaired", False, f"인용 셀 {ref.cid} → {corrected.cid} (열: {table.header[column]})")
                    return answered(table.cell(ref.row, column), [corrected])
            proposed = normalize_text(program.answer or "")
            cell_text = normalize_text(value)
            same = proposed == cell_text
            contained = bool(proposed) and len(proposed) >= 2 and proposed in cell_text
            if contained:
                a = parse_number(program.answer)
                b = parse_number(value)
                if a is not None and b is not None and abs(a.value - b.value) > 1e-9:
                    contained = False
            check("answer_matches_cell", same, f"제안 답: {program.answer!r}, 셀 {ref.cid}: {value!r}")
            if not same and not contained and proposed:
                found = REGISTRY.call("cell_find", table, {"text": program.answer, "exact": True}, trace)
                if len(found) == 1 and len(proposed) >= 2:
                    replacement = found[0]
                    check("evidence_repaired", False, f"인용 셀 {ref.cid} → 답과 일치하는 셀 {replacement.cid}")
                    return answered(table.cell(replacement.row, replacement.col), [replacement])
                return abstain("verification_failed")
            return answered(value, cells)

        if len({c.cid for c in cells}) != len(cells):
            check("distinct_cells", False, "중복 셀이 있습니다.")
            return abstain("invalid_program")
        try:
            calc = REGISTRY.call("calculate", table, {"op": program.op, "cells": [c.cid for c in cells]}, trace)
        except ToolError as exc:
            check("calculation", False, str(exc))
            return abstain("unit_mismatch" if "unit mismatch" in str(exc) else "invalid_program")
        check("calculation", True, f"{calc.expression} = {calc.formatted}")
        units_ok = len({item.unit for item in calc.inputs}) == 1 or program.op in ("ratio", "count")
        check("units_consistent", units_ok, f"입력 단위: {[item.unit for item in calc.inputs]}")
        if program.answer:
            proposed = parse_number(program.answer)
            check("answer_matches_calc", proposed is not None and _close(proposed.value, calc.result),
                  f"제안 답: {program.answer!r}, 계산 값: {calc.result} ({calc.formatted})")
        return answered(calc.formatted, cells, calc)

    result = decide()
    if entity_check and result.status == "answered" and result.cells and table is not None:
        subject, reason = subject_check(question, table, result.cells, context)
        if subject is not None:
            result.verdict.checks.append(subject)
            if reason is not None:
                result.verdict.checks.append(Check(name="abstain", passed=True, detail=f"질문 대상이 근거와 맞지 않아 보류합니다 (사유: {reason})."))
                return Resolution("abstained", None, [], None, Verdict(status="abstained", reason=reason, checks=result.verdict.checks), result.trace)
    return result
