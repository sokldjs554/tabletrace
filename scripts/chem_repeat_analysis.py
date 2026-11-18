"""The Korean-and-chemistry training once more (notebook 2, section O with RUN_KOCHEM_REPEAT; the owner ran it on Colab
on 2026-11-18), checked against what was written down before the run.

  python scripts/chem_repeat_analysis.py     # -> experiments/eval/chem_repeat_analysis.json

Before the run (commit b3bffd2, docs/REPORT.md §29.7, "반복 학습을 돌리기 전에 적어 둔다") four things were fixed:
  1. the third value of the paper-table count is reported as it comes; the headline stays the first run with files;
  2. on the 31 unanswerable chemistry questions the new model is compared with the Korean-only model: if the split found
     after section O's result holds, the new model withholds significantly more of them; if not, that split is
     rewritten as coming from one training only;
  3. on the 143 answerable chemistry questions no significant difference from the Korean-only model is expected;
  4. the per-set paired comparisons (new model against the Korean-only model, and against section N's model) are
     reported whether significant or not.
This script computes exactly those, and a few descriptive numbers next to them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chem_rerun_analysis as cr  # noqa: E402
import rl2_analysis as rl2  # noqa: E402

EVAL = ROOT / "experiments" / "eval"
NEW, FIRST, KO_ONLY = "exaone_kochem3_vllm", "exaone_kochem2_vllm", "exaone_koonly_vllm"
PRE_REGISTERED_AT = "b3bffd2"


def subset(rows: dict, keep) -> dict:
    return {q: r for q, r in rows.items() if keep(r)}


def same_output(a: dict, b: dict) -> dict:
    same = sum((a[q]["raw_output"] or "") == (b[q]["raw_output"] or "") for q in a)
    return {"questions": len(a), "same_raw_output": same, "rate": round(same / len(a), 4)}


def main() -> None:
    info = json.loads((ROOT / "experiments" / "exaone_lora_kochem3" / "train_info.json").read_text(encoding="utf-8"))
    first = json.loads((ROOT / "experiments" / "exaone_lora_kochem2" / "train_info.json").read_text(encoding="utf-8"))
    platform = json.loads((ROOT / "experiments" / "run_info_2_chemrepeat.json").read_text(encoding="utf-8"))
    rerun = json.loads((EVAL / "chem_rerun_analysis.json").read_text(encoding="utf-8"))
    log = info["loss_log"]
    out: dict = {
        "platform": platform["platform"], "gpus": platform["gpus"], "notebook_commit": platform["commit"], "finished": platform["finished"],
        "written_down_before_the_run": {"commit": PRE_REGISTERED_AT, "where": "docs/REPORT.md §29.7, 반복 학습을 돌리기 전에 적어 둔다"},
        "training": {"examples": info["n_examples"], "steps": info["steps"], "minutes": round(info["wall_s"] / 60, 1), "loop": info["loop"],
                     "targets_missing": info["targets_missing"], "targets_cut_short": info["targets_cut_short"],
                     "loss_first_20_steps": round(sum(x["loss"] for x in log[:20]) / 20, 4), "loss_last_20_steps": round(sum(x["loss"] for x in log[-20:]) / 20, 4),
                     "args_that_differ_from_the_first_training": sorted(k for k in set(info["args"]) | set(first["args"]) if info["args"].get(k) != first["args"].get(k))},
        "chemistry": {}, "korean": {},
    }
    every = {name: {} for name in ("new", "first", "ko_only")}
    for s, label in cr.CHEM_SETS.items():
        new, fst, ko = rl2.load(f"{NEW}_{s}"), rl2.load(f"{FIRST}_{s}"), rl2.load(f"{KO_ONLY}_{s}")
        assert set(new) == set(fst) == set(ko)
        out["chemistry"][s] = {"label": label,
                               "repeat": {**cr.right(new), **cr.kinds(new), "cited": cr.cited(new), "with_subject_check": cr.right(rl2.load(f"{NEW}_{s}_ec"))["correct"]},
                               "first_training": cr.right(fst), "korean_only": cr.right(ko),
                               "repeat_vs_korean_only": cr.paired(ko, new),          # item 4; only_candidate: only the repeat got it right
                               "repeat_vs_first_training": cr.paired(fst, new),
                               "outputs_repeat_vs_first_training": same_output(new, fst)}
        for name, rows in (("new", new), ("first", fst), ("ko_only", ko)):
            every[name].update({f"{s}/{q}": r for q, r in rows.items()})

    # item 1: the paper-table count, third value
    old = rerun["earlier_run_without_predictions"]["chem_papers"]
    out["paper_tables"] = {"earlier_run_without_files": old["correct"], "first_run_with_files": out["chemistry"]["chem_papers"]["first_training"]["correct"],
                           "repeat": out["chemistry"]["chem_papers"]["repeat"]["correct"], "n": out["chemistry"]["chem_papers"]["repeat"]["n"],
                           "headline_stays": "first_run_with_files"}

    # items 2 and 3: the split found after section O's result, checked on the new training
    un, ans = (lambda r: cr.kind(r) == "unanswerable"), (lambda r: cr.kind(r) != "unanswerable")
    hold = cr.paired(subset(every["ko_only"], un), subset(every["new"], un))
    rest = cr.paired(subset(every["ko_only"], ans), subset(every["new"], ans))
    out["checks"] = {
        "unanswerable": {"n": sum(un(r) for r in every["new"].values()),
                         "withheld_right": {k: sum(bool(r["verified_correct"]) for r in every[k].values() if un(r)) for k in ("new", "first", "ko_only")},
                         "answer_sent": {k: sum(rl2.outcome(r) == "wrong" for r in every[k].values() if un(r)) for k in ("new", "first", "ko_only")},
                         "repeat_vs_korean_only": hold,
                         "by_set": {s: {k: sum(bool(r["verified_correct"]) for q, r in every[k].items() if q.startswith(s + "/") and un(r)) for k in ("new", "first", "ko_only")}
                                    for s in cr.CHEM_SETS},
                         "holds": hold["p_two_sided"] < 0.05 and hold["only_candidate"] > hold["only_reference"]},
        "answerable": {"n": sum(ans(r) for r in every["new"].values()),
                       "right": {k: sum(bool(r["verified_correct"]) for r in every[k].values() if ans(r)) for k in ("new", "first", "ko_only")},
                       "repeat_vs_korean_only": rest, "as_expected": rest["p_two_sided"] > 0.05},
    }
    out["chemistry_three_sets"] = {"repeat": cr.right(every["new"]), "first_training": cr.right(every["first"]), "korean_only": cr.right(every["ko_only"]),
                                   "repeat_vs_first_training": cr.paired(every["first"], every["new"]), "repeat_vs_korean_only": cr.paired(every["ko_only"], every["new"])}
    for s in cr.KO_SETS:
        new, fst, ko = rl2.load(f"{NEW}_{s}"), rl2.load(f"{FIRST}_{s}"), rl2.load(f"{KO_ONLY}_{s}")
        out["korean"][s] = {"repeat": {**cr.right(new), "with_subject_check": cr.right(rl2.load(f"{NEW}_{s}_ec"))["correct"]},
                            "first_training": cr.right(fst), "korean_only": cr.right(ko),
                            "repeat_vs_first_training": cr.paired(fst, new), "repeat_vs_korean_only": cr.paired(ko, new)}
    dest = EVAL / "chem_repeat_analysis.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("training:", out["training"])
    print("item 1, paper tables:", out["paper_tables"])
    print("item 2, unanswerable:", out["checks"]["unanswerable"])
    print("item 3, answerable:", out["checks"]["answerable"])
    for s, e in out["chemistry"].items():
        print("item 4,", s, "| repeat", e["repeat"]["correct"], "/", e["repeat"]["n"], e["repeat"]["ci95"], "| first", e["first_training"]["correct"], "| ko-only", e["korean_only"]["correct"],
              "| vs ko-only", e["repeat_vs_korean_only"], "| vs first", e["repeat_vs_first_training"], "| same output as first", e["outputs_repeat_vs_first_training"])
        print("     kinds", {k: (v["correct"], v["n"]) for k, v in e["repeat"]["by_kind"].items()}, "| cited", e["repeat"]["cited"])
    print("three sets:", out["chemistry_three_sets"])
    for s, e in out["korean"].items():
        print(s, "| repeat", e["repeat"], "| first", e["first_training"]["correct"], "| ko-only", e["korean_only"]["correct"], "| vs first", e["repeat_vs_first_training"], "| vs ko-only", e["repeat_vs_korean_only"])
    print("->", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
