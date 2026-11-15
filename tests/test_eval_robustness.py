"""Two failures of the owner's GPU run (2026-11-14) that had nothing to do with a GPU.

1. One planner answer longer than the cell-search tool accepted made the verifier raise, which ended a whole
   evaluation run (the untuned 7.8B model, 699 questions lost).
2. Re-verifying a run that had scored a sample (--sample) failed with KeyError: the replay rebuilt the whole data set
   and looked every question up in the sampled predictions.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tabletrace.agent.program import parse
from tabletrace.schema import Table
from tabletrace.tools.registry import REGISTRY, ToolError
from tabletrace.verify.guard import resolve_guarded
from tabletrace.verify.verifier import resolve

ROOT = Path(__file__).resolve().parents[1]
TABLE = Table(id="t", doc_id="d", title="메달", lang="ko", header=["국가", "금", "은"], rows=[["한국", "13", "9"], ["일본", "12", "8"]])


@pytest.mark.parametrize("length", [201, 360])          # the program grammar allows at most 400 characters in all
def test_a_long_answer_is_withheld_not_an_error(length):
    program = parse(f"op: lookup ; cells: r0c1 ; answer: {'가' * length}", "t")
    out = resolve_guarded("한국의 금메달 수는?", TABLE, program, entity_check=False)
    assert out.status == "abstained" and out.verdict.reason == "verification_failed"
    assert resolve("한국의 금메달 수는?", TABLE, program, entity_check=False).status == "abstained"      # no exception from the verifier itself either


def test_the_guard_turns_a_tool_refusal_into_no_answer(monkeypatch):
    def refuse(name, table, args, trace=None):
        raise ToolError("invalid arguments for cell_find: refused")

    monkeypatch.setattr(REGISTRY, "call", refuse)
    program = parse("op: lookup ; cells: r0c1 ; answer: 99", "t")              # answer differs from the cell: the verifier searches for it
    with pytest.raises(ToolError):
        resolve("한국의 금메달 수는?", TABLE, program, entity_check=False)
    out = resolve_guarded("한국의 금메달 수는?", TABLE, program, entity_check=False)
    assert out.status == "abstained" and out.answer is None and out.cells == []
    assert [c.name for c in out.verdict.checks] == ["tool_call"] and not out.verdict.checks[0].passed


def test_replaying_a_sampled_run_re_verifies_the_same_questions(tmp_path):
    first, again = tmp_path / "first", tmp_path / "again"
    common = ["--corpus", "data/ko/documents.jsonl", "--data", "data/ko/custom_eval.jsonl", "--tokenizer", "approx"]
    run = [sys.executable, "-m", "tabletrace.eval.run", "--planner", "heuristic"]
    r = subprocess.run([*run, *common, "--sample", "12", "--sample-seed", "5", "--out", str(first)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    r = subprocess.run([*run, *common, "--replay-from", str(first), "--out", str(again)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    a, b = (json.loads((d / "metrics.json").read_text(encoding="utf-8")) for d in (first, again))
    assert a["metrics"]["n"] == b["metrics"]["n"] == 12 and b["meta"]["sample"] == {"n": 12, "seed": 5}
    qids = [[json.loads(x)["qid"] for x in (d / "predictions.jsonl").read_text(encoding="utf-8").splitlines()] for d in (first, again)]
    assert qids[0] == qids[1]
    assert a["metrics"]["verified_em"] == b["metrics"]["verified_em"]
