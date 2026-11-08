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
    # EXAONE-4.0-1.2B LoRA served by vLLM on the owner's T4 (different model size, pretraining and hardware; see README 10.3)
    ("exaone_vllm_vs_rl_v3_ko_test", "rl_v3_ko_test", "exaone_vllm_ko_test"),
    ("exaone_vllm_vs_rl_v3_ko_test_ec", "rl_v3_ko_test_ec", "exaone_vllm_ko_test_ec"),
    ("exaone_vllm_vs_heuristic_ko_test", "heuristic_ko_test", "exaone_vllm_ko_test"),
    ("exaone_vllm_vs_heuristic_ko_test_ec", "heuristic_ko_test_ec", "exaone_vllm_ko_test_ec"),
    ("subject_check_on_exaone_vllm_ko_test", "exaone_vllm_ko_test", "exaone_vllm_ko_test_ec"),
    ("exaone_vllm_tp2_vs_tp1_ko_test", "exaone_vllm_ko_test", "exaone_vllm_tp2_ko_test"),   # same model, TP=2 vs 1 GPU: run-to-run variation
    # second LoRA training run (same 300 examples, fp16 instead of emulated bf16) vs the first one: training-run variation
    ("exaone_vllm_run2_vs_run1_ko_test", "exaone_vllm_ko_test_run1", "exaone_vllm_ko_test_run2"),
    ("exaone_vllm_run2_vs_run1_ko_test_ec", "exaone_vllm_ko_test_ec_run1", "exaone_vllm_ko_test_ec_run2"),
    ("exaone_vllm_run3_vs_run2_ko_test", "exaone_vllm_ko_test_run2", "exaone_vllm_ko_test"),
    ("exaone_vllm_run3_vs_run1_ko_test", "exaone_vllm_ko_test_run1", "exaone_vllm_ko_test"),
    # same merged model (run 3) served by SGLang (with the Turing shim) instead of vLLM: engine-to-engine variation
    ("exaone_sglang_vs_vllm_ko_test", "exaone_vllm_ko_test", "exaone_sglang_ko_test"),
    ("exaone_sglang_vs_vllm_ko_test_ec", "exaone_vllm_ko_test_ec", "exaone_sglang_ko_test_ec"),
    ("exaone_sglang_vs_rl_v3_ko_test_ec", "rl_v3_ko_test_ec", "exaone_sglang_ko_test_ec"),
    # full-data LoRA (3,587 examples, 224 steps) from the fourth Kaggle session
    ("exaone_full_vs_300_ko_test", "exaone_vllm_ko_test", "exaone_full_vllm_ko_test"),
    ("exaone_full_vs_300_ko_test_ec", "exaone_vllm_ko_test_ec", "exaone_full_vllm_ko_test_ec"),
    ("exaone_full_vs_rl_v3_ko_test_ec", "rl_v3_ko_test_ec", "exaone_full_vllm_ko_test_ec"),
    ("exaone_full_vs_heuristic_ko_test_ec", "heuristic_ko_test_ec", "exaone_full_vllm_ko_test_ec"),
    ("exaone_full_sglang_vs_vllm_ko_test", "exaone_full_vllm_ko_test", "exaone_full_sglang_ko_test"),
    ("exaone_full_tp2_vs_tp1_ko_test", "exaone_full_vllm_ko_test", "exaone_full_vllm_tp2_ko_test"),
    ("subject_check_on_exaone_full_ko_test", "exaone_full_vllm_ko_test", "exaone_full_vllm_ko_test_ec"),
    ("exaone_full_vs_rl_v3_ko_custom_ec", "rl_v3_ko_custom_ec", "exaone_full_vllm_ko_custom_ec"),
    ("exaone_full_vs_heuristic_ko_custom_ec", "heuristic_ko_custom_ec", "exaone_full_vllm_ko_custom_ec"),
    # second full-data training (Colab free T4, same settings): training-run variation of the full model
    ("exaone_full_run2_vs_run1_ko_test", "exaone_full_vllm_ko_test", "exaone_full_vllm_ko_test_run2"),
    ("exaone_full_run2_vs_run1_ko_test_ec", "exaone_full_vllm_ko_test_ec", "exaone_full_vllm_ko_test_ec_run2"),
    ("exaone_full_run2_sglang_vs_vllm_ko_test", "exaone_full_vllm_ko_test_run2", "exaone_full_sglang_ko_test_run2"),
    ("exaone_full_run2_vs_run1_ko_custom", "exaone_full_vllm_ko_custom", "exaone_full_vllm_ko_custom_run2"),
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
