"""TableTrace HTTP API (FastAPI).

Endpoints
  GET  /v1/health, /v1/release            liveness; version + commit + planner mode
  GET  /v1/corpora                        corpora with document counts
  GET  /v1/documents?corpus=..            document list (id, title, n_tables)
  GET  /v1/documents/{doc_id}             full document (passages + tables)
  GET  /v1/tables/{table_id}
  GET  /v1/examples?corpus=..             representative questions for the console
  POST /v1/search                         {query, corpus, doc_id?} -> table + passage hits
  POST /v1/ask                            {question, corpus, doc_id?, table_id?, planner?} -> job (202) or result (?wait=1)
  GET  /v1/jobs/{id}                      job status / result / trace
  POST /v1/tools/calculate                {table_id, op, cells} -> Calculation (restricted calculator)
  GET  /v1/graph                          the LangGraph as Mermaid
The console (static files) is served at /.
"""
from __future__ import annotations

import os
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tabletrace import __version__
from tabletrace.agent.graph import AgentRuntime
from tabletrace.chat.agent import ChatAgent
from tabletrace.chat.memory import UserMemory
from tabletrace.corpus.store import CorpusStore
from tabletrace.model.serialize import get_row_select, get_table_format
from tabletrace.retrieval.index import CorpusIndex
from tabletrace.schema import CellRef, Corpus
from tabletrace.service.jobs import JobRunner
from tabletrace.service.settings import Settings
from tabletrace.tools.registry import REGISTRY, ToolError

ROOT = Path(__file__).resolve().parents[3]


def git_commit() -> str:
    env = os.environ.get("TABLETRACE_COMMIT")
    if env:
        return env
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True, timeout=2).strip()
    except Exception:
        return "unknown"


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=300)
    corpus: Corpus
    doc_id: str | None = Field(default=None, max_length=64)
    table_id: str | None = Field(default=None, max_length=64)
    planner: Literal["auto", "neural", "heuristic"] = "auto"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=300)
    session_id: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9]+$")
    user_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    corpus: Corpus | None = None
    doc_id: str | None = Field(default=None, max_length=64)
    table_id: str | None = Field(default=None, max_length=64)
    planner: Literal["auto", "neural", "heuristic"] = "auto"


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    corpus: Corpus
    doc_id: str | None = None
    k: int = Field(default=5, ge=1, le=20)


class CalcRequest(BaseModel):
    table_id: str
    op: Literal["diff", "ratio", "sum", "avg", "count", "pct_change"]
    cells: list[str] = Field(min_length=1, max_length=12)


def build_runtime(settings: Settings):
    store = CorpusStore.from_disk()
    indexes = {c: CorpusIndex(docs, "ko" if c == "ko_tables" else "en") for c, docs in store.corpora.items()}
    neural = None
    model_dir = ROOT / settings.model_dir
    if settings.engine_url and settings.planner in ("auto", "neural"):
        from tabletrace.service.engines import EnginePlanner

        if settings.engine_tools:
            from tabletrace.agent.toolcall import ToolCallingPlanner

            neural = ToolCallingPlanner(settings.engine_url, settings.engine_model, api_key=settings.engine_api_key, timeout_s=settings.job_timeout_s)
        else:
            neural = EnginePlanner(settings.engine_url, settings.engine_model, api_key=settings.engine_api_key, timeout_s=settings.job_timeout_s)
        neural.health()                      # fail at start-up, not on the first question, if the engine is not reachable
    elif settings.planner in ("auto", "neural") and model_dir.exists():
        from tabletrace.model.planner import NeuralPlanner

        neural = NeuralPlanner(model_dir, threads=settings.threads or None, quantize=(settings.quantize_scope or settings.quantize))
    elif settings.planner == "neural":
        raise RuntimeError(f"planner=neural but model dir {model_dir} is missing")
    second = None
    if settings.second_opinion:
        from tabletrace.encoder.second_opinion import SecondOpinion

        second = SecondOpinion(settings.second_opinion, mode=settings.second_opinion_mode)
    return store, AgentRuntime(indexes, neural, entity_check=settings.entity_check, evidence_repair=settings.evidence_repair, second_opinion=second)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    state: dict = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store, runtime = build_runtime(settings)
        state["store"], state["runtime"] = store, runtime
        state["runner"] = JobRunner(lambda req: runtime.run(**req), settings.max_concurrent_jobs, settings.job_timeout_s, settings.queue_limit)
        state["chat"] = ChatAgent(runtime, store, UserMemory(settings.memory_path))
        state["chat_runner"] = JobRunner(lambda req: state["chat"].handle(**req), settings.max_concurrent_jobs, settings.job_timeout_s, settings.queue_limit)
        state["started"] = time.time()
        grpc_server = None
        if settings.grpc_port:
            from tabletrace.service.grpc_server import start_grpc_server

            grpc_server, state["grpc_port"] = start_grpc_server(runtime, store, settings, settings.grpc_port, commit=git_commit())
        yield
        if grpc_server is not None:
            grpc_server.stop(grace=2).wait()

    app = FastAPI(title="TableTrace API", version=__version__, lifespan=lifespan)

    @app.get("/v1/health")
    def health():
        return {"ok": True, "uptime_s": round(time.time() - state.get("started", time.time()), 1)}

    @app.get("/v1/release")
    def release():
        rt: AgentRuntime = state["runtime"]
        return {"version": __version__, "commit": git_commit(), "release": settings.release,
                "planner": "neural" if rt.neural else "heuristic", "model_id": rt.neural.model_id if rt.neural else None,
                "quantized": bool(rt.neural and rt.neural.quantized), "table_format": get_table_format(), "row_select": get_row_select(), "entity_check": rt.entity_check, "evidence_repair": rt.evidence_repair,
                "second_opinion": {"model": rt.second_opinion.model_id, "mode": rt.second_opinion.mode} if rt.second_opinion else None, "grpc_port": state.get("grpc_port"), "max_concurrent_jobs": settings.max_concurrent_jobs,
                "job_timeout_s": settings.job_timeout_s}

    @app.get("/v1/corpora")
    def corpora():
        store: CorpusStore = state["store"]
        return [{"id": c, "lang": "ko" if c == "ko_tables" else "en", "documents": len(docs), "tables": sum(len(d.tables) for d in docs)}
                for c, docs in store.corpora.items()]

    @app.get("/v1/documents")
    def documents(corpus: Corpus, limit: int = Query(default=200, ge=1, le=2000), offset: int = Query(default=0, ge=0)):
        store: CorpusStore = state["store"]
        docs = store.corpora.get(corpus, [])
        return {"total": len(docs), "items": [{"id": d.id, "title": d.title, "n_tables": len(d.tables), "n_passages": len(d.passages)}
                                               for d in docs[offset:offset + limit]]}

    @app.get("/v1/documents/{doc_id}")
    def document(doc_id: str):
        store: CorpusStore = state["store"]
        if doc_id not in store.docs:
            raise HTTPException(404, "document not found")
        return store.docs[doc_id]

    @app.get("/v1/tables/{table_id}")
    def table(table_id: str):
        store: CorpusStore = state["store"]
        if table_id not in store.tables:
            raise HTTPException(404, "table not found")
        return store.tables[table_id]

    @app.get("/v1/examples")
    def examples(corpus: Corpus):
        path = ROOT / "console" / "data" / "examples.json"
        if not path.exists():
            return []
        import json

        return [e for e in json.loads(path.read_text(encoding="utf-8")) if e["corpus"] == corpus]

    @app.post("/v1/search")
    def search(req: SearchRequest):
        rt: AgentRuntime = state["runtime"]
        idx = rt.indexes.get(req.corpus)
        if idx is None:
            raise HTTPException(404, "corpus not loaded")
        return {"tables": [h.__dict__ for h in idx.search_tables(req.query, req.k, req.doc_id)],
                "passages": [h.__dict__ for h in idx.search_passages(req.query, req.k, req.doc_id)]}

    @app.post("/v1/ask", status_code=202)
    async def ask(req: AskRequest, wait: bool = Query(default=False)):
        store: CorpusStore = state["store"]
        if req.doc_id and req.doc_id not in store.docs:
            raise HTTPException(404, "document not found")
        if req.table_id and req.table_id not in store.tables:
            raise HTTPException(404, "table not found")
        if req.planner == "neural" and state["runtime"].neural is None:
            raise HTTPException(409, "neural planner is not loaded on this server")
        runner: JobRunner = state["runner"]
        try:
            job = runner.submit({"question": req.question, "corpus": req.corpus, "doc_id": req.doc_id,
                                 "table_id": req.table_id, "planner_mode": req.planner})
        except OverflowError as e:
            raise HTTPException(429, str(e)) from None
        if wait:
            await runner.wait(job, max_wait_s=settings.job_timeout_s + 1)
            return JSONResponse(job.view(), status_code=200 if job.status == "done" else 202)
        return job.view()

    @app.post("/v1/chat")
    async def chat(req: ChatRequest):
        """One turn of a conversation. Memory decides which table and which full question to ask; the answer still
        comes from the verified pipeline. Returns the reply text, what memory contributed, and the pipeline result."""
        store: CorpusStore = state["store"]
        if req.doc_id and req.doc_id not in store.docs:
            raise HTTPException(404, "document not found")
        if req.table_id and req.table_id not in store.tables:
            raise HTTPException(404, "table not found")
        if req.planner == "neural" and state["runtime"].neural is None:
            raise HTTPException(409, "neural planner is not loaded on this server")
        runner: JobRunner = state["chat_runner"]
        try:
            job = runner.submit(req.model_dump())
        except OverflowError as e:
            raise HTTPException(429, str(e)) from None
        await runner.wait(job, max_wait_s=settings.job_timeout_s + 1)
        if job.status != "done":
            raise HTTPException(504 if job.status in ("timeout", "running", "queued") else 500, job.error or job.status)
        return job.result

    @app.get("/v1/chat/{session_id}")
    def chat_session(session_id: str):
        session = state["chat"].sessions.get(session_id)
        if session is None:
            raise HTTPException(404, "session not found (sessions are dropped after two idle hours)")
        return session.view()

    @app.get("/v1/users/{user_id}/memory")
    def user_memory(user_id: str):
        try:
            return state["chat"].users.view(user_id)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None

    @app.delete("/v1/users/{user_id}/memory")
    def forget_user(user_id: str):
        try:
            return {"removed": state["chat"].users.forget(user_id)}
        except ValueError as e:
            raise HTTPException(422, str(e)) from None

    @app.get("/v1/jobs/{job_id}")
    def job(job_id: str):
        runner: JobRunner = state["runner"]
        j = runner.get(job_id)
        if j is None:
            raise HTTPException(404, "job not found")
        return j.view()

    @app.post("/v1/tools/calculate")
    def calculate(req: CalcRequest):
        store: CorpusStore = state["store"]
        if req.table_id not in store.tables:
            raise HTTPException(404, "table not found")
        t = store.tables[req.table_id]
        try:
            for c in req.cells:
                CellRef.parse(t.id, c)
            return REGISTRY.call("calculate", t, {"op": req.op, "cells": req.cells})
        except (ToolError, ValueError) as e:
            raise HTTPException(422, str(e)) from None

    @app.get("/v1/graph")
    def graph():
        rt: AgentRuntime = state["runtime"]
        return {"mermaid": rt.mermaid()}

    console = ROOT / settings.console_dir
    if console.exists():
        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(console / "index.html")

        app.mount("/", StaticFiles(directory=console), name="console")
    return app


app = create_app()
