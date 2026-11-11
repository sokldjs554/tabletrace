"""Row selection for tables that do not fit the model input (model/serialize.py): `first` must stay as it was,
`overlap` shows the rows the question talks about and keeps their original ids."""
import pytest

from tabletrace.agent.program import parse
from tabletrace.model import serialize
from tabletrace.model.approx_tokenizer import ApproxTokenizer
from tabletrace.schema import Document, Table
from tabletrace.training.data import build_examples
from tabletrace.verify.verifier import resolve

COUNTRIES = ["중국", "미국", "러시아", "영국", "독일", "오스트레일리아", "대한민국", "일본", "이탈리아", "프랑스", "우크라이나", "네덜란드"]


@pytest.fixture(autouse=True)
def _restore():
    before = serialize.get_row_select()
    yield
    serialize.set_row_select(before)


@pytest.fixture
def long_table() -> Table:
    return Table(id="t_long", doc_id="d_long", title="2008년 하계 올림픽 메달 집계", header=["순위", "국가", "금", "합계"],
                 rows=[[str(i + 1), name, str(50 - 3 * i), str(100 - 5 * i)] for i, name in enumerate(COUNTRIES)], lang="ko")


def budget_for(tok, question, table, rows) -> int:
    return len(tok(serialize.build_input(question, table, None, rows=rows)).input_ids)


def test_default_is_first_and_gives_the_same_prefix_as_before(long_table):
    tok = ApproxTokenizer()
    q = "프랑스의 합계는 몇 개입니까?"
    assert serialize.get_row_select() == "first"
    limit = budget_for(tok, q, long_table, [0, 1, 2, 3])
    ctx, n = serialize.choose_context_and_rows(tok, q, long_table, None, limit)
    assert serialize.choose_rows(tok, q, long_table, None, limit) == (ctx, list(range(n))) and n == 4
    assert serialize.build_input(q, long_table, None, max_rows=n) == serialize.build_input(q, long_table, None, rows=list(range(n)))


def test_overlap_keeps_the_row_the_question_names_with_its_original_id(long_table):
    tok = ApproxTokenizer()
    q = "프랑스의 합계는 몇 개입니까?"
    scores = serialize.row_scores(q, long_table)
    assert max(range(len(scores)), key=scores.__getitem__) == 9          # 프랑스 is row 9
    limit = budget_for(tok, q, long_table, [0, 1, 2, 3])
    _ctx, rows = serialize.choose_rows(tok, q, long_table, None, limit, strategy="overlap")
    assert 9 in rows and rows == sorted(rows) and len(rows) >= 3 and budget_for(tok, q, long_table, rows) <= limit
    text = serialize.build_input(q, long_table, None, rows=rows)
    assert "r9: 10 | 프랑스 | 23 | 55" in text and "r11:" not in text    # the label is the real row index
    # a question that names no row falls back to table order
    _ctx, plain = serialize.choose_rows(tok, "합계가 가장 큰 곳은?", long_table, None, limit, strategy="overlap")
    assert plain == [0, 1, 2, 3]


def test_whole_table_is_shown_when_it_fits(long_table):
    _ctx, rows = serialize.choose_rows(ApproxTokenizer(), "프랑스의 합계는?", long_table, None, 10_000, strategy="overlap")
    assert rows == list(range(12))


def test_hidden_rows_cannot_be_cited(long_table):
    shown = serialize.masked(long_table, [0, 9])
    assert shown.n_rows == 12 and shown.rows[9] == long_table.rows[9] and shown.rows[5] == ["", "", "", ""]
    ok = resolve("프랑스의 합계는?", shown, parse("op: lookup ; cells: r9c3 ; answer: 55", "t_long"), entity_check=False)
    assert ok.status == "answered" and [c.cid for c in ok.cells] == ["r9c3"]
    hidden = resolve("독일의 합계는?", shown, parse("op: lookup ; cells: r4c3 ; answer: 80", "t_long"), entity_check=False)
    assert hidden.status == "abstained"                                   # row 4 was not shown, and repair cannot find 80 either
    assert long_table.rows[5][1] == "오스트레일리아"                        # the original table is untouched


def test_examples_carry_the_selected_rows(long_table):
    tok = ApproxTokenizer()
    q = "프랑스의 합계는 몇 개입니까?"
    doc = Document(id="d_long", corpus="ko_tables", lang="ko", title=long_table.title, passages=[], tables=[long_table],
                   source={"name": "test", "url": "", "license": ""})
    rec = {"qid": "q1", "question": q, "answer": "55", "doc_id": "d_long", "table_id": "t_long", "op": "lookup", "gold_cells": [[9, 3]]}
    limit = budget_for(tok, q, long_table, [0, 1, 2, 3])
    first = build_examples([rec], {"d_long": doc}, tok, limit)[0]
    assert first.truncated_gold and first.shown_rows is None and first.table.n_rows == 4
    serialize.set_row_select("overlap")
    sel = build_examples([rec], {"d_long": doc}, tok, limit)[0]
    assert not sel.truncated_gold and 9 in sel.shown_rows and sel.rows_kept == len(sel.shown_rows)
    assert "r9: 10 | 프랑스" in sel.input_text and sel.table.n_rows == 12 and sel.table.rows[9][1] == "프랑스"
    assert sel.table.rows[next(i for i in range(12) if i not in sel.shown_rows)] == ["", "", "", ""]
    # a table that fits is the same example under both settings
    roomy = build_examples([rec], {"d_long": doc}, tok, 10_000)[0]
    assert roomy.shown_rows is None and roomy.table.n_rows == 12 and not roomy.truncated_gold
    with pytest.raises(ValueError):
        serialize.set_row_select("random")
