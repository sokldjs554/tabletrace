"""The service can switch the verifier's evidence repair off (TABLETRACE_EVIDENCE_REPAIR=0)."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tabletrace.agent.graph import AgentRuntime
from tabletrace.corpus.store import CorpusStore
from tabletrace.retrieval.index import CorpusIndex
from tabletrace.service.app import create_app
from tabletrace.service.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from make_recorded_runs import StoredOutputPlanner  # noqa: E402


def test_setting_defaults_to_repair_and_reads_the_environment(monkeypatch):
    assert Settings().evidence_repair is True
    monkeypatch.setenv("TABLETRACE_EVIDENCE_REPAIR", "0")
    assert Settings().evidence_repair is False


@pytest.mark.parametrize("flag", [True, False])
def test_release_reports_the_setting(flag):
    with TestClient(create_app(Settings(planner="heuristic", evidence_repair=flag))) as client:
        assert client.get("/v1/release").json()["evidence_repair"] is flag


def test_runtime_withholds_the_model_proposal_when_repair_is_off():
    """A stored EXAONE output that cites a cell without the answer: repaired by default, withheld when repair is off."""
    index = json.loads((ROOT / "console/data/recorded/index.json").read_text(encoding="utf-8"))
    examples = {e["id"]: e for e in json.loads((ROOT / "console/data/examples.json").read_text(encoding="utf-8"))["examples"]}
    stored = index["planners"]["ref7"]                 # the untuned 7.8B model: it often cites a neighbouring cell
    run = next(r for r in stored["runs"] if any(c["name"] == "evidence_repaired" for c in r["result"]["verdict"]["checks"]))
    ex = examples[run["id"]]
    store = CorpusStore.from_disk()
    indexes = {"ko_tables": CorpusIndex(store.corpora["ko_tables"], "ko")}
    planner = StoredOutputPlanner([ROOT / d for d in stored["source"]["eval_dirs"].values()], "stored")
    args = dict(doc_id=ex["doc_id"], table_id=ex["table_id"], planner_mode="neural")

    on = AgentRuntime(indexes, planner).run(run["question"], "ko_tables", **args)
    assert on.status == "answered" and any(c.name == "evidence_repaired" for c in on.verdict.checks)

    off = AgentRuntime(indexes, planner, evidence_repair=False).run(run["question"], "ko_tables", **args)
    first = next(s for s in off.trace if s.step == "verify")
    assert first.output["status"] == "abstained" and first.output["reason"] == "verification_failed"
    assert not any(c["name"] == "evidence_repaired" for c in first.output["checks"])
    assert not any(c.name == "evidence_repaired" for c in off.verdict.checks)
    # the graph then asks the fallback planner once, as it does for any proposal that fails verification
    assert any(s.step == "propose" and s.input.get("fallback") for s in off.trace)
