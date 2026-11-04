"""Make a saved tokenizer_config.json readable by older transformers (SGLang pins 4.57, training runs on 5.x).

transformers 5 writes `extra_special_tokens` as a LIST and may name the class `TokenizersBackend`; transformers 4.x expects a
dict there and does not know that class, so `AutoTokenizer.from_pretrained` fails inside SGLang with
`AttributeError: 'list' object has no attribute 'keys'`. The tokens themselves are in tokenizer.json, so the list is moved to
`additional_special_tokens` (understood by both) and the class name is set to PreTrainedTokenizerFast.

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


if __name__ == "__main__":
    for d in sys.argv[1:] or ["."]:
        print(f"{d}: {'fixed' if portable_tokenizer_config(d) else 'already portable (or no tokenizer_config.json)'}")
