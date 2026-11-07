"""Make a model folder saved by transformers 5.x readable by transformers 4.x (SGLang 0.5.9 pins 4.57; training runs on 5.x).

Two incompatibilities were hit on the owner's GPU runs (docs/dev/issues-log.md 37, 39):

* tokenizer_config.json: transformers 5 writes `extra_special_tokens` as a LIST and may name the class `TokenizersBackend`;
  4.x expects a dict there and does not know that class, so `AutoTokenizer.from_pretrained` fails inside SGLang with
  `AttributeError: 'list' object has no attribute 'keys'`. The tokens themselves are in tokenizer.json, so the list is moved to
  `additional_special_tokens` (understood by both) and the class name is set to PreTrainedTokenizerFast.
* config.json: transformers 5 stores RoPE settings only under `rope_parameters` and writes `rope_theta`/`rope_scaling` as
  null. 4.x reads `rope_theta` (Exaone4Config default 10000.0 instead of the model's 1,000,000) and `rope_scaling` (default
  None, so the llama3 scaling is dropped). The model then loads and talks fluently but ignores the context. Both keys are
  restored from `rope_parameters`; `torch_dtype` is restored from `dtype`. Additive only: 5.x keeps using `rope_parameters`.

  python scripts/serving/fix_tokenizer_config.py experiments/exaone_lora/merged [more dirs ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def portable_tokenizer_config(directory: str | Path) -> bool:
    """Rewrite <directory>/tokenizer_config.json in place; returns True when something changed."""
    p = Path(directory) / "tokenizer_config.json"
    if not p.exists():
        return False
    cfg = json.loads(p.read_text(encoding="utf-8"))
    changed = False
    extra = cfg.get("extra_special_tokens")
    if isinstance(extra, list):
        merged = list(dict.fromkeys([*(cfg.get("additional_special_tokens") or []), *extra]))
        cfg["additional_special_tokens"] = merged
        del cfg["extra_special_tokens"]
        changed = True
    if cfg.get("tokenizer_class") == "TokenizersBackend":
        cfg["tokenizer_class"] = "PreTrainedTokenizerFast"
        changed = True
    if changed:
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


def portable_model_config(directory: str | Path) -> bool:
    """Rewrite <directory>/config.json in place so transformers 4.x sees the same RoPE settings as 5.x; True when changed."""
    p = Path(directory) / "config.json"
    if not p.exists():
        return False
    cfg = json.loads(p.read_text(encoding="utf-8"))
    changed = False
    rp = cfg.get("rope_parameters")
    if isinstance(rp, dict):
        if cfg.get("rope_theta") is None and rp.get("rope_theta") is not None:
            cfg["rope_theta"] = rp["rope_theta"]
            changed = True
        scaling = {k: v for k, v in rp.items() if k != "rope_theta"}
        if cfg.get("rope_scaling") is None and scaling.get("rope_type", "default") != "default":
            cfg["rope_scaling"] = scaling
            changed = True
    if cfg.get("torch_dtype") is None and cfg.get("dtype"):
        cfg["torch_dtype"] = cfg["dtype"]
        changed = True
    if changed:
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return changed


def portable_model_dir(directory: str | Path) -> bool:
    a = portable_tokenizer_config(directory)
    b = portable_model_config(directory)
    return a or b


if __name__ == "__main__":
    for d in sys.argv[1:] or ["."]:
        t, c = portable_tokenizer_config(d), portable_model_config(d)
        print(f"{d}: tokenizer_config {'fixed' if t else 'unchanged'}, config.json {'fixed' if c else 'unchanged'}")
