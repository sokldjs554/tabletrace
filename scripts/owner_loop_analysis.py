"""The full-data model trained with the fine-tuning loop the owner wrote, next to the trainings with the loop built into the script
(stored files only, no model run).

Until 2026-11-16 every stored EXAONE fine-tuning had run with the built-in loop of `scripts/train/exaone_lora_sft.py` (written by
the AI tool). The owner then ran the same command with `--loop owner` (notebook 2, section M): label masking, the learning-rate
schedule and the accumulation / clipping / optimizer loop come from `src/tabletrace/training/lm_loop.py`. The two loops are not
the same procedure: the owner's decays the learning rate linearly to zero, the built-in one keeps it constant. So this file does
not claim equivalence. It records that the owner's loop trained the model, what the training looked like, and where the result
sits among the six trainings made with the built-in loop.

  python scripts/owner_loop_analysis.py     # -> experiments/eval/owner_loop_analysis.json
"""
from __future__ import annotations

import json
import math
import sys
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rl2_analysis as rl2  # noqa: E402

EVAL = ROOT / "experiments" / "eval"
OWN, OWN_DIR = "exaone_ownloop_vllm", "exaone_lora_ownloop"
SAME_COMMAND, SAME_DIR = "exaone_full4_vllm", "exaone_lora_full4"            # the same command without --loop owner (another session)
BUILT_IN = {"old_cap_run1": "exaone_full_vllm_ko_test", "old_cap_run2": "exaone_full_vllm_ko_test_run2", "old_cap_run3": "exaone_full2old_vllm_ko_test",
            "fixed_cap_run1": "exaone_full2_vllm_ko_test", "fixed_cap_run2": "exaone_full3_vllm_ko_test", "fixed_cap_run3": "exaone_full4_vllm_ko_test"}


def info(d: str) -> dict:
    return json.loads((ROOT / "experiments" / d / "train_info.json").read_text(encoding="utf-8"))


def metrics(run: str) -> dict:
    return json.loads((EVAL / run / "metrics.json").read_text(encoding="utf-8"))["metrics"]


def training(t: dict) -> dict:
    log = t["loss_log"]
    lrs = [x["lr"] for x in log if "lr" in x]
    out = {"loop": t.get("loop"), "examples": t["n_examples"], "steps": t["steps"], "minutes": round(t["wall_s"] / 60, 1), "precision": t["dtype"].replace("torch.", ""),
           "gpu": t["gpu"], "targets_missing": t["targets_missing"], "targets_cut_short": t["targets_cut_short"],
           "loss_first_20_steps": round(sum(x["loss"] for x in log[:20]) / 20, 4), "loss_last_20_steps": round(sum(x["loss"] for x in log[-20:]) / 20, 4),
           "steps_with_a_loss_that_is_not_finite": sum(not math.isfinite(x["loss"]) for x in log)}
    if lrs:                      # only the owner's loop records the rate per step
        out.update({"lr_first_step": lrs[0], "lr_last_step": round(lrs[-1], 10), "lr_falls_at_every_step": all(a > b for a, b in pairwise(lrs)),
                    "lr_steps_recorded": len(lrs)})
    else:
        out["lr_constant"] = t["args"]["lr"]
    return out


def main() -> None:
    own, same = info(OWN_DIR), info(SAME_DIR)
    differ = sorted(k for k in set(own["args"]) | set(same["args"]) if own["args"].get(k) != same["args"].get(k))
    platform = json.loads((ROOT / "experiments" / "run_info_2_ownloop.json").read_text(encoding="utf-8"))
    a = rl2.load(f"{OWN}_ko_test")
    ems = {k: metrics(run)["verified_em"] for k, run in BUILT_IN.items()}
    em_own = metrics(f"{OWN}_ko_test")["verified_em"]
    paired = {}
    for k, run in BUILT_IN.items():
        b = rl2.load(run)
        s = rl2.sign(b, a, list(a), lambda r: rl2.outcome(r) == "correct")
        paired[k] = {"run": run, "only_owner_loop": s["only_rl"], "only_built_in": s["only_start"], "p_two_sided": s["p_two_sided"], "p_display": s["p_display"]}
    f4, f3 = rl2.load(f"{SAME_COMMAND}_ko_test"), rl2.load("exaone_full3_vllm_ko_test")

    def same_output(x: dict, y: dict) -> dict:
        n = sum((x[q]["raw_output"] or "") == (y[q]["raw_output"] or "") for q in x)
        return {"same_raw_output": n, "questions": len(x), "rate": round(n / len(x), 4)}

    lookup = [q for q in a if rl2.kind(a[q]) == "lookup"]
    owner_q = {}
    for label, prefix in (("owner_loop", OWN), ("built_in_same_command", SAME_COMMAND)):
        rows = rl2.load(f"{prefix}_ko_owner")
        owner_q[label] = {"n": len(rows), "correct": sum(rl2.outcome(r) == "correct" for r in rows.values()),
                          "correct_with_subject_check": sum(rl2.outcome(r) == "correct" for r in rl2.load(f"{prefix}_ko_owner_ec").values())}
    out = {
        "run": f"{OWN}_ko_test", "platform": platform["platform"], "gpus": platform["gpus"], "notebook_commit": platform["commit"],
        "training": {"owner_loop": training(own), "built_in_same_command": training(same), "args_that_differ": differ},
        "test": {"questions": len(a), "verified_em_owner_loop": em_own, "verified_em_owner_loop_subject_check": metrics(f"{OWN}_ko_test_ec")["verified_em"],
                 "verified_em_built_in": ems, "built_in_lowest": min(ems.values()), "built_in_highest": max(ems.values()),
                 "owner_loop_inside_the_range_of_the_built_in_runs": min(ems.values()) <= em_own <= max(ems.values()),
                 "paired_with_each_built_in_run": paired, "smallest_p": min(v["p_two_sided"] for v in paired.values()),
                 "raw_output": {"owner_loop_vs_built_in_same_command": same_output(f4, a), "two_built_in_runs_of_that_command": same_output(f3, f4)},
                 "lookup_cited_gold_cell": {"questions": len(lookup), "owner_loop": sum(bool(a[q]["cells_exact_raw"]) for q in lookup),
                                            "built_in_same_command": sum(bool(f4[q]["cells_exact_raw"]) for q in lookup)}},
        "owner_questions": owner_q,
        "owner_written_lines": len((ROOT / "src" / "tabletrace" / "training" / "lm_loop.py").read_text(encoding="utf-8").splitlines()),
    }
    dest = EVAL / "owner_loop_analysis.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("training:", out["training"])
    print("test:", {k: v for k, v in out["test"].items() if k != "paired_with_each_built_in_run"})
    print("paired:", {k: (v["only_owner_loop"], v["only_built_in"], v["p_display"]) for k, v in paired.items()})
    print("owner questions:", owner_q, "->", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
