"""Analysis scripts added for the evidence-error, operating-point and table-overlap measurements."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "data"))

import evidence_error  # noqa: E402
import leak_effect  # noqa: E402


def test_wilson_interval():
    assert evidence_error.wilson(0, 0)["rate"] is None
    w = evidence_error.wilson(5, 10)
    assert w["rate"] == 0.5 and w["lo"] < 0.5 < w["hi"] and abs((0.5 - w["lo"]) - (w["hi"] - 0.5)) < 1e-3
    # textbook value: 6 of 455 -> about 0.6% to 2.9%
    w = evidence_error.wilson(6, 455)
    assert (w["lo"], w["hi"]) == pytest.approx((0.0061, 0.0285), abs=2e-4)
    edge = evidence_error.wilson(0, 20)
    assert edge["lo"] == 0.0 and 0 < edge["hi"] < 0.2


@pytest.mark.parametrize("raw, expected", [
    ("op: lookup ; cells: r2c5 ; answer: 60", ("cited_gold", "gold")),
    ("op: lookup ; cells: r2c1 ; answer: 60", ("no_answer_in_cell", "same_row")),       # right row, wrong column
    ("op: lookup ; cells: r0c5 ; answer: 60", ("no_answer_in_cell", "same_column")),
    ("op: lookup ; cells: r0c1 ; answer: 60", ("no_answer_in_cell", "other_row_and_column")),
    ("op: lookup ; cells: r9c9 ; answer: 60", ("no_answer_in_cell", "outside_table")),
    ("op: lookup ; cells: r2c5, r1c5 ; answer: 60", ("no_answer_in_cell", "several_cells")),
    ("the answer is 60", ("no_answer_in_cell", "unparsed")),
])
def test_classify_cited_cell(medal_table, raw, expected):
    assert medal_table.cell(2, 5) == "60"
    rec = {"gold_cells": [[2, 5]]}
    assert evidence_error.classify({"raw_output": raw}, rec, medal_table) == expected


def test_classify_same_value_in_another_cell(medal_table):
    """A cell that holds the same text as the answer is not counted as an evidence error."""
    twin = medal_table.model_copy(update={"rows": [list(r) for r in medal_table.rows]})
    twin.rows[0][1] = "60"
    got = evidence_error.classify({"raw_output": "op: lookup ; cells: r0c1 ; answer: 60"}, {"gold_cells": [[2, 5]]}, twin)
    assert got == ("same_value_elsewhere", "other_row_and_column")


def test_operating_point_counts():
    rows = [{"a": True, "ok": True}, {"a": True, "ok": False}, {"a": False, "ok": False}, {"a": True, "ok": True}]
    p = evidence_error.operating_point(rows, lambda r: r["a"], lambda r: r["ok"])
    assert (p["answered"], p["answered_correct"], p["answered_wrong"], p["coverage"]) == (3, 2, 1, 0.75)
    assert p["wrong_answer_rate"]["rate"] == 0.25 and p["accuracy_when_answered"]["k"] == 2


def test_bootstrap_resamples_tables_and_is_reproducible():
    seen = [[{"x": True}] * 3, [{"x": False}] * 3] * 20
    unseen = [[{"x": False}] * 3] * 40
    lo, hi = leak_effect.bootstrap_diff(seen, unseen, "x")
    assert 0.25 < lo < 0.5 < hi < 0.75                      # true difference is 0.5
    assert (lo, hi) == leak_effect.bootstrap_diff(seen, unseen, "x")


def _rows(name: str) -> list[dict]:
    return [json.loads(line) for line in open(ROOT / "data" / "ko" / name, encoding="utf-8")]


def test_leak_probe_sets_differ_only_in_table_exposure():
    seen, unseen, train = _rows("leak_probe_seen.jsonl"), _rows("leak_probe_unseen.jsonl"), _rows("train.jsonl")
    train_tables, train_qids = {r["table_id"] for r in train}, {r["qid"] for r in train}
    assert len(seen) == len(unseen) > 1000
    assert {r["table_id"] for r in seen} <= train_tables            # every seen-set table was trained on
    assert not {r["table_id"] for r in unseen} & train_tables       # no unseen-set table was
    assert not {r["qid"] for r in seen} & train_qids                # but no seen-set question was
    train_questions = {(r["table_id"], " ".join(r["question"].split()).lower()) for r in train}
    assert not {(r["table_id"], " ".join(r["question"].split()).lower()) for r in seen} & train_questions
    assert all(r["op"] == "lookup" and len(r["gold_cells"]) == 1 for r in seen + unseen)


def test_official_overlap_profile_is_consistent():
    p = json.loads((ROOT / "data" / "ko" / "official_split_profile.json").read_text(encoding="utf-8"))
    # identical tables are a subset of shared pages, and questions on shared tables a subset of questions on shared pages
    assert p["shared_tables_by_url_and_content"] <= p["dev"]["unique_tables_by_url_and_content"]
    assert p["dev_on_train_table"]["examples"] <= p["dev_on_train_url"]["examples"] <= p["dev"]["examples"]
    assert p["dev_same_table_same_answer_in_train"]["examples"] <= p["dev_on_train_table"]["examples"]


def test_no_repair_counterfactual_on_stored_runs():
    """Stored runs: the recomputed verified EM equals the recorded one, and switching repair off only removes answers."""
    eval_dir = ROOT / "experiments" / "eval"
    plain = evidence_error.one_run(eval_dir / "heuristic_ko_test")       # the heuristic never needs a repair
    assert plain["repaired_answers"] == 0 and plain["verified_em_no_repair"] == plain["verified_em"]
    weak = evidence_error.one_run(eval_dir / "rl_v3_ko_test")
    recorded = json.loads((eval_dir / "rl_v3_ko_test" / "metrics.json").read_text(encoding="utf-8"))["metrics"]["verified_em"]
    assert weak["verified_em"] == recorded
    assert weak["repaired_answers"] > 0 and weak["verified_em_no_repair"] < weak["verified_em"]
    with_repair, without = weak["verifier"], weak["verifier_no_repair"]
    assert without["answered"] == with_repair["answered"] - weak["repaired_answers"]
    assert without["answered_wrong"] <= with_repair["answered_wrong"] and without["answered_correct"] <= with_repair["answered_correct"]
