"""Summarise the evaluations on data/ko/unseen_dev (official-dev questions on tables never used for training, 97% of
them larger than the old size limit) -> experiments/eval/large_tables.json.

For every run: verified EM with a Wilson interval, how often the gold row was in the model input, how often the
system withheld, how often a wrong answer went out, and the same split by table size and by whether the table's page
also holds a training table.

    python scripts/large_tables.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_error import wilson  # noqa: E402

RUNS = {
    "heuristic_whole_table": "heuristic_unseen_dev",
    "heuristic_first512": "heuristic_unseen_dev_first512",
    "heuristic_overlap512": "heuristic_unseen_dev_overlap512",
    "mt5_first512": "rl_v3_unseen_dev_first",
    "mt5_overlap512": "rl_v3_unseen_dev_overlap",
    # filled in when the owner's GPU runs come back (notebooks/gpu_experiments_2.ipynb, section H)
    "exaone_first672": "exaone_full_first672_vllm_unseen_dev",
    "exaone_overlap672": "exaone_full_overlap672_vllm_unseen_dev",
    "exaone_first1500": "exaone_full_first1500_vllm_unseen_dev",
}


def block(rows: list[dict]) -> dict:
    n = len(rows)
    return {"n": n, "verified_em": wilson(sum(r["verified_correct"] for r in rows), n),
            "gold_row_shown": wilson(sum(not r["truncated_gold"] for r in rows), n),
            "withheld": wilson(sum(r["pred_abstained"] for r in rows), n),
            "wrong_answer_sent": wilson(sum((not r["pred_abstained"]) and not r["verified_correct"] for r in rows), n),
            "verified_em_when_gold_row_shown": wilson(sum(r["verified_correct"] for r in rows if not r["truncated_gold"]), max(1, sum(not r["truncated_gold"] for r in rows)))}


def main() -> None:
    meta = {json.loads(line)["qid"]: json.loads(line) for line in open(ROOT / "data/ko/unseen_dev.jsonl", encoding="utf-8")}
    out: dict = {"set": json.loads((ROOT / "data/ko/unseen_dev_report.json").read_text(encoding="utf-8")), "runs": {}}
    for name, d in RUNS.items():
        path = ROOT / "experiments" / "eval" / d
        if not (path / "predictions.jsonl").exists():
            continue
        rows = [json.loads(line) for line in open(path / "predictions.jsonl", encoding="utf-8")]
        info = json.loads((path / "metrics.json").read_text(encoding="utf-8"))["meta"]
        run = {"dir": d, "model": info["model"], "row_select": info.get("row_select", "first"), "sample": info.get("sample"), "all": block(rows)}
        for key, label in (("large", lambda r: meta[r["qid"]]["size"] == "large"), ("small", lambda r: meta[r["qid"]]["size"] == "small"),
                           ("page_unseen", lambda r: not meta[r["qid"]]["page_seen"]), ("page_seen", lambda r: meta[r["qid"]]["page_seen"])):
            sub = [r for r in rows if label(r)]
            if sub:
                run[key] = block(sub)
        out["runs"][name] = run
    dest = ROOT / "experiments" / "eval" / "large_tables.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, run in out["runs"].items():
        a = run["all"]
        print(f"{name:24s} n {a['n']:5d} verified EM {a['verified_em']['rate']:.3f} gold row shown {a['gold_row_shown']['rate']:.3f} "
              f"withheld {a['withheld']['rate']:.3f} wrong sent {a['wrong_answer_sent']['rate']:.3f} | page unseen {run.get('page_unseen', {}).get('verified_em', {}).get('rate')}")


if __name__ == "__main__":
    main()
