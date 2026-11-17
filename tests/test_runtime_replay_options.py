"""Two options of the agent runtime that let a stored evaluation be replayed exactly as it was evaluated:
`fallback=False` (no second proposal from the heuristic planner) and `given` (the caller fixes the table rows and the
passage text the planner and the verifier see). The demo's stored runs are recorded with both."""
from tabletrace.agent.graph import AgentRuntime
from tabletrace.agent.program import parse
from tabletrace.corpus.store import CorpusStore
from tabletrace.retrieval.index import CorpusIndex
from tabletrace.schema import Table


class FixedPlanner:
    """Answers every question with one raw output (stands in for a served model)."""

    model_id = "fixed"

    def __init__(self, raw: str) -> None:
        self.raw = raw

    def plan(self, question, table, context=None):
        return parse(self.raw, table.id), self.raw, None, 1.0


STORE = CorpusStore.from_disk()
INDEXES = {"ko_tables": CorpusIndex(STORE.corpora["ko_tables"], "ko")}
TABLE = STORE.table("ko_29fbd6328d")           # 2018 box office: 10 rows; r6 is 안시성, 5,436,789 viewers in column 4
QUESTION = "2018년 박스오피스에서 안시성의 관객수는 몇 명입니까?"
ARGS = dict(doc_id=TABLE.doc_id, table_id=TABLE.id, planner_mode="neural")


def test_without_fallback_a_failed_proposal_is_the_final_answer():
    wrong = FixedPlanner("op: lookup ; cells: r6c4 ; answer: 1")           # the cell does not hold "1", and no other cell does
    with_fallback = AgentRuntime(INDEXES, wrong).run(QUESTION, "ko_tables", **ARGS)
    assert any(s.step == "propose" and s.input.get("fallback") for s in with_fallback.trace)
    alone = AgentRuntime(INDEXES, wrong, fallback=False).run(QUESTION, "ko_tables", **ARGS)
    assert alone.status == "abstained" and alone.verdict.reason == "verification_failed"
    assert [s.step for s in alone.trace].count("propose") == 1 and not any(s.input.get("fallback") for s in alone.trace if s.step == "propose")


def test_given_rows_are_the_rows_the_verifier_checks_against():
    right = FixedPlanner("op: lookup ; cells: r6c4 ; answer: 5,436,789")
    rt = AgentRuntime(INDEXES, right, entity_check=False, fallback=False)
    whole = rt.run(QUESTION, "ko_tables", **ARGS)
    assert whole.status == "answered" and whole.answer == "5,436,789"
    first_five = Table(**{**TABLE.model_dump(), "rows": TABLE.rows[:5]})    # the planner was shown rows r0..r4 only
    cut = rt.run(QUESTION, "ko_tables", **ARGS, given={"table": first_five, "context": None, "context_id": None})
    assert cut.status == "abstained" and cut.table_id == TABLE.id
    assert any(c.name == "cells_in_range" and not c.passed for c in cut.verdict.checks)


def test_given_passage_is_the_passage_a_text_answer_is_checked_in():
    planner = FixedPlanner("op: text ; cells: - ; answer: 삼지 않는다")
    rt = AgentRuntime(INDEXES, planner, entity_check=False, fallback=False)
    doc = STORE.doc(TABLE.doc_id)
    passage = doc.passages[0]
    assert "삼지 않는다" in passage.text
    full = rt.run(QUESTION, "ko_tables", **ARGS, given={"table": TABLE, "context": passage.text, "context_id": passage.id})
    assert full.status == "answered" and full.evidence_spans and full.evidence_spans[0].passage_id == passage.id
    cut_text = passage.text[: passage.text.index("삼지 않는다")]
    cut = rt.run(QUESTION, "ko_tables", **ARGS, given={"table": TABLE, "context": cut_text, "context_id": passage.id})
    assert cut.status == "abstained"
