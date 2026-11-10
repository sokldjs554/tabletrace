"""Latency/throughput benchmark against an OpenAI-compatible engine (vLLM / SGLang). Needs a running server (scripts/serving/); not run in the CPU container."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import statistics
import time
from pathlib import Path

from tabletrace.model.serialize import TABLE_FORMATS, get_table_format, set_table_format
from tabletrace.service.engines import EnginePlanner
from tabletrace.training.data import build_examples, load_docs, read_records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", default="planner")
    ap.add_argument("--corpus", nargs="+", default=["data/ko/documents.jsonl"])
    ap.add_argument("--data", nargs="+", default=["data/ko/test.jsonl"])
    ap.add_argument("--n", type=int, default=64)
    ap.add_argument("--tokenizer", default=None, help="approx | hub name | path (default: models/mt5-small-base if present, else approx)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--out", default="experiments/bench/engine.json")
    ap.add_argument("--table-format", choices=TABLE_FORMATS, default=None, help="table format the served model was trained on (default: TABLETRACE_TABLE_FORMAT or plain)")
    a = ap.parse_args()
    if a.table_format:
        set_table_format(a.table_format)
    planner = EnginePlanner(a.url, a.model)
    from tabletrace.model.approx_tokenizer import load_tokenizer

    tok = load_tokenizer(a.tokenizer)
    docs = load_docs(*[Path(c) for c in a.corpus])
    exs = build_examples(read_records([Path(p) for p in a.data])[: a.n], docs, tok, 512)
    t0 = time.perf_counter()
    with cf.ThreadPoolExecutor(a.concurrency) as pool:
        res = list(pool.map(lambda e: planner.plan(e.question, e.table, e.context), exs))
    wall = time.perf_counter() - t0
    lat = sorted(r[3] for r in res)
    out = {"url": a.url, "model": a.model, "table_format": get_table_format(), "n": len(exs), "concurrency": a.concurrency, "wall_s": round(wall, 2),
           "throughput_req_per_s": round(len(exs) / wall, 3), "p50_ms": round(statistics.median(lat), 1), "p95_ms": round(lat[int(0.95 * len(lat)) - 1], 1),
           "parse_ok_rate": round(sum(1 for r in res if r[0] is not None) / len(res), 3)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps(out))


if __name__ == "__main__":
    main()
