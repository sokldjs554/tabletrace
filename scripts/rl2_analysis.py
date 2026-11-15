"""What the second RL experiment changed, question by question (stored predictions only, no model run).

Compares the 300-example start model with the model after 200 policy-gradient steps on the same 699 test questions,
once per verifier setting (first pass, and with the subject check). Every question ends in one of three outcomes:

  correct    the verifier let an answer out and it is right (for a question without an answer: nothing was sent)
  wrong      an answer went out and it is not right
  withheld   nothing went out although the question has an answer

The control run (balanced sampling as in the first experiment, everything else as in the second) was made in a later
session with its own start model. It gets the same analysis, and a comparison of the two arms: for every question the
change in the main experiment minus the change in the control (a sign test on the questions where the two differ).

The main experiment was then run once more ("repeat"), from the control's start model: its weights were still in the
session. Repeat and control differ in the sampler only, so their comparison needs no correction for the start model.

  python scripts/rl2_analysis.py     # -> experiments/eval/rl2_analysis.json, rl2_control_analysis.json, rl2_repeat_analysis.json
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from paired_tests import exact_p

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "experiments" / "eval"
START, RL = "exaone_rlstart2_vllm_ko_test", "exaone_grpo2_vllm_ko_test"
START_C, RL_C = "exaone_rlstart2b_vllm_ko_test", "exaone_grpo2b_vllm_ko_test"          # the control run and its own start model
RL_R = "exaone_grpo2c_vllm_ko_test"                                                    # the main experiment once more, from the control's start model
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


def setting(suffix: str, start: str = START, rl: str = RL) -> dict:
    a, b = load(start + suffix), load(rl + suffix)
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


def raw_side(start: str = START, rl: str = RL) -> dict:
    """What the models wrote before the verifier touched it (the same for both verifier settings)."""
    a, b = load(start), load(rl)
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


def training(run_dir: str = "exaone_grpo2") -> dict:
    info = json.loads((ROOT / "experiments" / run_dir / "train_info.json").read_text(encoding="utf-8"))
    steps = [json.loads(line) for line in open(ROOT / "experiments" / run_dir / "train_log.jsonl", encoding="utf-8")]
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


def deltas(start: str = START, rl: str = RL) -> dict:
    """Metric differences (RL model minus start model), so that a document can cite them without doing arithmetic by hand."""
    keys = ("verified_em", "raw_answer_em_answerable", "evidence_cells_exact_raw", "evidence_repaired_rate", "false_abstain_rate", "abstain_recall", "lookup_em")
    out: dict = {}
    for label, suffix in (("first_pass", ""), ("subject_check", "_ec")):
        a = json.loads((EVAL / (start + suffix) / "metrics.json").read_text(encoding="utf-8"))["metrics"]
        b = json.loads((EVAL / (rl + suffix) / "metrics.json").read_text(encoding="utf-8"))["metrics"]
        out[label] = {k: round(b[k] - a[k], 4) for k in keys}
    nr = json.loads((EVAL / "no_repair_check.json").read_text(encoding="utf-8"))["runs"]
    out["verified_em_without_repair"] = round(nr[rl]["verified_em_replayed"] - nr[start]["verified_em_replayed"], 4)
    ee = json.loads((EVAL / "evidence_error.json").read_text(encoding="utf-8"))
    out["evidence_error_among_right_lookup_answers"] = round(ee[rl]["strict"]["rate"] - ee[start]["strict"]["rate"], 4)
    return out


def cost() -> dict:
    """Training time on one T4, from the train_info files of this project."""
    def minutes(path: str) -> float:
        return round(json.loads((ROOT / "experiments" / path / "train_info.json").read_text(encoding="utf-8"))["wall_s"] / 60, 1)
    return {"start_sft_300_minutes": minutes("exaone_lora_rlstart2"), "rl_200_steps_minutes": minutes("exaone_grpo2"), "sft_full_data_minutes": minutes("exaone_lora_full")}


def arms(first: tuple[str, str] = (START, RL), second: tuple[str, str] = (START_C, RL_C), names: tuple[str, str] = ("main", "control")) -> dict:
    """One arm against another, question by question. Each arm has its own start model, so the quantity compared is
    the change an arm made: +1 if RL gained the property on that question, -1 if it lost it, 0 otherwise. The sign test
    runs on the questions where the two arms changed differently. (With one start model for both arms this is the
    plain paired comparison of the two models after RL.)"""
    out: dict = {}
    na, nb = names
    for label, suffix in (("first_pass", ""), ("subject_check", "_ec")):
        a0, a1, c0, c1 = load(first[0] + suffix), load(first[1] + suffix), load(second[0] + suffix), load(second[1] + suffix)
        assert set(a0) == set(c0)
        res = {}
        for name, qs, hit in (
            ("verified_correct_all", list(a0), lambda r: outcome(r) == "correct"),
            ("wrong_answer_all", list(a0), lambda r: outcome(r) == "wrong"),
            ("withheld_all", list(a0), lambda r: outcome(r) == "withheld"),
            ("cited_gold_cell_lookup", [q for q in a0 if kind(a0[q]) == "lookup"], lambda r: bool(r["cells_exact_raw"])),
            ("withheld_lookup", [q for q in a0 if kind(a0[q]) == "lookup"], lambda r: outcome(r) == "withheld"),
            ("wrong_answer_calc", [q for q in a0 if kind(a0[q]) == "calc"], lambda r: outcome(r) == "wrong"),
        ):
            main_change = {q: int(hit(a1[q])) - int(hit(a0[q])) for q in qs}
            control_change = {q: int(hit(c1[q])) - int(hit(c0[q])) for q in qs}
            more_in_main = sum(main_change[q] > control_change[q] for q in qs)
            more_in_control = sum(main_change[q] < control_change[q] for q in qs)
            p = exact_p(more_in_main, more_in_main + more_in_control)
            res[name] = {"n": len(qs), f"net_change_{na}": sum(main_change.values()), f"net_change_{nb}": sum(control_change.values()),
                         f"questions_changed_more_in_{na}": more_in_main, f"questions_changed_more_in_{nb}": more_in_control,
                         "p_two_sided": p, "p_display": "<0.001" if p < 0.001 else f"{p:.3f}"}
        out[label] = res
    return out


def start_models() -> dict:
    """The two start models: the same setting trained in two sessions."""
    a, b = load(START), load(START_C)
    same_output = sum((a[q]["raw_output"] or "") == (b[q]["raw_output"] or "") for q in a)
    return {"questions": len(a), "same_raw_output": same_output, "same_raw_output_rate": round(same_output / len(a), 4),
            "verified_correct": sign(a, b, list(a), lambda r: outcome(r) == "correct")}


def prompt_mix() -> dict:
    """What a training batch is made of under the two samplers (the kinds of the training prompts, from train_info.json)."""
    kinds = json.loads((ROOT / "experiments" / "exaone_grpo2b" / "train_info.json").read_text(encoding="utf-8"))["train_prompts"]
    total = sum(kinds.values())
    return {"train_prompts": total, "natural": {k: round(v / total, 4) for k, v in kinds.items()},
            "balanced": {k: round(1 / len(kinds), 4) for k in kinds},
            "balanced_share_without_lookup": round(1 - 1 / len(kinds), 4)}


def main() -> None:
    out = {"start": START, "rl": RL, "first_pass": setting(""), "subject_check": setting("_ec"), "raw": raw_side(), "training": training(),
           "delta_rl_minus_start": deltas(), "cost": cost()}
    dest = EVAL / "rl2_analysis.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    control = {"start": START_C, "rl": RL_C, "first_pass": setting("", START_C, RL_C), "subject_check": setting("_ec", START_C, RL_C), "raw": raw_side(START_C, RL_C),
               "training": training("exaone_grpo2b"), "delta_rl_minus_start": deltas(START_C, RL_C), "main_minus_control": arms(), "start_models": start_models(),
               "prompt_mix": prompt_mix()}
    dest_c = EVAL / "rl2_control_analysis.json"
    dest_c.write_text(json.dumps(control, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    info_r = json.loads((ROOT / "experiments" / "exaone_grpo2c" / "train_info.json").read_text(encoding="utf-8"))["args"]
    info_c = json.loads((ROOT / "experiments" / "exaone_grpo2b" / "train_info.json").read_text(encoding="utf-8"))["args"]
    repeat = {"start": START_C, "rl": RL_R, "first_pass": setting("", START_C, RL_R), "subject_check": setting("_ec", START_C, RL_R), "raw": raw_side(START_C, RL_R),
              "training": training("exaone_grpo2c"), "delta_rl_minus_start": deltas(START_C, RL_R),
              "repeat_minus_control": arms((START_C, RL_R), (START_C, RL_C), ("repeat", "control")),          # same start model: sampler only
              "main_minus_repeat": arms((START, RL), (START_C, RL_R), ("main", "repeat")),                    # the two runs of the main experiment
              "training_args_that_differ_from_control": sorted(k for k in set(info_r) | set(info_c) if info_r.get(k) != info_c.get(k)),
              "same_start_model_as_control": info_r["adapter"] == info_c["adapter"]}
    dest_r = EVAL / "rl2_repeat_analysis.json"
    dest_r.write_text(json.dumps(repeat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for title, d in (("main experiment (natural sampling)", out), ("control (balanced sampling)", control), ("repeat of the main experiment (natural sampling, the control's start model)", repeat)):
        print("==", title)
        for s in ("first_pass", "subject_check"):
            for k in ("all", "lookup", "calc", "unanswerable"):
                a, b = d[s]["outcomes"]["start"][k], d[s]["outcomes"]["rl"][k]
                print(f"{s:14s} {k:13s} n={a['n']:3d} | start correct {a['correct']:3d} wrong {a['wrong']:3d} withheld {a['withheld']:3d} | rl correct {b['correct']:3d} wrong {b['wrong']:3d} withheld {b['withheld']:3d}")
            print("   sign tests:", {k: (v["only_rl"], v["only_start"], v["p_display"]) for k, v in d[s]["sign_tests"].items()})
        r = d["raw"]
        print("   lookup, cited gold cell:", r["start"]["lookup_cited_gold_cell"], "->", r["rl"]["lookup_cited_gold_cell"], r["sign_test_cited_gold_cell_lookup"]["p_display"],
              "| calc answers that are expressions:", r["start"]["calc_answer_is_an_expression"], "->", r["rl"]["calc_answer_is_an_expression"])
    print("== main minus control")
    for s, res in control["main_minus_control"].items():
        print(s, {k: (v["net_change_main"], v["net_change_control"], v["questions_changed_more_in_main"], v["questions_changed_more_in_control"], v["p_display"]) for k, v in res.items()})
    print("start models:", control["start_models"])
    print("== repeat minus control (same start model)")
    for s, res in repeat["repeat_minus_control"].items():
        print(s, {k: (v["net_change_repeat"], v["net_change_control"], v["questions_changed_more_in_repeat"], v["questions_changed_more_in_control"], v["p_display"]) for k, v in res.items()})
    print("== main minus repeat (two runs of the main experiment)")
    for s, res in repeat["main_minus_repeat"].items():
        print(s, {k: (v["net_change_main"], v["net_change_repeat"], v["questions_changed_more_in_main"], v["questions_changed_more_in_repeat"], v["p_display"]) for k, v in res.items()})
    print("->", dest.relative_to(ROOT), dest_c.relative_to(ROOT), dest_r.relative_to(ROOT))


if __name__ == "__main__":
    main()
