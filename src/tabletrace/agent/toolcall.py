"""A planner in which the language model chooses the tools.

The graph in agent/graph.py runs a fixed sequence: one model call proposes a program, the verifier executes it. Here the
model does not see the table body. It gets the title, the column names and the number of rows, and works with tools:

    cell_find(text, exact)   which cells contain this text
    row_read(row)            all cells of a row
    column_read(col)         the cells of a column
    calculate(op, cells)     diff / sum / avg / ratio / pct_change over cell ids
    submit(op, cells, answer)   the final program
    abstain(reason)             the document does not answer the question

It decides which tool to call next, reads the result, and repeats until it calls `submit` or `abstain` (or runs out of
steps). Tool arguments are validated by the same registry as everywhere else, and the submitted program goes through
the same verifier, so nothing the model says is taken on trust. Because the table is read through tools, its size
does not have to fit the model input.

The server is any OpenAI-compatible chat endpoint. Tool calls are read from `message.tool_calls` when the server
parses them (vLLM: --enable-auto-tool-choice --tool-call-parser hermes) and otherwise from <tool_call>{...}</tool_call>
blocks in the text.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from tabletrace.agent.program import ProgramParseError, parse
from tabletrace.schema import Program, Table, TraceStep
from tabletrace.tools.registry import REGISTRY, ToolError

OPS = ["lookup", "text", "diff", "sum", "avg", "ratio", "pct_change"]
REASONS = ["not_in_document", "ambiguous_question", "unit_mismatch"]
SYSTEM = (
    "You answer a question about a table that you can only read through tools. Cell ids look like r3c2: data row 3 "
    "(from 0), column 2 (from 0). Find the cell or cells that hold the answer, then call `submit`.\n"
    "- The answer is the text of one cell: submit op \"lookup\" with that one cell and its text.\n"
    "- The answer needs arithmetic over cells: call `calculate` first, then submit the same op and cells with the result.\n"
    "- The table does not contain what is asked: call `abstain`.\n"
    "Always finish with `submit` or `abstain`. Do not answer in plain text."
)


def _fn(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": properties, "required": required}}}


TOOLS = [
    _fn("cell_find", "Find the cells whose text equals (exact=true) or contains (exact=false) the given text.",
        {"text": {"type": "string"}, "exact": {"type": "boolean"}}, ["text"]),
    _fn("row_read", "Read every cell of one data row.", {"row": {"type": "integer", "minimum": 0}}, ["row"]),
    _fn("column_read", "Read the cells of one column.", {"col": {"type": "integer", "minimum": 0}}, ["col"]),
    _fn("calculate", "Compute over cells. diff = first - second, ratio = first / second, pct_change = (first - second) / second * 100.",
        {"op": {"type": "string", "enum": ["diff", "sum", "avg", "ratio", "pct_change"]}, "cells": {"type": "array", "items": {"type": "string"}}}, ["op", "cells"]),
    _fn("submit", "Give the final answer with its evidence cells. op is \"lookup\" for the text of one cell; diff, sum, avg, ratio or pct_change only for a result of `calculate`.",
        {"op": {"type": "string", "enum": OPS}, "cells": {"type": "array", "items": {"type": "string"}}, "answer": {"type": "string"}}, ["op", "cells", "answer"]),
    _fn("abstain", "Decline: the table does not answer the question.", {"reason": {"type": "string", "enum": REASONS}}, []),
]
READ_TOOLS = {"cell_find", "row_read", "column_read", "calculate"}
_BLOCK = re.compile(r"<tool_call>\s*(\{.*?\})\s*(?:</tool_call>|\Z)", re.S)      # a model may end its turn without closing the last block


def tool_calls_of(message: dict) -> list[tuple[str, str, dict | None]]:
    """-> [(call id, tool name, arguments or None when they are not a JSON object)] from a chat completion message."""
    calls = []
    for i, c in enumerate(message.get("tool_calls") or []):
        fn = c.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = None
        calls.append((c.get("id") or f"call_{i}", fn.get("name") or "", args if isinstance(args, dict) else None))
    if not calls:                                        # the server did not parse tool calls: read them from the text
        for i, raw in enumerate(_BLOCK.findall(message.get("content") or "")):
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                calls.append((f"text_{i}", "", None))
                continue
            args = obj.get("arguments", obj.get("parameters"))
            calls.append((f"text_{i}", str(obj.get("name") or ""), args if isinstance(args, dict) else None))
    return calls


def _shown(out: Any) -> Any:
    if hasattr(out, "model_dump"):
        d = out.model_dump()
        return {k: d[k] for k in ("op", "result", "formatted", "unit", "expression") if k in d} or d
    if isinstance(out, list):
        return {"cells": [c.cid for c in out][:50], "count": len(out)}
    return out


class ToolCallingPlanner:
    """Same interface as the other planners (`plan` -> program, raw text, rows shown, ms), so the graph, the service
    and the evaluation runner use it unchanged. `plan_traced` also returns the tool calls as trace steps."""

    def __init__(self, base_url: str, model: str, api_key: str = "EMPTY", timeout_s: float = 60.0, max_steps: int = 8, max_tokens: int = 256) -> None:
        self.model = model
        self.model_id = f"engine:{model}+tools"
        self.quantized = False
        self.max_steps, self.max_tokens = max_steps, max_tokens
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s, headers={"Authorization": f"Bearer {api_key}"})

    def health(self) -> dict:
        r = self.client.get("/v1/models")
        r.raise_for_status()
        return r.json()

    @staticmethod
    def first_message(question: str, table: Table, context: str | None) -> str:
        cols = " | ".join(f"c{j} {h}" for j, h in enumerate(table.header))
        parts = [f"question: {question.strip()}", f"title: {table.title.strip()}", f"columns: {cols}", f"rows: {table.n_rows} (r0 to r{table.n_rows - 1})"]
        if context:
            parts.insert(2, f"context: {context.strip()}")
        return "\n".join(parts)

    def plan_traced(self, question: str, table: Table, context: str | None = None) -> tuple[Program | None, str, int, float, list[TraceStep], dict]:
        t0 = time.perf_counter()
        messages: list[dict] = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": self.first_message(question, table, context)}]
        steps: list[TraceStep] = []
        info = {"model_calls": 0, "tool_calls": 0, "tool_errors": 0, "finished_by": "max_steps"}
        program, raw = None, ""
        for _ in range(self.max_steps):
            r = self.client.post("/v1/chat/completions", json={"model": self.model, "messages": messages, "tools": TOOLS, "tool_choice": "auto",
                                                               "max_tokens": self.max_tokens, "temperature": 0.0})
            r.raise_for_status()
            message = r.json()["choices"][0]["message"]
            info["model_calls"] += 1
            calls = tool_calls_of(message)
            if not calls:                                # plain text: accept a program in the usual grammar, else stop
                raw = (message.get("content") or "").strip()
                try:
                    program = parse(raw, table.id)
                    info["finished_by"] = "text_program"
                except ProgramParseError:
                    info["finished_by"] = "no_tool_call"
                break
            messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": [
                {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args or {}, ensure_ascii=False)}} for cid, name, args in calls]})
            done = False
            for cid, name, args in calls:
                info["tool_calls"] += 1
                if name in ("submit", "abstain") and args is not None:
                    answer = str(args.get("answer") or "-").replace(";", ",").strip() or "-"      # ';' separates the fields of a program
                    raw = (f"op: {args.get('op', '')} ; cells: {', '.join(map(str, args.get('cells') or [])) or '-'} ; answer: {answer}"
                           if name == "submit" else f"op: abstain ; cells: - ; answer: - ; reason: {args.get('reason') or 'not_in_document'}")
                    try:
                        program = parse(raw, table.id)
                        info["finished_by"] = name
                    except ProgramParseError as e:
                        info["finished_by"] = "invalid_submit"
                        steps.append(TraceStep(step="tool", tool=name, input=args, output={"error": str(e)}, status="error"))
                    done = True
                    break
                if name not in READ_TOOLS or args is None:
                    result: Any = {"error": f"unknown tool {name!r}" if name not in READ_TOOLS else "arguments must be a JSON object"}
                    info["tool_errors"] += 1
                    steps.append(TraceStep(step="tool", tool=name or "?", input=args or {}, output=result, status="error"))
                else:
                    try:
                        result = _shown(REGISTRY.call(name, table, args, steps))       # validated arguments; appends its own trace step
                    except ToolError as e:
                        result = {"error": str(e)}                                      # the model sees the error and may try again
                        info["tool_errors"] += 1
                messages.append({"role": "tool", "tool_call_id": cid, "name": name, "content": json.dumps(result, ensure_ascii=False)})
            if done:
                break
        return program, raw, table.n_rows, (time.perf_counter() - t0) * 1000, steps, info

    def plan(self, question: str, table: Table, context: str | None = None) -> tuple[Program | None, str, int, float]:
        return self.plan_traced(question, table, context)[:4]
