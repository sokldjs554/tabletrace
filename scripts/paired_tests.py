"""Paired comparisons between two evaluation runs on the SAME questions (exact two-sided sign test on the
questions where exactly one of the two runs is verified-correct).

  python scripts/paired_tests.py     # writes experiments/eval/paired_tests.json

A difference of a few points between two models is usually inside the sampling noise of a few hundred questions; the
paired test uses the question-level overlap and is the number to read, not the headline percentages.
"""
from __future__ import annotations

import json
from math import comb
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1] / "experiments" / "eval"
PAIRS = [
    # name, run A (reference), run B (candidate)
    ("chem2_vs_chem1_ko_test", "sft_chem_ko_test", "sft_chem2_ko_test"),
    ("chem2_vs_ko2_ko_test", "sft_ko2_ko_test", "sft_chem2_ko_test"),
    ("rl_v3_vs_chem2_ko_test", "sft_chem2_ko_test", "rl_v3_ko_test"),
    ("rl_v3_vs_chem1_ko_test", "sft_chem_ko_test", "rl_v3_ko_test"),
    ("chem2_vs_chem1_text2_test", "sft_chem_text2_test", "sft_chem2_text2_test"),
    ("rl_v3_vs_chem2_text2_test", "sft_chem2_text2_test", "rl_v3_text2_test"),
    ("rl_v3_vs_chem2_ko_custom", "sft_chem2_ko_custom", "rl_v3_ko_custom"),
    ("rl_v3_vs_chem2_chem_custom", "sft_chem2_chem_custom", "rl_v3_chem_custom"),
    ("rl_v3_vs_chem2_chem_syndev", "sft_chem2_chem_syndev", "rl_v3_chem_syndev"),
    ("subject_check_on_chem2_ko_test", "sft_chem2_ko_test", "sft_chem2_ko_test_ec"),
    ("subject_check_on_chem1_ko_test", "sft_chem_ko_test", "sft_chem_ko_test_ec"),
    ("subject_check_on_ko2_ko_test", "sft_ko2_ko_test", "sft_ko2_ko_test_ec"),
    ("rl_v2_vs_ko2_ko_test", "sft_ko2_ko_test", "rl_ko_ko_test"),
    ("int8_all_vs_fp32_ko_test", "rl_v3_ko_test", "final_int8_all_ko_test"),
    ("int8_lm_head_vs_fp32_ko_test", "rl_v3_ko_test", "final_int8_lm_head_ko_test"),
    ("int8_no_lm_head_vs_fp32_ko_test", "rl_v3_ko_test", "final_int8_no_lm_head_ko_test"),
    ("int8_ffn_vs_fp32_ko_test", "rl_v3_ko_test", "final_int8_ffn_ko_test"),
    ("int8_attn_vs_fp32_ko_test", "rl_v3_ko_test", "final_int8_attn_ko_test"),
    ("int8_lm_head_vs_fp32_text2_test", "rl_v3_text2_test", "final_int8_lm_head_text2_test"),
    ("int8_lm_head_vs_fp32_ko_custom", "rl_v3_ko_custom", "final_int8_lm_head_ko_custom"),
    ("int8_lm_head_vs_fp32_chem_custom", "rl_v3_chem_custom", "final_int8_lm_head_chem_custom"),
]


def load(run: str) -> dict[str, bool]:
    with open(EVAL / run / "predictions.jsonl", encoding="utf-8") as f:
        return {r["qid"]: bool(r["verified_correct"]) for r in map(json.loads, f)}


def exact_p(k: int, n: int) -> float:
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(k, n - k) + 1)) / 2 ** n)


def main() -> None:
    out = {}
    for name, a, b in PAIRS:
        if not ((EVAL / a / "predictions.jsonl").exists() and (EVAL / b / "predictions.jsonl").exists()):
            continue
        A, B = load(a), load(b)
        b_only = sum(1 for q in A if B[q] and not A[q])
        a_only = sum(1 for q in A if A[q] and not B[q])
        out[name] = {"reference": a, "candidate": b, "n": len(A), "candidate_better": b_only, "reference_better": a_only,
                     "p_two_sided": exact_p(b_only, b_only + a_only),
                     "p_display": "<0.001" if exact_p(b_only, b_only + a_only) < 0.001 else f"{exact_p(b_only, b_only + a_only):.3f}"}
    (EVAL / "paired_tests.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for k, v in out.items():
        print(f"{k:34s} n={v['n']:4d} candidate better {v['candidate_better']:3d} / reference better {v['reference_better']:3d}  p={v['p_display']}")


if __name__ == "__main__":
    main()
