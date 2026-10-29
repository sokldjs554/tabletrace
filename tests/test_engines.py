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
