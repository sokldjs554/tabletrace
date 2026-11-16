"""Did the length cap that cut training targets hurt the full-data model? (stored predictions only, no model run)

Until 2026-11-15 every EXAONE fine-tuning cut the target of each training example whose prompt plus target was longer
than --max-len 768: 15.0% of the Korean training examples (docs/dev/issues-log.md 66). On 2026-11-16 the owner trained
the full-data model again with a cap that cuts nothing ("fixed") and, in the same session, once more with the old cap
("old, same session"). Two earlier trainings with the old cap are stored as well.

The comparison that counts is fixed against old in the same session, question by question, and separately for the
test questions that are as long as the training examples that lost their target (prompt + target over 768 tokens).
If the cut hurt, the fixed model should gain on exactly those questions. The three trainings with the old cap show
how much a training run moves when nothing is changed.

  python scripts/length_fix_analysis.py     # -> experiments/eval/length_fix_analysis.json
"""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

from paired_tests import exact_p

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "experiments" / "eval"
OLD_CAP = 768
RUNS = {"fixed": "exaone_full2_vllm_ko_test", "old_same_session": "exaone_full2old_vllm_ko_test",
        "old_run1": "exaone_full_vllm_ko_test", "old_run2": "exaone_full_vllm_ko_test_run2"}
EC = {"fixed": "exaone_full2_vllm_ko_test_ec", "old_same_session": "exaone_full2old_vllm_ko_test_ec",
      "old_run1": "exaone_full_vllm_ko_test_ec", "old_run2": "exaone_full_vllm_ko_test_ec_run2"}
OLD = ("old_run1", "old_run2", "old_same_session")


def load(run: str) -> dict[str, dict]:
    with open(EVAL / run / "predictions.jsonl", encoding="utf-8") as f:
        return {r["qid"]: r for r in map(json.loads, f)}


def sign(a: dict, b: dict, qs: list[str], hit) -> dict:
    """Exact two-sided sign test on the questions where exactly one of the two runs has the property (b = first name)."""
    only_b = sum(1 for q in qs if hit(b[q]) and not hit(a[q]))
    only_a = sum(1 for q in qs if hit(a[q]) and not hit(b[q]))
    p = exact_p(only_b, only_a + only_b)
    n = len(qs)
    diff = (only_b - only_a) / n                                                  # first minus second, as a share of the questions
    se = ((only_a + only_b - (only_b - only_a) ** 2 / n) ** 0.5) / n               # paired proportions, normal approximation
    return {"n": n, "only_first": only_b, "only_second": only_a, "p_two_sided": p, "p_display": "<0.001" if p < 0.001 else f"{p:.3f}",
            "difference": round(diff, 4), "ci95_low": round(diff - 1.959964 * se, 4), "ci95_high": round(diff + 1.959964 * se, 4)}


def rate(rows: dict, qs: list[str], hit) -> dict:
    k = sum(bool(hit(rows[q])) for q in qs)
    return {"k": k, "n": len(qs), "rate": round(k / len(qs), 4)}


def correct(r: dict) -> bool:
    return bool(r["verified_correct"])


def wrong(r: dict) -> bool:
    return not r["verified_correct"] and r["pred_status"] != "abstained"


def setting(names: dict[str, str], groups: dict[str, list[str]]) -> dict:
    rows = {k: load(v) for k, v in names.items()}
    assert all(set(r) == set(rows["fixed"]) for r in rows.values())
    out: dict = {"verified_em": {k: {g: rate(r, qs, correct) for g, qs in groups.items()} for k, r in rows.items()},
                 "wrong_answers": {k: {g: rate(r, qs, wrong) for g, qs in groups.items()} for k, r in rows.items()},
                 "fixed_vs_old_same_session": {g: {"verified_correct": sign(rows["old_same_session"], rows["fixed"], qs, correct),
                                                   "wrong_answer": sign(rows["old_same_session"], rows["fixed"], qs, wrong)} for g, qs in groups.items()},
                 "old_cap_trained_three_times": {}}
    allq = groups["all"]
    for a, b in combinations(OLD, 2):
        out["old_cap_trained_three_times"][f"{b}_vs_{a}"] = sign(rows[a], rows[b], allq, correct)
    em = [out["verified_em"][k]["all"]["rate"] for k in OLD]
    out["old_cap_trained_three_times"]["verified_em_lowest"] = min(em)
    out["old_cap_trained_three_times"]["verified_em_highest"] = max(em)
    out["old_cap_trained_three_times"]["verified_em_spread"] = round(max(em) - min(em), 4)
    out["fixed_inside_the_spread_of_the_old_cap"] = min(em) <= out["verified_em"]["fixed"]["all"]["rate"] <= max(em)
    return out


def evidence(groups: dict[str, list[str]]) -> dict:
    """Lookup questions: the cell the model cited is the gold cell (before the verifier touched the output)."""
    rows = {k: load(v) for k, v in RUNS.items()}
    lookup = {g: [q for q in qs if rows["fixed"][q]["gold_status"] == "answered" and rows["fixed"][q]["gold_op"] == "lookup"] for g, qs in groups.items()}
    cited = lambda r: bool(r["cells_exact_raw"])          # noqa: E731
    repaired = lambda r: bool(r["evidence_repaired"])     # noqa: E731
    return {"lookup_questions": {g: len(qs) for g, qs in lookup.items()},
            "cited_gold_cell": {k: {g: rate(r, qs, cited) for g, qs in lookup.items()} for k, r in rows.items()},
            "evidence_repaired": {k: {g: rate(r, qs, repaired) for g, qs in lookup.items()} for k, r in rows.items()},
            "fixed_vs_old_same_session_cited_gold_cell": {g: sign(rows["old_same_session"], rows["fixed"], qs, cited) for g, qs in lookup.items()}}


def training() -> dict:
    out: dict = {}
    infos = {}
    for label, d in (("fixed", "exaone_lora_full2"), ("old_same_session", "exaone_lora_full2old"), ("old_run1", "exaone_lora_full")):
        t = json.loads((ROOT / "experiments" / d / "train_info.json").read_text(encoding="utf-8"))
        infos[label] = t
        out[label] = {"examples": t["n_examples"], "steps": t["steps"], "minutes": round(t["wall_s"] / 60, 1),
                      "targets_missing": t.get("targets_missing"), "targets_cut_short": t.get("targets_cut_short")}
        if t.get("targets_missing") is not None:
            out[label]["targets_cut_share"] = round((t["targets_missing"] + t["targets_cut_short"]) / t["n_examples"], 4)
    a, b = infos["fixed"]["args"], infos["old_same_session"]["args"]
    out["args_that_differ_between_fixed_and_old_same_session"] = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    return out


def main() -> None:
    lengths = json.loads((EVAL / "ko_test_prompt_lengths.json").read_text(encoding="utf-8"))["questions"]
    total = {q: v["prompt_tokens"] + v["target_tokens"] for q, v in lengths.items()}
    allq = sorted(load(RUNS["fixed"]))
    assert set(allq) == set(total)
    groups = {"all": allq, "fits_old_cap": [q for q in allq if total[q] <= OLD_CAP], "over_old_cap": [q for q in allq if total[q] > OLD_CAP]}
    out = {"old_cap_tokens": OLD_CAP, "runs": RUNS,
           "test_questions": {g: len(qs) for g, qs in groups.items()},
           "over_old_cap_share": round(len(groups["over_old_cap"]) / len(allq), 4),
           "over_old_cap_whole_target_would_be_cut": sum(lengths[q]["prompt_tokens"] >= OLD_CAP for q in groups["over_old_cap"]),
           "longest_test_question_tokens": max(total.values()),
           "training": training(), "first_pass": setting(RUNS, groups), "subject_check": setting(EC, groups), "evidence": evidence(groups)}
    dest = EVAL / "length_fix_analysis.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("test questions:", out["test_questions"], "| training:", json.dumps(out["training"], ensure_ascii=False))
    for s in ("first_pass", "subject_check"):
        print("==", s)
        for k in RUNS:
            print(f"   {k:17s}", {g: (v["k"], v["rate"]) for g, v in out[s]["verified_em"][k].items()}, "| wrong", {g: v["k"] for g, v in out[s]["wrong_answers"][k].items()})
        print("   fixed vs old (same session):", {g: (v["verified_correct"]["only_first"], v["verified_correct"]["only_second"], v["verified_correct"]["p_display"]) for g, v in out[s]["fixed_vs_old_same_session"].items()})
        print("   old cap, three trainings:", {k: ((v["only_first"], v["only_second"], v["p_display"]) if isinstance(v, dict) else v) for k, v in out[s]["old_cap_trained_three_times"].items()},
              "| fixed inside the spread:", out[s]["fixed_inside_the_spread_of_the_old_cap"])
    e = out["evidence"]
    print("== cited gold cell (lookup)", e["lookup_questions"], {k: {g: (v["k"], v["rate"]) for g, v in d.items()} for k, d in e["cited_gold_cell"].items()})
    print("   fixed vs old:", {g: (v["only_first"], v["only_second"], v["p_display"]) for g, v in e["fixed_vs_old_same_session_cited_gold_cell"].items()},
          "| repaired:", {k: {g: v["k"] for g, v in d.items()} for k, d in e["evidence_repaired"].items()})
    print("->", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
