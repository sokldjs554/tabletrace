"""Model-dependent checks; skipped when no fine-tuned model directory is present (CI has none)."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODEL = next((p for p in [ROOT / "models/mt5-small-tabletrace", ROOT / "experiments/sft_ko/model"] if (p / "model.safetensors").exists()), None)
pytestmark = pytest.mark.skipif(MODEL is None, reason="no fine-tuned model available")


@pytest.mark.model
def test_neural_planner_emits_parsable_program(chem_table):
    from tabletrace.model.planner import NeuralPlanner

    p = NeuralPlanner(MODEL, threads=2)
    prog, raw, rows, ms = p.plan("What is the critical pressure of water?", chem_table)
    assert rows == 3 and ms > 0
    assert raw.startswith("op:"), raw
    assert prog is None or prog.op in ("lookup", "text", "diff", "ratio", "sum", "avg", "count", "pct_change", "abstain")


@pytest.mark.model
def test_graph_with_neural_planner_answers_korean_lookup():
    from tabletrace.agent.graph import AgentRuntime
    from tabletrace.corpus.store import CorpusStore
    from tabletrace.model.planner import NeuralPlanner
    from tabletrace.retrieval.index import CorpusIndex

    store = CorpusStore.from_disk()
    idx = {"ko_tables": CorpusIndex(store.corpora["ko_tables"], "ko")}
    rt = AgentRuntime(idx, NeuralPlanner(MODEL, threads=2))
    res = rt.run("2018년 박스오피스에서 안시성의 관객수는 몇 명입니까?", "ko_tables", table_id="ko_29fbd6328d", planner_mode="neural")
    assert res.planner.mode == "neural"
    assert res.status in ("answered", "abstained")
    if res.status == "answered":
        assert res.evidence_cells, "an answer must carry evidence cells"
