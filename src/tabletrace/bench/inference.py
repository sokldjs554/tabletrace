"""CPU inference benchmark for the TableTrace planner model.

Compares, on the same prompts and hardware:
  fp32 eager (baseline) | int8 dynamic quantization of nn.Linear | batch size 1 vs 8 | KV cache on/off
and reports latency (p50/p95 per request), throughput (examples/s), serialized model size, peak RSS (one
process per precision) and string agreement with the fp32 bs=1 output. Whether quantization hurts *accuracy*
is measured separately with `eval.run --quantize` (see docs/experiments/inference.md). Nothing is extrapolated.

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


def serialized_mb(model) -> float:
    import io

    buf = io.BytesIO()
    torch.save(model.state_dict(), buf)
    return round(buf.getbuffer().nbytes / 1e6, 1)


def run_one(a) -> dict:
    """Measure ONE precision in a fresh process so peak RSS is attributable to that configuration."""
    import resource

    from transformers import MT5ForConditionalGeneration, PreTrainedTokenizerFast

    tok = PreTrainedTokenizerFast.from_pretrained(a.model)
    docs = load_docs(*[Path(c) for c in a.corpus])
    recs = read_records([Path(p) for p in a.data])[: a.n]
    texts = [e.input_text for e in build_examples(recs, docs, tok, 512)]
    model = MT5ForConditionalGeneration.from_pretrained(a.model).eval()
    t0 = time.time()
    if a.only == "int8":
        model = torch.ao.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
    prep_s = round(time.time() - t0, 1)
    configs = [(1, True), (8, True)] + ([(1, False)] if a.only == "fp32" else [])
    results = []
    for bs, cache in configs:
        m, outs = run_config(model, tok, texts, bs, cache, a.max_out, a.warmup, a.repeats)
        m.update({"precision": a.only, "batch_size": bs, "kv_cache": cache, "outputs": outs})
        results.append(m)
        print(json.dumps({k: v for k, v in m.items() if k != "outputs"}, ensure_ascii=False), flush=True)
    return {"precision": a.only, "prepare_s": prep_s, "state_dict_mb": serialized_mb(model),
            "peak_rss_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 2), "results": results}


def main() -> None:
    import subprocess
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--corpus", nargs="+", default=["data/ko/documents.jsonl"])
    ap.add_argument("--data", nargs="+", default=["data/ko/test.jsonl"])
    ap.add_argument("--n", type=int, default=48)
    ap.add_argument("--max-out", type=int, default=48)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--only", choices=["fp32", "int8"], default=None, help="internal: measure one precision in this process")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    if a.only:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(run_one(a), ensure_ascii=False))
        return
    parts = {}
    for prec in ("fp32", "int8"):
        tmp = Path(a.out).with_suffix(f".{prec}.tmp.json")
        cmd = [sys.executable, "-m", "tabletrace.bench.inference", "--model", a.model, "--corpus", *a.corpus, "--data", *a.data, "--n", str(a.n),
               "--max-out", str(a.max_out), "--warmup", str(a.warmup), "--repeats", str(a.repeats), "--threads", str(a.threads), "--only", prec, "--out", str(tmp)]
        subprocess.run(cmd, check=True)
        parts[prec] = json.loads(tmp.read_text())
        tmp.unlink()
    ref = {(r["batch_size"], r["kv_cache"]): r["outputs"] for r in parts["fp32"]["results"]}[(1, True)]
    results = []
    for prec in ("fp32", "int8"):
        for r in parts[prec]["results"]:
            agree = sum(1 for x, y in zip(r["outputs"], ref, strict=True) if x.strip() == y.strip()) / len(ref)
            results.append({"config": f"{prec}, bs={r['batch_size']}, kv-cache {'on' if r['kv_cache'] else 'OFF'}", "precision": prec,
                            "batch_size": r["batch_size"], "kv_cache": r["kv_cache"], "p50_ms": r["p50_ms"], "p95_ms": r["p95_ms"], "mean_ms": r["mean_ms"],
                            "throughput_ex_per_s": r["throughput_ex_per_s"], "agreement_with_fp32_bs1": round(agree, 4),
                            "peak_rss_gb": parts[prec]["peak_rss_gb"], "state_dict_mb": parts[prec]["state_dict_mb"]})
    out = {"meta": {"model": a.model, "n_examples": len(ref), "max_new_tokens": a.max_out, "warmup_rounds": a.warmup, "measured_rounds": a.repeats,
                    "threads": a.threads, "cpu": platform.processor() or platform.machine(), "cores": os.cpu_count(), "torch": torch.__version__,
                    "cuda": torch.cuda.is_available(), "int8_prepare_s": parts["int8"]["prepare_s"], "finished": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "note": "each precision measured in its own process; peak_rss_gb = ru_maxrss of that process (includes the tokenizer/torch runtime); "
                            "dynamic int8 quantizes nn.Linear only, the 250k x 512 embedding and lm_head stay fp32"},
           "results": results}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("wrote", a.out)


if __name__ == "__main__":
    main()
