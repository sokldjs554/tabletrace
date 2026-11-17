"""What the chemistry training questions add: a model tuned on Korean only, scored on the chemistry questions
(notebook 2, section O; the owner ran it on Colab on 2026-11-17).

  python scripts/chem_share_analysis.py     # -> experiments/eval/chem_share_analysis.json

Section N compared the model tuned on Korean and chemistry with the untuned model. That difference mixes two things:
what the Korean questions teach (the output format, reading a table) and what the chemistry questions add. This run
puts the missing model in between: the same training command without the chemistry files. Compared question by
question with section N's model, with the untuned model and with the heuristic baseline.

The two tuned models come from two sessions and one training each, so a small difference between them cannot be told
from the spread between trainings; the spread of the Korean-only trainings on the Korean test set is given for scale.
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
KO_ONLY, BOTH, UNTUNED, EARLIER_KO_ONLY = "exaone_koonly_vllm", "exaone_kochem2_vllm", "ref_1p2b", "exaone_full4_vllm"
HAND_WRITTEN = ("chem_papers", "chem_custom")
FULL_DATA_RUNS = ("exaone_full_vllm_ko_test", "exaone_full_vllm_ko_test_run2", "exaone_full2old_vllm_ko_test", "exaone_full2_vllm_ko_test",
                  "exaone_full3_vllm_ko_test", "exaone_full4_vllm_ko_test", "exaone_ownloop_vllm_ko_test")


def subset(rows: dict, keep) -> dict:
    return {q: r for q, r in rows.items() if keep(r)}


def paired_by_kind(a: dict, b: dict) -> dict:
    """b against a within each kind of question (the gold program's)."""
    out = {}
    for k in ("lookup", "calc", "text", "unanswerable"):
        qs = [q for q in a if cr.kind(a[q]) == k]
        if qs:
            out[k] = {"n": len(qs), **cr.paired({q: a[q] for q in qs}, {q: b[q] for q in qs})}
    return out


def same_output(a: dict, b: dict) -> dict:
    same = sum((a[q]["raw_output"] or "") == (b[q]["raw_output"] or "") for q in a)
    return {"questions": len(a), "same_raw_output": same, "rate": round(same / len(a), 4)}


def main() -> None:
    info = json.loads((ROOT / "experiments" / "exaone_lora_koonly" / "train_info.json").read_text(encoding="utf-8"))
    earlier = json.loads((ROOT / "experiments" / "exaone_lora_full4" / "train_info.json").read_text(encoding="utf-8"))
    both_info = json.loads((ROOT / "experiments" / "exaone_lora_kochem2" / "train_info.json").read_text(encoding="utf-8"))
    platform = json.loads((ROOT / "experiments" / "run_info_2_share.json").read_text(encoding="utf-8"))
    log = info["loss_log"]

    def differ(other: dict) -> list[str]:
        return sorted(k for k in set(info["args"]) | set(other["args"]) if info["args"].get(k) != other["args"].get(k))

    out: dict = {
        "platform": platform["platform"], "gpus": platform["gpus"], "notebook_commit": platform["commit"], "finished": platform["finished"],
        "training": {"examples": info["n_examples"], "steps": info["steps"], "minutes": round(info["wall_s"] / 60, 1), "loop": info["loop"],
                     "targets_missing": info["targets_missing"], "targets_cut_short": info["targets_cut_short"],
                     "loss_first_20_steps": round(sum(x["loss"] for x in log[:20]) / 20, 4), "loss_last_20_steps": round(sum(x["loss"] for x in log[-20:]) / 20, 4),
                     "args_that_differ_from_the_stored_korean_only_training": differ(earlier),
                     "args_that_differ_from_the_korean_and_chemistry_training": differ(both_info),
                     "chemistry_questions_in_training": sum("chem" in f for f in info["args"]["train"])},
        "chemistry": {}, "korean": {},
    }
    pooled = {name: {} for name in ("ko_only", "both", "untuned")}
    every = {name: {} for name in ("ko_only", "both")}
    for s, label in cr.CHEM_SETS.items():
        ko, both, plain = rl2.load(f"{KO_ONLY}_{s}"), rl2.load(f"{BOTH}_{s}"), rl2.load(f"{UNTUNED}_{s}")
        assert set(ko) == set(both) == set(plain)
        entry = {"label": label,
                 "korean_only": {**cr.right(ko), **cr.kinds(ko), "cited": cr.cited(ko), "with_subject_check": cr.right(rl2.load(f"{KO_ONLY}_{s}_ec"))["correct"]},
                 "korean_and_chemistry": {**cr.right(both), **cr.kinds(both), "cited": cr.cited(both)},
                 "untuned_six_examples": cr.right(plain),
                 "with_chemistry_vs_korean_only": cr.paired(ko, both),             # only_candidate: only the model that also saw chemistry
                 "with_chemistry_vs_korean_only_by_kind": paired_by_kind(ko, both),
                 "korean_only_vs_untuned": cr.paired(plain, ko),
                 "questions_gained_over_untuned": {"korean_only": cr.right(ko)["correct"] - cr.right(plain)["correct"],
                                                   "korean_and_chemistry": cr.right(both)["correct"] - cr.right(plain)["correct"]},
                 "outputs_korean_only_vs_with_chemistry": same_output(ko, both)}
        if (EVAL / f"heuristic_{s}" / "predictions.jsonl").exists():
            h = rl2.load(f"heuristic_{s}")
            entry["heuristic"] = cr.right(h)
            entry["korean_only_vs_heuristic"] = cr.paired(h, ko)
        out["chemistry"][s] = entry
        every["ko_only"].update({f"{s}/{q}": r for q, r in ko.items()})
        every["both"].update({f"{s}/{q}": r for q, r in both.items()})
        if s in HAND_WRITTEN:
            for name, rows in (("ko_only", ko), ("both", both), ("untuned", plain)):
                pooled[name].update({f"{s}/{q}": r for q, r in rows.items()})
    # the two hand-written chemistry sets together: more questions for the same comparison (the synthetic set shares its templates with the training questions)
    # Like the split by kind below, this pooling was done after the per-set numbers had been seen. Planned before the run
    # (docs/REPORT.md §29.7 as it stood then) was the per-set comparison of the two tuned models, question by question.
    out["chemistry_hand_written_together"] = {
        "planned_before_the_result": False, "sets": list(HAND_WRITTEN), "korean_only": cr.right(pooled["ko_only"]), "korean_and_chemistry": cr.right(pooled["both"]), "untuned_six_examples": cr.right(pooled["untuned"]),
        "with_chemistry_vs_korean_only": cr.paired(pooled["ko_only"], pooled["both"]),
        "with_chemistry_vs_korean_only_without_passage_questions": cr.paired(subset(pooled["ko_only"], lambda r: cr.kind(r) != "text"), subset(pooled["both"], lambda r: cr.kind(r) != "text")),
        "korean_only_vs_untuned": cr.paired(pooled["untuned"], pooled["ko_only"])}
    # where the two tuned models part, over the three chemistry sets. This split was looked at after the per-set numbers
    # had been seen (the unanswerable questions stood out in each set), so it describes the result; it was not a planned test.
    answerable = lambda r: cr.kind(r) != "unanswerable"  # noqa: E731
    out["chemistry_three_sets_by_kind"] = {
        "planned_before_the_result": False, "questions": len(every["ko_only"]),
        "korean_only": cr.by_kind(every["ko_only"]), "korean_and_chemistry": cr.by_kind(every["both"]),
        "with_chemistry_vs_korean_only": paired_by_kind(every["ko_only"], every["both"]),
        "with_chemistry_vs_korean_only_on_answerable_questions": {"n": sum(answerable(r) for r in every["ko_only"].values()),
                                                                  **cr.paired(subset(every["ko_only"], answerable), subset(every["both"], answerable))},
        # what the Korean-only model did with the unanswerable chemistry questions it got wrong
        "korean_only_unanswerable_errors": {"answer_sent": sum(rl2.outcome(r) == "wrong" for r in every["ko_only"].values() if not answerable(r)),
                                            "of": sum(not answerable(r) for r in every["ko_only"].values())}}
    for s in cr.KO_SETS:
        ko, both, old = rl2.load(f"{KO_ONLY}_{s}"), rl2.load(f"{BOTH}_{s}"), rl2.load(f"{EARLIER_KO_ONLY}_{s}")
        out["korean"][s] = {"korean_only": {**cr.right(ko), "by_kind": cr.by_kind(ko), "with_subject_check": cr.right(rl2.load(f"{KO_ONLY}_{s}_ec"))["correct"]},
                            "korean_and_chemistry": cr.right(both), "korean_only_earlier_training": cr.right(old),
                            "with_chemistry_vs_korean_only": cr.paired(ko, both), "this_training_vs_the_earlier_korean_only_training": cr.paired(old, ko)}
    spread = [cr.metrics(r)["verified_em"] for r in FULL_DATA_RUNS]
    em = cr.metrics(f"{KO_ONLY}_ko_test")["verified_em"]
    out["korean"]["ko_test"]["full_data_trainings_before_this_one"] = {"lowest": min(spread), "highest": max(spread), "runs": len(spread),
                                                                       "this_training_inside_their_range": min(spread) <= em <= max(spread),
                                                                       "questions_between_lowest_and_highest": round((max(spread) - min(spread)) * out["korean"]["ko_test"]["korean_only"]["n"])}
    dest = EVAL / "chem_share_analysis.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("training:", out["training"])
    for s, e in out["chemistry"].items():
        print(s, "| korean only", e["korean_only"]["correct"], "/", e["korean_only"]["n"], e["korean_only"]["ci95"], "| with chemistry", e["korean_and_chemistry"]["correct"],
              "| untuned", e["untuned_six_examples"]["correct"], "| heuristic", e.get("heuristic", {}).get("correct"),
              "| +chem vs ko-only", e["with_chemistry_vs_korean_only"], "| ko-only vs untuned", e["korean_only_vs_untuned"], "| vs heuristic", e.get("korean_only_vs_heuristic"))
        print("   kinds ko-only", {k: (v["correct"], v["n"]) for k, v in e["korean_only"]["by_kind"].items()}, "| with chem", {k: (v["correct"], v["n"]) for k, v in e["korean_and_chemistry"]["by_kind"].items()})
        print("   by kind paired", {k: (v["only_candidate"], v["only_reference"], v["p_display"]) for k, v in e["with_chemistry_vs_korean_only_by_kind"].items()},
              "| cited", e["korean_only"]["cited"], "vs", e["korean_and_chemistry"]["cited"], "| same output", e["outputs_korean_only_vs_with_chemistry"])
    print("hand-written together:", out["chemistry_hand_written_together"])
    print("three sets by kind:", out["chemistry_three_sets_by_kind"])
    for s, e in out["korean"].items():
        print(s, "| korean only", e["korean_only"]["correct"], "/", e["korean_only"]["n"], "| with chemistry", e["korean_and_chemistry"]["correct"], "| earlier korean-only", e["korean_only_earlier_training"]["correct"],
              "|", e["with_chemistry_vs_korean_only"], "|", e["this_training_vs_the_earlier_korean_only_training"])
    print(out["korean"]["ko_test"]["full_data_trainings_before_this_one"], "->", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
