"""Re-verify results that came back from a GPU session and compare them, question by question, with what the session stored.

A result archive holds each run twice: the first pass (verifier without the subject check) and its re-verification
(`_ec`, subject check on). Both are reproduced here from the stored raw model outputs with the verifier in this
repository. If the outcome of any question differs, the stored numbers do not belong to this code.

  python scripts/replay_check.py --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B                      # -> experiments/eval/replay_check_gpu3.json
  python scripts/replay_check.py --session control --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B    # -> experiments/eval/replay_check_control.json
  python scripts/replay_check.py --session repeat --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B     # -> experiments/eval/replay_check_repeat.json
  python scripts/replay_check.py --session full2 --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B      # -> experiments/eval/replay_check_full2.json
  python scripts/replay_check.py --session rl3 --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B        # -> experiments/eval/replay_check_rl3.json
  python scripts/replay_check.py --session owner --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B      # -> experiments/eval/replay_check_owner.json
  python scripts/replay_check.py --session ownloop --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B    # -> experiments/eval/replay_check_ownloop.json
  python scripts/replay_check.py --session chem --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B       # -> experiments/eval/replay_check_chem.json (section N, run on 2026-11-17)
  python scripts/replay_check.py --session share --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B      # -> experiments/eval/replay_check_share.json (section O, run on 2026-11-17)
  python scripts/replay_check.py --session chemrepeat --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B # -> experiments/eval/replay_check_chemrepeat.json (section O's repeat, run on 2026-11-18)
  python scripts/replay_check.py --session koonly2 --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B    # -> experiments/eval/replay_check_koonly2.json (section P, the Korean-only repeat, run on 2026-11-20)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "experiments" / "eval"
SESSIONS = {                   # all were evaluated with an input budget of 672 tokens
    "gpu3": [                  # the third GPU session (2026-11-15)
        "ref_1p2b_ko_test", "ref_1p2b_ko_custom", "ref_7p8b_awq_ko_test", "ref_7p8b_awq_ko_custom",
        "tools_1p2b_ko_test", "tools_1p2b_ko_custom", "tools_1p2b_unseen_dev500",
        "exaone_rlstart2_vllm_ko_test", "exaone_rlstart2_vllm_ko_custom", "exaone_grpo2_vllm_ko_test", "exaone_grpo2_vllm_ko_custom",
    ],
    "control": [               # the control run of the second RL experiment (2026-11-15, a later session with its own start model)
        "exaone_rlstart2b_vllm_ko_test", "exaone_rlstart2b_vllm_ko_custom", "exaone_grpo2b_vllm_ko_test", "exaone_grpo2b_vllm_ko_custom",
    ],
    "repeat": [                # the main experiment once more, from the control's start model (2026-11-15, the session after)
        "exaone_grpo2c_vllm_ko_test", "exaone_grpo2c_vllm_ko_custom",
    ],
    "full2": [                 # full-data fine-tuning with whole targets, and the old cap once more in the same session (2026-11-16)
        "exaone_full2_vllm_ko_test", "exaone_full2_vllm_ko_custom", "exaone_full2old_vllm_ko_test", "exaone_full2old_vllm_ko_custom",
    ],
    "rl3": [                   # RL started from a full-data model: that model, trained again in the session, and the model after RL (2026-11-16)
        "exaone_full3_vllm_ko_test", "exaone_full3_vllm_ko_custom", "exaone_grpo3_vllm_ko_test", "exaone_grpo3_vllm_ko_custom",
    ],
    "owner": [                 # EXAONE on the 30 questions the owner wrote: a full-data model trained in the session, and the two untuned sizes (2026-11-16)
        "exaone_full4_vllm_ko_test", "exaone_full4_vllm_ko_custom", "exaone_full4_vllm_ko_owner", "ref_1p2b_ko_owner", "ref_7p8b_awq_ko_owner",
    ],
    "ownloop": [               # the full-data model trained with the fine-tuning loop the owner wrote (2026-11-16, Colab, one T4)
        "exaone_ownloop_vllm_ko_test", "exaone_ownloop_vllm_ko_custom", "exaone_ownloop_vllm_ko_owner",
    ],
    "chem": [                  # section N: the model tuned on Korean and chemistry, and the untuned 1.2B model on the chemistry sets (2026-11-17, Colab)
        "exaone_kochem2_vllm_chem_custom", "exaone_kochem2_vllm_chem_syndev", "exaone_kochem2_vllm_chem_papers",
        "exaone_kochem2_vllm_ko_test", "exaone_kochem2_vllm_ko_custom", "exaone_kochem2_vllm_ko_owner",
        "ref_1p2b_chem_custom", "ref_1p2b_chem_syndev", "ref_1p2b_chem_papers",
    ],
    "share": [                 # section O: a model tuned on Korean only on the same six sets (2026-11-17, Colab)
        "exaone_koonly_vllm_chem_custom", "exaone_koonly_vllm_chem_syndev", "exaone_koonly_vllm_chem_papers",
        "exaone_koonly_vllm_ko_test", "exaone_koonly_vllm_ko_custom", "exaone_koonly_vllm_ko_owner",
    ],
    "chemrepeat": [            # section O with RUN_KOCHEM_REPEAT: section N's training once more, in a session of its own (2026-11-18, Colab)
        "exaone_kochem3_vllm_chem_custom", "exaone_kochem3_vllm_chem_syndev", "exaone_kochem3_vllm_chem_papers",
        "exaone_kochem3_vllm_ko_test", "exaone_kochem3_vllm_ko_custom", "exaone_kochem3_vllm_ko_owner",
    ],
    "koonly2": [               # section P with P_KOONLY: section O's Korean-only training once more (2026-11-20, Colab)
        "exaone_koonly2_vllm_chem_custom", "exaone_koonly2_vllm_chem_syndev", "exaone_koonly2_vllm_chem_papers",
        "exaone_koonly2_vllm_ko_test", "exaone_koonly2_vllm_ko_custom", "exaone_koonly2_vllm_ko_owner",
    ],
}
FIELDS = ("pred_status", "pred_answer", "pred_cells", "verified_correct", "evidence_repaired")


def rows(d: Path) -> dict[str, dict]:
    with open(d / "predictions.jsonl", encoding="utf-8") as f:
        return {r["qid"]: r for r in map(json.loads, f)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", default="LGAI-EXAONE/EXAONE-4.0-1.2B", help="EXAONE tokenizer: hub name or local folder (the row budget is counted with it)")
    ap.add_argument("--max-in", type=int, default=672)
    ap.add_argument("--session", choices=sorted(SESSIONS), default="gpu3")
    a = ap.parse_args()
    out: dict = {"tokenizer": "LGAI-EXAONE/EXAONE-4.0-1.2B", "max_in": a.max_in, "runs": {}}
    with tempfile.TemporaryDirectory() as tmp:
        for run in SESSIONS[a.session]:
            meta = json.loads((EVAL / run / "metrics.json").read_text(encoding="utf-8"))["meta"]
            res = {}
            for label, stored, extra in (("first_pass", EVAL / run, ["--no-entity-check"]), ("subject_check", EVAL / f"{run}_ec", [])):
                dest = Path(tmp) / f"{run}_{label}"
                cmd = [sys.executable, "-m", "tabletrace.eval.run", "--planner", "engine", "--replay-from", str(EVAL / run), *extra,
                       "--tokenizer", a.tokenizer, "--max-in", str(a.max_in), "--corpus", *meta["corpus"], "--data", *meta["data"], "--out", str(dest)]
                r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
                if r.returncode != 0:
                    raise SystemExit(f"{run} ({label}): replay failed\n{r.stderr[-1500:]}")
                old, new = rows(stored), rows(dest)
                differ = sorted(q for q in old if q not in new or any(old[q].get(k) != new[q].get(k) for k in FIELDS))
                m_old = json.loads((stored / "metrics.json").read_text(encoding="utf-8"))["metrics"]
                m_new = json.loads((dest / "metrics.json").read_text(encoding="utf-8"))["metrics"]
                res[label] = {"questions": len(old), "questions_that_differ": len(differ) + len(set(new) - set(old)), "examples": differ[:5],
                              "verified_em_stored": m_old["verified_em"], "verified_em_replayed": m_new["verified_em"]}
            out["runs"][run] = res
            print(f"{run:34s} first pass: {res['first_pass']['questions_that_differ']} of {res['first_pass']['questions']} differ | "
                  f"subject check: {res['subject_check']['questions_that_differ']} of {res['subject_check']['questions']} differ")
    out["replays"] = 2 * len(out["runs"])
    out["questions_checked"] = sum(v[k]["questions"] for v in out["runs"].values() for k in v)
    out["questions_that_differ"] = sum(v[k]["questions_that_differ"] for v in out["runs"].values() for k in v)
    dest = EVAL / f"replay_check_{a.session}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("->", dest.relative_to(ROOT), "| replays", out["replays"], "| questions", out["questions_checked"], "| differ", out["questions_that_differ"])
    sys.exit(1 if out["questions_that_differ"] else 0)


if __name__ == "__main__":
    main()
