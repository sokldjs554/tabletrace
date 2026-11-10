"""How often is the answer text right while the cited cell is wrong?  (stored predictions only, no model run)

For every stored evaluation it looks at lookup questions whose answer the planner wrote correctly and asks what
the planner itself cited, before the verifier touched the output:

  cited_gold           the cited cell is the gold cell
  same_value_elsewhere the cited cell is another cell that holds the same text as the answer (the gold cell is
                       derived from the answer text, so this is not counted as an error in the strict rate)
  no_answer_in_cell    the cited cell does not hold the answer (or is outside the table, or nothing was cited)

  loose rate  = (same_value_elsewhere + no_answer_in_cell) / correct lookup answers
  strict rate =  no_answer_in_cell                         / correct lookup answers

Both come with Wilson 95% intervals. The file also records what the verifier then did with the strict errors
(repaired the evidence, or withheld the answer) and operating points per run: the planner's raw output,
the verifier, the verifier with the subject check, and the verifier with evidence repair switched off.

  python scripts/evidence_error.py            # writes experiments/eval/evidence_error.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tabletrace.agent.program import ProgramParseError, parse  # noqa: E402
from tabletrace.eval.metrics import answer_match  # noqa: E402
from tabletrace.training.data import load_docs, read_records  # noqa: E402

EVAL = ROOT / "experiments" / "eval"
Z = 1.959963984540054


def wilson(k: int, n: int) -> dict:
    if n == 0:
        return {"k": k, "n": 0, "rate": None, "lo": None, "hi": None}
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return {"k": k, "n": n, "rate": round(p, 4), "lo": round(max(0.0, c - h), 4), "hi": round(min(1.0, c + h), 4)}


def classify(row: dict, rec: dict, table) -> tuple[str, str]:
    """(category, where) for one correct lookup answer."""
    try:
        prog = parse(row["raw_output"], table.id)
    except ProgramParseError:
        return "no_answer_in_cell", "unparsed"
    cited = [(c.row, c.col) for c in prog.cells]
    gold = [tuple(c) for c in rec["gold_cells"]]
    if set(cited) == set(gold):
        return "cited_gold", "gold"
    if len(cited) != 1:
        return "no_answer_in_cell", "no_cell" if not cited else "several_cells"
    (r, c), (gr, gc) = cited[0], gold[0]
    try:
        text = table.cell(r, c)
    except IndexError:
        return "no_answer_in_cell", "outside_table"
    where = "same_row" if r == gr else "same_column" if c == gc else "other_row_and_column"
    if answer_match(prog.answer, text):
        return "same_value_elsewhere", where
    return "no_answer_in_cell", where


def operating_point(rows: list[dict], answered, correct) -> dict:
    n = len(rows)
    a = [r for r in rows if answered(r)]
    ok = sum(1 for r in a if correct(r))
    return {"n": n, "answered": len(a), "coverage": round(len(a) / n, 4), "answered_correct": ok,
            "answered_wrong": len(a) - ok, "accuracy_when_answered": wilson(ok, len(a)),
            "wrong_answer_rate": wilson(len(a) - ok, n)}


def one_run(run: Path) -> dict | None:
    meta = json.loads((run / "metrics.json").read_text(encoding="utf-8"))["meta"]
    rows = [json.loads(line) for line in open(run / "predictions.jsonl", encoding="utf-8")]
    recs = {r["qid"]: r for r in read_records([ROOT / p for p in meta["data"]])}
    docs = load_docs(*[ROOT / c for c in meta["corpus"]])
    pool = [r for r in rows if r["gold_status"] == "answered" and r["gold_op"] == "lookup"]
    if not pool:
        return None
    right = [r for r in pool if r["raw_correct"] and r["pred_op"] == "lookup"]
    cats = {"cited_gold": 0, "same_value_elsewhere": 0, "no_answer_in_cell": 0}
    where: dict[str, int] = {}
    strict_rows = []
    for r in right:
        rec = recs[r["qid"]]
        cat, w = classify(r, rec, docs[rec["doc_id"]].table(rec["table_id"]))
        cats[cat] += 1
        if cat == "no_answer_in_cell":
            where[w] = where.get(w, 0) + 1
            strict_rows.append(r)
    n = len(right)
    out = {
        "lookup_questions": len(pool), "correct_lookup_answers": n,
        "correct_answer_by_other_op": sum(1 for r in pool if r["raw_correct"] and r["pred_op"] != "lookup"),
        **cats,
        "loose": wilson(cats["same_value_elsewhere"] + cats["no_answer_in_cell"], n),
        "strict": wilson(cats["no_answer_in_cell"], n),
        "strict_where": dict(sorted(where.items())),
        "verifier_on_strict": {
            "repaired_and_answered": sum(1 for r in strict_rows if r["pred_status"] == "answered" and r["evidence_repaired"]),
            "answered_without_repair": sum(1 for r in strict_rows if r["pred_status"] == "answered" and not r["evidence_repaired"]),
            "withheld": sum(1 for r in strict_rows if r["pred_status"] == "abstained"),
        },
    }
    # Operating points over ALL questions of the run (answerable and unanswerable).
    out["raw"] = operating_point(rows, lambda r: r["pred_op"] not in (None, "abstain"), lambda r: r["raw_correct"])
    out["verifier"] = operating_point(rows, lambda r: r["pred_status"] == "answered", lambda r: r["verified_correct"])
    # Counterfactual: the same verifier without evidence repair. In verify/verifier.py the branch that repairs
    # would otherwise return abstain("verification_failed"), so a repaired answer becomes an abstention.
    def kept(r: dict) -> bool:
        return r["pred_status"] == "answered" and not r["evidence_repaired"]

    def right_without_repair(r: dict) -> bool:
        if r["pred_status"] == "answered" and r["evidence_repaired"]:
            return r["gold_status"] == "abstained"
        return bool(r["verified_correct"])

    out["verifier_no_repair"] = operating_point(rows, kept, lambda r: r["verified_correct"])
    out["verified_em"] = round(sum(1 for r in rows if r["verified_correct"]) / len(rows), 4)
    out["verified_em_no_repair"] = round(sum(1 for r in rows if right_without_repair(r)) / len(rows), 4)
    out["repaired_answers"] = sum(1 for r in rows if r["pred_status"] == "answered" and r["evidence_repaired"])
    # What the verifier changed relative to the planner's own answer text.
    gained = [r for r in rows if r["pred_status"] == "answered" and r["verified_correct"] and not r["raw_correct"]]
    lost = [r for r in rows if r["raw_correct"] and not (r["pred_status"] == "answered" and r["verified_correct"])]
    calc = [r for r in gained if r["gold_op"] not in ("lookup", "text")]
    out["verifier_changes"] = {
        "gained": len(gained), "gained_calculation": len(calc),
        "gained_calculation_with_gold_cells": sum(1 for r in calc if r["cells_exact_raw"]),   # right cells and op, wrong arithmetic
        "gained_lookup": sum(1 for r in gained if r["gold_op"] == "lookup"),                  # answer text completed from the cited cell
        "lost": len(lost),
    }
    ec = run.with_name(run.name + "_ec")
    if run.name.endswith(("_run1", "_run2")):   # exaone_vllm_ko_test_run1 -> exaone_vllm_ko_test_ec_run1
        base, tag = run.name.rsplit("_", 1)
        ec = run.with_name(f"{base}_ec_{tag}")
    if (ec / "predictions.jsonl").exists():
        ec_rows = [json.loads(line) for line in open(ec / "predictions.jsonl", encoding="utf-8")]
        out["verifier_subject_check"] = operating_point(ec_rows, lambda r: r["pred_status"] == "answered", lambda r: r["verified_correct"])
    return out


def main() -> None:
    out = {}
    for run in sorted(EVAL.iterdir()):
        if not (run / "predictions.jsonl").exists() or run.name.endswith("_ec") or "_ec_" in run.name:
            continue
        res = one_run(run)
        if res:
            out[run.name] = res
    dest = EVAL / "evidence_error.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for name in ("base_ko_test", "sft_ko2_ko_test", "sft_chem_ko_test", "rl_ko_v1_ko_test", "rl_v3_ko_test", "exaone_vllm_ko_test",
                 "exaone_vllm_ko_test_run1", "exaone_vllm_ko_test_run2", "exaone_full_vllm_ko_test", "exaone_full_vllm_ko_test_run2"):
        if name in out:
            o = out[name]
            print(f"{name:34s} right={o['correct_lookup_answers']:4d} gold={o['cited_gold']:4d} dup={o['same_value_elsewhere']:3d} "
                  f"strict={o['strict']['k']:4d} ({o['strict']['rate']}, {o['strict']['lo']}-{o['strict']['hi']})  loose={o['loose']['rate']}  "
                  f"where={o['strict_where']} verifier={o['verifier_on_strict']}")
    print(f"{len(out)} runs -> {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
