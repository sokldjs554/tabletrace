"""A tokenizer stand-in for the row-budget logic when the real tokenizer is not at hand.

`choose_context_and_rows` / `build_examples` only need `tok(text).input_ids` to measure how many rows fit. When the
planner is an engine-served causal LM on a GPU box, the mT5 tokenizer is not there (model weights are not in git), so
`--tokenizer approx` uses ~1 token per 1.6 characters, which is close to what SentencePiece gives on Korean tables. It is
a budget estimate, not a tokenizer: use the planner's own tokenizer (`--tokenizer <hf-name-or-path>`) when it matters.
"""
from __future__ import annotations

import math


class _Out:
    def __init__(self, n: int) -> None:
        self.input_ids = [0] * n


class ApproxTokenizer:
    chars_per_token = 1.6

    def __call__(self, text: str) -> _Out:
        return _Out(math.ceil(len(text) / self.chars_per_token))


def load_tokenizer(spec: str | None, fallback_dir: str = "models/mt5-small-base"):
    """`approx` -> ApproxTokenizer; a path or hub name -> the HF tokenizer; None -> fallback_dir if present, else approx."""
    from pathlib import Path

    if spec == "approx":
        return ApproxTokenizer()
    if spec is None:
        spec = fallback_dir if Path(fallback_dir).exists() else "approx"
        if spec == "approx":
            return ApproxTokenizer()
    if (Path(spec) / "tokenizer.json").exists():      # a saved fast tokenizer (the mT5 one): no slow-tokenizer detour
        from transformers import PreTrainedTokenizerFast

        return PreTrainedTokenizerFast.from_pretrained(spec)
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(spec)
