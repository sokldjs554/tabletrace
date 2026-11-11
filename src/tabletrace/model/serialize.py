"""Turn (question, table, optional context) into the model input string, with a row budget so
inputs stay within `max_tokens`. The format is language-neutral and mirrors the console's
r/c cell ids so the model's evidence ids map 1:1 to what the user sees.

Two table formats:

  plain   header: 연도 | 방송사 | 제목 ; r0: 2011 | MBC | 놀러와 ; r1: ...
          Rows carry their index; the column index of a cell has to be counted from the separators.
  colid   header: c0 연도 | c1 방송사 | c2 제목 ; r0: c0 2011 | c1 MBC | c2 놀러와 ; r1: ...
          Every cell carries its column index, so the id `r0c2` can be read off next to the value.

`plain` is the format every stored result was produced with and stays the default. A model must be served with the
format it was trained on, so the choice is one process-wide setting: the environment variable
TABLETRACE_TABLE_FORMAT, or `set_table_format()` (the training / evaluation scripts expose it as --table-format).

Which rows are shown when a table does not fit the input budget is a second setting (TABLETRACE_ROW_SELECT,
`set_row_select()`, --row-select):

  first     the first rows that fit (every stored result up to 2026-11-10)
  overlap   the rows that share the most words with the question, in table order. Rows keep their original index
            ("r0: ... ; r7: ... ; r12: ..."), so a cited cell id needs no translation.
"""
from __future__ import annotations

import os

from tabletrace.schema import Table

ROW_SEP = " ; "
COL_SEP = " | "
TABLE_FORMATS = ("plain", "colid")
ROW_SELECTS = ("first", "overlap")
_table_format = os.environ.get("TABLETRACE_TABLE_FORMAT", "plain")
_row_select = os.environ.get("TABLETRACE_ROW_SELECT", "first")


def set_row_select(name: str) -> None:
    global _row_select
    if name not in ROW_SELECTS:
        raise ValueError(f"unknown row selection {name!r}; choose one of {ROW_SELECTS}")
    _row_select = name


def get_row_select() -> str:
    if _row_select not in ROW_SELECTS:
        raise ValueError(f"TABLETRACE_ROW_SELECT={_row_select!r}; choose one of {ROW_SELECTS}")
    return _row_select


def set_table_format(name: str) -> None:
    global _table_format
    if name not in TABLE_FORMATS:
        raise ValueError(f"unknown table format {name!r}; choose one of {TABLE_FORMATS}")
    _table_format = name


def get_table_format() -> str:
    if _table_format not in TABLE_FORMATS:      # a bad environment value must not silently fall back
        raise ValueError(f"TABLETRACE_TABLE_FORMAT={_table_format!r}; choose one of {TABLE_FORMATS}")
    return _table_format


def table_to_text(table: Table, max_rows: int | None = None, table_format: str | None = None, rows: list[int] | None = None) -> str:
    """`rows`: indices of the rows to show (in the given order, with their original labels); overrides `max_rows`."""
    fmt = table_format or get_table_format()
    if fmt not in TABLE_FORMATS:
        raise ValueError(f"unknown table format {fmt!r}; choose one of {TABLE_FORMATS}")
    shown = list(rows) if rows is not None else list(range(table.n_rows if max_rows is None else min(max_rows, table.n_rows)))
    if fmt == "colid":
        def cells(values) -> str:
            return COL_SEP.join(f"c{j} {(v or '').strip()}".rstrip() for j, v in enumerate(values))
    else:
        def cells(values) -> str:
            return COL_SEP.join((v or "").strip() for v in values)
    body = ROW_SEP.join(f"r{i}: " + cells(table.rows[i]) for i in shown)
    return f"header: {cells(table.header)}{ROW_SEP}{body}"


def build_input(question: str, table: Table, context: str | None = None, max_rows: int | None = None, rows: list[int] | None = None) -> str:
    parts = [f"question: {question.strip()}", f"title: {table.title.strip()}"]
    if context:
        parts.append(f"context: {context.strip()}")
    parts.append("table: " + table_to_text(table, max_rows, rows=rows))
    return " ".join(parts)


def row_scores(question: str, table: Table) -> list[float]:
    """How much each row has to do with the question: for every content word of the question that occurs in the row,
    1 / (number of rows it occurs in). A word found in one row counts fully, a word found in every row hardly at all."""
    from tabletrace.retrieval.tokenize import tokenize
    from tabletrace.tools.cells import normalize_text

    words = [w for w in dict.fromkeys(normalize_text(t) for t in tokenize(question, table.lang)) if len(w) >= 2 or w.isdigit()]
    texts = [normalize_text(" ".join(r)) for r in table.rows]
    scores = [0.0] * len(texts)
    for w in words:
        hits = [i for i, t in enumerate(texts) if w in t]
        for i in hits:
            scores[i] += 1.0 / len(hits)
    return scores


def choose_rows(tokenizer, question: str, table: Table, context: str | None, max_tokens: int,
                strategy: str | None = None) -> tuple[str | None, list[int]]:
    """-> (context actually used, indices of the rows to show, ascending). With strategy `first`, or whenever the whole
    table fits, this is the prefix `choose_context_and_rows` gives. With `overlap`, rows are added by `row_scores`
    (ties: table order) until the budget is full."""
    ctx, n = choose_context_and_rows(tokenizer, question, table, context, max_tokens)
    if (strategy or get_row_select()) == "first" or n >= table.n_rows:
        return ctx, list(range(n))
    scores = row_scores(question, table)
    order = sorted(range(table.n_rows), key=lambda i: (-scores[i], i))

    def size(rows: list[int]) -> int:
        return len(tokenizer(build_input(question, table, ctx, rows=sorted(rows))).input_ids)

    kept: list[int] = []
    for i in order:                              # one tokenizer call per row: exact, and tables here have tens of rows
        if size([*kept, i]) <= max_tokens:
            kept.append(i)
    return ctx, sorted(kept)


def masked(table: Table, rows: list[int]) -> Table:
    """The table as the model saw it, at full size: rows that were not shown are blank. A cited cell in a hidden row
    then fails verification, as a cell beyond a truncated table always did."""
    keep = set(rows)
    return table.model_copy(update={"rows": [r if i in keep else [""] * len(r) for i, r in enumerate(table.rows)]})


def fit_rows(tokenizer, question: str, table: Table, context: str | None, max_tokens: int) -> int:
    """Largest number of rows whose serialization fits in max_tokens (binary search)."""
    lo, hi = 0, table.n_rows
    while lo < hi:
        mid = (lo + hi + 1) // 2
        n = len(tokenizer(build_input(question, table, context, max_rows=mid)).input_ids)
        if n <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    return lo


def choose_context_and_rows(tokenizer, question: str, table: Table, context: str | None, max_tokens: int,
                            context_steps: tuple[int, ...] = (300, 150, 0)) -> tuple[str | None, int]:
    """Prefer showing the whole table: shrink the passage (300 -> 150 -> none chars) before cutting rows.
    Returns (context actually used, rows kept)."""
    best: tuple[str | None, int] | None = None
    for limit in context_steps:
        ctx = (context[:limit] if (context and limit) else None)
        n = fit_rows(tokenizer, question, table, ctx, max_tokens)
        if n >= table.n_rows:
            return ctx, n
        if best is None or n > best[1]:
            best = (ctx, n)
    return best if best is not None else (None, 0)
