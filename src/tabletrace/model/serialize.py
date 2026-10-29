"""Turn (question, table, optional context) into the model input string, with a row budget so
inputs stay within `max_tokens`. The format is language-neutral and mirrors the console's
r/c cell ids so the model's evidence ids map 1:1 to what the user sees."""
from __future__ import annotations

from tabletrace.schema import Table

ROW_SEP = " ; "
COL_SEP = " | "


def table_to_text(table: Table, max_rows: int | None = None) -> str:
    header = COL_SEP.join(h.strip() for h in table.header)
    rows = table.rows if max_rows is None else table.rows[:max_rows]
    body = ROW_SEP.join(f"r{i}: " + COL_SEP.join((c or "").strip() for c in r) for i, r in enumerate(rows))
    return f"header: {header}{ROW_SEP}{body}"


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
