"""Metrics for TableTrace evaluations. All are plain functions over per-example records."""
from __future__ import annotations

from tabletrace.tools.cells import normalize_text
from tabletrace.tools.numbers import parse_number


def answer_match(pred: str | None, gold: str | None) -> bool:
    if pred is None or gold is None:
        return pred is None and gold is None
    p, g = normalize_text(pred), normalize_text(gold)
    if p == g:
        return True
    pn, gn = parse_number(pred), parse_number(gold)
    if pn and gn and (pn.unit == gn.unit or pn.unit is None or gn.unit is None):
        return abs(pn.value - gn.value) <= max(1e-6, 0.005 * abs(gn.value))
    return False


def cells_match(pred: list[str], gold: list[str]) -> bool:
    return set(pred) == set(gold) and bool(gold)


def summarize(rows: list[dict]) -> dict:
    """rows: per-example dicts produced by eval.run (fields listed there)."""
    n = len(rows)
    answerable = [r for r in rows if r["gold_status"] == "answered"]
    gold_abstain = [r for r in rows if r["gold_status"] == "abstained"]
    calc = [r for r in answerable if r["gold_op"] != "lookup"]
    lookup = [r for r in answerable if r["gold_op"] == "lookup"]

    def rate(xs, key):
        return round(sum(1 for x in xs if x[key]) / len(xs), 4) if xs else None

    out = {
        "n": n, "n_answerable": len(answerable), "n_gold_abstain": len(gold_abstain), "n_calc": len(calc), "n_lookup": len(lookup),
        "verified_em": rate(rows, "verified_correct"),              # final answer/abstain decision correct, all items
        "answer_em_answerable": rate(answerable, "verified_correct"),
        "raw_answer_em_answerable": rate(answerable, "raw_correct"),  # planner's own answer before verification
        "evidence_cells_exact": rate(answerable, "cells_exact"),
        "evidence_cells_overlap": rate(answerable, "cells_overlap"),
        "op_acc": rate(rows, "op_correct"),
        "lookup_em": rate(lookup, "verified_correct"),
        "calc_em": rate(calc, "verified_correct"),
        "calc_result_correct": rate(calc, "calc_correct"),
        "unit_error_rate": rate([r for r in calc if r["unit_error"] is not None], "unit_error"),
        "abstain_recall": rate(gold_abstain, "pred_abstained"),       # abstained when it should
        "false_abstain_rate": rate(answerable, "pred_abstained"),      # abstained although answerable
        "abstain_precision": None,
        "parse_fail_rate": rate(rows, "parse_fail"),
        "verifier_corrections": rate(answerable, "verifier_changed"),  # verifier replaced/blocked the proposal
        "truncated_gold_rate": rate(rows, "truncated_gold"),
        "mean_ms_per_example": round(sum(r.get("ms", 0) for r in rows) / n, 1) if n else None,
    }
    pa = [r for r in rows if r["pred_abstained"]]
    if pa:
        out["abstain_precision"] = round(sum(1 for r in pa if r["gold_status"] == "abstained") / len(pa), 4)
    by_src: dict[str, list[dict]] = {}
    for r in rows:
        by_src.setdefault(r["source"], []).append(r)
    out["by_source"] = {s: {"n": len(v), "verified_em": rate(v, "verified_correct")} for s, v in by_src.items()}
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("category"):
            by_cat.setdefault(r["category"], []).append(r)
    if by_cat:
        out["by_category"] = {c: {"n": len(v), "verified_em": rate(v, "verified_correct")} for c, v in sorted(by_cat.items())}
    return out
