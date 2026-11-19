"""Tests for agent/heuristic.py, the word-overlap baseline (rewrite step 5, docs/rewrite/10_agent_heuristic.md).

Written by the AI coding tool as the specification the owner's rewrite must meet. They pass on the current
implementation. The last test checks the stored evaluation results: on every stored heuristic run, each question
whose table was not cut must get exactly the program the run stored. `python scripts/rewrite_parity.py heuristic`
compares the whole behaviour, every question in every set, with the original.
"""
import json
from pathlib import Path

import pytest

from tabletrace.agent.heuristic import _calc_intent, plan
from tabletrace.agent.program import serialize
from tabletrace.model.approx_tokenizer import ApproxTokenizer
from tabletrace.schema import Table
from tabletrace.training.data import build_examples, load_docs

ROOT = Path(__file__).resolve().parents[1]

K_LEAGUE = Table(id="k", doc_id="d", title="2002년 K리그 도움 순위", header=["선수", "클럽", "도움", "경기"],
                 rows=[["이천수", "울산 현대", "9", "18"], ["김대의", "성남 일화", "9", "27"], ["메도", "포항 스틸러스", "7", "18"],
                       ["데니스", "수원 삼성", "6", "17"]], lang="ko")
GASES = Table(id="e", doc_id="d", title="gases", header=["Gas", "Formula", "Molar mass (g/mol)", "Boiling point (°C)"],
              rows=[["carbon dioxide", "CO2", "44.01", "-78.5"], ["nitrogen dioxide", "NO2", "46.01", "21.2"],
                    ["methane", "CH4", "16.04", "-161.5"], ["water vapour", "H2O", "18.02", "100"]],
              units={2: "g/mol", 3: "°C"}, lang="en")


def run(table: Table, question: str) -> str:
    return serialize(plan(question, table, table.lang))


# ---------------------------------------------------------------- lookups

@pytest.mark.parametrize("question, program", [
    ("메도의 클럽은 어디입니까?", "op: lookup ; cells: r2c1 ; answer: 포항 스틸러스"),
    ("메도의 소속 클럽은?", "op: lookup ; cells: r2c1 ; answer: 포항 스틸러스"),
    ("데니스는 몇 경기에 나왔나요?", "op: lookup ; cells: r3c3 ; answer: 17"),
    # two columns score the same (선수, 도움): the first one wins, so the baseline answers with a name
    ("울산 현대 선수의 도움은?", "op: lookup ; cells: r0c0 ; answer: 이천수"),
])
def test_lookup_takes_the_best_row_and_the_named_column(question, program):
    assert run(K_LEAGUE, question) == program


@pytest.mark.parametrize("question, program", [
    ("What is the molar mass of carbon dioxide?", "op: lookup ; cells: r0c2 ; answer: 44.01"),   # 'carbon dioxide' beats 'dioxide'
    ("What is the boiling point of nitrogen dioxide?", "op: lookup ; cells: r1c3 ; answer: 21.2"),
    ("What is the formula of methane?", "op: lookup ; cells: r2c1 ; answer: CH4"),
])
def test_lookup_in_english_and_whole_cells_in_the_question_count_extra(question, program):
    assert run(GASES, question) == program


@pytest.mark.parametrize("table, question, program", [
    (K_LEAGUE, "?", "op: abstain ; cells: - ; answer: - ; reason: ambiguous_question"),                # no word to match
    (K_LEAGUE, "홍길동의 도움은?", "op: abstain ; cells: - ; answer: - ; reason: not_in_document"),     # no row matches
    (K_LEAGUE, "도움이 9개인 선수의 클럽은?", "op: abstain ; cells: - ; answer: - ; reason: ambiguous_question"),   # two rows tie
    (GASES, "What is the dioxide?", "op: abstain ; cells: - ; answer: - ; reason: ambiguous_question"),
    (GASES, "What is the density of argon?", "op: abstain ; cells: - ; answer: - ; reason: not_in_document"),
    # no column named and more than one column left over in the row: cannot tell which one is asked
    (K_LEAGUE, "메도", "op: abstain ; cells: - ; answer: - ; reason: ambiguous_question"),
])
def test_abstentions(table, question, program):
    assert run(table, question) == program


# ---------------------------------------------------------------- calculations

@pytest.mark.parametrize("question, program", [
    ("이천수의 도움은 메도보다 몇 개 더 많습니까?", "op: diff ; cells: r0c2, r2c2 ; answer: -"),
    ("메도와 이천수의 도움 차이는?", "op: diff ; cells: r2c2, r0c2 ; answer: -"),      # operands in the order the question names them
    ("이천수, 김대의, 메도의 도움 합계는?", "op: sum ; cells: r0c2, r1c2, r2c2 ; answer: -"),   # a sum takes up to three rows
    ("이천수와 메도의 평균 도움은?", "op: avg ; cells: r0c2, r2c2 ; answer: -"),
    ("이천수의 도움은 메도의 몇 배입니까?", "op: ratio ; cells: r0c2, r2c2 ; answer: -"),
    ("이천수의 경기 수는 메도보다 몇 % 많습니까?", "op: pct_change ; cells: r0c3, r2c3 ; answer: -"),
    ("이천수의 경기와 메도의 경기 차이는?", "op: diff ; cells: r0c3, r2c3 ; answer: -"),
    ("이천수의 도움 차이는?", "op: lookup ; cells: r0c2 ; answer: 9"),   # one row named: the calculation word is ignored
])
def test_calculations_in_korean(question, program):
    assert run(K_LEAGUE, question) == program


@pytest.mark.parametrize("question, program", [
    ("How much higher is the boiling point of water vapour than that of methane?", "op: diff ; cells: r3c3, r2c3 ; answer: -"),
    ("What is the ratio of the molar mass of carbon dioxide to that of methane?", "op: ratio ; cells: r0c2, r2c2 ; answer: -"),
    ("What is the combined molar mass of methane and water vapour?", "op: sum ; cells: r2c2, r3c2 ; answer: -"),
    ("What is the average molar mass of methane and water vapour?", "op: avg ; cells: r2c2, r3c2 ; answer: -"),
    # no column named: the last numeric column
    ("What is the difference between carbon dioxide and methane?", "op: diff ; cells: r0c3, r2c3 ; answer: -"),
])
def test_calculations_in_english(question, program):
    assert run(GASES, question) == program


def test_calculation_answer_is_left_to_the_calculator():
    p = plan("이천수의 도움은 메도보다 몇 개 더 많습니까?", K_LEAGUE, "ko")
    assert p.op == "diff" and p.answer is None and p.reason is None
    assert all(c.table_id == "k" for c in p.cells)


def test_a_column_with_too_few_numbers_is_not_numeric():
    # 경기 has a number in only 1 of 4 rows, so no column is numeric: the question is read as a lookup, where the two named rows tie
    t = Table(id="n", doc_id="d", title="t", header=["선수", "경기"], rows=[["가나", "18"], ["다라", "-"], ["마바", "부상"], ["사아", "없음"]], lang="ko")
    assert run(t, "가나와 다라의 경기 차이는?") == "op: abstain ; cells: - ; answer: - ; reason: ambiguous_question"


@pytest.mark.parametrize("column, program", [
    (["18", "20", "-", "부상", "없음"], "op: abstain ; cells: - ; answer: - ; reason: ambiguous_question"),   # 2 of 5 numbers: below 60%
    (["18", "20", "22", "부상", "없음"], "op: diff ; cells: r0c2, r1c2 ; answer: -"),                       # 3 of 5: numeric
])
def test_a_numeric_column_needs_numbers_in_60_percent_of_its_rows(column, program):
    t = Table(id="n", doc_id="d", title="t", header=["선수", "팀", "경기"],
              rows=[[n, team, v] for n, team, v in zip(["가나", "다라", "마바", "사아", "자차"], "ABCDE", column, strict=True)], lang="ko")
    assert run(t, "가나와 다라의 경기 차이는?") == program


def test_plan_leaves_the_table_alone():
    before = K_LEAGUE.model_dump_json()
    plan("이천수, 김대의, 메도의 도움 합계는?", K_LEAGUE, "ko")
    assert K_LEAGUE.model_dump_json() == before


# ---------------------------------------------------------------- the calculation word

@pytest.mark.parametrize("question, op", [
    ("몇 배 차이가 나나요?", "ratio"),          # ratio is tried before diff
    ("증가율은 몇 %입니까?", "pct_change"), ("평균 득점 차이", "avg"), ("합계 차이는?", "diff"),   # diff before sum: 합계 is often a column
    ("몇 명 더 많습니까", "diff"), ("총 관객 수", "sum"),
    ("total points", "sum"), ("How much larger", "diff"), ("by what factor did it increase", "ratio"),
    ("percent change in sales", "pct_change"), ("the mean value", "avg"), ("Average Mass", "avg"),
    ("메도의 클럽은 어디입니까?", None), ("What is the formula of methane?", None),
])
def test_calc_intent(question, op):
    assert _calc_intent(question) == op


# ---------------------------------------------------------------- the stored runs

@pytest.mark.parametrize("run_name", ["heuristic_ko_test", "heuristic_ko_custom", "heuristic_ko_owner", "heuristic_chem_custom",
                                      "heuristic_chem_papers"])
def test_plan_gives_the_stored_program_of_a_heuristic_run(run_name):
    """The stored runs counted the row budget with the mT5 tokenizer, which is not in the repository. With the
    approximate tokenizer every question whose table is shown whole is the same input as in the run."""
    d = ROOT / "experiments" / "eval" / run_name
    meta = json.loads((d / "metrics.json").read_text(encoding="utf-8"))["meta"]
    stored = {r["qid"]: r["raw_output"] for r in map(json.loads, (d / "predictions.jsonl").read_text(encoding="utf-8").splitlines())}
    docs = load_docs(*[ROOT / c for c in meta["corpus"]])
    recs = [json.loads(line) for p in meta["data"] for line in (ROOT / p).read_text(encoding="utf-8").splitlines() if line.strip()]
    whole = [e for e in build_examples(recs, docs, ApproxTokenizer(), 512) if e.table_full is None or e.table_full.rows == e.table.rows]
    assert len(whole) >= 20
    wrong = [(e.qid, stored[e.qid], serialize(plan(e.question, e.table, e.table.lang))) for e in whole
             if serialize(plan(e.question, e.table, e.table.lang)) != stored[e.qid]]
    assert not wrong, f"{len(wrong)} of {len(whole)} differ, e.g. {wrong[:2]}"
