"""What does the `colid` table format cost in tokens, and which input budget gives it the same rows as `plain`?

Counts with the tokenizer of the model that will be trained (no model weights needed):

  python scripts/table_format_cost.py --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B        # hub name or a local folder

For each (format, input budget) it builds the Korean test and training inputs exactly as training and evaluation
do and records how many gold rows fall outside the budget. Writes experiments/serialize/table_format_cost.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tabletrace.model import serialize  # noqa: E402
from tabletrace.model.approx_tokenizer import load_tokenizer  # noqa: E402
from tabletrace.training.data import build_examples, load_docs, read_records  # noqa: E402

CASES = [("plain", 672), ("colid", 672), ("colid", 800), ("colid", 928)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--name", default=None, help="tokenizer name to record (default: --tokenizer)")
    ap.add_argument("--out", default="experiments/serialize/table_format_cost.json")
    a = ap.parse_args()
    tok = load_tokenizer(a.tokenizer)
    docs = load_docs(ROOT / "data/ko/documents.jsonl")
    test = read_records([ROOT / "data/ko/test.jsonl", ROOT / "data/ko/synthetic_test.jsonl"])
    train = read_records([ROOT / "data/ko/train.jsonl", ROOT / "data/ko/synthetic_train.jsonl"])
    out: dict = {"tokenizer": a.name or a.tokenizer, "test_questions": len(test), "train_questions": len(train), "cases": {}}
    before = serialize.get_table_format()
    try:
        for fmt, budget in CASES:
            serialize.set_table_format(fmt)
            ex = build_examples(test, docs, tok, budget)
            kept = build_examples(train, docs, tok, budget, drop_truncated_gold=True)
            whole = [len(tok(serialize.build_input(e.question, e.table_full, e.context_full)).input_ids) for e in ex]
            cut = sum(e.truncated_gold for e in ex)
            out["cases"][f"{fmt}_{budget}"] = {
                "format": fmt, "max_in": budget, "test_gold_row_cut": cut, "test_gold_row_cut_rate": round(cut / len(ex), 4),
                "test_tables_with_rows_cut": sum(e.rows_kept < e.table_full.n_rows for e in ex),
                "train_examples_kept": len(kept), "whole_input_tokens_median": statistics.median(whole),
            }
            print(f"{fmt:6s} max_in={budget}: {out['cases'][f'{fmt}_{budget}']}")
    finally:
        serialize.set_table_format(before)
    p, c = out["cases"]["plain_672"], out["cases"]["colid_672"]
    out["colid_extra_tokens_rate"] = round(c["whole_input_tokens_median"] / p["whole_input_tokens_median"] - 1, 4)
    dest = ROOT / a.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("->", dest.relative_to(ROOT), "| colid costs", f"{100 * out['colid_extra_tokens_rate']:.1f}% more tokens (median whole input)")


if __name__ == "__main__":
    main()
