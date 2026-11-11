"""Re-verify stored model outputs with evidence repair switched off and compare with the counterfactual.

scripts/evidence_error.py derives "verified EM without repair" from the stored predictions (a repaired answer is
counted as withheld). This script measures it: every listed run is replayed through the verifier with
`resolve(..., repair=False)` (eval.run --replay-from RUN --no-repair) and compared question by question.

The replays need the tokenizers the original runs used, which are not in git: models/mt5-small-base for the mT5
runs and the EXAONE tokenizer (a local folder or the hub name).

  python scripts/no_repair_check.py --exaone-tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B
  -> experiments/eval/no_repair_check.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence_error import compare_no_repair  # noqa: E402

EVAL = ROOT / "experiments" / "eval"
# run, planner flag, tokenizer family, input budget of the original run
RUNS = [
    ("sft_ko2_ko_test", "neural", "mt5", 512), ("sft_chem_ko_test", "neural", "mt5", 512), ("rl_ko_v1_ko_test", "neural", "mt5", 512),
    ("rl_v3_ko_test", "neural", "mt5", 512),
    ("exaone_vllm_ko_test_run1", "engine", "exaone", 672), ("exaone_vllm_ko_test_run2", "engine", "exaone", 672), ("exaone_vllm_ko_test", "engine", "exaone", 672),
    ("exaone_colid_vllm_ko_test", "engine", "exaone", 800),
    ("exaone_full_vllm_ko_test", "engine", "exaone", 672), ("exaone_full_vllm_ko_test_run2", "engine", "exaone", 672),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mt5-tokenizer", default="models/mt5-small-base")
    ap.add_argument("--exaone-tokenizer", default="LGAI-EXAONE/EXAONE-4.0-1.2B")
    a = ap.parse_args()
    tok = {"mt5": a.mt5_tokenizer, "exaone": a.exaone_tokenizer}
    out: dict = {"tokenizers": {"mt5": "models/mt5-small-base (converted mT5 tokenizer)", "exaone": "LGAI-EXAONE/EXAONE-4.0-1.2B"}, "runs": {}}
    with tempfile.TemporaryDirectory() as tmp:
        for run, planner, family, max_in in RUNS:
            meta = json.loads((EVAL / run / "metrics.json").read_text(encoding="utf-8"))["meta"]
            dest = Path(tmp) / run
            cmd = [sys.executable, "-m", "tabletrace.eval.run", "--planner", planner, "--replay-from", str(EVAL / run), "--no-entity-check", "--no-repair",
                   "--tokenizer", tok[family], "--max-in", str(max_in), "--corpus", *meta["corpus"], "--data", *meta["data"], "--out", str(dest)]
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit(f"{run}: replay failed\n{r.stderr[-1500:]}")
            res = compare_no_repair(EVAL / run, dest)
            res.pop("examples")
            res["verified_em_with_repair"] = json.loads((EVAL / run / "metrics.json").read_text(encoding="utf-8"))["metrics"]["verified_em"]
            res["max_in"] = max_in
            out["runs"][run] = res
            print(f"{run:32s} with repair {res['verified_em_with_repair']:.4f} | without: counterfactual {res['verified_em_counterfactual']:.4f}, "
                  f"replayed {res['verified_em_replayed']:.4f} | repaired answers {res['repaired_in_original']:3d} | questions that differ {res['questions_that_differ']}")
    out["runs_checked"] = len(out["runs"])
    out["questions_checked"] = sum(r["questions"] for r in out["runs"].values())
    out["questions_that_differ"] = sum(r["questions_that_differ"] for r in out["runs"].values())
    dest = EVAL / "no_repair_check.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("->", dest.relative_to(ROOT), "| differ in total:", out["questions_that_differ"])
    sys.exit(1 if out["questions_that_differ"] else 0)


if __name__ == "__main__":
    main()
