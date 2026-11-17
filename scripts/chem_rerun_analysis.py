"""EXAONE on the chemistry questions, with per-question predictions (notebook 2, section N; the owner ran it on Colab on 2026-11-17).

  python scripts/chem_rerun_analysis.py     # -> experiments/eval/chem_rerun_analysis.json

The model tuned on Korean and chemistry (the data of section G, the corrected length setting) and the untuned 1.2B model
with six chemistry examples, on the three chemistry sets; the tuned model also on the three Korean sets. Compared, question
by question where predictions exist, with the heuristic baseline, the final mT5-small, and the full-data model tuned on
Korean only. The earlier run of the same experiment (section G, 2026-11-14) left numbers read off the notebook's output
and no predictions, so it can only be set beside this run, not tested against it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rl2_analysis as rl2  # noqa: E402
from evidence_error import wilson  # noqa: E402

EVAL = ROOT / "experiments" / "eval"
TUNED, UNTUNED, KO_ONLY = "exaone_kochem2_vllm", "ref_1p2b", "exaone_full4_vllm"
CHEM_SETS = {"chem_custom": "화학 교과서 표, 수작업", "chem_syndev": "화학 합성 개발", "chem_papers": "화학 논문 표, 수작업"}
KO_SETS = ("ko_test", "ko_custom", "ko_owner")
OTHERS = {"heuristic": "heuristic", "mt5_small_final": "rl_v3"}


def metrics(run: str) -> dict:
    return json.loads((EVAL / run / "metrics.json").read_text(encoding="utf-8"))["metrics"]


def right(rows: dict) -> dict:
    k = sum(rl2.outcome(r) == "correct" for r in rows.values())
    return {"n": len(rows), "correct": k, "rate": round(k / len(rows), 4), "ci95": {x: round(wilson(k, len(rows))[x], 4) for x in ("lo", "hi")}}


def kind(r: dict) -> str:
    """By the gold program. rl2_analysis.kind knows the Korean calculations only (diff, sum, avg) and would count the
    chemistry ratios and percentage changes, and the questions answered from the passage, as lookups."""
    if r["gold_status"] != "answered":
        return "unanswerable"
    return r["gold_op"] if r["gold_op"] in ("lookup", "text") else "calc"


def by_kind(rows: dict) -> dict:
    out = {}
    for k in ("lookup", "calc", "text", "unanswerable"):
        qs = [q for q in rows if kind(rows[q]) == k]
        if qs:
            out[k] = {"n": len(qs), **{o: sum(rl2.outcome(rows[q]) == o for q in qs) for o in ("correct", "wrong", "withheld")}}
    return out


def by_category(rows: dict) -> dict:
    """By the category the question file gives (the hand-written sets; the synthetic set has none). The per-question
    view of the demo counts by the same categories."""
    cats = [r.get("category") for r in rows.values()]
    if not all(cats):
        return {}
    return {c: {"n": cats.count(c), **{o: sum(rl2.outcome(r) == o for r in rows.values() if r["category"] == c) for o in ("correct", "wrong", "withheld")}}
            for c in ("cell", "calc", "unit_period", "text_table", "abstain") if c in cats}


def kinds(rows: dict) -> dict:
    cat = by_category(rows)
    return {"by_kind": by_kind(rows), **({"by_category": cat} if cat else {})}


def paired(a: dict, b: dict) -> dict:
    """b against a on the questions both answered: how many only b got right, how many only a, and the exact sign test."""
    s = rl2.sign(a, b, list(a), lambda r: rl2.outcome(r) == "correct")
    return {"only_candidate": s["only_rl"], "only_reference": s["only_start"], "p_two_sided": s["p_two_sided"], "p_display": s["p_display"]}


def cited(rows: dict) -> dict:
    """Lookup questions: did the model cite the gold cell (before the verifier touched it)?"""
    qs = [q for q in rows if kind(rows[q]) == "lookup"]
    ok = sum(bool(rows[q]["cells_exact_raw"]) for q in qs)
    return {"lookup_questions": len(qs), "cited_gold_cell": ok, "rate": round(ok / len(qs), 4) if qs else None,
            "evidence_repaired": sum(bool(rows[q]["evidence_repaired"]) for q in rows)}


def main() -> None:
    info = json.loads((ROOT / "experiments" / "exaone_lora_kochem2" / "train_info.json").read_text(encoding="utf-8"))
    same = json.loads((ROOT / "experiments" / "exaone_lora_full4" / "train_info.json").read_text(encoding="utf-8"))
    platform = json.loads((ROOT / "experiments" / "run_info_2_chem.json").read_text(encoding="utf-8"))
    recovered = json.loads((ROOT / "experiments" / "gpu2_2026-11-14" / "recovered.json").read_text(encoding="utf-8"))["evals"]
    log = info["loss_log"]
    chem_lines = sum(1 for line in (ROOT / "data" / "chem" / "synthetic_train.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
    out: dict = {
        "platform": platform["platform"], "gpus": platform["gpus"], "notebook_commit": platform["commit"], "finished": platform["finished"],
        "training": {"examples": info["n_examples"], "korean_examples_in_the_full_data_training": same["n_examples"],
                     "chemistry_examples_added": info["n_examples"] - same["n_examples"],
                     # the training script leaves out a question whose gold row does not fit the input length
                     "chemistry_questions_in_the_file": chem_lines, "chemistry_questions_left_out": chem_lines - (info["n_examples"] - same["n_examples"]),
                     "steps": info["steps"], "minutes": round(info["wall_s"] / 60, 1),
                     "loop": info["loop"], "targets_missing": info["targets_missing"], "targets_cut_short": info["targets_cut_short"],
                     "loss_first_20_steps": round(sum(x["loss"] for x in log[:20]) / 20, 4), "loss_last_20_steps": round(sum(x["loss"] for x in log[-20:]) / 20, 4),
                     "args_that_differ_from_the_korean_only_training": sorted(k for k in set(info["args"]) | set(same["args"]) if info["args"].get(k) != same["args"].get(k))},
        "chemistry": {}, "korean": {}, "earlier_run_without_predictions": {},
    }
    for s, label in CHEM_SETS.items():
        tuned, untuned = rl2.load(f"{TUNED}_{s}"), rl2.load(f"{UNTUNED}_{s}")
        entry = {"label": label, "tuned": {**right(tuned), **kinds(tuned), "cited": cited(tuned), "with_subject_check": right(rl2.load(f"{TUNED}_{s}_ec"))["correct"]},
                 "untuned_six_examples": {**right(untuned), **kinds(untuned), "cited": cited(untuned),
                                          "parse_fail_rate": metrics(f"{UNTUNED}_{s}")["parse_fail_rate"]},
                 "tuned_vs_untuned": paired(untuned, tuned)}
        for name, prefix in OTHERS.items():
            if (EVAL / f"{prefix}_{s}" / "predictions.jsonl").exists():
                rows = rl2.load(f"{prefix}_{s}")
                entry[name] = {**right(rows), **kinds(rows)}
                entry[f"tuned_vs_{name}"] = paired(rows, tuned)
        out["chemistry"][s] = entry
        old = recovered[f"exaone_kochem_vllm_{s}"]["v1"]["metrics"]
        out["earlier_run_without_predictions"][s] = {"n": old["n"], "verified_em": old["verified_em"], "correct": round(old["verified_em"] * old["n"]),
                                                     "this_run_minus_earlier_in_questions": entry["tuned"]["correct"] - round(old["verified_em"] * old["n"])}
    full_range = [metrics(r)["verified_em"] for r in ("exaone_full_vllm_ko_test", "exaone_full_vllm_ko_test_run2", "exaone_full2old_vllm_ko_test", "exaone_full2_vllm_ko_test",
                                                       "exaone_full3_vllm_ko_test", "exaone_full4_vllm_ko_test", "exaone_ownloop_vllm_ko_test")]
    for s in KO_SETS:
        tuned, ko = rl2.load(f"{TUNED}_{s}"), rl2.load(f"{KO_ONLY}_{s}")
        out["korean"][s] = {"with_chemistry": {**right(tuned), "by_kind": by_kind(tuned), "with_subject_check": right(rl2.load(f"{TUNED}_{s}_ec"))["correct"]},
                            "korean_only_same_lengths": {**right(ko), "by_kind": by_kind(ko)}, "with_chemistry_vs_korean_only": paired(ko, tuned)}
    em = out["korean"]["ko_test"]["with_chemistry"]["rate"]
    out["korean"]["ko_test"]["full_data_trainings"] = {"lowest": min(full_range), "highest": max(full_range), "runs": len(full_range),
                                                        "with_chemistry_inside_their_range": min(full_range) <= metrics(f"{TUNED}_ko_test")["verified_em"] <= max(full_range)}
    for s in ("ko_test", "ko_custom"):
        old = recovered[f"exaone_kochem_vllm_{s}"]["v1"]["metrics"]
        out["earlier_run_without_predictions"][s] = {"n": old["n"], "verified_em": old["verified_em"], "correct": round(old["verified_em"] * old["n"]),
                                                     "this_run_minus_earlier_in_questions": out["korean"][s]["with_chemistry"]["correct"] - round(old["verified_em"] * old["n"])}
    out["earlier_run_without_predictions"]["note"] = ("section G, 2026-11-14: the same data with the old length setting (targets could be cut); "
                                                      "numbers recovered from the notebook's output, no per-question file, so no paired test is possible")
    assert abs(em - metrics(f"{TUNED}_ko_test")["verified_em"]) < 1e-3
    dest = EVAL / "chem_rerun_analysis.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("training:", out["training"])
    for s, e in out["chemistry"].items():
        print(s, "| tuned", e["tuned"]["correct"], "/", e["tuned"]["n"], e["tuned"]["ci95"], "| untuned", e["untuned_six_examples"]["correct"],
              "| heuristic", e.get("heuristic", {}).get("correct"), "| mT5", e.get("mt5_small_final", {}).get("correct"),
              "| vs untuned", e["tuned_vs_untuned"], "| vs heuristic", e.get("tuned_vs_heuristic"), "| kinds", e["tuned"]["by_kind"], "| cited", e["tuned"]["cited"])
    for s, e in out["korean"].items():
        print(s, "| with chem", e["with_chemistry"]["correct"], "/", e["with_chemistry"]["n"], "| korean only", e["korean_only_same_lengths"]["correct"], "|", e["with_chemistry_vs_korean_only"],
              "| kinds", e["with_chemistry"]["by_kind"], "vs", e["korean_only_same_lengths"]["by_kind"])
    print("earlier:", out["earlier_run_without_predictions"], "->", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
