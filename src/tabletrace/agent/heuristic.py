"""A non-neural planner used as (a) the baseline in evaluations and (b) the fallback when no
model is available. It only uses lexical overlap, so it is transparent and cheap."""
from __future__ import annotations

import re

from tabletrace.agent.program import make, make_abstain
from tabletrace.retrieval.tokenize import tokenize
from tabletrace.schema import CellRef, Program, Table
from tabletrace.tools.cells import column_overlap_scores, normalize_text, row_overlap_scores
from tabletrace.tools.numbers import parse_number

CALC_PATTERNS = {
    "diff": re.compile(r"차이|차는|더 많|더 적|더 (길|크|높|낮|짧|무거|가벼)|몇 .{0,6}더|빼면|감소|증가(량|폭)|difference|more than|fewer|less than|increase|decrease|change in|how much (higher|lower|larger|smaller|greater|bigger|longer|heavier)"),
    "sum": re.compile(r"합계|합은|합이|총합|모두 합|더하면|총 |total|sum of|combined|altogether|in total"),
    "avg": re.compile(r"평균|average|mean"),
    "ratio": re.compile(r"비율|몇 배|배인|ratio|times (larger|greater|higher|more)|fold|by what factor"),
    "pct_change": re.compile(r"몇 ?%|퍼센트|percent(age)? change|증가율|감소율|성장률"),
}


def _calc_intent(question: str) -> str | None:
    q = question.lower()
    # ratio / percent / avg first ("by what factor does it increase" is a ratio); diff before sum
    # because 합계/total is often a column name inside a difference question
    for op in ("ratio", "pct_change", "avg", "diff", "sum"):
        if CALC_PATTERNS[op].search(q):
            return op
    return None


def _numeric_cols(table: Table) -> list[int]:
    cols = []
    for c in range(table.n_cols):
        vals = [parse_number(v, table.units.get(c)) for v in table.column(c)]
        if vals and sum(v is not None for v in vals) >= max(2, int(0.6 * len(vals))):
            cols.append(c)
    return cols


def _phrase_bonus(question: str, table: Table, exclude_col: int | None) -> list[float]:
    """+2 for every cell (>=2 chars) that appears verbatim in the question: 'carbon dioxide' beats 'dioxide'."""
    q = normalize_text(question)
    out = []
    for row in table.rows:
        b = 0.0
        for c, v in enumerate(row):
            if exclude_col is not None and c == exclude_col:
                continue
            nv = normalize_text(v)
            if len(nv) >= 2 and nv in q:
                b += 2.0
        out.append(b)
    return out


def plan(question: str, table: Table, lang: str) -> Program:
    toks = set(tokenize(question, lang))
    toks |= {normalize_text(t) for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\.\-]+", question)}
    toks.discard("")
    if not toks:
        return make_abstain("ambiguous_question")
    # single-character tokens (년, 수, 명 ...) are too noisy for matching row cells
    row_toks = {t for t in toks if len(t) >= 2 or t.isdigit()}
    col_scores = column_overlap_scores(table, toks)
    for i, h in enumerate(table.header):
        nh = normalize_text(h)
        if len(nh) >= 2 and any(nh in t and nh != t for t in toks):
            col_scores[i] += 1.0
    best_col = max(range(table.n_cols), key=lambda i: col_scores[i]) if table.n_cols else None
    has_col = best_col is not None and col_scores[best_col] > 0
    intent = _calc_intent(question)
    numeric = _numeric_cols(table)

    if intent in ("diff", "sum", "avg", "ratio", "pct_change"):
        target = best_col if (has_col and best_col in numeric) else (numeric[-1] if numeric else None)
        if target is not None:
            rows = row_overlap_scores(table, row_toks, exclude_col=target)
            rows = [a + b for a, b in zip(rows, _phrase_bonus(question, table, target), strict=True)]
            order = sorted(range(table.n_rows), key=lambda i: -rows[i])
            top = [i for i in order if rows[i] > 0][: (2 if intent != "sum" else 3)]
            if len(top) >= 2:
                # order operands by where their row is mentioned in the question ("X ... than Y" -> X - Y)
                q_norm = normalize_text(question)

                def first_mention(r: int) -> int:
                    pos = [q_norm.find(normalize_text(v)) for v in table.rows[r] if len(normalize_text(v)) >= 2]
                    pos = [x for x in pos if x >= 0]
                    return min(pos) if pos else 10**6

                cells = [CellRef(table_id=table.id, row=r, col=target) for r in sorted(top, key=first_mention)]
                return make(intent, cells, None)  # answer filled by the calculator
        # fewer than two rows mentioned: the "calculation" word was probably a header (e.g. 합계) -> lookup

    excl = best_col if has_col else None
    rows = row_overlap_scores(table, row_toks, exclude_col=excl)
    rows = [a + b for a, b in zip(rows, _phrase_bonus(question, table, excl), strict=True)]
    if not rows or max(rows) == 0:
        return make_abstain("not_in_document")
    best = max(rows)
    cand = [i for i, s in enumerate(rows) if s == best]
    if len(cand) > 1:
        return make_abstain("ambiguous_question")
    r = cand[0]
    if has_col:
        c = best_col
    else:
        # answer column = the column whose header is *not* mentioned and whose cell is not in the question
        unused = [i for i in range(table.n_cols) if not any(t in normalize_text(table.rows[r][i]) for t in row_toks)]
        if len(unused) != 1:
            return make_abstain("ambiguous_question")
        c = unused[0]
    return make("lookup", [CellRef(table_id=table.id, row=r, col=c)], table.cell(r, c))
