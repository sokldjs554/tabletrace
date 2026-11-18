"""Tests for eval/metrics.py: answer_match, cells_match, summarize (rewrite step 7, docs/rewrite/08_eval_metrics.md).

Written by the AI coding tool as the specification the owner's rewrite must meet. They pass on the current
implementation. The last test also checks the stored evaluation results: summarize over a stored predictions file
must give that evaluation's stored metrics. `python scripts/rewrite_parity.py metrics` does the same for all of them.
"""
import json
from pathlib import Path

import pytest

from tabletrace.eval.metrics import answer_match, cells_match, summarize

ROOT = Path(__file__).resolve().parents[1]

KEYS = ["n", "n_answerable", "n_gold_abstain", "n_calc", "n_lookup", "verified_em", "answer_em_answerable", "raw_answer_em_answerable",
        "evidence_cells_exact", "evidence_cells_exact_raw", "evidence_repaired_rate", "evidence_cells_overlap", "op_acc", "lookup_em", "calc_em",
        "calc_result_correct", "unit_error_rate", "abstain_recall", "false_abstain_rate", "abstain_precision", "parse_fail_rate",
        "verifier_corrections", "truncated_gold_rate", "verified_em_untruncated", "mean_ms_per_example", "by_source"]
FLAGS = ["verified_correct", "raw_correct", "cells_exact", "cells_exact_raw", "evidence_repaired", "cells_overlap", "op_correct",
         "calc_correct", "pred_abstained", "parse_fail", "verifier_changed", "truncated_gold"]


def row(**kw) -> dict:
    """One evaluation record with every flag false; keyword arguments override."""
    r = {"gold_status": "answered", "gold_op": "lookup", "source": "s", "unit_error": None, **{f: False for f in FLAGS}}
    r.update(kw)
    return r


# ---------------------------------------------------------------- answer_match

@pytest.mark.parametrize("pred, gold, want", [
    (None, None, True), (None, "1", False), ("1", None, False), (None, "", False),
    ("ABC", "abc", True), ("Ｂ", "b", True), ("  a   b ", "a b", True), ("a\tb\n", "a b", True), ("", "", True), ("", "  ", True),
    ("abc", "abd", False), ("서울", "서울시", False),
])
def test_answer_match_compares_normalized_text_first(pred, gold, want):
    assert answer_match(pred, gold) is want


@pytest.mark.parametrize("pred, gold, want", [
    ("1,062,201", "1062201", True),          # the same number written differently
    ("1,062,201 명", "1,062,201", True),     # a unit on one side only
    ("1,062,201", "1,062,201 명", True),
    ("12.5%", "12.5", True), ("2024년", "2024", True),
    ("3", "3 m", True), ("3 km", "3 m", False),   # different units are different answers, whatever the value
    ("１,０００", "1000", True),              # full-width digits
    ("−5", "-5", True), ("-5", "5", False),
    ("1.5만", "15000", False),                # the parser does not read 만: not a number, and the text differs
    ("약 3 kg", "3 kg", False),
])
def test_answer_match_reads_numbers_and_units(pred, gold, want):
    assert answer_match(pred, gold) is want


@pytest.mark.parametrize("pred, gold, want", [
    ("100.5", "100", True),        # 0.5% of the gold value, the boundary included
    ("100.502", "100", False),
    ("99.5", "100", True), ("99.49", "100", False),
    ("-100.4", "-100", True), ("-100.6", "-100", False),   # the tolerance uses the size of the gold value
    ("0.0000005", "0", True),      # near zero the tolerance is at least 1e-6
    ("0.0000011", "0", False),
    ("1000004", "1000000", True), ("1005001", "1000000", False),
])
def test_answer_match_tolerance_is_half_a_percent_of_the_gold_value(pred, gold, want):
    assert answer_match(pred, gold) is want


def test_answer_match_is_not_symmetric_near_the_boundary():
    """The tolerance is taken from the gold value, so swapping the two can change the result."""
    assert answer_match("100.502", "100") is False
    assert answer_match("100", "100.502") is True


# ---------------------------------------------------------------- cells_match

@pytest.mark.parametrize("pred, gold, want", [
    (["r1c2", "r0c1"], ["r0c1", "r1c2"], True),   # order does not matter
    (["r0c1", "r0c1"], ["r0c1"], True),           # duplicates do not matter
    (["r0c1"], ["r0c1", "r1c1"], False), (["r0c1", "r1c1"], ["r0c1"], False),
    (["r0c2"], ["r0c1"], False),
    ([], [], False), (["r0c1"], [], False), ([], ["r0c1"], False),   # no gold cells: never a match
])
def test_cells_match_compares_sets_and_needs_gold_cells(pred, gold, want):
    assert cells_match(pred, gold) is want


# ---------------------------------------------------------------- summarize

def test_summarize_of_no_rows():
    assert summarize([]) == {**{k: None for k in KEYS}, "n": 0, "n_answerable": 0, "n_gold_abstain": 0, "n_calc": 0, "n_lookup": 0, "by_source": {}}
    assert list(summarize([])) == KEYS


def test_summarize_groups_questions_and_counts_text_questions_as_calculations():
    rows = [row(gold_op="lookup"), row(gold_op="lookup"), row(gold_op="diff"), row(gold_op="text"),
            row(gold_status="abstained", gold_op="abstain")]
    m = summarize(rows)
    assert (m["n"], m["n_answerable"], m["n_gold_abstain"], m["n_calc"], m["n_lookup"]) == (5, 4, 1, 2, 2)


def test_summarize_rates_are_rounded_to_four_places_and_none_when_the_group_is_empty():
    rows = [row(verified_correct=True), row(), row()]
    m = summarize(rows)
    assert m["verified_em"] == 0.3333 and m["lookup_em"] == 0.3333
    assert m["calc_em"] is None and m["calc_result_correct"] is None and m["unit_error_rate"] is None   # no calculation questions
    assert m["abstain_recall"] is None                                                               # no unanswerable questions
    two = summarize([row(verified_correct=True), row(verified_correct=True), row()])
    assert two["verified_em"] == 0.6667


def test_summarize_every_rate_uses_its_own_group():
    rows = [
        row(gold_op="lookup", verified_correct=True, raw_correct=True, cells_exact=True, cells_exact_raw=False, evidence_repaired=True,
            cells_overlap=True, op_correct=True, verifier_changed=True),
        row(gold_op="diff", verified_correct=False, calc_correct=True, unit_error=False, op_correct=True, cells_overlap=True),
        row(gold_op="sum", verified_correct=True, calc_correct=False, unit_error=True, pred_abstained=False),
        row(gold_op="avg", unit_error=None, pred_abstained=True),                   # no unit comparison for this one
        row(gold_status="abstained", gold_op="abstain", pred_abstained=True, verified_correct=True, op_correct=True),
        row(gold_status="abstained", gold_op="abstain", pred_abstained=False, parse_fail=True),
    ]
    m = summarize(rows)
    assert m["verified_em"] == round(3 / 6, 4)
    assert m["answer_em_answerable"] == round(2 / 4, 4) and m["raw_answer_em_answerable"] == round(1 / 4, 4)
    assert m["evidence_cells_exact"] == 0.25 and m["evidence_cells_exact_raw"] == 0.0 and m["evidence_repaired_rate"] == 0.25
    assert m["evidence_cells_overlap"] == 0.5 and m["op_acc"] == 0.5
    assert m["lookup_em"] == 1.0 and m["calc_em"] == round(1 / 3, 4) and m["calc_result_correct"] == round(1 / 3, 4)
    assert m["unit_error_rate"] == 0.5                                               # over the two calculation rows with a unit comparison
    assert m["abstain_recall"] == 0.5 and m["false_abstain_rate"] == 0.25
    assert m["abstain_precision"] == 0.5                                             # 2 withheld, 1 of them should have been
    assert m["parse_fail_rate"] == round(1 / 6, 4) and m["verifier_corrections"] == 0.25


def test_summarize_abstain_precision_is_present_even_when_nothing_was_withheld():
    m = summarize([row(), row(gold_status="abstained", gold_op="abstain")])
    assert "abstain_precision" in m and m["abstain_precision"] is None


def test_summarize_untruncated_and_mean_time():
    rows = [row(verified_correct=True, truncated_gold=True, ms=10), row(verified_correct=False, ms=20.26), row(verified_correct=True)]
    m = summarize(rows)
    assert m["truncated_gold_rate"] == round(1 / 3, 4) and m["verified_em_untruncated"] == 0.5
    assert m["mean_ms_per_example"] == 10.1                                          # (10 + 20.26 + 0) / 3, one decimal; a missing ms counts as 0
    assert summarize([row(truncated_gold=True)])["verified_em_untruncated"] is None


def test_summarize_by_source_keeps_first_appearance_order():
    rows = [row(source="b", verified_correct=True), row(source="a"), row(source="b"), row(source="c", verified_correct=True)]
    m = summarize(rows)
    assert list(m["by_source"]) == ["b", "a", "c"]
    assert m["by_source"] == {"b": {"n": 2, "verified_em": 0.5}, "a": {"n": 1, "verified_em": 0.0}, "c": {"n": 1, "verified_em": 1.0}}


def test_summarize_by_category_only_when_some_row_has_one_and_sorted():
    assert "by_category" not in summarize([row(), row(category=None), row(category="")])
    rows = [row(category="cell", verified_correct=True), row(category="calc"), row(category="cell"), row(category=None, verified_correct=True), row()]
    m = summarize(rows)
    assert list(m) == [*KEYS, "by_category"]
    assert list(m["by_category"]) == ["calc", "cell"]
    assert m["by_category"] == {"calc": {"n": 1, "verified_em": 0.0}, "cell": {"n": 2, "verified_em": 0.5}}


def test_summarize_takes_truthy_values_and_ignores_other_fields_and_leaves_the_rows_alone():
    rows = [row(verified_correct=1, extra="x", checks=[{"name": "a"}]), row(verified_correct=0)]
    before = json.dumps(rows, sort_keys=True)
    m = summarize(rows)
    assert m["verified_em"] == 0.5 and list(m) == KEYS
    assert json.dumps(rows, sort_keys=True) == before


@pytest.mark.parametrize("run", ["heuristic_ko_test", "rl_v3_ko_test", "exaone_full_vllm_ko_test", "exaone_full4_vllm_ko_owner",
                                 "exaone_kochem2_vllm_chem_papers", "ref_1p2b_chem_custom", "exaone_vllm_ko_test_ec"])
def test_summarize_gives_the_stored_metrics_of_an_evaluation(run):
    """The evaluation runner wrote metrics.json from summarize over these very rows (and then added a few keys of its
    own after them). The rewrite must give the same values, in the same order."""
    d = ROOT / "experiments" / "eval" / run
    rows = [json.loads(x) for x in (d / "predictions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    stored = json.loads((d / "metrics.json").read_text(encoding="utf-8"))["metrics"]
    m = summarize(rows)
    assert list(stored)[: len(m)] == list(m)
    assert {k: stored[k] for k in m} == m
