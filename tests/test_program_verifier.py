import pytest

from tabletrace.agent.heuristic import plan
from tabletrace.agent.program import ProgramParseError, make_abstain, parse, serialize
from tabletrace.schema import CellRef, Program
from tabletrace.verify.verifier import find_span, resolve


def test_parse_roundtrip():
    for text in ["op: lookup ; cells: r2c5 ; answer: 60", "op: diff ; cells: r1c5, r2c5 ; answer: 52",
                 "op: abstain ; cells: - ; answer: - ; reason: not_in_document", "op: text ; cells: - ; answer: 2018년 1월 1일"]:
        p = parse(text, "t_medal")
        assert serialize(p) == text


@pytest.mark.parametrize("bad", ["", "hello", "op: fly ; cells: r1c1 ; answer: x", "op: lookup ; cells: - ; answer: 1",
                                 "op: lookup ; cells: x1 ; answer: 1", "op: lookup ; cells: r1c1 ; op: diff", "answer: 3",
                                 "op: text ; cells: - ; answer: -", "op: lookup ; cells: " + ", ".join(f"r{i}c0" for i in range(20)) + " ; answer: 1"])
def test_parse_rejects(bad):
    with pytest.raises(ProgramParseError):
        parse(bad, "t")


def test_lookup_verified(medal_table):
    r = resolve("러시아가 획득한 메달은 몇 개입니까?", medal_table, parse("op: lookup ; cells: r2c5 ; answer: 60", "t_medal"))
    assert r.status == "answered" and r.answer == "60" and [c.cid for c in r.cells] == ["r2c5"]
    assert any(c.name == "answer_matches_cell" and c.passed for c in r.verdict.checks)


def test_lookup_unsupported_answer_is_blocked(medal_table):
    r = resolve("러시아의 메달 수는?", medal_table, parse("op: lookup ; cells: r2c5 ; answer: 61", "t_medal"))
    assert r.status == "abstained" and r.verdict.reason == "verification_failed"


def test_lookup_out_of_range(medal_table):
    r = resolve("q", medal_table, parse("op: lookup ; cells: r9c1 ; answer: x", "t_medal"))
    assert r.status == "abstained" and r.verdict.reason == "invalid_program"


def test_calc_recomputed_and_corrected(medal_table):
    r = resolve("미국과 러시아의 합계 차이는?", medal_table, parse("op: diff ; cells: r1c5, r2c5 ; answer: 50", "t_medal"))
    assert r.status == "answered" and r.answer == "52" and r.calculation.expression == "112.0 - 60.0"
    assert any(c.name == "answer_matches_calc" and not c.passed for c in r.verdict.checks)


def test_calc_unit_mismatch(sales_table):
    r = resolve("매출액과 영업이익의 차이는?", sales_table, parse("op: diff ; cells: r0c1, r0c2 ; answer: 1", "t_sales"))
    assert r.status == "abstained" and r.verdict.reason == "unit_mismatch"


def test_period_check_is_reported(sales_table):
    r = resolve("2024년 1분기 매출액은?", sales_table, parse("op: lookup ; cells: r0c1 ; answer: 1,200", "t_sales"))
    chk = {c.name: c for c in r.verdict.checks}
    assert chk["period_consistent"].passed is False


def test_abstain_paths(medal_table):
    assert resolve("q", None, None).verdict.reason == "retrieval_low"
    assert resolve("q", medal_table, None).verdict.reason == "invalid_program"
    assert resolve("q", medal_table, make_abstain("ambiguous_question")).verdict.reason == "ambiguous_question"


def test_text_answer_requires_passage(medal_table):
    p = Program(op="text", cells=[], answer="2018년 1월 1일")
    assert resolve("q", medal_table, p, context=None).verdict.reason == "not_in_document"
    assert resolve("q", medal_table, p, context="통계는 2018년 1월 1일부터 집계").answer == "2018년 1월 1일"
    assert resolve("q", medal_table, p, context="다른 문장").verdict.reason == "verification_failed"
    assert find_span("36 °C,27 °C", "are 36 °C, 27 °C, and 9.5 °C") is not None


def test_heuristic_planner(medal_table):
    p = plan("미국과 러시아의 합계 차이는?", medal_table, "ko")
    assert p.op == "diff" and {c.cid for c in p.cells} == {"r1c5", "r2c5"}
    assert plan("일본의 금메달 수는?", medal_table, "ko").op == "abstain"
    p = plan("영국의 합계는 몇 개입니까?", medal_table, "ko")
    assert p.op == "lookup" and p.cells[0] == CellRef(table_id="t_medal", row=3, col=5)
    # single-character headers (은) cannot be matched lexically -> the baseline abstains instead of guessing
    assert plan("영국의 은메달은 몇 개입니까?", medal_table, "ko").op == "abstain"


def test_lookup_short_numeric_fragment_is_not_supported(medal_table):
    # "1" is a substring of "112" but it is a different number -> blocked
    r = resolve("q", medal_table, parse("op: lookup ; cells: r1c5 ; answer: 1", "t_medal"))
    assert r.status == "abstained" and r.verdict.reason == "verification_failed"
    # a meaningful text fragment of the cell is accepted and the full cell text is returned
    t = medal_table.model_copy(update={"rows": [["1", "최규하(崔圭夏)", "1", "1", "1", "1"]]})
    r = resolve("q", t, parse("op: lookup ; cells: r0c1 ; answer: 최규하", "t_medal"))
    assert r.status == "answered" and r.answer == "최규하(崔圭夏)"
    assert any(c.name == "answer_matches_cell" and not c.passed for c in r.verdict.checks)
