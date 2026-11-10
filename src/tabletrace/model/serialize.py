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
"""
from __future__ import annotations

import os

from tabletrace.schema import Table

ROW_SEP = " ; "
COL_SEP = " | "
TABLE_FORMATS = ("plain", "colid")
_table_format = os.environ.get("TABLETRACE_TABLE_FORMAT", "plain")


def set_table_format(name: str) -> None:
    global _table_format
    if name not in TABLE_FORMATS:
        raise ValueError(f"unknown table format {name!r}; choose one of {TABLE_FORMATS}")
    _table_format = name


def get_table_format() -> str:
    if _table_format not in TABLE_FORMATS:      # a bad environment value must not silently fall back
        raise ValueError(f"TABLETRACE_TABLE_FORMAT={_table_format!r}; choose one of {TABLE_FORMATS}")
    return _table_format


def table_to_text(table: Table, max_rows: int | None = None, table_format: str | None = None) -> str:
    fmt = table_format or get_table_format()
    if fmt not in TABLE_FORMATS:
        raise ValueError(f"unknown table format {fmt!r}; choose one of {TABLE_FORMATS}")
    rows = table.rows if max_rows is None else table.rows[:max_rows]
    if fmt == "colid":
        def cells(values) -> str:
            return COL_SEP.join(f"c{j} {(v or '').strip()}".rstrip() for j, v in enumerate(values))
    else:
        def cells(values) -> str:
            return COL_SEP.join((v or "").strip() for v in values)
    body = ROW_SEP.join(f"r{i}: " + cells(r) for i, r in enumerate(rows))
    return f"header: {cells(table.header)}{ROW_SEP}{body}"


def build_input(question: str, table: Table, context: str | None = None, max_rows: int | None = None) -> str:
    parts = [f"question: {question.strip()}", f"title: {table.title.strip()}"]
    if context:
        parts.append(f"context: {context.strip()}")
    parts.append("table: " + table_to_text(table, max_rows))
    return " ".join(parts)


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
