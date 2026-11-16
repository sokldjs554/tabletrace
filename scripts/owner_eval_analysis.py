"""The owner's review of the 30 hand-made questions the AI tool wrote, and the 30 questions the owner wrote (stored files only, no model run).

  review     data/ko/custom_eval_review.jsonl: one verdict per AI-written question. For every stored evaluation of that
             set the score is recomputed without the questions the owner marked `fix` or `drop`, so that a reader can
             see how much any number leans on a flawed question. The questions themselves are left as they are: the
             stored model outputs answer exactly those texts.
  owner set  data/ko/owner_eval.jsonl: what the two planners that run on CPU score on it, by category, next to the
             AI-written set; and what a reader should know about the set (questions that ask the cells an existing test
             question asks, text answers that occur more than once in the passage).

  python scripts/owner_eval_analysis.py     # -> experiments/eval/owner_eval_analysis.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence_error import wilson  # noqa: E402

EVAL = ROOT / "experiments" / "eval"
KO = ROOT / "data" / "ko"
CPU_PLANNERS = {"heuristic": "heuristic", "mt5_small_final": "rl_v3"}          # label -> run prefix


def load(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def verdicts(run: str) -> dict[str, bool]:
    return {r["qid"]: bool(r["verified_correct"]) for r in load(EVAL / run / "predictions.jsonl")}


def score(v: dict[str, bool], qids: list[str]) -> dict:
    k = sum(v[q] for q in qids)
    return {"n": len(qids), "correct": k, "rate": round(k / len(qids), 4) if qids else None}


def main() -> None:
    owner, custom, review = load(KO / "owner_eval.jsonl"), load(KO / "custom_eval.jsonl"), load(KO / "custom_eval_review.jsonl")
    docs = {d["id"]: d for d in load(KO / "documents.jsonl")}

    # --- the review of the AI-written set
    by_verdict = Counter(r["verdict"] for r in review)
    flagged = sorted(r["qid"] for r in review if r["verdict"] != "ok")
    kept = [q["qid"] for q in custom if q["qid"] not in flagged]
    cat = {q["qid"]: q["category"] for q in custom}
    runs = {}
    for d in sorted(EVAL.iterdir()):
        if not (d.name.endswith("_ko_custom") or d.name.endswith("_ko_custom_ec")) or not (d / "predictions.jsonl").exists():
            continue
        v = verdicts(d.name)
        if set(v) != set(cat):
            continue
        a, b = score(v, list(cat)), score(v, kept)
        runs[d.name] = {"all": a, "without_flagged": b, "flagged": score(v, flagged), "rate_change": round(b["rate"] - a["rate"], 4)}
    shifts = [r["rate_change"] for r in runs.values()]
    order_all = sorted(runs, key=lambda r: -runs[r]["all"]["rate"])
    pairs = [(x, y) for i, x in enumerate(order_all) for y in order_all[i + 1:] if runs[x]["all"]["rate"] > runs[y]["all"]["rate"]]
    flipped = [(x, y) for x, y in pairs if runs[x]["without_flagged"]["rate"] < runs[y]["without_flagged"]["rate"]]
    review_out = {"questions": len(review), "ok": by_verdict.get("ok", 0), "fix": by_verdict.get("fix", 0), "drop": by_verdict.get("drop", 0),
                  "flagged": flagged, "flagged_categories": dict(Counter(cat[q] for q in flagged)), "kept": len(kept),
                  "stored_runs": len(runs), "largest_rate_gain_without_flagged": max(shifts), "largest_rate_loss_without_flagged": min(shifts),
                  "runs_with_a_flagged_question_right": sum(r["flagged"]["correct"] > 0 for r in runs.values()),
                  "pairs_of_runs_ranked_strictly": len(pairs), "pairs_whose_order_reverses_without_flagged": len(flipped)}

    # --- the owner's set
    existing = [r for f in ("test", "synthetic_test", "custom_eval") for r in load(KO / f"{f}.jsonl")]

    def key(r: dict) -> tuple:
        return r["table_id"], r["op"], tuple(sorted(map(tuple, r["gold_cells"])))

    seen = {key(r): r["qid"] for r in existing if r.get("gold_cells")}
    same_cells = {r["qid"]: seen[key(r)] for r in owner if r["gold_cells"] and key(r) in seen}
    repeated_text = []
    for r in owner:
        if r["op"] == "text":
            body = " ".join(p["text"] for p in docs[r["doc_id"]]["passages"])
            if body.count(r["answer"]) > 1:
                repeated_text.append(r["qid"])
    ocat = {q["qid"]: q["category"] for q in owner}
    owner_out = {"questions": len(owner), "categories": dict(Counter(ocat.values())), "tables": len({q["table_id"] for q in owner}),
                 "tables_also_used_by_the_ai_written_set": len({q["table_id"] for q in owner} & {q["table_id"] for q in custom}),
                 "questions_with_cells": sum(bool(q["gold_cells"]) for q in owner),
                 "same_cells_as_an_existing_test_question": {"count": len(same_cells), "pairs": same_cells},
                 "text_answer_occurs_more_than_once_in_the_passage": repeated_text}

    planners = {}
    for label, prefix in CPU_PLANNERS.items():
        res = {}
        for name, qcat, suffix in (("owner", ocat, "ko_owner"), ("ai_written", cat, "ko_custom")):
            for setting, ec in (("first_pass", ""), ("subject_check", "_ec")):
                v = verdicts(f"{prefix}_{suffix}{ec}")
                s = score(v, list(qcat))
                res[f"{name}_{setting}"] = {**s, "ci95": {k: wilson(s["correct"], s["n"])[k] for k in ("lo", "hi")},
                                            "by_category": {c: score(v, [q for q in qcat if qcat[q] == c]) for c in sorted(set(qcat.values()))}}
        res["ai_written_first_pass_without_flagged"] = score(verdicts(f"{prefix}_ko_custom"), kept)
        for name, qcat, suffix in (("owner", ocat, "ko_owner"), ("ai_written", cat, "ko_custom")):       # which operation the planner wrote for the calculation questions
            ops = [r.get("pred_op") for r in load(EVAL / f"{prefix}_{suffix}" / "predictions.jsonl") if qcat[r["qid"]] == "calc"]
            res[f"{name}_calc_questions"] = {"n": len(ops), "given_a_calculation": sum(o in ("diff", "sum", "avg", "ratio", "pct_change") for o in ops),
                                             "given_a_lookup": sum(o == "lookup" for o in ops), "withheld_or_unparsable": sum(o in (None, "abstain") for o in ops)}
        planners[label] = res

    out = {"review": review_out, "runs_on_the_ai_written_set": runs, "owner_set": owner_out, "cpu_planners": planners}
    dest = EVAL / "owner_eval_analysis.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("review:", {k: v for k, v in review_out.items() if k != "flagged"}, review_out["flagged"])
    print("owner set:", owner_out)
    for label, res in planners.items():
        print(label, {k: (v["correct"], v["n"]) for k, v in res.items() if "correct" in v}, {k: v for k, v in res.items() if k.endswith("calc_questions")})
        print("   owner by category:", {c: (s["correct"], s["n"]) for c, s in res["owner_first_pass"]["by_category"].items()},
              "| ai-written:", {c: (s["correct"], s["n"]) for c, s in res["ai_written_first_pass"]["by_category"].items()})
    print("->", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
