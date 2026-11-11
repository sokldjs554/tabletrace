"""Run a planner over an evaluation file and write metrics + per-example predictions.

  python -m tabletrace.eval.run --planner heuristic --corpus data/ko/documents.jsonl --data data/ko/test.jsonl --out experiments/eval/heuristic_ko_test
  python -m tabletrace.eval.run --planner neural --model experiments/sft_ko/model --corpus ... --data ... --out ...

Every example goes through the same verifier as the API, so "verified_em" is what a user of the
service would actually see.
"""
from __future__ import annotations

import argparse
import inspect
import json
import platform
import time
from pathlib import Path

from tabletrace.agent.heuristic import plan as heuristic_plan
from tabletrace.agent.program import ProgramParseError, parse, serialize
from tabletrace.eval.metrics import answer_match, cells_match, summarize
from tabletrace.model.serialize import (
    ROW_SELECTS,
    TABLE_FORMATS,
    get_row_select,
    get_table_format,
    set_row_select,
    set_table_format,
)
from tabletrace.training.data import build_examples, load_docs, read_records
from tabletrace.verify.verifier import resolve


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planner", choices=["heuristic", "neural", "engine"], required=True)
    ap.add_argument("--model", default=None)
    ap.add_argument("--tokenizer", default=None, help="tokenizer for the row budget: approx | hub name | path (default: --model, else models/mt5-small-base, else approx)")
    ap.add_argument("--engine-url", default=None, help="OpenAI-compatible server (vLLM / SGLang) for --planner engine")
    ap.add_argument("--engine-model", default="planner")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--corpus", nargs="+", required=True)
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sample", type=int, default=0, help="evaluate a seeded random sample of this many records (file order kept)")
    ap.add_argument("--sample-seed", type=int, default=13)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--max-in", type=int, default=512)
    ap.add_argument("--quantize", action="store_true")
    ap.add_argument("--quantize-scope", default="all", help="which nn.Linear layers get int8 (see model/quant.py)")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--label", default=None)
    ap.add_argument("--no-entity-check", action="store_true", help="verifier without the subject check (the evaluation before it existed)")
    ap.add_argument("--column-check", action="store_true", help="verifier moves a lookup to the column the question names")
    ap.add_argument("--no-repair", action="store_true",
                    help="verifier withholds a lookup whose cited cell does not hold the answer instead of repairing the evidence "
                         "(needs resolve(..., repair=False), docs/rewrite/05_verifier_repair_option.md)")
    ap.add_argument("--engine-timeout", type=float, default=120.0, help="seconds to wait for one engine request (raise it for a CPU server)")
    ap.add_argument("--tool-calling", action="store_true",
                    help="engine planner only: the model reads the table through tools and picks them itself (agent/toolcall.py). "
                         "The whole table is available, so there is no row budget")
    ap.add_argument("--row-select", choices=ROW_SELECTS, default=None,
                    help="which rows a table that does not fit the input shows: first (default, all stored results) or overlap "
                         "(rows sharing words with the question, original row ids kept). Default with --replay-from: the replayed run's")
    ap.add_argument("--few-shot", nargs="*", default=[],
                    help="engine planner only: training files to draw demonstrations from (one lookup, one calculation, one abstention, "
                         "repeated --shots-per-kind times). For models that were not tuned on the program grammar")
    ap.add_argument("--shots-per-kind", type=int, default=1)
    ap.add_argument("--confidence", action="store_true",
                    help="also store the log-probability summary of each generated program (neural: from the model; engine: needs a "
                         "server that returns logprobs). scripts/risk_coverage.py reads it")
    ap.add_argument("--replay-from", default=None, help="eval dir whose predictions.jsonl raw outputs are re-verified (no model run)")
    ap.add_argument("--table-format", choices=TABLE_FORMATS, default=None,
                    help="how tables are written into the model input (model/serialize.py); must be the format the planner was trained on. "
                         "Default: the replayed run's format with --replay-from, else TABLETRACE_TABLE_FORMAT, else plain")
    a = ap.parse_args()
    if a.table_format is None and a.replay_from:      # a replay must rebuild the same inputs (row budget) as the run it replays
        a.table_format = json.loads((Path(a.replay_from) / "metrics.json").read_text(encoding="utf-8"))["meta"].get("table_format")
    if a.table_format:
        set_table_format(a.table_format)
    if a.row_select is None and a.replay_from:
        a.row_select = json.loads((Path(a.replay_from) / "metrics.json").read_text(encoding="utf-8"))["meta"].get("row_select")
    if a.row_select:
        set_row_select(a.row_select)
    verify_opts = {}
    if a.no_repair:
        if "repair" not in inspect.signature(resolve).parameters:
            raise SystemExit("--no-repair: this verifier has no `repair` option yet (docs/rewrite/05_verifier_repair_option.md)")
        verify_opts["repair"] = False
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    docs = load_docs(*[Path(c) for c in a.corpus])
    recs = read_records([Path(p) for p in a.data])
    if a.limit:
        recs = recs[: a.limit]
    if a.sample and a.sample < len(recs):
        import random

        keep = set(random.Random(a.sample_seed).sample(range(len(recs)), a.sample))
        recs = [r for i, r in enumerate(recs) if i in keep]
    from tabletrace.model.approx_tokenizer import load_tokenizer

    tok = load_tokenizer(a.tokenizer or (a.model if a.planner == "neural" else None))
    examples = build_examples(recs, docs, tok, a.max_in)
    lang = next(iter(docs.values())).lang
    t0 = time.time()
    planner_id = "heuristic"
    confidences: dict[str, dict | None] = {}
    tool_infos: dict[str, dict] = {}
    if a.replay_from:
        # Re-verify the stored raw planner outputs of an earlier run with the current verifier; no model is loaded.
        with open(Path(a.replay_from) / "predictions.jsonl", encoding="utf-8") as fh:
            old_rows = {r["qid"]: r for r in map(json.loads, fh)}
        if json.loads((Path(a.replay_from) / "metrics.json").read_text(encoding="utf-8"))["meta"].get("tool_calling"):
            from dataclasses import (
                replace,  # a tool-calling run read the whole table: verify against the whole table again
            )

            a.tool_calling = True
            examples = [replace(e, table=e.table_full or e.table, context=e.context_full or e.context, truncated_gold=False) for e in examples]
            tool_infos = {q: r["tool_calling"] for q, r in old_rows.items() if "tool_calling" in r}
        plans = []
        for e in examples:
            o = old_rows[e.qid]
            try:
                prog = parse(o["raw_output"], e.table.id)
            except ProgramParseError:
                prog = None
            plans.append((prog, o["raw_output"], e.rows_kept, o["ms"]))
            if "confidence" in o:
                confidences[e.qid] = o["confidence"]
        planner_id = f"replay of {a.replay_from}"
    elif a.planner == "engine" and a.tool_calling:
        import concurrent.futures as cf
        from dataclasses import replace

        from tabletrace.agent.toolcall import ToolCallingPlanner

        planner = ToolCallingPlanner(a.engine_url, a.engine_model, timeout_s=a.engine_timeout)
        planner_id = planner.model_id
        planner.health()
        examples = [replace(e, table=e.table_full or e.table, context=e.context_full or e.context, truncated_gold=False) for e in examples]
        with cf.ThreadPoolExecutor(a.concurrency) as pool:
            traced = list(pool.map(lambda e: planner.plan_traced(e.question, e.table, e.context), examples))
        plans = [t[:4] for t in traced]
        tool_infos = {e.qid: {**t[5], "tools": [s.tool for s in t[4]]} for e, t in zip(examples, traced, strict=True)}
    elif a.planner == "engine":
        import concurrent.futures as cf

        from tabletrace.service.engines import EnginePlanner

        shots = []
        if a.few_shot:
            demo = build_examples(read_records([Path(p) for p in a.few_shot]), docs, tok, a.max_in, drop_truncated_gold=True)
            by_kind: dict[str, list] = {}
            for d in demo:
                kind = d.gold.op if d.gold.op in ("lookup", "abstain") else "calc"
                by_kind.setdefault(kind, []).append(d)
            for i in range(a.shots_per_kind):                       # the i-th shortest example of each kind: small, and the same every run
                for kind in ("lookup", "calc", "abstain"):
                    pool = sorted(by_kind.get(kind, []), key=lambda d: (len(d.input_text), d.qid))
                    if i < len(pool):
                        shots.append((pool[i].input_text, pool[i].target_text))
        planner = EnginePlanner(a.engine_url, a.engine_model, timeout_s=a.engine_timeout, shots=shots)
        planner_id = planner.model_id + (f" +{len(shots)} shots" if shots else "")
        planner.health()
        with cf.ThreadPoolExecutor(a.concurrency) as pool:
            scored = list(pool.map(lambda e: planner.plan_scored(e.question, e.table_full if e.shown_rows else e.table, e.context,
                                                               logprobs=a.confidence, rows=e.shown_rows), examples))
        plans = [s[:4] for s in scored]
        if a.confidence:
            confidences = {e.qid: s[4] for e, s in zip(examples, scored, strict=True)}
    elif a.planner == "neural":
        from tabletrace.model.planner import NeuralPlanner

        planner = NeuralPlanner(a.model, max_in=a.max_in, threads=a.threads or None,
                               quantize=(a.quantize_scope if a.quantize else False))
        planner_id = planner.model_id
        items = [(e.question, e.table_full, e.context, e.shown_rows) if e.shown_rows else (e.question, e.table, e.context) for e in examples]
        if a.confidence:
            scored = planner.plan_batch_scored(items, batch_size=a.bs)
            plans = [s[:4] for s in scored]
            confidences = {e.qid: s[4] for e, s in zip(examples, scored, strict=True)}
        else:
            plans = planner.plan_batch(items, batch_size=a.bs)
    else:
        plans = []
        for e in examples:
            t1 = time.perf_counter()
            p = heuristic_plan(e.question, e.table, lang)
            plans.append((p, serialize(p), e.rows_kept, (time.perf_counter() - t1) * 1000))
    rows = []
    rec_by_qid = {r["qid"]: r for r in recs}
    for e, (prog, raw, _n, ms) in zip(examples, plans, strict=True):
        gold_res = resolve(e.question, e.table_full or e.table, e.gold, context=e.context_full or e.context, entity_check=False)
        res = resolve(e.question, e.table, prog, context=e.context, entity_check=not a.no_entity_check, column_check=a.column_check, **verify_opts)
        # what the subject check alone would do to the GOLD program: the abstention rate a perfect planner would suffer
        gold_chk = resolve(e.question, e.table_full or e.table, e.gold, context=e.context_full or e.context, entity_check=True)
        gold_subject_fail = gold_res.status == "answered" and gold_chk.status == "abstained"
        alts = rec_by_qid[e.qid].get("alt_answers") or []
        gold_cells = [c.cid for c in e.gold.cells]
        pred_cells = [c.cid for c in res.cells]
        raw_cells = [c.cid for c in prog.cells] if prog else []
        golds = [gold_res.answer, *alts]
        verified_correct = (res.status == gold_res.status) and (gold_res.status == "abstained" or any(answer_match(res.answer, g) for g in golds))
        raw_correct = gold_res.status == "answered" and prog is not None and prog.op != "abstain" and any(answer_match(prog.answer, g) for g in golds)
        unit_error = None
        if gold_res.calculation is not None and res.calculation is not None:
            unit_error = (res.calculation.unit != gold_res.calculation.unit)
        rows.append({
            "qid": e.qid, "source": e.source, "category": rec_by_qid[e.qid].get("category"),
            "question": e.question, "gold_status": gold_res.status, "gold_op": e.gold.op, "gold_answer": gold_res.answer,
            "gold_cells": gold_cells, "raw_output": raw, "pred_op": prog.op if prog else None,
            "pred_status": res.status, "pred_answer": res.answer, "pred_cells": pred_cells,
            "pred_reason": res.verdict.reason, "verified_correct": verified_correct, "raw_correct": raw_correct,
            "cells_exact": cells_match(pred_cells, gold_cells) if gold_cells else (e.gold.op == "text" and bool(res.spans)),
            "cells_exact_raw": cells_match(raw_cells, gold_cells) if gold_cells else (e.gold.op == "text" and bool(res.spans)),
            "evidence_repaired": any(c.name == "evidence_repaired" for c in res.verdict.checks),
            "cells_overlap": bool(set(pred_cells) & set(gold_cells)) if gold_cells else (e.gold.op == "text" and bool(res.spans)),
            "op_correct": (prog.op if prog else None) == e.gold.op,
            "calc_correct": (res.calculation is not None and gold_res.calculation is not None and abs(res.calculation.result - gold_res.calculation.result) < 1e-6),
            "unit_error": unit_error, "pred_abstained": res.status == "abstained", "parse_fail": prog is None,
            "verifier_changed": (prog is not None and prog.op != "abstain" and (res.status == "abstained" or (prog.answer is not None and not answer_match(prog.answer, res.answer)))),
            "truncated_gold": e.truncated_gold, "ms": ms, "gold_subject_fail": gold_subject_fail,
            "checks": [c.model_dump() for c in res.verdict.checks],
        })
        if e.qid in confidences:
            rows[-1]["confidence"] = confidences[e.qid]
        if e.qid in tool_infos:
            rows[-1]["tool_calling"] = tool_infos[e.qid]
    metrics = summarize(rows)
    answerable_rows = [r for r in rows if r["gold_status"] == "answered"]
    metrics["gold_subject_fail_rate"] = round(sum(r["gold_subject_fail"] for r in answerable_rows) / len(answerable_rows), 4) if answerable_rows else None
    metrics["entity_check"] = not a.no_entity_check
    meta = {"planner": a.planner, "model": planner_id, "data": a.data, "corpus": a.corpus, "n": len(rows),
            "wall_s": round(time.time() - t0, 1), "hardware": platform.processor() or platform.machine(),
            "label": a.label, "table_format": get_table_format(), "row_select": get_row_select(), "evidence_repair": not a.no_repair, "entity_check": not a.no_entity_check, "column_check": a.column_check, "replay_from": a.replay_from, "finished": time.strftime("%Y-%m-%dT%H:%M:%S"), "quantize": a.quantize, "quantize_scope": a.quantize_scope if a.quantize else None,
            "confidence": bool(confidences), "few_shot": a.few_shot or None,
            "sample": {"n": a.sample, "seed": a.sample_seed} if a.sample else None, "tool_calling": a.tool_calling}
    if tool_infos:
        n_t = len(tool_infos)
        metrics["tool_calling"] = {"model_calls_mean": round(sum(t["model_calls"] for t in tool_infos.values()) / n_t, 2),
                                   "tool_calls_mean": round(sum(t["tool_calls"] for t in tool_infos.values()) / n_t, 2),
                                   "tool_errors": sum(t["tool_errors"] for t in tool_infos.values()),
                                   "finished_by": {k: sum(t["finished_by"] == k for t in tool_infos.values()) for k in sorted({t["finished_by"] for t in tool_infos.values()})}}
    (out / "metrics.json").write_text(json.dumps({"meta": meta, "metrics": metrics}, ensure_ascii=False, indent=1))
    with open(out / "predictions.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"meta": meta, "metrics": {k: v for k, v in metrics.items() if k not in ("by_source", "by_category")}}, ensure_ascii=False, indent=1))
    if "by_category" in metrics:
        print(json.dumps(metrics["by_category"], ensure_ascii=False))


if __name__ == "__main__":
    main()
