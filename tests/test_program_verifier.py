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


def test_lookup_evidence_repair_when_citation_is_wrong(medal_table):
    # the model names the right value but cites the wrong cell: the unique matching cell becomes the evidence
    r = resolve("러시아의 합계는?", medal_table, parse("op: lookup ; cells: r2c1 ; answer: 60", "t_medal"))
    assert r.status == "answered" and r.answer == "60" and [c.cid for c in r.cells] == ["r2c5"]
    assert any(c.name == "evidence_repaired" and not c.passed for c in r.verdict.checks)
    # ambiguous (13 appears twice) -> still blocked
    r = resolve("q", medal_table, parse("op: lookup ; cells: r0c0 ; answer: 13", "t_medal"))
    assert r.status == "abstained" and r.verdict.reason == "verification_failed"


def test_degenerate_calculation_is_rejected(medal_table):
    r = resolve("q", medal_table, parse("op: diff ; cells: r2c5, r2c5 ; answer: 0", "t_medal"))
    assert r.status == "abstained" and r.verdict.reason == "invalid_program"
    assert any(c.name == "distinct_cells" and not c.passed for c in r.verdict.checks)


# --- subject check: the cited rows must be about what the question asks ------------------------------------------

def test_subject_missing_from_table_is_not_in_document(medal_table):
    # "캐나다" is not in the table; a lookup that cites some other country's row must not be answered
    q = "2008년 하계 올림픽에서 캐나다가 획득한 메달은 몇 개입니까?"
    p = parse("op: lookup ; cells: r2c5 ; answer: 60", "t_medal")
    assert resolve(q, medal_table, p, entity_check=False).status == "answered"      # the old verifier let this through
    r = resolve(q, medal_table, p)
    assert r.status == "abstained" and r.verdict.reason == "not_in_document"
    chk = next(c for c in r.verdict.checks if c.name == "subject_in_evidence")
    assert not chk.passed and "캐나다" in chk.detail


def test_subject_present_in_cited_row_passes(medal_table):
    q = "러시아가 획득한 메달은 몇 개입니까?"
    r = resolve(q, medal_table, parse("op: lookup ; cells: r2c5 ; answer: 60", "t_medal"))
    assert r.status == "answered"
    assert any(c.name == "subject_in_evidence" and c.passed for c in r.verdict.checks)


def test_subject_in_other_row_means_wrong_row_cited(medal_table):
    q = "러시아가 획득한 메달은 몇 개입니까?"
    r = resolve(q, medal_table, parse("op: lookup ; cells: r0c5 ; answer: 100", "t_medal"))
    assert r.status == "abstained" and r.verdict.reason == "verification_failed"


def test_table_title_words_are_not_subjects(medal_table):
    # "올림픽" names the table; it must neither satisfy nor trigger the check, so a question with no other
    # proper noun is not blocked by it
    q = "하계 올림픽에서 1위 국가의 금메달은 몇 개입니까?"
    r = resolve(q, medal_table, parse("op: lookup ; cells: r0c2 ; answer: 48", "t_medal"))
    assert r.status == "answered"


def test_transliteration_variants_are_tolerated():
    from tabletrace.schema import Table

    t = Table(id="t", doc_id="d", title="출연 목록", header=["이름", "역할"], rows=[["자오위에", "센터"], ["김철수", "리더"]], lang="ko")
    r = resolve("자오웨의 역할은 무엇입니까?", t, parse("op: lookup ; cells: r0c1 ; answer: 센터", "t"))
    assert r.status == "answered"


def test_gold_programs_bypass_the_check(medal_table):
    q = "캐나다의 메달 수는?"
    p = parse("op: lookup ; cells: r2c5 ; answer: 60", "t_medal")
    assert resolve(q, medal_table, p, entity_check=False).status == "answered"


def test_english_formula_subject():
    from tabletrace.schema import Table

    t = Table(id="t", doc_id="d", title="Critical constants", header=["Substance", "Tc (K)"],
              rows=[["H2O", "647"], ["CO2", "304"]], lang="en")
    ok = resolve("What is the critical temperature of CO2?", t, parse("op: lookup ; cells: r1c1 ; answer: 304", "t"))
    assert ok.status == "answered"
    bad = resolve("What is the critical temperature of NH3?", t, parse("op: lookup ; cells: r1c1 ; answer: 304", "t"))
    assert bad.status == "abstained" and bad.verdict.reason == "not_in_document"
    # topic and unit words alone never block an answer
    topic = resolve("What is the temperature in Celsius for the Arrhenius data of water?", t, parse("op: lookup ; cells: r0c1 ; answer: 647", "t"))
    assert topic.status == "answered"


def test_column_check_moves_to_the_named_column_but_is_off_by_default():
    from tabletrace.schema import Table

    t = Table(id="t_m", doc_id="d_m", title="올림픽 메달 집계", header=["순위", "국가", "금메달", "은메달", "합계"],
              rows=[["3", "러시아", "24", "13", "60"]], lang="ko")
    q = "러시아가 획득한 금메달은 몇 개입니까?"                    # asks for 금메달 (c2); the model cited 합계 (c4)
    p = parse("op: lookup ; cells: r0c4 ; answer: 60", "t_m")
    assert resolve(q, t, p).answer == "60"                       # default: unchanged
    r = resolve(q, t, p, column_check=True)
    assert r.answer == "24" and [c.cid for c in r.cells] == ["r0c2"]
    assert any(c.name == "column_repaired" and not c.passed for c in r.verdict.checks)
    # the cited column is the named one: nothing to repair
    ok = resolve("러시아의 합계는 몇 개입니까?", t, p, column_check=True)
    assert ok.answer == "60" and not any(c.name == "column_repaired" for c in ok.verdict.checks)
