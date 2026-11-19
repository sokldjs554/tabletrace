"""Section P of notebook 2: three experiments that were run once, run once more (docs/REPORT.md §31).

What each repeat is checked for was written down here and in docs/REPORT.md §31 before any of them ran (this file's
first commit). A repeat that has not come back yet is reported as not run.

  P1  the Korean-only model (exaone_koonly2, section O's command once more)
      1a  on the 31 unanswerable chemistry questions of the three sets, the Korean-and-chemistry repeat (exaone_kochem3)
          still beats a second Korean-only model: more questions only it got right, p < 0.05 (first time 10 to 0)
      1b  on the 62 paper-table questions, the new Korean-only model still beats the untuned model, p < 0.05 (30 to 3)
  P2  reinforcement learning from a full-data model (exaone_full5 -> exaone_grpo4, section J's command once more)
      2   on the Korean test, no detectable change in verified EM from RL: p >= 0.05 (first time 86.0% and 86.1%, 8 to 7)
  P3  fine-tuning with the loop the owner wrote (exaone_ownloop2, section M's command once more)
      3a  the two trainings with the owner's loop cannot be told apart on the Korean test: p >= 0.05
      3b  the new one cannot be told apart from the same command with the built-in loop (exaone_full4): p >= 0.05
Next to them, descriptive numbers: scores, the range of all full-data Korean-only trainings, cited-cell rates.

  python scripts/repeat_once_analysis.py     # -> experiments/eval/repeat_once_analysis.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chem_rerun_analysis as cr  # noqa: E402
import rl2_analysis as rl2  # noqa: E402

PRE_REGISTERED = "docs/REPORT.md §31 and this file, before section P ran"
KO_ONLY_TRAININGS = ["exaone_full_vllm_ko_test", "exaone_full_vllm_ko_test_run2", "exaone_full2old_vllm_ko_test", "exaone_full2_vllm_ko_test",
                     "exaone_full3_vllm_ko_test", "exaone_full4_vllm_ko_test", "exaone_ownloop_vllm_ko_test", "exaone_koonly_vllm_ko_test"]


def have(*runs: str) -> bool:
    return all((rl2.EVAL / r / "predictions.jsonl").exists() for r in runs)


def holds_better(p: dict) -> bool:
    return p["only_candidate"] > p["only_reference"] and p["p_two_sided"] < 0.05


def holds_no_difference(p: dict) -> bool:
    return p["p_two_sided"] >= 0.05


def unanswerable(model: str) -> dict:
    return {f"{s}/{q}": r for s in cr.CHEM_SETS for q, r in rl2.load(f"{model}_{s}").items() if cr.kind(r) == "unanswerable"}


def p1() -> dict:
    new = "exaone_koonly2_vllm"
    if not have(*(f"{new}_{s}" for s in (*cr.CHEM_SETS, "ko_test"))):
        return {"run": False}
    a = cr.paired(unanswerable(new), unanswerable("exaone_kochem3_vllm"))
    b = cr.paired(rl2.load("ref_1p2b_chem_papers"), rl2.load(f"{new}_chem_papers"))
    return {"run": True,
            "1a_unanswerable_repeat_vs_new_korean_only": {**a, "n": len(unanswerable(new)), "holds": holds_better(a)},
            "1b_papers_new_korean_only_vs_untuned": {**b, "holds": holds_better(b)},
            "scores": {s: {"new_korean_only": cr.right(rl2.load(f"{new}_{s}")), "first_korean_only": cr.right(rl2.load(f"exaone_koonly_vllm_{s}"))}
                       for s in (*cr.CHEM_SETS, "ko_test")},
            "papers_new_vs_first_korean_only": cr.paired(rl2.load("exaone_koonly_vllm_chem_papers"), rl2.load(f"{new}_chem_papers")),
            "unanswerable_first_training_vs_new_korean_only": cr.paired(unanswerable(new), unanswerable("exaone_kochem2_vllm"))}


def p2() -> dict:
    start, rl = "exaone_full5_vllm_ko_test", "exaone_grpo4_vllm_ko_test"
    if not have(start, rl):
        return {"run": False, "start_model_evaluated": have(start)}
    s, r = rl2.load(start), rl2.load(rl)
    p = cr.paired(s, r)
    return {"run": True, "2_rl_vs_start_on_the_korean_test": {**p, "holds": holds_no_difference(p)},
            "scores": {"start": cr.right(s), "after_rl": cr.right(r)}, "cited_gold_cell": {"start": cr.cited(s), "after_rl": cr.cited(r)},
            "first_time": {"start": cr.right(rl2.load("exaone_full3_vllm_ko_test")), "after_rl": cr.right(rl2.load("exaone_grpo3_vllm_ko_test")),
                           "rl_vs_start": cr.paired(rl2.load("exaone_full3_vllm_ko_test"), rl2.load("exaone_grpo3_vllm_ko_test"))}}


def p3() -> dict:
    new = "exaone_ownloop2_vllm_ko_test"
    if not have(new):
        return {"run": False}
    n = rl2.load(new)
    a = cr.paired(rl2.load("exaone_ownloop_vllm_ko_test"), n)
    b = cr.paired(rl2.load("exaone_full4_vllm_ko_test"), n)
    rates = {r: cr.right(rl2.load(r))["rate"] for r in KO_ONLY_TRAININGS}
    return {"run": True, "3a_new_vs_first_owner_loop": {**a, "holds": holds_no_difference(a)},
            "3b_new_owner_loop_vs_builtin_loop_same_command": {**b, "holds": holds_no_difference(b)},
            "score": cr.right(n), "earlier_full_data_korean_only_trainings": rates,
            "inside_their_range": min(rates.values()) <= cr.right(n)["rate"] <= max(rates.values())}


def analyse() -> dict:
    return {"written_down_before_the_runs": PRE_REGISTERED, "P1_korean_only": p1(), "P2_rl_from_full_data": p2(), "P3_owner_loop": p3()}


def main() -> None:
    out = analyse()
    dest = rl2.EVAL / "repeat_once_analysis.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for part, res in out.items():
        if isinstance(res, dict):
            checks = {k: v["holds"] for k, v in res.items() if isinstance(v, dict) and "holds" in v}
            print(part, "run" if res.get("run") else "not run yet", checks)
    print("wrote", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
