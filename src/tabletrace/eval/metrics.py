"""Metrics for answer, evidence, and evaluation records."""

from tabletrace.tools.cells import normalize_text
from tabletrace.tools.numbers import parse_number


def answer_match(pred: str | None, gold: str | None) -> bool:
    if pred is None or gold is None:
        return pred is None and gold is None
    if normalize_text(pred) == normalize_text(gold):
        return True
    prediction = parse_number(pred)
    target = parse_number(gold)
    if prediction is None or target is None:
        return False
    if prediction.unit is not None and target.unit is not None and prediction.unit != target.unit:
        return False
    tolerance = max(1e-6, 0.005 * abs(target.value))
    return abs(prediction.value - target.value) <= tolerance


def cells_match(pred: list[str], gold: list[str]) -> bool:
    return bool(gold) and set(pred) == set(gold)


def summarize(rows: list[dict]) -> dict:
    answerable = [r for r in rows if r["gold_status"] == "answered"]
    withheld_gold = [r for r in rows if r["gold_status"] == "abstained"]
    lookups = [r for r in answerable if r["gold_op"] == "lookup"]
    calculations = [r for r in answerable if r["gold_op"] != "lookup"]
    unit_checked = [r for r in calculations if r.get("unit_error") is not None]
    withheld_pred = [r for r in rows if r.get("pred_abstained")]
    untruncated = [r for r in rows if not r.get("truncated_gold")]

    def rate(group, field):
        return round(sum(bool(r.get(field)) for r in group) / len(group), 4) if group else None

    sources = {}
    categories = {}
    for record in rows:
        sources.setdefault(record["source"], []).append(record)
        category = record.get("category")
        if category:
            categories.setdefault(category, []).append(record)

    def breakdown(group):
        return {"n": len(group), "verified_em": rate(group, "verified_correct")}

    result = {
        "n": len(rows),
        "n_answerable": len(answerable),
        "n_gold_abstain": len(withheld_gold),
        "n_calc": len(calculations),
        "n_lookup": len(lookups),
        "verified_em": rate(rows, "verified_correct"),
        "answer_em_answerable": rate(answerable, "verified_correct"),
        "raw_answer_em_answerable": rate(answerable, "raw_correct"),
        "evidence_cells_exact": rate(answerable, "cells_exact"),
        "evidence_cells_exact_raw": rate(answerable, "cells_exact_raw"),
        "evidence_repaired_rate": rate(answerable, "evidence_repaired"),
        "evidence_cells_overlap": rate(answerable, "cells_overlap"),
        "op_acc": rate(rows, "op_correct"),
        "lookup_em": rate(lookups, "verified_correct"),
        "calc_em": rate(calculations, "verified_correct"),
        "calc_result_correct": rate(calculations, "calc_correct"),
        "unit_error_rate": rate(unit_checked, "unit_error"),
        "abstain_recall": rate(withheld_gold, "pred_abstained"),
        "false_abstain_rate": rate(answerable, "pred_abstained"),
        "abstain_precision": (
            round(sum(r["gold_status"] == "abstained" for r in withheld_pred) / len(withheld_pred), 4)
            if withheld_pred else None
        ),
        "parse_fail_rate": rate(rows, "parse_fail"),
        "verifier_corrections": rate(answerable, "verifier_changed"),
        "truncated_gold_rate": rate(rows, "truncated_gold"),
        "verified_em_untruncated": rate(untruncated, "verified_correct"),
        "mean_ms_per_example": round(sum(r.get("ms", 0) for r in rows) / len(rows), 1) if rows else None,
        "by_source": {name: breakdown(group) for name, group in sources.items()},
    }
    if categories:
        result["by_category"] = {name: breakdown(categories[name]) for name in sorted(categories)}
    return result
