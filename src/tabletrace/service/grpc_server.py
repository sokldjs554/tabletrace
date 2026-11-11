"""gRPC front end for the same agent runtime the REST API uses (proto/tabletrace/service/pb/tabletrace.proto).

Why gRPC next to REST: `AskStream` pushes every graph step (retrieve, propose, tool calls, verify) to the client as it
finishes, which the REST API can only approximate by polling a job. Unary `Ask`, `Calculate` and `Release` mirror
the REST endpoints so that non-browser clients get typed messages.

Limits are the service's own: at most `max_concurrent_jobs` questions run at once, `queue_limit` more may wait,
anything beyond that is refused with RESOURCE_EXHAUSTED; a client deadline shorter than the run cancels the wait.
"""
from __future__ import annotations

import json
import threading
from concurrent import futures

import grpc

from tabletrace import __version__
from tabletrace.agent.graph import AgentRuntime
from tabletrace.corpus.store import CorpusStore
from tabletrace.model.serialize import get_table_format
from tabletrace.schema import AnswerResult, CellRef, TraceStep
from tabletrace.service.pb import tabletrace_pb2 as pb
from tabletrace.service.pb import tabletrace_pb2_grpc as pb_grpc
from tabletrace.service.settings import Settings
from tabletrace.tools.registry import REGISTRY, ToolError

CORPORA = ("ko_tables", "chem_docs")
PLANNERS = ("auto", "neural", "heuristic")
CALC_OPS = ("diff", "ratio", "sum", "avg", "count", "pct_change")


def _cell(c) -> pb.CellRef:
    return pb.CellRef(table_id=c.table_id, row=c.row, col=c.col)


def to_reply(res: AnswerResult) -> pb.AskReply:
    cited = res.program.cells if res.program else []
    checks = res.verdict.checks if res.verdict else []
    return pb.AskReply(
        status=res.status, answer=res.answer or "", reason=(res.verdict.reason or "") if res.verdict else "",
        evidence_cells=[_cell(c) for c in res.evidence_cells], cited_cells=[_cell(c) for c in cited],
        checks=[pb.Check(name=c.name, passed=c.passed, detail=c.detail) for c in checks],
        planner_mode=res.planner.mode if res.planner else "", model_id=(res.planner.model_id or "") if res.planner else "",
        raw_output=(res.planner.raw_output or "") if res.planner else "", elapsed_ms=res.elapsed_ms,
        table_id=res.table_id or "", result_json=res.model_dump_json(),
    )


def to_step(node: str, step: TraceStep) -> pb.Step:
    detail = json.dumps({"input": step.input, "output": step.output}, ensure_ascii=False, default=str)
    return pb.Step(node=node, step=step.step, tool=step.tool or "", status=step.status, ms=step.ms or 0.0, detail_json=detail)


class TableTraceServicer(pb_grpc.TableTraceServicer):
    def __init__(self, runtime: AgentRuntime, store: CorpusStore, settings: Settings, commit: str = "unknown") -> None:
        self.rt, self.store, self.settings, self.commit = runtime, store, settings, commit
        self._running = threading.BoundedSemaphore(settings.max_concurrent_jobs)
        self._admitted = threading.BoundedSemaphore(settings.max_concurrent_jobs + settings.queue_limit)

    # ---- request checks -------------------------------------------------------------------
    def _validate(self, req: pb.AskRequest, ctx) -> dict:
        q = req.question.strip()
        if not 2 <= len(q) <= self.settings.max_question_chars:
            ctx.abort(grpc.StatusCode.INVALID_ARGUMENT, f"question must be 2..{self.settings.max_question_chars} characters")
        if req.corpus not in CORPORA:
            ctx.abort(grpc.StatusCode.INVALID_ARGUMENT, f"corpus must be one of {CORPORA}")
        planner = req.planner or "auto"
        if planner not in PLANNERS:
            ctx.abort(grpc.StatusCode.INVALID_ARGUMENT, f"planner must be one of {PLANNERS}")
        if req.doc_id and req.doc_id not in self.store.docs:
            ctx.abort(grpc.StatusCode.NOT_FOUND, "document not found")
        if req.table_id and req.table_id not in self.store.tables:
            ctx.abort(grpc.StatusCode.NOT_FOUND, "table not found")
        if planner == "neural" and self.rt.neural is None:
            ctx.abort(grpc.StatusCode.FAILED_PRECONDITION, "neural planner is not loaded on this server")
        return {"question": q, "corpus": req.corpus, "doc_id": req.doc_id or None, "table_id": req.table_id or None, "planner_mode": planner}

    def _enter(self, ctx) -> None:
        """Admission control: refuse when the queue is full, wait for a run slot up to the deadline / job timeout."""
        if not self._admitted.acquire(blocking=False):
            ctx.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "queue is full, retry later")
        remaining = ctx.time_remaining()
        wait = self.settings.job_timeout_s if remaining is None else min(remaining, self.settings.job_timeout_s)
        if not self._running.acquire(timeout=max(0.0, wait)):
            self._admitted.release()
            ctx.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "no run slot became free in time")

    def _leave(self) -> None:
        self._running.release()
        self._admitted.release()

    # ---- RPCs -----------------------------------------------------------------------------
    def Release(self, request, context):
        rt = self.rt
        return pb.ReleaseReply(version=__version__, commit=self.commit, planner="neural" if rt.neural else "heuristic",
                               model_id=(rt.neural.model_id or "") if rt.neural else "", entity_check=rt.entity_check,
                               evidence_repair=rt.evidence_repair, table_format=get_table_format())

    def Ask(self, request, context):
        args = self._validate(request, context)
        self._enter(context)
        try:
            return to_reply(self.rt.run(**args))
        finally:
            self._leave()

    def AskStream(self, request, context):
        args = self._validate(request, context)
        self._enter(context)
        try:
            for kind, node, payload in self.rt.stream(**args):
                if not context.is_active():          # the client went away: stop working for it
                    return
                if kind == "step":
                    yield pb.AskEvent(step=to_step(node, payload))
                else:
                    yield pb.AskEvent(result=to_reply(payload))
        finally:
            self._leave()

    def Calculate(self, request, context):
        if request.table_id not in self.store.tables:
            context.abort(grpc.StatusCode.NOT_FOUND, "table not found")
        if request.op not in CALC_OPS:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"op must be one of {CALC_OPS}")
        if not 1 <= len(request.cells) <= 12:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "1..12 cells")
        table = self.store.tables[request.table_id]
        try:
            for c in request.cells:
                CellRef.parse(table.id, c)
            calc = REGISTRY.call("calculate", table, {"op": request.op, "cells": list(request.cells)})
        except (ToolError, ValueError) as e:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        return pb.CalculateReply(op=calc.op, expression=calc.expression, result=calc.result, formatted=calc.formatted, unit=calc.unit or "")


def start_grpc_server(runtime: AgentRuntime, store: CorpusStore, settings: Settings, port: int, host: str = "0.0.0.0",
                      commit: str = "unknown") -> tuple[grpc.Server, int]:
    """Start the server in background threads and return (server, bound port). `port=0` picks a free port."""
    workers = settings.max_concurrent_jobs + settings.queue_limit + 4      # waiting requests hold a thread each
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tt-grpc"))
    pb_grpc.add_TableTraceServicer_to_server(TableTraceServicer(runtime, store, settings, commit), server)
    bound = server.add_insecure_port(f"{host}:{port}")
    server.start()
    return server, bound
