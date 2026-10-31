"""EnginePlanner against a mock OpenAI-compatible server (what vLLM / SGLang expose)."""
import threading

import pytest
import uvicorn
from fastapi import FastAPI

from tabletrace.service.engines import SYSTEM_PROMPT, EnginePlanner


@pytest.fixture(scope="module")
def mock_engine():
    app = FastAPI()
    seen = {}

    @app.get("/v1/models")
    def models():
        return {"data": [{"id": "planner"}]}

    @app.post("/v1/chat/completions")
    def chat(body: dict):
        seen["body"] = body
        user = body["messages"][-1]["content"]
        # a deterministic "model": answer the ammonia question, abstain otherwise
        content = "op: lookup ; cells: r4c2 ; answer: 11,300" if "ammonia" in user else "op: abstain ; cells: - ; answer: - ; reason: not_in_document"
        return {"id": "x", "object": "chat.completion", "model": body["model"], "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]}

    config = uvicorn.Config(app, host="127.0.0.1", port=8765, log_level="error")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    import time
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    yield seen
    server.should_exit = True
    t.join(timeout=3)


def test_engine_planner_roundtrip(mock_engine, chem_table):
    p = EnginePlanner("http://127.0.0.1:8765", "planner")
    assert p.health()["data"][0]["id"] == "planner"
    prog, _raw, rows, _ms = p.plan("What is the critical pressure of ammonia?", chem_table)
    assert prog is not None and prog.op == "lookup" and prog.cells[0].cid == "r4c2" and rows == 3
    body = mock_engine["body"]
    assert body["messages"][0]["content"] == SYSTEM_PROMPT and body["temperature"] == 0.0 and "question:" in body["messages"][1]["content"]
    prog, _raw, _, _ = p.plan("What is the density of argon?", chem_table)
    assert prog is not None and prog.op == "abstain"


def test_service_uses_the_engine_when_engine_url_is_set(mock_engine):
    """TABLETRACE_ENGINE_URL replaces the in-process model: the agent's propose step calls the OpenAI-compatible server."""
    from tabletrace.service.app import build_runtime
    from tabletrace.service.settings import Settings

    _store, rt = build_runtime(Settings(engine_url="http://127.0.0.1:8765", engine_model="planner", planner="auto"))
    assert isinstance(rt.neural, EnginePlanner) and rt.neural.model_id == "engine:planner"


def test_eval_runner_with_engine_planner(mock_engine, tmp_path):
    """eval.run --planner engine: same verifier and metrics as the other planners, planner output from the HTTP server."""
    import json
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "eng"
    subprocess.run([sys.executable, "-m", "tabletrace.eval.run", "--planner", "engine", "--engine-url", "http://127.0.0.1:8765", "--engine-model", "planner",
                    "--tokenizer", "approx", "--corpus", str(root / "data/chem/documents.jsonl"), "--data", str(root / "data/chem/custom_eval.jsonl"),
                    "--limit", "6", "--concurrency", "2", "--out", str(out)], check=True, cwd=root, capture_output=True)
    m = json.loads((out / "metrics.json").read_text())
    assert m["meta"]["planner"] == "engine" and m["meta"]["model"] == "engine:planner" and m["metrics"]["n"] == 6
    rows = [json.loads(line) for line in (out / "predictions.jsonl").read_text().splitlines()]
    assert all(r["raw_output"].startswith("op:") for r in rows)


def test_approx_tokenizer_budget():
    from tabletrace.model.approx_tokenizer import load_tokenizer

    tok = load_tokenizer("approx")
    assert len(tok("가" * 160).input_ids) == 100 and load_tokenizer(None) is not None
