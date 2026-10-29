"""Command-line entry points: `tabletrace serve | ask | eval | graph`."""
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
    q = sub.add_parser("ask", help="answer one question from the shell")
    q.add_argument("question")
    q.add_argument("--corpus", choices=["ko_tables", "chem_docs"], required=True)
    q.add_argument("--doc", default=None)
    q.add_argument("--table", default=None)
    q.add_argument("--planner", choices=["auto", "neural", "heuristic"], default="auto")
    sub.add_parser("graph", help="print the agent graph as Mermaid")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        import uvicorn

        uvicorn.run("tabletrace.service.app:app", host=a.host, port=a.port)
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
