"""Record what the optional column check (verifier `column_check=True`) does on the DEV predictions of the final model.

The rule was designed and judged on dev only; the test sets were not looked at. Writes experiments/eval/column_check_dev.json.
  python -m tabletrace.eval.run ... --out experiments/eval/rl_v3_ko_dev --no-entity-check             (model run on dev)
  python -m tabletrace.eval.run ... --replay-from experiments/eval/rl_v3_ko_dev --out ..._ec            (verifier v2)
  python -m tabletrace.eval.run ... --replay-from experiments/eval/rl_v3_ko_dev --out ..._ec_col --column-check
"""
from __future__ import annotations

import json
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1] / "experiments" / "eval"


def load(name: str) -> dict:
    with open(EVAL / name / "predictions.jsonl", encoding="utf-8") as f:
        return {r["qid"]: r for r in map(json.loads, f)}


def main() -> None:
    a, b = load("rl_v3_ko_dev_ec"), load("rl_v3_ko_dev_ec_col")
    fired = [q for q, r in b.items() if any(c["name"] == "column_repaired" for c in r["checks"])]
    fixed = sum(1 for q in fired if b[q]["verified_correct"] and not a[q]["verified_correct"])
    broke = sum(1 for q in fired if a[q]["verified_correct"] and not b[q]["verified_correct"])
    both_right = sum(1 for q in fired if a[q]["verified_correct"] and b[q]["verified_correct"])
    m = {n: json.loads((EVAL / n / "metrics.json").read_text())["metrics"] for n in ("rl_v3_ko_dev_ec", "rl_v3_ko_dev_ec_col")}
    out = {"n": len(b), "fired": len(fired), "fixed": fixed, "broke": broke, "both_right": both_right, "both_wrong": len(fired) - fixed - broke - both_right,
           "verified_em_without": m["rl_v3_ko_dev_ec"]["verified_em"], "verified_em_with": m["rl_v3_ko_dev_ec_col"]["verified_em"],
           "adopted": False, "reason": "net gain of a few questions, and it breaks answers whenever a header word in the question is a condition rather than the asked attribute"}
    (EVAL / "column_check_dev.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
