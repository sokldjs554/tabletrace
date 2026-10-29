"""Run a planner over an evaluation file and write metrics + per-example predictions.

  python -m tabletrace.eval.run --planner heuristic --corpus data/ko/documents.jsonl --data data/ko/test.jsonl --out experiments/eval/heuristic_ko_test
  python -m tabletrace.eval.run --planner neural --model experiments/sft_ko/model --corpus ... --data ... --out ...

Every example goes through the same verifier as the API, so "verified_em" is what a user of the
service would actually see.
"""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

from tabletrace.agent.heuristic import plan as heuristic_plan
from tabletrace.agent.program import serialize
from tabletrace.eval.metrics import answer_match, cells_match, summarize
from tabletrace.training.data import build_examples, load_docs, read_records
from tabletrace.verify.verifier import resolve


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planner", choices=["heuristic", "neural"], required=True)
    ap.add_argument("--model", default=None)
    ap.add_argument("--corpus", nargs="+", required=True)
    ap.add_argument("--data", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--max-in", type=int, default=512)
    ap.add_argument("--quantize", action="store_true")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--label", default=None)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    docs = load_docs(*[Path(c) for c in a.corpus])
    recs = read_records([Path(p) for p in a.data])
    if a.limit:
        recs = recs[: a.limit]
    from transformers import PreTrainedTokenizerFast

    tok_dir = a.model or "models/mt5-small-base"
    tok = PreTrainedTokenizerFast.from_pretrained(tok_dir)
    examples = build_examples(recs, docs, tok, a.max_in)
    lang = next(iter(docs.values())).lang
    t0 = time.time()
    planner_id = "heuristic"
    if a.planner == "neural":
        from tabletrace.model.planner import NeuralPlanner

        planner = NeuralPlanner(a.model, max_in=a.max_in, threads=a.threads or None, quantize=a.quantize)
        planner_id = planner.model_id
        plans = planner.plan_batch([(e.question, e.table, e.context) for e in examples], batch_size=a.bs)
    else:
        plans = []
        for e in examples:
            t1 = time.perf_counter()
            p = heuristic_plan(e.question, e.table, lang)
            plans.append((p, serialize(p), e.rows_kept, (time.perf_counter() - t1) * 1000))
    rows = []
    rec_by_qid = {r["qid"]: r for r in recs}
    for e, (prog, raw, _n, ms) in zip(examples, plans, strict=True):
        gold_res = resolve(e.question, e.table, e.gold, context=e.context)
        res = resolve(e.question, e.table, prog, context=e.context)
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
            "truncated_gold": e.truncated_gold, "ms": ms,
            "checks": [c.model_dump() for c in res.verdict.checks],
        })
    metrics = summarize(rows)
    meta = {"planner": a.planner, "model": planner_id, "data": a.data, "corpus": a.corpus, "n": len(rows),
            "wall_s": round(time.time() - t0, 1), "hardware": platform.processor() or platform.machine(),
            "label": a.label, "finished": time.strftime("%Y-%m-%dT%H:%M:%S"), "quantize": a.quantize}
    (out / "metrics.json").write_text(json.dumps({"meta": meta, "metrics": metrics}, ensure_ascii=False, indent=1))
    with open(out / "predictions.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"meta": meta, "metrics": {k: v for k, v in metrics.items() if k not in ("by_source", "by_category")}}, ensure_ascii=False, indent=1))
    if "by_category" in metrics:
        print(json.dumps(metrics["by_category"], ensure_ascii=False))


if __name__ == "__main__":
    main()
