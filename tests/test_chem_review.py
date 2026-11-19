"""The tools for the owner's review of the chemistry questions (docs/rewrite/11_chem_eval_review.md).

The review itself is the owner's. These tests check that the tool accepts only a complete review and that the analysis,
with nothing set aside, gives exactly the stored comparisons the documents quote.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import chem_review_analysis as analysis  # noqa: E402
import chem_review_tool as tool  # noqa: E402


@pytest.fixture(scope="module")
def nothing_set_aside():
    return analysis.analyse(set())


def test_with_nothing_set_aside_the_stored_comparisons_come_back(nothing_set_aside):
    c = nothing_set_aside["checks"]
    assert (c["1_paper_headline"]["all"]["correct"], c["1_paper_headline"]["all"]["n"]) == (46, 62)
    pairs = {k: (v["all"]["only_candidate"], v["all"]["only_reference"]) for k, v in c.items() if "same_conclusion" in v}
    assert pairs == {"2_papers_korean_only_vs_chemistry": (7, 3), "3_papers_untuned_vs_korean_only": (30, 3),
                     "3_papers_baseline_vs_korean_only": (24, 9), "4_textbook_korean_only_vs_chemistry": (5, 0),
                     "5_unanswerable_repeat_vs_korean_only": (10, 0)}
    assert c["5_unanswerable_repeat_vs_korean_only"]["all"]["p_display"] == "0.002"
    assert nothing_set_aside["every_conclusion_same"] and nothing_set_aside["paper_runs_whose_order_reverses"] == 0


def test_setting_questions_aside_takes_them_out_of_every_count():
    papers = [json.loads(x)["qid"] for x in (ROOT / "data/chem_papers/custom_eval.jsonl").read_text(encoding="utf-8").splitlines()]
    unanswerable = [json.loads(x)["qid"] for x in (ROOT / "data/chem_papers/custom_eval.jsonl").read_text(encoding="utf-8").splitlines()
                    if json.loads(x)["op"] == "abstain"]
    out = analysis.analyse({papers[0], unanswerable[0]})
    assert out["checks"]["1_paper_headline"]["without_set_aside"]["n"] == 60
    assert out["checks"]["5_unanswerable_repeat_vs_korean_only"]["questions_set_aside"] == 1
    assert out["runs"]["exaone_kochem2_vllm_chem_papers"]["without_set_aside"]["n"] == 60
    assert out["runs"]["exaone_kochem2_vllm_chem_custom"]["without_set_aside"]["n"] == 32


def rows_for(name: str, verdict: str = "ok") -> list[dict]:
    return [{"qid": r["qid"], "verdict": verdict, "comment": ""} for r in tool.load(tool.SETS[name]["questions"])]


@pytest.mark.parametrize("name", ["papers", "textbook"])
def test_a_complete_review_passes(name):
    rows = rows_for(name)
    rows[0] = {**rows[0], "verdict": "fix", "comment": "the unit in the answer is wrong"}
    assert tool.check_review(name, rows) == []


@pytest.mark.parametrize("change, message", [
    (lambda rows: rows[:-1], "판정이 없는 문항"),
    (lambda rows: [{**rows[0], "verdict": ""}, *rows[1:]], "verdict는"),
    (lambda rows: [{**rows[0], "verdict": "drop"}, *rows[1:]], "까닭"),
    (lambda rows: [*rows, rows[0]], "두 번"),
    (lambda rows: [{**rows[0], "qid": "chem_paper_99"}, *rows[1:]], "없는 문항"),
])
def test_an_incomplete_review_is_refused(change, message):
    errs = tool.check_review("papers", change(rows_for("papers")))
    assert any(message in e for e in errs), errs


def test_template_leaves_every_verdict_blank_and_never_overwrites(tmp_path, monkeypatch):
    target = tmp_path / "review.jsonl"
    monkeypatch.setitem(tool.SETS, "papers", {**tool.SETS["papers"], "review": target})
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    assert tool.cmd_template("papers") == 0
    rows = [json.loads(x) for x in target.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 62 and all(r["verdict"] == "" for r in rows)
    assert tool.check_review("papers", rows)          # blank verdicts do not pass
    target.write_text("kept", encoding="utf-8")
    assert tool.cmd_template("papers") == 1 and target.read_text(encoding="utf-8") == "kept"
