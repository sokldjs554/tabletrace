"""The table encoder as a second opinion on a lookup answer.

The verifier checks that an answer and its evidence cell agree with each other; a consistently wrong proposal (a
plausible cell in the wrong row) passes. The encoder never sees the proposal. It scores every cell from the question
and the table alone, so when its best cell is somewhere else, two independent readers disagree and the answer is
withheld.

    mode "row"   the encoder's best cell must be in the evidence row      (keeps more answers)
    mode "cell"  the encoder's best cell must be the evidence cell        (stricter)

Measured on stored predictions in scripts/encoder_agreement.py.
"""
from __future__ import annotations

from pathlib import Path

from tabletrace.schema import CellRef, Table

MODES = ("row", "cell")


class SecondOpinion:
    def __init__(self, model_dir: str | Path, mode: str = "row", backbone: str | Path | None = None, max_len: int = 512) -> None:
        import json

        import torch
        from transformers import AutoTokenizer

        from tabletrace.encoder.features import Featurizer
        from tabletrace.encoder.model import TableEncoder

        if mode not in MODES:
            raise ValueError(f"unknown second-opinion mode {mode!r}; choose one of {MODES}")
        self.mode = mode
        meta = json.loads((Path(model_dir) / "table_encoder.json").read_text(encoding="utf-8"))
        backbone = backbone or meta["backbone"]
        self.model = TableEncoder.load(model_dir, backbone).eval()
        self.tok = AutoTokenizer.from_pretrained(backbone)
        self.featurize = Featurizer(self.tok, max_len=max_len)
        self._torch = torch
        self.model_id = f"table-encoder:{meta.get('name', Path(model_dir).parent.name)}"

    def top_cell(self, question: str, table: Table) -> tuple[int, int, float, int]:
        """-> (row, col, margin to the second-best cell, rows the encoder could read)."""
        from tabletrace.encoder.features import collate

        f = self.featurize(question, table)
        with self._torch.no_grad():
            scores = self.model(**collate([f], self.tok.pad_token_id))[0]
        top = scores.topk(min(2, f.n_cells))
        row, col = f.position(int(top.indices[0]))
        margin = float(top.values[0] - top.values[1]) if f.n_cells > 1 else 0.0
        return row, col, margin, f.n_rows

    def agrees(self, question: str, table: Table, evidence: CellRef) -> tuple[bool, str, dict]:
        row, col, margin, rows_read = self.top_cell(question, table)
        info = {"encoder_cell": f"r{row}c{col}", "evidence_cell": evidence.cid, "margin": round(margin, 3), "mode": self.mode}
        if evidence.row >= rows_read:                       # the encoder could not read that far: no opinion, the answer stands
            return True, f"표가 길어 두 번째 모델이 근거 행(r{evidence.row})을 읽지 못해 의견 없음", {**info, "opinion": "none"}
        same = (row == evidence.row) if self.mode == "row" else (row, col) == (evidence.row, evidence.col)
        what = "행" if self.mode == "row" else "셀"
        if same:
            return True, f"두 번째 모델(표 인코더)도 같은 {what}을 골랐습니다 (r{row}c{col})", {**info, "opinion": "agree"}
        return False, f"두 번째 모델(표 인코더)은 다른 {what}을 골랐습니다 (r{row}c{col}, 근거는 {evidence.cid})", {**info, "opinion": "disagree"}
