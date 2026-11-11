"""Second opinion in the agent graph: a verified lookup is withheld when an independent reader points elsewhere."""
import pytest

from tabletrace.agent.graph import AgentRuntime
from tabletrace.corpus.store import CorpusStore
from tabletrace.retrieval.index import CorpusIndex


class FixedOpinion:
    """Stands in for encoder.second_opinion.SecondOpinion: always points at one row."""
    mode, model_id = "row", "stub"

    def __init__(self, row: int) -> None:
        self.row = row
        self.calls = 0

    def agrees(self, question, table, evidence):
        self.calls += 1
        same = evidence.row == self.row
        return same, ("같은 행" if same else "다른 행"), {"encoder_cell": f"r{self.row}c0", "evidence_cell": evidence.cid, "opinion": "agree" if same else "disagree"}


@pytest.fixture(scope="module")
def backend():
    store = CorpusStore.from_disk()
    return store, {"ko_tables": CorpusIndex(store.corpora["ko_tables"], "ko")}


Q, TABLE = "국도 1호 자동차 전용도로 구간 중 호남로의 총연장은 몇 km입니까?", "ko_8bcc6a21a4"       # the heuristic answers 22.8 from r3c3


def test_without_a_second_opinion_nothing_changes(backend):
    _store, indexes = backend
    res = AgentRuntime(indexes).run(Q, "ko_tables", table_id=TABLE, planner_mode="heuristic")
    assert res.status == "answered" and res.answer == "22.8" and [c.cid for c in res.evidence_cells] == ["r3c3"]
    assert all(c.name != "second_opinion" for c in res.verdict.checks)


def test_agreement_is_recorded_as_a_passed_check(backend):
    _store, indexes = backend
    opinion = FixedOpinion(row=3)
    res = AgentRuntime(indexes, second_opinion=opinion).run(Q, "ko_tables", table_id=TABLE, planner_mode="heuristic")
    assert res.status == "answered" and res.answer == "22.8" and opinion.calls == 1
    check = next(c for c in res.verdict.checks if c.name == "second_opinion")
    assert check.passed and any(s.tool == "second_opinion" and s.output["opinion"] == "agree" for s in res.trace)


def test_disagreement_withholds_the_answer(backend):
    _store, indexes = backend
    res = AgentRuntime(indexes, second_opinion=FixedOpinion(row=0)).run(Q, "ko_tables", table_id=TABLE, planner_mode="heuristic")
    assert res.status == "abstained" and res.answer is None and res.evidence_cells == []
    assert res.verdict.reason == "verification_failed"
    check = next(c for c in res.verdict.checks if c.name == "second_opinion")
    assert not check.passed and any(c.name == "answer_matches_cell" for c in res.verdict.checks)      # the verifier's own checks stay visible


def test_only_lookups_are_second_guessed(backend):
    _store, indexes = backend
    opinion = FixedOpinion(row=0)
    rt = AgentRuntime(indexes, second_opinion=opinion)
    res = rt.run("빛가람장성로는 목포대교보다 총연장이 몇 km 더 깁니까?", "ko_tables", table_id=TABLE, planner_mode="heuristic")
    assert res.program.op == "diff" and res.status == "answered" and res.answer == "15.68 km"       # a calculation: the encoder is not asked
    assert opinion.calls == 0 and all(s.tool != "second_opinion" for s in res.trace)


def test_real_encoder_gives_an_opinion(tmp_path, medal_table):
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    tokenizers = pytest.importorskip("tokenizers")
    from tabletrace.encoder.model import TableEncoder
    from tabletrace.encoder.second_opinion import SecondOpinion
    from tabletrace.schema import CellRef

    tk = tokenizers.Tokenizer(tokenizers.models.WordLevel({"<pad>": 0, "</s>": 1, "<unk>": 2, "|": 3}, unk_token="<unk>"))
    tk.pre_tokenizer = tokenizers.pre_tokenizers.Whitespace()
    tok = transformers.PreTrainedTokenizerFast(tokenizer_object=tk, pad_token="<pad>", eos_token="</s>", unk_token="<unk>")
    backbone = tmp_path / "backbone"
    tok.save_pretrained(backbone)
    torch.manual_seed(0)
    transformers.T5EncoderModel(transformers.T5Config(vocab_size=8, d_model=16, d_kv=4, d_ff=32, num_layers=1, num_heads=2)).save_pretrained(backbone)
    from tabletrace.encoder.model import load_backbone

    TableEncoder(load_backbone(backbone)).save(tmp_path / "enc" / "model", {"backbone": str(backbone), "name": "tiny"})
    second = SecondOpinion(tmp_path / "enc" / "model", mode="cell")
    row, col, _margin, rows_read = second.top_cell("러시아의 합계는?", medal_table)
    assert 0 <= row < 4 and 0 <= col < 6 and rows_read == 4 and second.model_id == "table-encoder:tiny"
    agree, detail, info = second.agrees("러시아의 합계는?", medal_table, CellRef(table_id="t_medal", row=row, col=col))
    assert agree and info["opinion"] == "agree" and "같은 셀" in detail
    agree, _detail, info = second.agrees("러시아의 합계는?", medal_table, CellRef(table_id="t_medal", row=(row + 1) % 4, col=col))
    assert not agree and info["opinion"] == "disagree"
    with pytest.raises(ValueError):
        SecondOpinion(tmp_path / "enc" / "model", mode="column")
