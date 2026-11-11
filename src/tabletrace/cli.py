"""Command-line entry points: `tabletrace serve | ask | grpc-ask | graph`."""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tabletrace")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the FastAPI service")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--grpc-port", type=int, default=None, help="also serve the gRPC API on this port (same as TABLETRACE_GRPC_PORT)")
    g = sub.add_parser("grpc-ask", help="ask a running server over gRPC and print each step as it arrives")
    g.add_argument("question")
    g.add_argument("--corpus", choices=["ko_tables", "chem_docs"], required=True)
    g.add_argument("--doc", default="")
    g.add_argument("--table", default="")
    g.add_argument("--planner", choices=["auto", "neural", "heuristic"], default="auto")
    g.add_argument("--target", default="127.0.0.1:50051")
    q = sub.add_parser("ask", help="answer one question from the shell")
    q.add_argument("question")
    q.add_argument("--corpus", choices=["ko_tables", "chem_docs"], required=True)
    q.add_argument("--doc", default=None)
    q.add_argument("--table", default=None)
    q.add_argument("--planner", choices=["auto", "neural", "heuristic"], default="auto")
    sub.add_parser("graph", help="print the agent graph as Mermaid")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        import os

        import uvicorn

        if a.grpc_port:
            os.environ["TABLETRACE_GRPC_PORT"] = str(a.grpc_port)
        uvicorn.run("tabletrace.service.app:app", host=a.host, port=a.port)
        return 0
    if a.cmd == "grpc-ask":
        import grpc

        from tabletrace.service.pb import tabletrace_pb2 as pb
        from tabletrace.service.pb import tabletrace_pb2_grpc as pb_grpc

        req = pb.AskRequest(question=a.question, corpus=a.corpus, doc_id=a.doc, table_id=a.table, planner=a.planner)
        with grpc.insecure_channel(a.target) as channel:
            for ev in pb_grpc.TableTraceStub(channel).AskStream(req, timeout=120):
                if ev.WhichOneof("event") == "step":
                    print(f"[{ev.step.node}] {ev.step.step}{' ' + ev.step.tool if ev.step.tool else ''} · {ev.step.status} · {ev.step.ms:.0f} ms")
                else:
                    r = ev.result
                    print(json.dumps({"status": r.status, "answer": r.answer, "reason": r.reason,
                                      "evidence_cells": [f"r{c.row}c{c.col}" for c in r.evidence_cells],
                                      "checks": [{"name": c.name, "passed": c.passed} for c in r.checks]}, ensure_ascii=False, indent=1))
        return 0
    from tabletrace.service.app import build_runtime
    from tabletrace.service.settings import Settings

    settings = Settings()
    if a.cmd == "ask" and a.planner == "heuristic":
        settings = Settings(planner="heuristic")
    _store, rt = build_runtime(settings)
    if a.cmd == "graph":
        print(rt.mermaid())
        return 0
    res = rt.run(a.question, a.corpus, doc_id=a.doc, table_id=a.table, planner_mode=a.planner)
    print(json.dumps(json.loads(res.model_dump_json()), ensure_ascii=False, indent=1))
    return 0 if res.status != "error" else 1


if __name__ == "__main__":
    sys.exit(main())
