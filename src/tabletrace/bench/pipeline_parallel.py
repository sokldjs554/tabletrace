"""Two-stage pipeline model parallelism for the mT5 planner with torch.distributed.

Rank 0 holds the encoder (+ shared embedding), rank 1 holds the decoder + lm_head. Rank 0 encodes
a batch and sends the encoder hidden states to rank 1, which runs greedy decoding and sends the
generated ids back. This is MODEL parallelism (one model split across two workers), not DDP
(where each worker holds a full copy).

Backends: `gloo` (CPU, used for the functional check in this project) or `nccl` (GPU, each rank on
its own device). Run:
  torchrun --nproc_per_node=2 -m tabletrace.bench.pipeline_parallel --model experiments/sft_ko/model --backend gloo --n 16
  torchrun --nproc_per_node=2 -m tabletrace.bench.pipeline_parallel --model ... --backend nccl --n 64   # 2 GPUs
  # no tuned weights at hand (they are not in git): --model google/mt5-small (the untuned base, same architecture; this measures
  # the splitting, the transfer and the 1-GPU vs 2-GPU output equality, not answer quality; needs `pip install sentencepiece`)
The single-process baseline for the same inputs is measured by --single (no distributed init).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path

import psutil
import torch
import torch.distributed as dist

from tabletrace.training.data import build_examples, load_docs, read_records


def mem_mb(device: torch.device) -> float:
    if device.type == "cuda":
        return torch.cuda.max_memory_allocated(device) / 1e6
    return psutil.Process(os.getpid()).memory_info().rss / 1e6


def greedy_decode(decoder, lm_head, enc_hidden, enc_mask, max_out, device, use_cache=True):
    bs = enc_hidden.shape[0]
    ids = torch.zeros((bs, 1), dtype=torch.long, device=device)  # decoder_start_token_id = pad = 0
    past = None
    finished = torch.zeros(bs, dtype=torch.bool, device=device)
    for _ in range(max_out):
        out = decoder(input_ids=ids[:, -1:] if (use_cache and past is not None) else ids, encoder_hidden_states=enc_hidden,
                      encoder_attention_mask=enc_mask, past_key_values=past, use_cache=use_cache)
        past = out.past_key_values if use_cache else None
        logits = lm_head(out.last_hidden_state[:, -1])
        nxt = logits.argmax(-1)
        nxt = torch.where(finished, torch.zeros_like(nxt), nxt)
        ids = torch.cat([ids, nxt[:, None]], dim=1)
        finished |= nxt == 1  # </s>
        if bool(finished.all()):
            break
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--corpus", nargs="+", default=["data/ko/documents.jsonl"])
    ap.add_argument("--data", nargs="+", default=["data/ko/test.jsonl"])
    ap.add_argument("--n", type=int, default=16)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--max-out", type=int, default=48)
    ap.add_argument("--backend", default="gloo")
    ap.add_argument("--single", action="store_true", help="single-process baseline, no distributed init")
    ap.add_argument("--out", default=None)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--tokenizer", default=None, help="hub name or path; default: --model (use google/mt5-small together with --model google/mt5-small)")
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    from transformers import MT5ForConditionalGeneration

    from tabletrace.model.approx_tokenizer import load_tokenizer

    tok = load_tokenizer(a.tokenizer or a.model)
    docs = load_docs(*[Path(c) for c in a.corpus])
    recs = read_records([Path(p) for p in a.data])[: a.n]
    texts = [e.input_text for e in build_examples(recs, docs, tok, 512)]
    batches = [texts[i:i + a.bs] for i in range(0, len(texts), a.bs)]

    if a.single:
        device = torch.device("cuda:0" if (a.backend == "nccl" and torch.cuda.is_available()) else "cpu")
        model = MT5ForConditionalGeneration.from_pretrained(a.model).eval().to(device)
        lat, outs = [], []
        for chunk in batches:
            enc = tok(chunk, return_tensors="pt", padding=True, truncation=True, max_length=512).to(device)
            t0 = time.perf_counter()
            with torch.no_grad():
                h = model.encoder(input_ids=enc.input_ids, attention_mask=enc.attention_mask).last_hidden_state
                ids = greedy_decode(model.decoder, model.lm_head, h, enc.attention_mask, a.max_out, device)
            lat.append(time.perf_counter() - t0)
            outs += tok.batch_decode(ids, skip_special_tokens=True)
        res = {"mode": "single-process", "device": str(device), "n": len(texts), "bs": a.bs, "batch_latency_s": [round(x, 3) for x in lat],
               "throughput_ex_per_s": round(len(texts) / sum(lat), 3), "mem_mb": round(mem_mb(device), 1),
               "params_total": sum(p.numel() for p in model.parameters()), "outputs_sha": hash(tuple(outs)) & 0xFFFFFFFF, "outputs": outs}
        print(json.dumps({k: v for k, v in res.items() if k != "outputs"}))
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))
        return

    dist.init_process_group(a.backend)
    rank, world = dist.get_rank(), dist.get_world_size()
    assert world == 2, "this pipeline has exactly 2 stages"
    device = torch.device(f"cuda:{rank}" if a.backend == "nccl" else "cpu")
    if device.type == "cuda":
        torch.cuda.set_device(device)
    full = MT5ForConditionalGeneration.from_pretrained(a.model).eval()
    d_model = full.config.d_model
    if rank == 0:
        stage = full.encoder.to(device)          # encoder + shared embedding
        params = sum(p.numel() for p in stage.parameters())
        del full.decoder, full.lm_head
    else:
        decoder, lm_head = full.decoder.to(device), full.lm_head.to(device)
        params = sum(p.numel() for p in decoder.parameters()) + sum(p.numel() for p in lm_head.parameters())
        del full.encoder
    dist.barrier()
    lat, outs = [], []
    t_all = time.perf_counter()
    for chunk in batches:
        enc = tok(chunk, return_tensors="pt", padding=True, truncation=True, max_length=512)
        bs, L = enc.input_ids.shape
        shape = torch.tensor([bs, L], dtype=torch.long)
        t0 = time.perf_counter()
        if rank == 0:
            with torch.no_grad():
                h = stage(input_ids=enc.input_ids.to(device), attention_mask=enc.attention_mask.to(device)).last_hidden_state
            dist.send(shape, dst=1)
            dist.send(h.contiguous().cpu() if a.backend == "gloo" else h.contiguous(), dst=1)
            dist.send(enc.attention_mask.contiguous(), dst=1)
            n_tok = torch.zeros(1, dtype=torch.long)
            dist.recv(n_tok, src=1)
            ids = torch.zeros((bs, int(n_tok)), dtype=torch.long)
            dist.recv(ids, src=1)
            outs += tok.batch_decode(ids, skip_special_tokens=True)
        else:
            dist.recv(shape, src=0)
            bs, L = int(shape[0]), int(shape[1])
            h = torch.zeros((bs, L, d_model), dtype=torch.float32, device=device if a.backend == "nccl" else "cpu")
            dist.recv(h, src=0)
            mask = torch.zeros((bs, L), dtype=torch.long)
            dist.recv(mask, src=0)
            with torch.no_grad():
                ids = greedy_decode(decoder, lm_head, h.to(device), mask.to(device), a.max_out, device)
            ids = ids.cpu()
            dist.send(torch.tensor([ids.shape[1]], dtype=torch.long), dst=0)
            dist.send(ids.contiguous(), dst=0)
        lat.append(time.perf_counter() - t0)
    total = time.perf_counter() - t_all
    res = {"mode": "pipeline-parallel-2-stage", "backend": a.backend, "rank": rank, "device": str(device), "stage": "encoder" if rank == 0 else "decoder+lm_head",
           "stage_params": params, "n": len(texts), "bs": a.bs, "batch_latency_s": [round(x, 3) for x in lat],
           "throughput_ex_per_s": round(len(texts) / total, 3), "mem_mb": round(mem_mb(device), 1), "threads": a.threads}
    if rank == 0:
        res["outputs"] = outs
    gathered = [None, None]
    dist.all_gather_object(gathered, {k: v for k, v in res.items() if k != "outputs"})
    if rank == 0:
        summary = {"stages": gathered, "n": len(texts), "bs": a.bs, "wall_s": round(total, 3), "throughput_ex_per_s": res["throughput_ex_per_s"],
                   "mean_batch_latency_s": round(statistics.mean(lat), 3), "outputs": outs}
        print(json.dumps({k: v for k, v in summary.items() if k != "outputs"}))
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
