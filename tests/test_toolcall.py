"""Tool-calling planner against a scripted OpenAI-compatible server: the model picks the tools, the registry validates
the arguments, and the submitted program goes through the usual verifier."""
import json
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI

from tabletrace.agent.toolcall import TOOLS, ToolCallingPlanner, tool_calls_of
from tabletrace.verify.verifier import resolve

PORT = 8767


def call(name, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"id": f"c_{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}


SCRIPTS = {
    # find the row, read it, submit the cell
    "lookup": [call("cell_find", text="러시아"), call("row_read", row=2), call("submit", op="lookup", cells=["r2c5"], answer="60")],
    # a bad argument and an unknown tool are reported back; the model recovers
    "recover": [call("row_read", row=99), call("delete_table"), call("column_read", col=1), call("submit", op="lookup", cells=["r1c5"], answer="112")],
    "calc": [call("calculate", op="diff", cells=["r1c5", "r0c5"]), call("submit", op="diff", cells=["r1c5", "r0c5"], answer="12")],
    "abstain": [call("cell_find", text="대한민국"), call("abstain", reason="not_in_document")],
    "loop": [call("row_read", row=0)] * 20,
    "text": [{"role": "assistant", "content": "op: lookup ; cells: r2c5 ; answer: 60"}],
    "chatter": [{"role": "assistant", "content": "합계는 60개입니다."}],
    "text_blocks": [{"role": "assistant", "content": '<tool_call>{"name": "row_read", "arguments": {"row": 2}}</tool_call>'},
                    {"role": "assistant", "content": '<tool_call>\n{"name": "submit", "arguments": {"op": "lookup", "cells": ["r2c5"], "answer": "60"}}\n</tool_call>'}],
    "wrong": [call("submit", op="lookup", cells=["r2c1"], answer="61")],
}


@pytest.fixture(scope="module")
def engine():
    app = FastAPI()
    seen: dict = {"requests": []}

    @app.get("/v1/models")
    def models():
        return {"data": [{"id": "planner"}]}

    @app.post("/v1/chat/completions")
    def chat(body: dict):
        seen["requests"].append(body)
        script = SCRIPTS[body["messages"][1]["content"].split("question: ")[1].split("\n")[0]]
        turn = sum(m["role"] == "assistant" for m in body["messages"])
        return {"choices": [{"index": 0, "message": script[min(turn, len(script) - 1)], "finish_reason": "tool_calls"}]}

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    yield seen
    server.should_exit = True
    t.join(timeout=3)


@pytest.fixture
def planner():
    return ToolCallingPlanner(f"http://127.0.0.1:{PORT}", "planner", max_steps=6)


def test_model_reads_the_table_through_tools_and_submits(engine, planner, medal_table):
    prog, raw, _rows, _ms, steps, info = planner.plan_traced("lookup", medal_table)
    assert raw == "op: lookup ; cells: r2c5 ; answer: 60" and prog.op == "lookup" and prog.cells[0].cid == "r2c5"
    assert [s.tool for s in steps] == ["cell_find", "row_read"] and info == {"model_calls": 3, "tool_calls": 3, "tool_errors": 0, "finished_by": "submit"}
    first = engine["requests"][-3]
    assert first["tools"] == TOOLS and "r0c0" not in first["messages"][1]["content"]          # the table body is not in the prompt
    assert "columns: c0 순위 | c1 국가" in first["messages"][1]["content"] and "rows: 4" in first["messages"][1]["content"]
    last = engine["requests"][-1]["messages"]
    assert [m["role"] for m in last] == ["system", "user", "assistant", "tool", "assistant", "tool"]
    assert json.loads(last[-1]["content"])["cells"]["r2c5"] == "60"                            # what row_read returned to the model
    res = resolve("러시아가 획득한 메달은 몇 개입니까?", medal_table, prog, entity_check=False)
    assert res.status == "answered" and res.answer == "60"


def test_invalid_calls_are_reported_to_the_model_not_executed(engine, planner, medal_table):
    prog, _raw, _rows, _ms, steps, info = planner.plan_traced("recover", medal_table)
    assert prog.cells[0].cid == "r1c5" and info["tool_errors"] == 2 and info["finished_by"] == "submit"
    assert [(s.tool, s.status) for s in steps] == [("row_read", "error"), ("delete_table", "error"), ("column_read", "ok")]
    msgs = engine["requests"][-1]["messages"]
    assert "error" in json.loads(msgs[3]["content"]) and "unknown tool" in json.loads(msgs[5]["content"])["error"]


def test_calculation_abstention_and_step_limit(engine, planner, medal_table):
    prog, raw, *_ = planner.plan_traced("calc", medal_table)
    assert prog.op == "diff" and [c.cid for c in prog.cells] == ["r1c5", "r0c5"]
    assert resolve("미국과 중국의 합계 차이는?", medal_table, prog, entity_check=False).answer == "12"
    prog, raw, *_ = planner.plan_traced("abstain", medal_table)
    assert prog.op == "abstain" and "not_in_document" in raw
    prog, raw, _rows, _ms, steps, info = planner.plan_traced("loop", medal_table)
    assert prog is None and info == {"model_calls": 6, "tool_calls": 6, "tool_errors": 0, "finished_by": "max_steps"} and len(steps) == 6


def test_plain_text_answers_and_text_tool_calls(engine, planner, medal_table):
    prog, _raw, _rows, _ms, _steps, info = planner.plan_traced("text", medal_table)
    assert prog.cells[0].cid == "r2c5" and info["finished_by"] == "text_program"
    prog, raw, _rows, _ms, _steps, info = planner.plan_traced("chatter", medal_table)
    assert prog is None and raw == "합계는 60개입니다." and info["finished_by"] == "no_tool_call"
    prog, _raw, _rows, _ms, steps, info = planner.plan_traced("text_blocks", medal_table)       # a server that does not parse tool calls
    assert prog.cells[0].cid == "r2c5" and [s.tool for s in steps] == ["row_read"] and info["finished_by"] == "submit"
    assert tool_calls_of({"content": "<tool_call>{not json}</tool_call>"}) == [("text_0", "", None)]


def test_a_wrong_submission_is_still_stopped_by_the_verifier(engine, planner, medal_table):
    prog, *_ = planner.plan("wrong", medal_table)
    res = resolve("러시아가 획득한 메달은 몇 개입니까?", medal_table, prog, entity_check=False)
    assert res.status == "abstained" and res.verdict.reason == "verification_failed"


def test_the_service_graph_shows_the_models_tool_calls_in_the_trace(engine):
    from tabletrace.service.app import build_runtime
    from tabletrace.service.settings import Settings

    store, rt = build_runtime(Settings(engine_url=f"http://127.0.0.1:{PORT}", engine_model="planner", engine_tools=True, planner="auto"))
    assert isinstance(rt.neural, ToolCallingPlanner)
    table = next(t for t in store.tables.values() if t.lang == "ko" and t.n_rows >= 3 and t.n_cols >= 6)
    res = rt.run("lookup", "ko_tables", table_id=table.id)
    tools = [s.tool for s in res.trace if s.step == "tool"]
    assert tools[:2] == ["cell_find", "row_read"]                                               # chosen by the model, executed by the registry
    assert any(s.step == "propose" and s.input.get("tool_calling", {}).get("finished_by") == "submit" for s in res.trace)
    assert res.status in ("answered", "abstained")                                              # the verifier has the last word on this unrelated table
