"""What the second RL experiment changed, question by question (stored predictions only, no model run).

Compares the 300-example start model with the model after 200 policy-gradient steps on the same 699 test questions,
once per verifier setting (first pass, and with the subject check). Every question ends in one of three outcomes:

  correct    the verifier let an answer out and it is right (for a question without an answer: nothing was sent)
  wrong      an answer went out and it is not right
  withheld   nothing went out although the question has an answer

  python scripts/rl2_analysis.py     # -> experiments/eval/rl2_analysis.json
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from paired_tests import exact_p

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "experiments" / "eval"
START, RL = "exaone_rlstart2_vllm_ko_test", "exaone_grpo2_vllm_ko_test"
CALC = ("diff", "sum", "avg")
OUTCOMES = ("correct", "wrong", "withheld")


def load(run: str) -> dict[str, dict]:
    with open(EVAL / run / "predictions.jsonl", encoding="utf-8") as f:
        return {r["qid"]: r for r in map(json.loads, f)}


def outcome(r: dict) -> str:
    if r["verified_correct"]:
        return "correct"
    return "withheld" if r["pred_status"] == "abstained" else "wrong"


def kind(r: dict) -> str:
    if r["gold_status"] != "answered":
        return "unanswerable"
    return "calc" if r["gold_op"] in CALC else "lookup"


def counts(rows: list[dict]) -> dict:
    c = Counter(outcome(r) for r in rows)
    n = len(rows)
    return {"n": n, **{k: c.get(k, 0) for k in OUTCOMES}, **{f"{k}_rate": round(c.get(k, 0) / n, 4) for k in OUTCOMES}}


def sign(a: dict, b: dict, qs: list[str], hit) -> dict:
    """Exact two-sided sign test on the questions where exactly one of the two models has the property."""
    only_b = sum(1 for q in qs if hit(b[q]) and not hit(a[q]))
    only_a = sum(1 for q in qs if hit(a[q]) and not hit(b[q]))
    p = exact_p(only_b, only_a + only_b)
    return {"n": len(qs), "only_rl": only_b, "only_start": only_a, "p_two_sided": p, "p_display": "<0.001" if p < 0.001 else f"{p:.3f}"}


def setting(suffix: str) -> dict:
    a, b = load(START + suffix), load(RL + suffix)
    assert set(a) == set(b)
    out: dict = {"outcomes": {}, "transitions": {}, "sign_tests": {}}
    for name, rows in (("start", a), ("rl", b)):
        out["outcomes"][name] = {"all": counts(list(rows.values()))}
        for k in ("lookup", "calc", "unanswerable"):
            out["outcomes"][name][k] = counts([r for r in rows.values() if kind(r) == k])
    for k in ("lookup", "calc", "unanswerable"):
        qs = [q for q in a if kind(a[q]) == k]
        t = Counter(f"{outcome(a[q])}_to_{outcome(b[q])}" for q in qs)
        out["transitions"][k] = {f"{x}_to_{y}": t.get(f"{x}_to_{y}", 0) for x in OUTCOMES for y in OUTCOMES}
    allq = list(a)
    out["sign_tests"]["correct_all"] = sign(a, b, allq, lambda r: outcome(r) == "correct")
    out["sign_tests"]["wrong_all"] = sign(a, b, allq, lambda r: outcome(r) == "wrong")
    out["sign_tests"]["withheld_all"] = sign(a, b, allq, lambda r: outcome(r) == "withheld")
    for k in ("lookup", "calc"):
        qs = [q for q in a if kind(a[q]) == k]
        out["sign_tests"][f"correct_{k}"] = sign(a, b, qs, lambda r: outcome(r) == "correct")
        out["sign_tests"][f"wrong_{k}"] = sign(a, b, qs, lambda r: outcome(r) == "wrong")
    return out


def raw_side() -> dict:
    """What the models wrote before the verifier touched it (the same for both verifier settings)."""
    a, b = load(START), load(RL)
    out: dict = {}
    for name, rows in (("start", a), ("rl", b)):
        lk = [r for r in rows.values() if kind(r) == "lookup"]
        ca = [r for r in rows.values() if kind(r) == "calc"]
        ops = Counter(r["pred_op"] or "none" for r in rows.values())
        out[name] = {
            "lookup_questions": len(lk),
            "lookup_answer_right": sum(r["raw_correct"] for r in lk),
            "lookup_cited_gold_cell": sum(r["cells_exact_raw"] for r in lk),
            "lookup_answer_right_and_cited_gold_cell": sum(r["raw_correct"] and r["cells_exact_raw"] for r in lk),
            "lookup_evidence_repaired": sum(r["evidence_repaired"] for r in lk),
            "calc_questions": len(ca),
            "calc_written_as_lookup": sum(r["pred_op"] == "lookup" for r in ca),
            "calc_answer_is_an_expression": sum(any(s in (r["raw_output"] or "").split("answer:")[-1] for s in (" - ", " + ", " = ", " / ")) for r in ca),
            "calc_answer_text_right": sum(r["raw_correct"] for r in ca),
            "programs_by_op": dict(ops),
        }
    qs = [q for q in a if kind(a[q]) == "lookup"]
    out["sign_test_cited_gold_cell_lookup"] = sign(a, b, qs, lambda r: bool(r["cells_exact_raw"]))
    out["sign_test_answer_right_lookup"] = sign(a, b, qs, lambda r: bool(r["raw_correct"]))
    return out


def training() -> dict:
    info = json.loads((ROOT / "experiments" / "exaone_grpo2" / "train_info.json").read_text(encoding="utf-8"))
    steps = [json.loads(line) for line in open(ROOT / "experiments" / "exaone_grpo2" / "train_log.jsonl", encoding="utf-8")]
    steps = [s for s in steps if "step" in s]
    phases = []
    for i in range(0, len(steps), 50):
        part = steps[i:i + 50]
        tot = {k: sum(s[k] for s in part) for k in ("correct", "repaired", "withheld", "wrong", "unparsable")}
        phases.append({"steps": f"{part[0]['step']}-{part[-1]['step']}", "mean_reward": round(sum(s["reward_mean"] for s in part) / len(part), 4),
                       "samples": sum(tot.values()), **tot, **{f"{k}_rate": round(v / sum(tot.values()), 4) for k, v in tot.items()}})
    dev = {f"step_{d['step']}": d for d in info["dev_history"]}
    best = max(info["dev_history"], key=lambda d: d["mean_reward"])
    return {"steps": info["steps"], "updates_applied": info["updates_applied"], "kept_step": info["kept_step"], "best_dev_step": best["step"],
            "dev": dev, "dev_first": info["dev_history"][0], "dev_kept": dev[f"step_{info['kept_step']}"], "dev_last": info["dev_history"][-1],
            "dev_kinds": info["dev_kinds"], "phases": {f"p{i + 1}": p for i, p in enumerate(phases)},
            "samples_per_step": info["args"]["prompts"] * info["args"]["group"], "wall_minutes": round(info["wall_s"] / 60, 1),
            "prompts_cut_train": info["prompts_cut"]["train"], "prompts_cut_dev": info["prompts_cut"]["dev"], "sampling": info["sampling"]}


def deltas() -> dict:
    """Metric differences (RL model minus start model), so that a document can cite them without doing arithmetic by hand."""
    keys = ("verified_em", "raw_answer_em_answerable", "evidence_cells_exact_raw", "evidence_repaired_rate", "false_abstain_rate", "abstain_recall", "lookup_em")
    out: dict = {}
    for label, suffix in (("first_pass", ""), ("subject_check", "_ec")):
        a = json.loads((EVAL / (START + suffix) / "metrics.json").read_text(encoding="utf-8"))["metrics"]
        b = json.loads((EVAL / (RL + suffix) / "metrics.json").read_text(encoding="utf-8"))["metrics"]
        out[label] = {k: round(b[k] - a[k], 4) for k in keys}
    nr = json.loads((EVAL / "no_repair_check.json").read_text(encoding="utf-8"))["runs"]
    out["verified_em_without_repair"] = round(nr[RL]["verified_em_replayed"] - nr[START]["verified_em_replayed"], 4)
    ee = json.loads((EVAL / "evidence_error.json").read_text(encoding="utf-8"))
    out["evidence_error_among_right_lookup_answers"] = round(ee[RL]["strict"]["rate"] - ee[START]["strict"]["rate"], 4)
    return out


def cost() -> dict:
    """Training time on one T4, from the train_info files of this project."""
    def minutes(path: str) -> float:
        return round(json.loads((ROOT / "experiments" / path / "train_info.json").read_text(encoding="utf-8"))["wall_s"] / 60, 1)
    return {"start_sft_300_minutes": minutes("exaone_lora_rlstart2"), "rl_200_steps_minutes": minutes("exaone_grpo2"), "sft_full_data_minutes": minutes("exaone_lora_full")}


def main() -> None:
    out = {"start": START, "rl": RL, "first_pass": setting(""), "subject_check": setting("_ec"), "raw": raw_side(), "training": training(),
           "delta_rl_minus_start": deltas(), "cost": cost()}
    dest = EVAL / "rl2_analysis.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for s in ("first_pass", "subject_check"):
        for k in ("all", "lookup", "calc", "unanswerable"):
            a, b = out[s]["outcomes"]["start"][k], out[s]["outcomes"]["rl"][k]
            print(f"{s:14s} {k:13s} n={a['n']:3d} | start correct {a['correct']:3d} wrong {a['wrong']:3d} withheld {a['withheld']:3d} | rl correct {b['correct']:3d} wrong {b['wrong']:3d} withheld {b['withheld']:3d}")
        print("   sign tests:", {k: (v["only_rl"], v["only_start"], v["p_display"]) for k, v in out[s]["sign_tests"].items()})
    print("raw:", json.dumps(out["raw"], ensure_ascii=False))
    print("->", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
