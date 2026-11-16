"""Token length of every Korean test question as an EXAONE training example would see it (tokenizer only, no model).

The old fine-tuning cap (--max-len 768) cut the target of every training example whose prompt plus target was longer
than the cap (docs/dev/issues-log.md 66). To ask whether that hurt, the test questions are split by the same length.
The lengths need the EXAONE tokenizer, which is not in git, so they are stored once and read by
scripts/length_fix_analysis.py.

  python scripts/prompt_lengths.py --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B      # -> experiments/eval/ko_test_prompt_lengths.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tabletrace.model.serialize import set_table_format
from tabletrace.service.engines import SYSTEM_PROMPT
from tabletrace.training.data import build_examples, load_docs, read_records

ROOT = Path(__file__).resolve().parents[1]
TEST = ["data/ko/test.jsonl", "data/ko/synthetic_test.jsonl"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", default="LGAI-EXAONE/EXAONE-4.0-1.2B", help="model name or a local directory with the tokenizer")
    ap.add_argument("--max-in", type=int, default=672, help="input budget of the evaluated runs (rows that do not fit are dropped, as in training)")
    a = ap.parse_args()
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(a.tokenizer)
    docs = load_docs(ROOT / "data/ko/documents.jsonl")
    set_table_format("plain")
    exs = build_examples(read_records([ROOT / f for f in TEST]), docs, tok, a.max_in, drop_truncated_gold=False)      # evaluation keeps every question
    out: dict = {"tokenizer": "LGAI-EXAONE/EXAONE-4.0-1.2B", "table_format": "plain", "max_in": a.max_in, "questions": {}}
    for e in exs:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": e.input_text}]
        prompt = len(tok(tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True), add_special_tokens=False).input_ids)
        target = len(tok(e.target_text + tok.eos_token, add_special_tokens=False).input_ids)
        out["questions"][e.qid] = {"prompt_tokens": prompt, "target_tokens": target}
    dest = ROOT / "experiments" / "eval" / "ko_test_prompt_lengths.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    total = [v["prompt_tokens"] + v["target_tokens"] for v in out["questions"].values()]
    print("questions", len(total), "| longest", max(total), "| over 768:", sum(t > 768 for t in total), "->", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
