"""Cell-level tools: lookup, text search inside a table, and row/column matching helpers."""
from __future__ import annotations

import re
import unicodedata

from tabletrace.schema import CellRef, Table


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("−", "-").replace("–", "-")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def lookup_cell(table: Table, row: int, col: int) -> dict:
    """Return the cell text plus its row label and column header so the UI can show context."""
    text = table.cell(row, col)
    return {
        "cell": CellRef(table_id=table.id, row=row, col=col).cid,
        "text": text,
        "header": table.header[col],
        "row_label": table.rows[row][0] if table.rows[row] else "",
        "unit": table.units.get(col),
    }


def find_cells(table: Table, text: str, exact: bool = True) -> list[CellRef]:
    """All cells whose normalized text equals (or contains) `text`."""
    q = normalize_text(text)
    if not q:
        return []
    out = []
    for r, row in enumerate(table.rows):
        for c in range(len(table.header)):
            v = normalize_text(row[c] if c < len(row) else "")
            if (v == q) if exact else (q in v):
                out.append(CellRef(table_id=table.id, row=r, col=c))
    return out


def row_overlap_scores(table: Table, tokens: set[str], exclude_col: int | None = None) -> list[float]:
    """Score each row by how many question tokens appear in its cells (used by the heuristic planner)."""
    scores = []
    for row in table.rows:
        hits = 0
        for c, v in enumerate(row):
            if exclude_col is not None and c == exclude_col:
                continue
            nv = normalize_text(v)
            hits += sum(1 for t in tokens if t and t in nv)
        scores.append(float(hits))
    return scores


def column_overlap_scores(table: Table, tokens: set[str]) -> list[float]:
    scores = []
    for h in table.header:
        nh = normalize_text(h)
        scores.append(float(sum(1 for t in tokens if t and t in nh)))
    return scores
