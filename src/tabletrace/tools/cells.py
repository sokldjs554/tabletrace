import unicodedata

from tabletrace.schema import CellRef, Table


def normalize_text(s: str) -> str:
    text = unicodedata.normalize("NFKC", s or "")
    text = text.replace("−", "-").replace("–", "-")
    return " ".join(text.split()).lower()


def lookup_cell(table: Table, row: int, col: int) -> dict:
    value = table.cell(row, col)
    return {
        "cell": CellRef(table_id=table.id, row=row, col=col).cid,
        "text": value,
        "header": table.header[col],
        "row_label": table.rows[row][0] if table.rows[row] else "",
        "unit": table.units.get(col),
    }


def find_cells(table: Table, text: str, exact: bool = True) -> list[CellRef]:
    query = normalize_text(text)
    if not query:
        return []
    found = []
    for row in range(len(table.rows)):
        for col in range(len(table.header)):
            value = normalize_text(table.cell(row, col))
            if (value == query) if exact else (query in value):
                found.append(CellRef(table_id=table.id, row=row, col=col))
    return found


def row_overlap_scores(table: Table, tokens: list[str], exclude_col: int | None = None) -> list[float]:
    scores = []
    for row in table.rows:
        score = 0
        for col, cell in enumerate(row):
            if col != exclude_col:
                value = normalize_text(cell)
                score += sum(1 for token in tokens if token and token in value)
        scores.append(float(score))
    return scores


def column_overlap_scores(table: Table, tokens: list[str]) -> list[float]:
    scores = []
    for header in table.header:
        value = normalize_text(header)
        scores.append(float(sum(1 for token in tokens if token and token in value)))
    return scores
