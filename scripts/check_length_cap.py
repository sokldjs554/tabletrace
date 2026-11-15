"""How many EXAONE training targets and reinforcement-learning prompts does the length cap cut? Tokenizer only, no model.

Every EXAONE fine-tuning run up to 2026-11-14 built its inputs with a budget of --max-len minus 96 tokens. The system
prompt and the chat template alone take about 147, so the longest examples did not fit: the fine-tuning script cut the
END (the target), the reinforcement-learning script cut the BEGINNING of the prompt. Nothing reported it
(docs/dev/issues-log.md 66). This script counts both for the old setting and for the corrected one.

  python scripts/check_length_cap.py --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B      # -> experiments/gpu2_2026-11-14/length_cap_check.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tabletrace.model.serialize import set_table_format
from tabletrace.service.engines import SYSTEM_PROMPT
from tabletrace.training.data import build_examples, load_docs, read_records

ROOT = Path(__file__).resolve().parents[1]
SETS = (("train", ["data/ko/train.jsonl", "data/ko/synthetic_train.jsonl"]), ("dev", ["data/ko/dev.jsonl", "data/ko/synthetic_dev.jsonl"]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", default="LGAI-EXAONE/EXAONE-4.0-1.2B", help="model name or a local directory with the tokenizer")
    ap.add_argument("--out", default=str(ROOT / "experiments/gpu2_2026-11-14/length_cap_check.json"))
    a = ap.parse_args()
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(a.tokenizer)
    docs = load_docs(ROOT / "data/ko/documents.jsonl")
    set_table_format("plain")

    def prompt(text: str) -> list[int]:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}]
        return tok(tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True), add_special_tokens=False).input_ids

    out = {"tokenizer": "LGAI-EXAONE/EXAONE-4.0-1.2B", "table_format": "plain", "system_prompt_and_template_tokens": len(prompt("")), "settings": {}}
    for label, max_in, max_len in (("as_run_until_2026_11_14", 672, 768), ("corrected", 672, 960)):
        res: dict = {"max_in": max_in, "max_len": max_len}
        for name, files in SETS:
            exs = build_examples(read_records([ROOT / f for f in files]), docs, tok, max_in, drop_truncated_gold=True)
            missing = short = cut_prompt = longest = 0
            first_cut = 0
            for i, e in enumerate(exs):
                p = prompt(e.input_text)
                t = tok(e.target_text + tok.eos_token, add_special_tokens=False).input_ids
                longest = max(longest, len(p) + len(t))
                if len(p) >= max_len:
                    missing += 1
                elif len(p) + len(t) > max_len:
                    short += 1
                if len(p) > max_len - 8:
                    cut_prompt += 1
                    first_cut += i < 64
            res[name] = {"examples": len(exs), "targets_missing": missing, "targets_cut_short": short, "targets_cut_share": round((missing + short) / len(exs), 4),
                         "prompts_cut_in_rl": cut_prompt, "prompts_cut_share": round(cut_prompt / len(exs), 4), "longest_prompt_plus_target": longest}
            if name == "dev":
                res["dev_first_64_prompts_cut_in_rl"] = first_cut
        out["settings"][label] = res
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out["settings"], ensure_ascii=False))


if __name__ == "__main__":
    main()
