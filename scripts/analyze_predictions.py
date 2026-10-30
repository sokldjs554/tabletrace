"""Error analysis for an evaluation run: where do lookups go wrong (row vs column), what blocks answers,
and which op confusions occur.   python scripts/analyze_predictions.py experiments/eval/sft_ko_ko_test"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path


def rc(cid: str) -> tuple[int, int]:
    return int(cid[1:cid.index("c")]), int(cid[cid.index("c") + 1:])


def main(path: str) -> None:
    rows = [json.loads(line) for line in open(Path(path) / "predictions.jsonl", encoding="utf-8")]
    ans = [r for r in rows if r["gold_status"] == "answered"]
    out = {"run": path, "n": len(rows), "n_answerable": len(ans)}
    out["pred_status_answerable"] = dict(collections.Counter(r["pred_status"] for r in ans))
    out["abstain_reason_answerable"] = dict(collections.Counter(r["pred_reason"] for r in ans if r["pred_status"] == "abstained"))
    out["raw_correct_but_blocked"] = sum(1 for r in ans if r["raw_correct"] and not r["verified_correct"])
    out["evidence_repaired"] = sum(1 for r in ans if r.get("evidence_repaired"))
    n = rowok = colok = both = 0
    for r in ans:
        if r["pred_op"] == "lookup" and r["gold_op"] == "lookup" and r["gold_cells"] and "cells:" in (r["raw_output"] or ""):
            cited = r["raw_output"].split("cells:")[1].split(";")[0].strip().split(",")[0].strip()
            try:
                pr, pc = rc(cited)
            except ValueError:
                continue
            gr, gc = rc(r["gold_cells"][0])
            n += 1
            rowok += pr == gr
            colok += pc == gc
            both += pr == gr and pc == gc
    out["lookup_citation"] = {"n": n, "row_correct": round(rowok / n, 3) if n else None, "col_correct": round(colok / n, 3) if n else None,
                              "both_correct": round(both / n, 3) if n else None}
    # Abstention bookkeeping: the headline abstain_recall counts the FINAL status, so a degenerate program that the
    # verifier rejects "abstains" too. Separate what the planner itself decided from what the verifier caught.
    gold_ab = [r for r in rows if r["gold_status"] == "abstained"]
    n_ab = len(gold_ab)
    out["abstain_breakdown"] = {
        "n_gold_abstain": n_ab,
        "planner_chose_abstain_recall": round(sum(1 for r in gold_ab if r["pred_op"] == "abstain") / n_ab, 4) if n_ab else None,
        "final_abstain_recall": round(sum(1 for r in gold_ab if r["pred_status"] == "abstained") / n_ab, 4) if n_ab else None,
        "abstained_via_invalid_program_recall": round(sum(1 for r in gold_ab if r["pred_status"] == "abstained" and r["pred_op"] != "abstain" and r["pred_reason"] == "invalid_program") / n_ab, 4) if n_ab else None,
        "abstained_via_verifier_recall": round(sum(1 for r in gold_ab if r["pred_status"] == "abstained" and r["pred_op"] != "abstain" and r["pred_reason"] not in ("invalid_program", None)) / n_ab, 4) if n_ab else None,
    }
    calc_ops = ("diff", "sum", "avg", "ratio", "pct_change")
    degenerate = 0
    for r in rows:
        raw = r["raw_output"] or ""
        if r["pred_op"] in calc_ops and "cells:" in raw:
            cells = [c.strip() for c in raw.split("cells:")[1].split(";")[0].split(",") if c.strip()]
            degenerate += len(set(cells)) < len(cells)
    out["degenerate_calc_outputs"] = degenerate      # calculation programs that reuse the same cell
    out["degenerate_calc_rate"] = round(degenerate / len(rows), 4)
    out["op_confusion_top"] = [[f"{g}->{p}", c] for (g, p), c in collections.Counter((r["gold_op"], r["pred_op"]) for r in rows).most_common(8)]
    out["by_source_verified"] = {}
    for src in sorted({r["source"] for r in rows}):
        xs = [r for r in rows if r["source"] == src]
        out["by_source_verified"][src] = {"n": len(xs), "verified_em": round(sum(r["verified_correct"] for r in xs) / len(xs), 3)}
    (Path(path) / "analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
