"""Training-data construction (row budget / gold truncation) and the RL reward, without a model."""
from pathlib import Path

import pytest

pytest.importorskip("torch")          # CI installs only the lightweight extras; these tests need the model extra
pytest.importorskip("transformers")

from tabletrace.agent.program import serialize
from tabletrace.schema import Document, Source
from tabletrace.training.data import build_examples
from tabletrace.training.rl_grpo import reward

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def tok():
    from transformers import PreTrainedTokenizerFast

    p = ROOT / "models" / "mt5-small-base"
    if not (p / "tokenizer.json").exists():
        pytest.skip("converted mT5 tokenizer not available")
    return PreTrainedTokenizerFast.from_pretrained(p)


def _doc(table):
    return Document(id=table.doc_id, corpus="ko_tables", lang="ko", title="t", tables=[table], source=Source(name="x", license="y"))


def test_build_examples_targets_and_row_budget(tok, medal_table):
    docs = {medal_table.doc_id: _doc(medal_table)}
    recs = [{"qid": "a", "question": "러시아의 합계는?", "answer": "60", "doc_id": medal_table.doc_id, "table_id": medal_table.id, "op": "lookup", "gold_cells": [[2, 5]], "source": "t"},
            {"qid": "b", "question": "없는 질문", "answer": None, "doc_id": medal_table.doc_id, "table_id": medal_table.id, "op": "abstain", "reason": "not_in_document", "gold_cells": [], "source": "t"}]
    exs = build_examples(recs, docs, tok, max_in=512)
    assert exs[0].target_text == "op: lookup ; cells: r2c5 ; answer: 60"
    assert exs[1].target_text == "op: abstain ; cells: - ; answer: - ; reason: not_in_document"
    assert exs[0].input_text.startswith("question: 러시아의 합계는? title:") and "r2: 3 | 러시아 | 24 | 13 | 23 | 60" in exs[0].input_text
    assert exs[0].rows_kept == 4 and not exs[0].truncated_gold
    # a tiny budget forces rows to be dropped; the gold row (r2) is then marked truncated and can be excluded
    tight = build_examples(recs[:1], docs, tok, max_in=60)
    assert tight[0].rows_kept < 3 and tight[0].truncated_gold
    assert build_examples(recs[:1], docs, tok, max_in=60, drop_truncated_gold=True) == []


def test_reward_shapes_behaviour(tok, medal_table):
    docs = {medal_table.doc_id: _doc(medal_table)}
    recs = [{"qid": "a", "question": "러시아의 합계는?", "answer": "60", "doc_id": medal_table.doc_id, "table_id": medal_table.id, "op": "lookup", "gold_cells": [[2, 5]], "source": "t"},
            {"qid": "b", "question": "일본의 합계는?", "answer": None, "doc_id": medal_table.doc_id, "table_id": medal_table.id, "op": "abstain", "reason": "not_in_document", "gold_cells": [], "source": "t"},
            {"qid": "c", "question": "미국과 러시아의 합계 차이는?", "answer": "52", "doc_id": medal_table.doc_id, "table_id": medal_table.id, "op": "diff", "gold_cells": [[1, 5], [2, 5]], "source": "t"}]
    ex_lookup, ex_abstain, ex_calc = build_examples(recs, docs, tok, 512)
    r_gold, _ = reward(serialize(ex_lookup.gold), ex_lookup)
    r_wrong_cell, _ = reward("op: lookup ; cells: r1c5 ; answer: 112", ex_lookup)
    r_unsupported, _ = reward("op: lookup ; cells: r2c5 ; answer: 61", ex_lookup)
    r_abstain, _ = reward("op: abstain ; cells: - ; answer: - ; reason: not_in_document", ex_lookup)
    r_garbage, _ = reward("hello", ex_lookup)
    # the reward runs the verifier WITH the subject check (RL v3): a citation of another country's row is rejected like an
    # unsupported proposal, so it ranks below an explicit abstention on an answerable prompt
    assert r_gold > r_abstain > r_wrong_cell >= r_unsupported > r_garbage
    assert reward("op: abstain ; cells: - ; answer: - ; reason: not_in_document", ex_abstain)[0] == 1.0
    # answering about a country that is not in the table: the subject check blocks it (0.0), it never pays
    assert reward("op: lookup ; cells: r0c1 ; answer: 중국", ex_abstain)[0] <= 0.0
    r_calc_gold, _ = reward(serialize(ex_calc.gold), ex_calc)
    r_calc_wrong_num, _ = reward("op: diff ; cells: r1c5, r2c5 ; answer: 50", ex_calc)   # verifier recomputes -> still correct answer
    assert r_calc_gold >= r_calc_wrong_num > 0


def test_reward_does_not_pay_for_garbage_abstention(tok, medal_table):
    """v1 paid +1.0 for any final 'abstained' on a no-answer prompt, including rejected garbage programs."""
    docs = {medal_table.doc_id: _doc(medal_table)}
    rec = {"qid": "b", "question": "일본의 합계는?", "answer": None, "doc_id": medal_table.doc_id, "table_id": medal_table.id, "op": "abstain",
           "reason": "not_in_document", "gold_cells": [], "source": "t"}
    (ex,) = build_examples([rec], docs, tok, 512)
    explicit, info = reward("op: abstain ; cells: - ; answer: - ; reason: not_in_document", ex)
    degenerate, info_d = reward("op: diff ; cells: r1c5, r1c5 ; answer: 0", ex)       # repeated cells -> invalid_program -> abstained
    caught, _ = reward("op: lookup ; cells: r1c5 ; answer: 999", ex)                    # unsupported value -> verification_failed
    halluc, _ = reward("op: lookup ; cells: r1c5 ; answer: 112", ex)                    # answers although it must abstain
    assert explicit == 1.0 and info["explicit_abstain"] is True
    assert info_d["abstained"] is True and info_d["explicit_abstain"] is False and degenerate == 0.0
    assert explicit > caught > degenerate >= halluc
    # the subject check ("일본" is not in the cited row or anywhere in the table) turns the hallucination into an
    # abstention with reason not_in_document: no credit (0.0) instead of the -0.8 it earned before the check existed
    assert halluc == 0.0
