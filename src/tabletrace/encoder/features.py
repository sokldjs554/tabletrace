"""Turn (question, table) into model inputs that keep the table's structure.

Token layout (SEP is the tokenizer's separator, or its end-of-sequence token when it has none):

    [CLS] question SEP title SEP h0 | h1 | ... SEP r0c0 | r0c1 | ... SEP r1c0 | ... SEP

Every token also carries
    row id   0 for the question, the title and the header row; i + 1 for data row i
    col id   0 for the question and the title; j + 1 for column j (header cells included)
    cell     index of the data cell the token belongs to (row-major, i * n_cols + j), or -1

The separators stay in the text on purpose: a model without structure embeddings sees exactly the same tokens, so
switching the embeddings on or off is the only difference between the two settings.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tabletrace.schema import Table

CELL_TOKEN_BUDGETS = (12, 8, 6, 4, 3)   # tried in order until the table fits


@dataclass
class Features:
    input_ids: list[int]
    row_ids: list[int]
    col_ids: list[int]
    cell_index: list[int]
    n_rows: int                 # data rows that fit (trailing rows are dropped when even the smallest budget is too long)
    n_cols: int
    cell_tokens: int            # per-cell token budget that was used
    dropped_rows: int = 0
    meta: dict = field(default_factory=dict)

    @property
    def n_cells(self) -> int:
        return self.n_rows * self.n_cols

    def cell_of(self, row: int, col: int) -> int | None:
        """Index of data cell (row, col) among the scored cells, or None when the row was dropped."""
        return row * self.n_cols + col if row < self.n_rows and col < self.n_cols else None

    def position(self, cell: int) -> tuple[int, int]:
        return divmod(cell, self.n_cols)


class Featurizer:
    def __init__(self, tokenizer, max_len: int = 512, max_question_tokens: int = 64, max_title_tokens: int = 24) -> None:
        self.tok = tokenizer
        self.max_len = max_len
        self.max_q, self.max_title = max_question_tokens, max_title_tokens
        self.cls = tokenizer.cls_token_id
        self.sep = tokenizer.sep_token_id if tokenizer.sep_token_id is not None else tokenizer.eos_token_id
        if self.sep is None:
            raise ValueError("the tokenizer has neither a separator nor an end-of-sequence token")
        self.bar = self._ids("|")[:1]
        self._cache: dict[str, list[int]] = {}

    def _ids(self, text: str) -> list[int]:
        return self.tok(text, add_special_tokens=False)["input_ids"]

    def _cell(self, text: str) -> list[int]:
        ids = self._cache.get(text)
        if ids is None:
            ids = self._ids(text.strip() or "-")
            self._cache[text] = ids
        return ids

    def __call__(self, question: str, table: Table) -> Features:
        n_cols = len(table.header)
        q = self._ids(question)[: self.max_q]
        title = self._ids(table.title or "")[: self.max_title]
        for budget in CELL_TOKEN_BUDGETS:
            feats = self._build(q, title, table, n_cols, budget, len(table.rows))
            if len(feats.input_ids) <= self.max_len:
                return feats
        rows = len(table.rows)
        while rows > 1:                      # still too long: drop trailing rows (the caller sees dropped_rows)
            rows -= 1
            feats = self._build(q, title, table, n_cols, CELL_TOKEN_BUDGETS[-1], rows)
            if len(feats.input_ids) <= self.max_len:
                return feats
        raise ValueError(f"table {table.id} does not fit in {self.max_len} tokens even with one row")

    def _build(self, q: list[int], title: list[int], table: Table, n_cols: int, budget: int, n_rows: int) -> Features:
        ids: list[int] = []
        rows: list[int] = []
        cols: list[int] = []
        cells: list[int] = []

        def put(tokens: list[int], row: int, col: int, cell: int) -> None:
            ids.extend(tokens)
            rows.extend([row] * len(tokens))
            cols.extend([col] * len(tokens))
            cells.extend([cell] * len(tokens))

        if self.cls is not None:
            put([self.cls], 0, 0, -1)
        put(q, 0, 0, -1)
        put([self.sep], 0, 0, -1)
        if title:
            put(title, 0, 0, -1)
            put([self.sep], 0, 0, -1)
        for j, h in enumerate(table.header):
            if j:
                put(self.bar, 0, 0, -1)
            put(self._cell(h)[:budget], 0, j + 1, -1)
        put([self.sep], 0, 0, -1)
        for i in range(n_rows):
            row = table.rows[i]
            for j in range(n_cols):
                if j:
                    put(self.bar, 0, 0, -1)
                put(self._cell(row[j] if j < len(row) else "")[:budget], i + 1, j + 1, i * n_cols + j)
            put([self.sep], 0, 0, -1)
        return Features(ids, rows, cols, cells, n_rows, n_cols, budget, dropped_rows=len(table.rows) - n_rows)


def collate(batch: list[Features], pad_id: int, targets: list[int] | None = None, cell_labels: list[list[int]] | None = None) -> dict:
    """Pad a list of Features into tensors. `targets` are gold cell indices (cell selection); `cell_labels` are 0/1 per
    cell (corrupt-cell detection)."""
    import torch

    n = max(len(f.input_ids) for f in batch)
    m = max(f.n_cells for f in batch)

    def pad(seq: list[int], fill: int) -> list[int]:
        return seq + [fill] * (n - len(seq))

    out = {
        "input_ids": torch.tensor([pad(f.input_ids, pad_id) for f in batch]),
        "attention_mask": torch.tensor([pad([1] * len(f.input_ids), 0) for f in batch]),
        "row_ids": torch.tensor([pad(f.row_ids, 0) for f in batch]),
        "col_ids": torch.tensor([pad(f.col_ids, 0) for f in batch]),
        "cell_index": torch.tensor([pad(f.cell_index, -1) for f in batch]),
        "cell_mask": torch.tensor([[1] * f.n_cells + [0] * (m - f.n_cells) for f in batch], dtype=torch.bool),
    }
    if targets is not None:
        out["targets"] = torch.tensor(targets)
    if cell_labels is not None:
        out["cell_labels"] = torch.tensor([lab + [0] * (m - len(lab)) for lab in cell_labels], dtype=torch.float)
    return out
