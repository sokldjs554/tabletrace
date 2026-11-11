"""Self-supervised pretraining data for the table encoder: corrupt-cell detection.

A fraction of the data cells is replaced and the model must say, for every cell, whether it was replaced. No question
and no label is needed, only tables. Two kinds of replacement, half each:

    other_column   the text of a cell from a different column of the same table  (right table, wrong column)
    other_table    the text of a cell from another table                         (wrong table)

A replacement that happens to equal the original text is skipped, so a positive label always marks a real change.
The idea follows ELECTRA's replaced-token detection, applied to whole cells as in TABBIE (Iida et al., NAACL 2021).
"""
from __future__ import annotations

import random

from tabletrace.schema import Table


def corrupt_table(table: Table, pool: list[str], rng: random.Random, rate: float = 0.15) -> tuple[Table, list[int]]:
    """-> (table with some cells replaced, 0/1 label per data cell in row-major order)."""
    n_rows, n_cols = len(table.rows), len(table.header)
    rows = [list(r) + [""] * (n_cols - len(r)) for r in table.rows]
    labels = [0] * (n_rows * n_cols)
    if n_rows == 0 or n_cols == 0:
        return table, labels
    k = max(1, round(rate * n_rows * n_cols))
    for cell in rng.sample(range(n_rows * n_cols), min(k, n_rows * n_cols)):
        i, j = divmod(cell, n_cols)
        original = table.rows[i][j] if j < len(table.rows[i]) else ""
        if n_cols > 1 and rng.random() < 0.5:
            jj = rng.choice([c for c in range(n_cols) if c != j])
            ii = rng.randrange(n_rows)
            new = table.rows[ii][jj] if jj < len(table.rows[ii]) else ""
        else:
            new = rng.choice(pool)
        if new.strip() and new.strip() != original.strip():
            rows[i][j] = new
            labels[cell] = 1
    return table.model_copy(update={"rows": rows}), labels


def cell_pool(tables: list[Table], limit: int = 200_000) -> list[str]:
    cells = [c for t in tables for r in t.rows for c in r if c.strip()]
    return cells[:limit]
