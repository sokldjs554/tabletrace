"""A few derived values of the third GPU session (2026-11-15) that documents cite (stored predictions only).

  python scripts/gpu3_summary.py     # -> experiments/eval/gpu3_summary.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "experiments" / "eval"


def rows(run: str) -> list[dict]:
    with open(EVAL / run / "predictions.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def metrics(run: str) -> dict:
    return json.loads((EVAL / run / "metrics.json").read_text(encoding="utf-8"))["metrics"]


def answer_text(r: dict) -> str:
    m = re.search(r"answer:\s*(.*)$", r["raw_output"] or "", re.S)
    return m.group(1) if m else ""


def main() -> None:
    big = rows("ref_7p8b_awq_ko_test")
    long_answers = [r for r in big if len(answer_text(r)) > 200]          # the length that stopped this evaluation in the session before
    out = {
        "ref_7p8b_awq_ko_test": {
            "questions": len(big),
            "answers_over_200_chars": len(long_answers),
            "of_those_withheld": sum(r["pred_status"] == "abstained" for r in long_answers),
            "guard_triggered": sum(any(c["name"] == "tool_call" for c in r["checks"]) for r in big),
        },
        "ms_per_question_ratio_7p8b_to_tuned_1p2b": round(metrics("ref_7p8b_awq_ko_test")["mean_ms_per_example"] / metrics("exaone_full_vllm_ko_test")["mean_ms_per_example"], 1),
        "untuned_verified_em_by_size": {
            "exaone_4_0_1p2b": metrics("ref_1p2b_ko_test")["verified_em"],
            "exaone_3_5_7p8b_awq": metrics("ref_7p8b_awq_ko_test")["verified_em"],
            "exaone_4_0_32b_awq_previous_session": json.loads((ROOT / "experiments" / "gpu2_2026-11-14" / "recovered.json").read_text(encoding="utf-8"))["evals"]["ref_32b_awq_ko_test"]["v1"]["metrics"]["verified_em"],
            "exaone_4_0_1p2b_tuned_on_3587": metrics("exaone_full_vllm_ko_test")["verified_em"],
        },
        "tools_same_setting_two_sessions": {
            "previous_session": json.loads((ROOT / "experiments" / "gpu2_2026-11-14" / "recovered.json").read_text(encoding="utf-8"))["evals"]["tools_1p2b_ko_test"]["v1"]["metrics"]["verified_em"],
            "this_session": metrics("tools_1p2b_ko_test")["verified_em"],
        },
    }
    dest = EVAL / "gpu3_summary.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
