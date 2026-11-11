"""The CPU engine server speaks the same two endpoints as vLLM / SGLang (scripts/serving/hf_cpu_server.py)."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("peft")            # test_lora_sft_smoke builds the tiny model and needs it at import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "serving"))


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from fastapi.testclient import TestClient
    from hf_cpu_server import build_app

    from test_lora_sft_smoke import _tiny_model

    return TestClient(build_app(str(_tiny_model(tmp_path_factory.mktemp("tiny"))), served_name="planner", threads=1))


def test_models_and_a_completion(client):
    assert client.get("/v1/models").json()["data"][0]["id"] == "planner"
    r = client.post("/v1/chat/completions", json={"model": "planner", "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "question: x"}], "max_tokens": 5})
    body = r.json()
    assert r.status_code == 200 and isinstance(body["choices"][0]["message"]["content"], str)
    assert 0 <= body["usage"]["completion_tokens"] <= 5 and body["usage"]["prompt_tokens"] > 0
    assert "logprobs" not in body["choices"][0]


def test_logprobs_cover_every_generated_token(client):
    body = client.post("/v1/chat/completions", json={"model": "planner", "messages": [{"role": "user", "content": "question: x"}], "max_tokens": 6, "logprobs": True}).json()
    lps = body["choices"][0]["logprobs"]["content"]
    assert len(lps) == body["usage"]["completion_tokens"] and all(x["logprob"] <= 0 for x in lps)


def test_tool_call_arguments_sent_as_json_strings_are_accepted(client):
    msgs = [{"role": "user", "content": "q"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "row_read", "arguments": '{"row": 2}'}}]},
            {"role": "tool", "tool_call_id": "c1", "name": "row_read", "content": '{"row": 2}'}]
    r = client.post("/v1/chat/completions", json={"model": "planner", "messages": msgs, "max_tokens": 3,
                                                  "tools": [{"type": "function", "function": {"name": "row_read", "parameters": {"type": "object", "properties": {}}}}]})
    assert r.status_code == 200
    assert client.get("/stats").json()["requests"] >= 1
