"""Structure-aware table encoder: a pretrained language model plus row/column embeddings and a cell-selection head.

    features.py   question + table -> token ids with a row id, a column id and a cell index for every token
    model.py      TableEncoder: backbone + (zero-initialised) row/column embeddings + per-cell heads
    corrupt.py    self-supervised pretraining data: replace cells and ask which ones were replaced

The generative planners write the cell id as text ("cells: r3c2"). This encoder scores every cell directly, so it can
be compared with them on one question: which cell holds the answer?
"""
