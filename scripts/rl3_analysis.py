"""RL started from a model fine-tuned on all the data: what changed, question by question (stored predictions only, no model run).

The second RL experiment started from a model fine-tuned on 300 examples, which leaves a lot to learn. This one starts
from the full-data model (3,587 examples, trained in the same session with the fixed length cap) and keeps every other
setting of the second experiment: the owner's reward and loss, natural sampling, 200 steps, the same seed.

Besides the before/after comparison of `rl2_analysis.py` it records

  signal        how much of a training batch could move the model at all (a group whose eight samples score the same
                has zero advantage everywhere), next to the same count for the three runs of the second experiment
  outputs       how many test questions got a different raw output
  confidence    what RL did to the model's own confidence as a filter (risk-coverage), with a paired bootstrap
  retraining    how far two trainings of the same full-data setting are apart: the yardstick for "no change"

  python scripts/rl3_analysis.py     # -> experiments/eval/rl3_analysis.json
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rl2_analysis as rl2  # noqa: E402
from risk_coverage import SIGNALS, curve, sent_and_right  # noqa: E402

EVAL = ROOT / "experiments" / "eval"
START, RL = "exaone_full3_vllm_ko_test", "exaone_grpo3_vllm_ko_test"
EARLIER_FULL = "exaone_full2_vllm_ko_test"                         # the same full-data setting, trained one session earlier
RL_RUNS = {"from_full_data_model": "exaone_grpo3", "second_experiment": "exaone_grpo2", "second_experiment_repeat": "exaone_grpo2c",
           "second_experiment_control": "exaone_grpo2b"}
BOOTSTRAP, SEED = 2000, 0


def signal(run_dir: str) -> dict:
    """Why a step did or did not change the weights, and what the sampled answers looked like."""
    steps = [s for s in map(json.loads, open(ROOT / "experiments" / run_dir / "train_log.jsonl", encoding="utf-8")) if "step" in s]
    applied = sum(s["update_applied"] for s in steps)
    no_signal = sum(not s["update_applied"] and s["groups_all_equal"] == 1.0 for s in steps)
    levels = {k: sum(s[k] for s in steps) for k in ("correct", "repaired", "withheld", "wrong", "unparsable")}
    samples = sum(levels.values())
    return {"steps": len(steps), "updates_applied": applied, "steps_without_signal": no_signal, "steps_gradient_not_usable": len(steps) - applied - no_signal,
            "groups_with_equal_rewards": round(sum(s["groups_all_equal"] for s in steps) / len(steps), 4),
            "steps_all_samples_correct": sum(s["correct"] == samples // len(steps) for s in steps),
            "samples": samples, **{f"samples_{k}": v for k, v in levels.items()}, **{f"samples_{k}_rate": round(v / samples, 4) for k, v in levels.items()}}


def outputs(a: dict[str, dict], b: dict[str, dict]) -> dict:
    same = sum((a[q]["raw_output"] or "") == (b[q]["raw_output"] or "") for q in a)
    changed = [q for q in a if (a[q]["raw_output"] or "") != (b[q]["raw_output"] or "")]
    return {"questions": len(a), "same_raw_output": same, "same_raw_output_rate": round(same / len(a), 4), "different_raw_output": len(changed),
            "different_raw_output_same_outcome": sum(rl2.outcome(a[q]) == rl2.outcome(b[q]) for q in changed),
            "different_outcome": sum(rl2.outcome(a[q]) != rl2.outcome(b[q]) for q in a)}


def quick(rows: list[dict], sig: str) -> tuple[float, float, float]:
    """(area under the risk-coverage curve, AUROC, largest coverage with risk <= 5%) for the verifier's answers; the definitions of risk_coverage.curve."""
    items = sorted(((r["confidence"][sig], sent_and_right(r, "verifier")[1]) for r in rows if sent_and_right(r, "verifier")[0]), key=lambda x: -x[0])
    wrong, risks, cov5 = 0, [], 0.0
    for k, (_, right) in enumerate(items, start=1):
        wrong += not right
        risks.append(wrong / k)
        if wrong / k <= 0.05 and k >= 20:
            cov5 = k / len(rows)
    pos, neg = sum(right for _, right in items), sum(not right for _, right in items)
    ranked = sorted(items, key=lambda x: x[0])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        rank_sum += sum((i + j + 1) / 2 for t in range(i, j) if ranked[t][1])
        i = j
    auroc = (rank_sum - pos * (pos + 1) / 2) / (pos * neg) if pos and neg else float("nan")
    return sum(risks) / max(1, len(risks)), auroc, cov5


def confidence(a: dict[str, dict], b: dict[str, dict]) -> dict:
    """Risk-coverage of the verifier's answers before and after RL, and a paired bootstrap over questions for the difference."""
    qids = sorted(a)
    out: dict = {"bootstrap_resamples": BOOTSTRAP, "seed": SEED}
    for sig in SIGNALS:
        ca, cb = curve(list(a.values()), "verifier", sig), curve(list(b.values()), "verifier", sig)
        qa, qb = quick(list(a.values()), sig), quick(list(b.values()), sig)
        assert round(qa[0], 4) == ca["aurc"] and round(qb[1], 4) == cb["auroc_right_vs_wrong"] and round(qa[2], 4) == ca["max_coverage_with_risk_under_pct"]["5"]["coverage"]
        rng = random.Random(SEED)
        diffs = []
        for _ in range(BOOTSTRAP):
            pick = [qids[rng.randrange(len(qids))] for _ in qids]
            x, y = quick([a[q] for q in pick], sig), quick([b[q] for q in pick], sig)
            diffs.append((y[0] - x[0], y[1] - x[1], y[2] - x[2]))
        res = {}
        for i, name in enumerate(("aurc", "auroc", "coverage_at_risk_5")):
            d = sorted(v[i] for v in diffs if v[i] == v[i])
            res[name] = {"start": round(qa[i], 4), "rl": round(qb[i], 4), "rl_minus_start": round(qb[i] - qa[i], 4),
                         "ci95_lo": round(d[int(0.025 * len(d))], 4), "ci95_hi": round(d[int(0.975 * len(d)) - 1], 4),
                         "share_of_resamples_with_rl_worse": round(sum((v > 0) if name == "aurc" else (v < 0) for v in d) / len(d), 4)}
        res["coverage_at_risk_10"] = {"start": ca["max_coverage_with_risk_under_pct"]["10"]["coverage"], "rl": cb["max_coverage_with_risk_under_pct"]["10"]["coverage"]}
        res["risk_without_threshold"] = {"start": ca["no_threshold"]["risk"], "rl": cb["no_threshold"]["risk"]}
        res["answers_without_threshold"] = {"start": ca["no_threshold"]["answers"], "rl": cb["no_threshold"]["answers"]}
        out[sig] = res
    # how sure the model is of what it writes: the confidence of the answers the verifier let out
    for name, rows in (("start", a), ("rl", b)):
        sent = [r for r in rows.values() if sent_and_right(r, "verifier")[0]]
        right = [r["confidence"]["sum_logprob"] for r in sent if sent_and_right(r, "verifier")[1]]
        wrong = [r["confidence"]["sum_logprob"] for r in sent if not sent_and_right(r, "verifier")[1]]
        out[f"sum_logprob_{name}"] = {"right_answers": len(right), "wrong_answers": len(wrong), "median_right": round(sorted(right)[len(right) // 2], 4),
                                      "median_wrong": round(sorted(wrong)[len(wrong) // 2], 4),
                                      "wrong_answers_above_median_right": sum(w >= sorted(right)[len(right) // 2] for w in wrong)}
    return out


def custom() -> dict:
    out = {}
    for label, suffix in (("first_pass", ""), ("subject_check", "_ec")):
        a, b = rl2.load(START.replace("ko_test", "ko_custom") + suffix), rl2.load(RL.replace("ko_test", "ko_custom") + suffix)
        out[label] = {"questions": len(a), "start_correct": sum(rl2.outcome(r) == "correct" for r in a.values()), "rl_correct": sum(rl2.outcome(r) == "correct" for r in b.values()),
                      "only_rl": sum(rl2.outcome(b[q]) == "correct" and rl2.outcome(a[q]) != "correct" for q in a),
                      "only_start": sum(rl2.outcome(a[q]) == "correct" and rl2.outcome(b[q]) != "correct" for q in a)}
    return out


def main() -> None:
    a, b, e = rl2.load(START), rl2.load(RL), rl2.load(EARLIER_FULL)
    sft = json.loads((ROOT / "experiments" / "exaone_lora_full3" / "train_info.json").read_text(encoding="utf-8"))
    unans = [q for q in a if rl2.kind(a[q]) == "unanswerable"]
    args = {d: json.loads((ROOT / "experiments" / d / "train_info.json").read_text(encoding="utf-8"))["args"] for d in ("exaone_grpo3", "exaone_grpo2", "exaone_grpo2c")}
    differ = {d: sorted(k for k in set(args["exaone_grpo3"]) | set(args[d]) if args["exaone_grpo3"].get(k) != args[d].get(k)) for d in ("exaone_grpo2", "exaone_grpo2c")}
    out = {"start": START, "rl": RL, "first_pass": rl2.setting("", START, RL), "subject_check": rl2.setting("_ec", START, RL), "raw": rl2.raw_side(START, RL),
           "training": rl2.training("exaone_grpo3"), "delta_rl_minus_start": rl2.deltas(START, RL),
           "training_args_that_differ_from_second_experiment": differ["exaone_grpo2"], "training_args_that_differ_from_its_repeat": differ["exaone_grpo2c"],
           "signal": {name: signal(d) for name, d in RL_RUNS.items()},
           "outputs": outputs(a, b),
           "unanswerable_first_pass": rl2.sign(a, b, unans, lambda r: rl2.outcome(r) == "correct"),
           "confidence": confidence(a, b),
           "retraining": {"earlier": EARLIER_FULL, "outputs": outputs(e, a), "verified_correct": rl2.sign(e, a, list(a), lambda r: rl2.outcome(r) == "correct")},
           "custom": custom(),
           "start_sft": {"examples": sft["n_examples"], "steps": sft["steps"], "minutes": round(sft["wall_s"] / 60, 1), "targets_cut_short": sft["targets_cut_short"],
                         "targets_missing": sft["targets_missing"], "max_in": sft["max_in"], "max_len": sft["args"]["max_len"]}}
    dest = EVAL / "rl3_analysis.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for s in ("first_pass", "subject_check"):
        for k in ("all", "lookup", "calc", "unanswerable"):
            x, y = out[s]["outcomes"]["start"][k], out[s]["outcomes"]["rl"][k]
            print(f"{s:14s} {k:13s} n={x['n']:3d} | start correct {x['correct']:3d} wrong {x['wrong']:3d} withheld {x['withheld']:3d} | rl correct {y['correct']:3d} wrong {y['wrong']:3d} withheld {y['withheld']:3d}")
        print("   sign tests:", {k: (v["only_rl"], v["only_start"], v["p_display"]) for k, v in out[s]["sign_tests"].items()})
    print("signal:", {k: (v["updates_applied"], v["steps_without_signal"], v["groups_with_equal_rewards"], v["samples_correct_rate"]) for k, v in out["signal"].items()})
    print("outputs:", out["outputs"], "| retraining:", out["retraining"]["outputs"], out["retraining"]["verified_correct"])
    for sig in SIGNALS:
        print("confidence", sig, {k: v for k, v in out["confidence"][sig].items()})
    print("custom:", out["custom"])
    print("->", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
