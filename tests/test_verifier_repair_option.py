"""The verifier's `repair` option (docs/rewrite/05_verifier_repair_option.md).

These tests are skipped until `resolve` accepts `repair`; they then check that switching evidence repair off
withholds the answer instead of re-pointing the evidence, and changes nothing else.
"""
import inspect
import json
from pathlib import Path

import pytest

from tabletrace.agent.program import ProgramParseError, parse
from tabletrace.training.data import context_for, load_docs, read_records
from tabletrace.verify.verifier import resolve

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif("repair" not in inspect.signature(resolve).parameters,
                                reason="verify.verifier.resolve has no `repair` option yet (owner task 4b)")
Q = "러시아가 획득한 메달은 몇 개입니까?"
WRONG_CELL = "op: lookup ; cells: r2c1 ; answer: 60"      # r2c1 holds "러시아"; "60" is only in r2c5


def names(res) -> list[str]:
    return [c.name for c in res.verdict.checks]


def test_default_still_repairs_the_evidence(medal_table):
    for res in (resolve(Q, medal_table, parse(WRONG_CELL, "t_medal"), entity_check=False),
                resolve(Q, medal_table, parse(WRONG_CELL, "t_medal"), entity_check=False, repair=True)):
        assert res.status == "answered" and res.answer == "60" and [c.cid for c in res.cells] == ["r2c5"]
        assert "evidence_repaired" in names(res)
        assert any(t.tool == "cell_find" for t in res.trace)


def test_repair_off_withholds_instead(medal_table):
    res = resolve(Q, medal_table, parse(WRONG_CELL, "t_medal"), entity_check=False, repair=False)
    assert res.status == "abstained" and res.verdict.reason == "verification_failed"
    assert res.answer is None and res.cells == []
    assert "evidence_repaired" not in names(res)
    assert any(c.name == "answer_matches_cell" and not c.passed for c in res.verdict.checks)
    assert not any(t.tool == "cell_find" for t in res.trace)


@pytest.mark.parametrize("raw", [
    "op: lookup ; cells: r2c5 ; answer: 60",                              # cited cell holds the answer
    "op: lookup ; cells: r2c1 ; answer: 러시",                             # answer is part of the cited cell
    "op: diff ; cells: r0c5, r1c5 ; answer: 12",                          # calculation
    "op: abstain ; cells: - ; answer: - ; reason: not_in_document",      # explicit abstention
])
def test_repair_off_leaves_other_paths_alone(medal_table, raw):
    on = resolve(Q, medal_table, parse(raw, "t_medal"), entity_check=False)
    off = resolve(Q, medal_table, parse(raw, "t_medal"), entity_check=False, repair=False)
    assert (off.status, off.answer, [c.cid for c in off.cells], off.verdict.reason) == (on.status, on.answer, [c.cid for c in on.cells], on.verdict.reason)
    assert names(off) == names(on)
    assert [t.tool for t in off.trace] == [t.tool for t in on.trace]


@pytest.mark.parametrize("run", ["exaone_full_vllm_ko_custom", "rl_v3_ko_custom"])
def test_repair_off_on_stored_model_outputs(run):
    """Stored outputs of the hand-made 30: a repaired answer becomes an abstention, everything else stays as it was."""
    docs = load_docs(ROOT / "data" / "ko" / "documents.jsonl")
    recs = {r["qid"]: r for r in read_records([ROOT / "data" / "ko" / "custom_eval.jsonl"])}
    repaired = 0
    for line in open(ROOT / "experiments" / "eval" / run / "predictions.jsonl", encoding="utf-8"):
        row = json.loads(line)
        rec = recs[row["qid"]]
        doc = docs[rec["doc_id"]]
        table = doc.table(rec["table_id"])
        try:
            prog = parse(row["raw_output"], table.id)
        except ProgramParseError:
            prog = None
        ctx = context_for(doc, rec, limit=None)
        on = resolve(row["question"], table, prog, context=ctx, entity_check=False)
        if (on.status, on.answer) != (row["pred_status"], row["pred_answer"]):
            continue                      # the stored run saw a trimmed table or passage for this question
        off = resolve(row["question"], table, prog, context=ctx, entity_check=False, repair=False)
        if row["pred_status"] == "answered" and row["evidence_repaired"]:
            repaired += 1
            assert off.status == "abstained" and off.verdict.reason == "verification_failed", row["qid"]
        else:
            assert (off.status, off.answer) == (on.status, on.answer), row["qid"]
    assert repaired >= 1
