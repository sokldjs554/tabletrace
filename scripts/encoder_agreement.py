"""Second opinion from the table encoder: answer only when it points at the cell the generative model cited.

The verifier checks that an answer and its evidence cell agree with each other. A model that is consistently wrong
(right-looking cell, wrong row) passes. The table encoder scores every cell on its own, from the question and the
table, without seeing the generative model's output. This script asks, on the 539 lookup questions of the test split
and from stored predictions only (no model is run):

    verifier              what the pipeline sends today
    + same cell           send only when the encoder's top cell is the evidence cell
    + same row            send only when the encoder's top cell is in the evidence row

For each: coverage (answers sent / questions), wrong answers sent / questions, risk (wrong / sent), and how many of
the verifier's wrong answers the extra check stops against how many right answers it costs.

    python scripts/encoder_agreement.py structure_pool        # -> experiments/encoder/agreement.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_error import wilson  # noqa: E402

RUNS = ["rl_v3_ko_test", "exaone_vllm_ko_test", "exaone_colid_vllm_ko_test", "exaone_full_vllm_ko_test", "exaone_full_vllm_ko_test_run2"]


def cell(cid: str) -> tuple[int, int]:
    r, c = cid[1:].split("c")
    return int(r), int(c)


def policy(rows: list[dict], keep) -> dict:
    n = len(rows)
    sent = [r for r in rows if r["answered"] and keep(r)]
    wrong = sum(not r["correct"] for r in sent)
    return {"coverage": wilson(len(sent), n), "wrong_sent": wilson(wrong, n), "risk": wilson(wrong, max(1, len(sent))), "right_sent": wilson(len(sent) - wrong, n)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("encoders", nargs="+", help="names under experiments/encoder/")
    a = ap.parse_args()
    out: dict = {"questions": "the lookup questions of data/ko/test.jsonl", "encoders": {}}
    for name in a.encoders:
        enc = {json.loads(line)["qid"]: json.loads(line) for line in open(ROOT / "experiments" / "encoder" / name / "test_predictions.jsonl", encoding="utf-8")}
        res: dict = {"encoder_cell_accuracy": wilson(sum(p["cell"] for p in enc.values()), len(enc)), "runs": {}}
        for run in RUNS:
            path = ROOT / "experiments" / "eval" / run / "predictions.jsonl"
            if not path.exists():
                continue
            rows = []
            for line in open(path, encoding="utf-8"):
                r = json.loads(line)
                if r["qid"] not in enc:
                    continue
                answered = r["pred_status"] == "answered" and bool(r["pred_cells"])
                ev = cell(r["pred_cells"][0]) if answered else None
                top = tuple(enc[r["qid"]]["pred"])
                rows.append({"answered": answered, "correct": bool(r["verified_correct"]) and answered, "same_cell": answered and ev == top,
                             "same_row": answered and ev[0] == top[0], "margin": enc[r["qid"]]["margin"]})
            base = policy(rows, lambda r: True)
            same_cell = policy(rows, lambda r: r["same_cell"])
            same_row = policy(rows, lambda r: r["same_row"])
            wrong = [r for r in rows if r["answered"] and not r["correct"]]
            right = [r for r in rows if r["answered"] and r["correct"]]
            res["runs"][run] = {
                "n": len(rows), "verifier": base, "verifier_and_same_cell": same_cell, "verifier_and_same_row": same_row,
                "same_cell_stops_wrong": wilson(sum(not r["same_cell"] for r in wrong), max(1, len(wrong))),
                "same_cell_costs_right": wilson(sum(not r["same_cell"] for r in right), max(1, len(right))),
                "same_row_stops_wrong": wilson(sum(not r["same_row"] for r in wrong), max(1, len(wrong))),
                "same_row_costs_right": wilson(sum(not r["same_row"] for r in right), max(1, len(right)))}
            v = res["runs"][run]
            print(f"{name:16s} {run:34s} verifier cov {base['coverage']['rate']:.3f} risk {base['risk']['rate']:.3f} | same cell cov {same_cell['coverage']['rate']:.3f} "
                  f"risk {same_cell['risk']['rate']:.3f} (stops {v['same_cell_stops_wrong']['k']}/{v['same_cell_stops_wrong']['n']} wrong, costs {v['same_cell_costs_right']['k']}/{v['same_cell_costs_right']['n']} right) | "
                  f"same row cov {same_row['coverage']['rate']:.3f} risk {same_row['risk']['rate']:.3f}")
        out["encoders"][name] = res
    dest = ROOT / "experiments" / "encoder" / "agreement.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
