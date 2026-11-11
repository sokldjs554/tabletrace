"""TableEncoder: a pretrained encoder that is told where each token sits in the table.

    embedding(token) + row_embedding(row id) + col_embedding(col id)  ->  backbone  ->  hidden states
    cell score = mean over the cell's tokens of a linear head on the hidden state

The row and column embeddings start at zero. At step 0 the model is therefore exactly the pretrained backbone, and
whatever the embeddings learn is learned from tables (this is how TAPAS adds its row/column embeddings to BERT).
Two heads share the pooling: `select` (which cell answers the question) and `corrupt` (was this cell replaced).
"""
from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn

MAX_ROWS, MAX_COLS = 64, 32


def load_backbone(path: str | Path):
    """A text encoder that accepts `inputs_embeds`: the encoder half of (m)T5, or any BERT/ELECTRA-style model."""
    from transformers import AutoConfig, AutoModel, T5EncoderModel

    kind = AutoConfig.from_pretrained(path).model_type
    if kind in ("t5", "mt5"):
        return T5EncoderModel.from_pretrained(path)          # the decoder weights in the checkpoint are not loaded
    return AutoModel.from_pretrained(path)


class TableEncoder(nn.Module):
    def __init__(self, backbone, structure: bool = True, freeze_word_embeddings: bool = True) -> None:
        super().__init__()
        self.backbone = backbone
        self.structure = structure
        words = backbone.get_input_embeddings()
        dim = words.embedding_dim
        hidden = backbone.config.hidden_size
        if freeze_word_embeddings:                 # a 250k-word multilingual vocabulary is most of the parameters; keep it fixed
            words.weight.requires_grad_(False)
        if structure:
            self.row_emb = nn.Embedding(MAX_ROWS + 1, dim)
            self.col_emb = nn.Embedding(MAX_COLS + 1, dim)
            nn.init.zeros_(self.row_emb.weight)
            nn.init.zeros_(self.col_emb.weight)
        self.select = nn.Linear(hidden, 1)
        self.corrupt = nn.Linear(hidden, 1)

    def encode(self, input_ids, attention_mask, row_ids, col_ids):
        emb = self.backbone.get_input_embeddings()(input_ids)
        if self.structure:
            emb = emb + self.row_emb(row_ids.clamp(max=MAX_ROWS)) + self.col_emb(col_ids.clamp(max=MAX_COLS))
        return self.backbone(inputs_embeds=emb, attention_mask=attention_mask).last_hidden_state

    @staticmethod
    def pool(token_scores, cell_index, n_cells: int):
        """Mean of the token scores of each cell -> (batch, n_cells). Tokens outside data cells (index -1) are ignored."""
        inside = cell_index >= 0
        idx = cell_index.clamp(min=0)
        total = torch.zeros(token_scores.size(0), n_cells, dtype=token_scores.dtype, device=token_scores.device)
        count = torch.zeros_like(total)
        total.scatter_add_(1, idx, token_scores * inside)
        count.scatter_add_(1, idx, inside.to(token_scores.dtype))
        return total / count.clamp(min=1)

    def forward(self, input_ids, attention_mask, row_ids, col_ids, cell_index, cell_mask, head: str = "select", **_):
        hidden = self.encode(input_ids, attention_mask, row_ids, col_ids)
        layer = self.select if head == "select" else self.corrupt
        scores = self.pool(layer(hidden).squeeze(-1), cell_index, cell_mask.size(1))
        return scores.masked_fill(~cell_mask, -1e4) if head == "select" else scores

    def save(self, out_dir: str | Path, meta: dict) -> None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        keep = {k: v for k, v in self.state_dict().items() if not k.endswith("shared.weight") and "word_embeddings" not in k} \
            if not self.backbone.get_input_embeddings().weight.requires_grad else self.state_dict()
        torch.save(keep, out / "table_encoder.pt")          # frozen word embeddings are not stored again
        (out / "table_encoder.json").write_text(json.dumps({"structure": self.structure, **meta}, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, out_dir: str | Path, backbone_path: str | Path | None = None) -> TableEncoder:
        meta = json.loads((Path(out_dir) / "table_encoder.json").read_text(encoding="utf-8"))
        model = cls(load_backbone(backbone_path or meta["backbone"]), structure=meta["structure"])
        missing, unexpected = model.load_state_dict(torch.load(Path(out_dir) / "table_encoder.pt", map_location="cpu"), strict=False)
        left = [k for k in missing if not k.endswith("shared.weight") and "word_embeddings" not in k and "embed_tokens" not in k]
        if left or unexpected:
            raise RuntimeError(f"checkpoint does not match the model: missing {left[:5]}, unexpected {unexpected[:5]}")
        return model
