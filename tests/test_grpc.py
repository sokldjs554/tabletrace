"""gRPC API (service/grpc_server.py): same runtime as REST, typed replies, step streaming, limits."""
import json
import socket
import threading
import time
from pathlib import Path

import pytest

grpc = pytest.importorskip("grpc")

from fastapi.testclient import TestClient  # noqa: E402

from tabletrace.schema import AnswerResult  # noqa: E402
from tabletrace.service.app import build_runtime, create_app  # noqa: E402
from tabletrace.service.grpc_server import start_grpc_server  # noqa: E402
from tabletrace.service.pb import tabletrace_pb2 as pb  # noqa: E402
from tabletrace.service.pb import tabletrace_pb2_grpc as pb_grpc  # noqa: E402
from tabletrace.service.settings import Settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = {e["id"]: e for e in json.loads((ROOT / "console/data/examples.json").read_text(encoding="utf-8"))}


@pytest.fixture(scope="module")
def backend():
    settings = Settings(planner="heuristic", max_concurrent_jobs=2, queue_limit=4, job_timeout_s=20)
    store, runtime = build_runtime(settings)
    server, port = start_grpc_server(runtime, store, settings, 0, host="127.0.0.1", commit="test")
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    yield pb_grpc.TableTraceStub(channel), runtime, store
    channel.close()
    server.stop(grace=0)


def ask_request(ex_id: str, **over) -> pb.AskRequest:
    ex = EXAMPLES[ex_id]
    args = {"question": ex["question"], "corpus": ex["corpus"], "doc_id": ex["doc_id"], "table_id": ex.get("table_id") or "", **over}
    return pb.AskRequest(**args)


def test_release_reports_configuration(backend):
    stub, runtime, _ = backend
    r = stub.Release(pb.ReleaseRequest(), timeout=5)
    assert r.planner == "heuristic" and r.commit == "test" and r.version
    assert r.entity_check is runtime.entity_check and r.evidence_repair is True and r.table_format == "plain"


def test_ask_returns_the_same_answer_as_the_runtime(backend):
    stub, runtime, _ = backend
    ex = EXAMPLES["ko_custom_01"]
    direct = runtime.run(ex["question"], ex["corpus"], doc_id=ex["doc_id"], table_id=ex["table_id"])
    r = stub.Ask(ask_request("ko_custom_01"), timeout=20)
    assert (r.status, r.answer) == (direct.status, direct.answer) == ("answered", "5,436,789")
    assert [(c.row, c.col) for c in r.evidence_cells] == [(c.row, c.col) for c in direct.evidence_cells]
    assert [c.name for c in r.checks] == [c.name for c in direct.verdict.checks]
    full = json.loads(r.result_json)                       # the REST result travels along for clients that want all of it
    assert full["status"] == "answered" and full["trace"] and r.planner_mode == "heuristic"


def test_ask_stream_reports_each_step_then_the_result(backend):
    stub, _, _ = backend
    events = list(stub.AskStream(ask_request("ko_custom_03"), timeout=20))
    steps = [e.step for e in events if e.WhichOneof("event") == "step"]
    results = [e.result for e in events if e.WhichOneof("event") == "result"]
    assert events[-1].WhichOneof("event") == "result" and len(results) == 1
    assert [s.step for s in steps][:2] == ["retrieve", "propose"] and steps[-1].step == "verify"
    assert any(s.step == "tool" and s.tool == "calculate" for s in steps)
    assert {s.node for s in steps} >= {"retrieve", "propose", "verify"}
    assert json.loads(steps[0].detail_json)["input"]["query"] == EXAMPLES["ko_custom_03"]["question"]
    unary = stub.Ask(ask_request("ko_custom_03"), timeout=20)
    assert (results[0].status, results[0].answer) == (unary.status, unary.answer)
    assert len(steps) == len(json.loads(results[0].result_json)["trace"])     # nothing reported twice or dropped


@pytest.mark.parametrize("request_, code", [
    (pb.AskRequest(question="x", corpus="ko_tables"), "INVALID_ARGUMENT"),
    (pb.AskRequest(question="관객수는?", corpus="nope"), "INVALID_ARGUMENT"),
    (pb.AskRequest(question="관객수는?", corpus="ko_tables", planner="gpt"), "INVALID_ARGUMENT"),
    (pb.AskRequest(question="관객수는?", corpus="ko_tables", table_id="missing"), "NOT_FOUND"),
    (pb.AskRequest(question="관객수는?", corpus="ko_tables", planner="neural"), "FAILED_PRECONDITION"),
])
def test_bad_requests_get_typed_errors(backend, request_, code):
    stub, _, _ = backend
    with pytest.raises(grpc.RpcError) as err:
        stub.Ask(request_, timeout=5)
    assert err.value.code().name == code


def test_calculate_uses_the_bounded_calculator(backend):
    stub, _, _ = backend
    ex = EXAMPLES["ko_custom_03"]
    r = stub.Calculate(pb.CalculateRequest(table_id=ex["table_id"], op="diff", cells=["r0c4", "r1c4"]), timeout=5)
    assert r.op == "diff" and r.formatted.startswith("1,062,201") and r.result == pytest.approx(1062201)
    with pytest.raises(grpc.RpcError) as err:
        stub.Calculate(pb.CalculateRequest(table_id=ex["table_id"], op="eval", cells=["r0c4"]), timeout=5)
    assert err.value.code().name == "INVALID_ARGUMENT"
    with pytest.raises(grpc.RpcError) as err:
        stub.Calculate(pb.CalculateRequest(table_id=ex["table_id"], op="diff", cells=["r0c4", "__import__('os')"]), timeout=5)
    assert err.value.code().name == "INVALID_ARGUMENT"


class _SlowRuntime:
    """Stands in for the agent runtime: holds every question until released."""
    neural, entity_check, evidence_repair = None, True, True

    def __init__(self) -> None:
        self.gate = threading.Event()

    def run(self, question, corpus, **_):
        self.gate.wait(10)
        return AnswerResult(question=question, corpus=corpus, status="abstained")


def test_queue_limit_refuses_instead_of_piling_up(backend):
    _, _, store = backend
    slow = _SlowRuntime()
    settings = Settings(planner="heuristic", max_concurrent_jobs=1, queue_limit=0, job_timeout_s=10)
    server, port = start_grpc_server(slow, store, settings, 0, host="127.0.0.1")
    try:
        with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = pb_grpc.TableTraceStub(channel)
            first = stub.Ask.future(pb.AskRequest(question="첫 번째 질문", corpus="ko_tables"), timeout=10)
            time.sleep(0.3)                                    # let the first call take the only slot
            with pytest.raises(grpc.RpcError) as err:
                stub.Ask(pb.AskRequest(question="두 번째 질문", corpus="ko_tables"), timeout=5)
            assert err.value.code().name == "RESOURCE_EXHAUSTED"
            slow.gate.set()
            assert first.result().status == "abstained"
            assert stub.Ask(pb.AskRequest(question="세 번째 질문", corpus="ko_tables"), timeout=5).status == "abstained"   # slot is free again
    finally:
        server.stop(grace=0)


def test_rest_app_can_serve_grpc_on_the_same_runtime():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with TestClient(create_app(Settings(planner="heuristic", grpc_port=port))) as client:
        assert client.get("/v1/release").json()["grpc_port"] == port
        with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
            reply = pb_grpc.TableTraceStub(channel).Ask(ask_request("ko_custom_01"), timeout=20)
        rest = client.post("/v1/ask?wait=1", json={k: EXAMPLES["ko_custom_01"][k] for k in ("question", "corpus", "doc_id", "table_id")}).json()
        assert reply.answer == rest["result"]["answer"]
