"""Dynamic int8 quantization of selected nn.Linear layers.

`quantize_dynamic(model, {nn.Linear})` also quantizes `lm_head`, the 512 x 250,112 output projection, and that layer
is the usual suspect when a T5-family model loses accuracy (docs/REPORT.md section 8). `scope` selects layers by name:

  all          every nn.Linear (what round one measured)
  no_lm_head   everything except lm_head
  ffn          only the feed-forward projections (DenseReluDense.wi_*/wo)
  attn         only the attention projections (q, k, v, o)
  lm_head      only lm_head
"""
from __future__ import annotations

import re

SCOPES = {
    "all": r".",
    "no_lm_head": r"^(?!lm_head$)",
    "ffn": r"DenseReluDense\.",
    "attn": r"(SelfAttention|EncDecAttention)\.",
    "lm_head": r"^lm_head$",
}


def linear_names(model, scope: str) -> set[str]:
    import torch.nn as nn

    if scope not in SCOPES:
        raise ValueError(f"unknown quantization scope {scope!r}; choose from {sorted(SCOPES)}")
    pat = re.compile(SCOPES[scope])
    return {n for n, m in model.named_modules() if isinstance(m, nn.Linear) and pat.search(n)}


def quantize_model(model, scope: str = "all"):
    import torch

    return torch.ao.quantization.quantize_dynamic(model, qconfig_spec=linear_names(model, scope), dtype=torch.qint8)
