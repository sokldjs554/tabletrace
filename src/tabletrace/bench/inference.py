"""CPU inference benchmark for the TableTrace planner model.

Compares, on the same prompts and hardware:
  fp32 eager (baseline) | int8 dynamic quantization of nn.Linear | batch size 1 vs 8 | KV cache on/off
and reports latency (p50/p95 per request), throughput (examples/s), peak RSS and answer agreement with
the baseline. Everything is measured here; nothing is extrapolated.

  python -m tabletrace.bench.inference --model experiments/sft_ko/model --data data/ko/test.jsonl --n 48 --out experiments/bench/inference.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time
from pathlib import Path

import psutil
import torch

from tabletrace.training.data import build_examples, load_docs, read_records


def rss_gb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / 1e9


def run_config(model, tok, texts, bs, use_cache, max_out, warmup, repeats):
    lat, outs = [], []
    for rep in range(warmup + repeats):
        outs = []
        for i in range(0, len(texts), bs):
            chunk = texts[i:i + bs]
            enc = tok(chunk, return_tensors="pt", padding=True, truncation=True, max_length=512)
            t0 = time.perf_counter()
            with torch.no_grad():
                g = model.generate(**enc, max_new_tokens=max_out, do_sample=False, num_beams=1, use_cache=use_cache)
            dt = (time.perf_counter() - t0) / len(chunk)
            if rep >= warmup:
                lat.extend([dt] * len(chunk))
            outs.extend(tok.batch_decode(g, skip_special_tokens=True))
    lat_ms = sorted(x * 1000 for x in lat)
    total_s = sum(lat) / repeats
    return {"p50_ms": round(statistics.median(lat_ms), 1), "p95_ms": round(lat_ms[int(0.95 * len(lat_ms)) - 1], 1),
            "mean_ms": round(statistics.mean(lat_ms), 1), "throughput_ex_per_s": round(len(texts) / total_s, 3)}, outs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--corpus", nargs="+", default=["data/ko/documents.jsonl"])
    ap.add_argument("--data", nargs="+", default=["data/ko/test.jsonl"])
    ap.add_argument("--n", type=int, default=48)
    ap.add_argument("--max-out", type=int, default=48)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    from transformers import MT5ForConditionalGeneration, PreTrainedTokenizerFast

    tok = PreTrainedTokenizerFast.from_pretrained(a.model)
    docs = load_docs(*[Path(c) for c in a.corpus])
    recs = read_records([Path(p) for p in a.data])[: a.n]
    texts = [e.input_text for e in build_examples(recs, docs, tok, 512)]
    base = MT5ForConditionalGeneration.from_pretrained(a.model).eval()
    results = []
    configs = [("fp32 eager, bs=1, kv-cache on", base, 1, True), ("fp32 eager, bs=8, kv-cache on", base, 8, True),
               ("fp32 eager, bs=1, kv-cache OFF", base, 1, False)]
    t0 = time.time()
    q = torch.ao.quantization.quantize_dynamic(MT5ForConditionalGeneration.from_pretrained(a.model).eval(), {torch.nn.Linear}, dtype=torch.qint8)
    quant_s = round(time.time() - t0, 1)
    configs += [("int8 dynamic (Linear), bs=1, kv-cache on", q, 1, True), ("int8 dynamic (Linear), bs=8, kv-cache on", q, 8, True)]
    base_outs = None
    for name, model, bs, cache in configs:
        rss0 = rss_gb()
        m, outs = run_config(model, tok, texts, bs, cache, a.max_out, a.warmup, a.repeats)
        if base_outs is None:
            base_outs = outs
        agree = sum(1 for x, y in zip(outs, base_outs, strict=True) if x.strip() == y.strip()) / len(outs)
        m.update({"config": name, "batch_size": bs, "kv_cache": cache, "rss_gb_after": round(rss_gb(), 2), "rss_gb_before": round(rss0, 2),
                  "agreement_with_fp32_bs1": round(agree, 4)})
        results.append(m)
        print(json.dumps(m, ensure_ascii=False), flush=True)
    sizes = {"fp32_state_dict_mb": round(sum(p.numel() * 4 for p in base.parameters()) / 1e6, 1)}
    out = {"meta": {"model": a.model, "n_examples": len(texts), "max_new_tokens": a.max_out, "warmup_rounds": a.warmup, "measured_rounds": a.repeats,
                    "threads": a.threads, "cpu": platform.processor() or platform.machine(), "cores": os.cpu_count(),
                    "torch": torch.__version__, "cuda": torch.cuda.is_available(), "quantize_time_s": quant_s,
                    "finished": time.strftime("%Y-%m-%dT%H:%M:%S"), **sizes},
           "results": results}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
