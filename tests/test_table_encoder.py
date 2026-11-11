"""Structure-aware table encoder: features, the cell pooling head and the pretraining corruption."""
from __future__ import annotations

import random

import pytest

from tabletrace.encoder.corrupt import cell_pool, corrupt_table
from tabletrace.encoder.features import Featurizer
from tabletrace.schema import Table


class CharTokenizer:
    """One token per character; enough to test the layout without model files."""
    cls_token_id, sep_token_id, eos_token_id, pad_token_id = 1, 2, 2, 0

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [3 + (ord(ch) % 200) for ch in text]}


def table(rows=3, cols=3, cell="x") -> Table:
    return Table(id="t", doc_id="d", title="제목", header=[f"h{j}" for j in range(cols)],
                 rows=[[f"{cell}{i}{j}" for j in range(cols)] for i in range(rows)])


def test_every_token_knows_its_row_column_and_cell():
    f = Featurizer(CharTokenizer())("질문?", table())
    assert len(f.input_ids) == len(f.row_ids) == len(f.col_ids) == len(f.cell_index)
    assert (f.n_rows, f.n_cols, f.n_cells) == (3, 3, 9)
    for cell in range(9):
        i, j = divmod(cell, 3)
        positions = [k for k, c in enumerate(f.cell_index) if c == cell]
        assert positions and {f.row_ids[k] for k in positions} == {i + 1} and {f.col_ids[k] for k in positions} == {j + 1}
    header = [k for k, (r, c) in enumerate(zip(f.row_ids, f.col_ids, strict=True)) if r == 0 and c > 0]
    assert header and all(f.cell_index[k] == -1 for k in header)        # header cells are located but never scored
    assert f.row_ids[0] == f.col_ids[0] == 0 and f.cell_index[0] == -1   # [CLS] and the question sit outside the table
    assert f.cell_of(2, 1) == 7 and f.position(7) == (2, 1)


def test_long_tables_shrink_cells_first_and_drop_rows_last():
    fz = Featurizer(CharTokenizer(), max_len=120)
    f = fz("질문?", table(rows=4, cols=3, cell="긴 셀 내용 " * 3))
    assert len(f.input_ids) <= 120 and f.cell_tokens < 12 and f.dropped_rows == 0
    g = Featurizer(CharTokenizer(), max_len=60)("질문?", table(rows=12, cols=3, cell="abcdef"))
    assert len(g.input_ids) <= 60 and g.dropped_rows > 0 and g.cell_of(11, 0) is None and g.cell_of(0, 0) == 0


def test_corruption_marks_only_cells_that_changed():
    t = table(rows=6, cols=4)
    pool = cell_pool([table(rows=5, cols=3, cell="other")])
    corrupted, labels = corrupt_table(t, pool, random.Random(0), rate=0.25)
    flat_before = [c for r in t.rows for c in r]
    flat_after = [c for r in corrupted.rows for c in r]
    assert len(labels) == 24 and sum(labels) >= 1
    assert [int(x != y) for x, y in zip(flat_before, flat_after, strict=True)] == labels
    assert t.rows[0][0] == "x00"                                         # the input table is not modified


def test_zero_initialised_structure_embeddings_leave_the_backbone_unchanged():
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    from tabletrace.encoder.features import collate
    from tabletrace.encoder.model import TableEncoder

    torch.manual_seed(0)
    cfg = transformers.T5Config(vocab_size=256, d_model=32, d_kv=8, d_ff=64, num_layers=1, num_heads=2)
    f = Featurizer(CharTokenizer())("질문?", table())
    b = collate([f], 0, targets=[4])
    plain = TableEncoder(transformers.T5EncoderModel(cfg), structure=False).eval()
    aware = TableEncoder(transformers.T5EncoderModel(cfg), structure=True).eval()
    aware.load_state_dict(plain.state_dict(), strict=False)
    with torch.no_grad():
        assert torch.allclose(plain(**b), aware(**b), atol=1e-6)          # step 0: identical to the model without structure
        aware.col_emb.weight[2] += 1.0
        assert not torch.allclose(plain(**b), aware(**b), atol=1e-4)      # and the embeddings do reach the output
    logits = aware(**b)
    assert logits.shape == (1, 9)
    loss = torch.nn.functional.cross_entropy(logits, b["targets"])
    loss.backward()
    assert aware.row_emb.weight.grad is not None and aware.row_emb.weight.grad.abs().sum() > 0


def test_pool_is_the_mean_over_each_cells_tokens():
    torch = pytest.importorskip("torch")
    from tabletrace.encoder.model import TableEncoder

    scores = torch.tensor([[9.0, 1.0, 3.0, 5.0, 7.0, 100.0]])
    cells = torch.tensor([[-1, 0, 0, 1, 1, -1]])
    assert TableEncoder.pool(scores, cells, 3).tolist() == [[2.0, 6.0, 0.0]]
