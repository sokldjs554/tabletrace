"""Supervised fine-tuning of mT5 on the TableTrace program format (PyTorch + Transformers, CPU or GPU).

Example:
  python -m tabletrace.training.sft --model models/mt5-small-base \
      --train data/ko/train.jsonl data/ko/synthetic_train.jsonl --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl \
      --corpus data/ko/documents.jsonl --out experiments/sft_ko/model --epochs 2 --bs 8 --lr 3e-4

Writes <out>/ (best checkpoint by dev verified-EM), <out>/../train_log.jsonl, <out>/../summary.json.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import time
from pathlib import Path

import psutil
import torch

from tabletrace.training.data import build_examples, load_docs, read_records


def set_seed(s: int) -> None:
    random.seed(s)
    torch.manual_seed(s)


def collate(tok, batch, max_in, max_out):
    enc = tok([e.input_text for e in batch], return_tensors="pt", padding=True, truncation=True, max_length=max_in)
    lab = tok([e.target_text for e in batch], return_tensors="pt", padding=True, truncation=True, max_length=max_out).input_ids
    lab[lab == tok.pad_token_id] = -100
    return enc, lab


def evaluate(model, tok, examples, bs, max_in, max_out) -> dict:
    """Greedy decode; compare the whole program string and the answer field with the target."""
    from tabletrace.agent.program import ProgramParseError, parse
    from tabletrace.verify.verifier import resolve

    model.eval()
    exact = ans_ok = parse_fail = 0
    for i in range(0, len(examples), bs):
        chunk = examples[i:i + bs]
        enc = tok([e.input_text for e in chunk], return_tensors="pt", padding=True, truncation=True, max_length=max_in)
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=max_out, do_sample=False, num_beams=1)
        for e, raw in zip(chunk, tok.batch_decode(out, skip_special_tokens=True), strict=True):
            exact += int(raw.strip() == e.target_text.strip())
            try:
                prog = parse(raw, e.table.id)
            except ProgramParseError:
                parse_fail += 1
                prog = None
            res = resolve(e.question, e.table, prog, context=e.context)
            gold_res = resolve(e.question, e.table_full or e.table, e.gold, context=e.context_full or e.context)
            if res.status == gold_res.status and (res.answer or "").strip().lower() == (gold_res.answer or "").strip().lower():
                ans_ok += 1
    model.train()
    n = max(1, len(examples))
    return {"n": len(examples), "program_exact": exact / n, "verified_em": ans_ok / n, "parse_fail": parse_fail / n}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--dev", nargs="+", required=True)
    ap.add_argument("--corpus", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--bs", type=int, default=8)
    ap.add_argument("--grad-accum", type=int, default=1)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--warmup", type=float, default=0.05)
    ap.add_argument("--max-in", type=int, default=512)
    ap.add_argument("--max-out", type=int, default=64)
    ap.add_argument("--max-steps", type=int, default=0, help="stop early (smoke tests)")
    ap.add_argument("--max-train", type=int, default=0)
    ap.add_argument("--eval-bs", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--log-every", type=int, default=10)
    a = ap.parse_args()
    if a.threads:
        torch.set_num_threads(a.threads)
    set_seed(a.seed)
    from transformers import MT5ForConditionalGeneration, PreTrainedTokenizerFast

    out = Path(a.out)
    run_dir = out.parent
    run_dir.mkdir(parents=True, exist_ok=True)
    tok = PreTrainedTokenizerFast.from_pretrained(a.model)
    model = MT5ForConditionalGeneration.from_pretrained(a.model)
    docs = load_docs(*[Path(c) for c in a.corpus])
    train_recs = read_records([Path(p) for p in a.train])
    dev_recs = read_records([Path(p) for p in a.dev])
    train = build_examples(train_recs, docs, tok, a.max_in, drop_truncated_gold=True)
    dev = build_examples(dev_recs, docs, tok, a.max_in, drop_truncated_gold=False)
    random.shuffle(train)
    if a.max_train:
        train = train[: a.max_train]
    steps_per_epoch = math.ceil(len(train) / (a.bs * a.grad_accum))
    total_steps = int(steps_per_epoch * a.epochs) if not a.max_steps else a.max_steps
    warm = max(1, int(total_steps * a.warmup))
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.0)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * max(0.0, (total_steps - s) / max(1, total_steps - warm)) if s >= warm else (s + 1) / warm)
    info = {
        "args": vars(a), "n_train": len(train), "n_train_dropped_truncated": len(train_recs) - len(train), "n_dev": len(dev),
        "steps_per_epoch": steps_per_epoch, "total_steps": total_steps, "params": sum(p.numel() for p in model.parameters()),
        "hardware": {"cpu": platform.processor() or platform.machine(), "threads": torch.get_num_threads(),
                     "cuda": torch.cuda.is_available(), "ram_gb": round(psutil.virtual_memory().total / 1e9, 1)},
        "torch": torch.__version__, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "train_sources": dict(sorted((s, sum(1 for e in train if e.source == s)) for s in {e.source for e in train})),
    }
    (run_dir / "config.json").write_text(json.dumps(info, ensure_ascii=False, indent=1))
    log = open(run_dir / "train_log.jsonl", "a", encoding="utf-8")  # noqa: SIM115
    t0 = time.time()
    model.train()
    step, best, history = 0, -1.0, []
    done = False
    epoch = 0
    while not done:
        random.shuffle(train)
        for i in range(0, len(train), a.bs):
            batch = train[i:i + a.bs]
            enc, lab = collate(tok, batch, a.max_in, a.max_out)
            loss = model(**enc, labels=lab).loss / a.grad_accum
            loss.backward()
            if ((i // a.bs) + 1) % a.grad_accum != 0:
                continue
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            if step % a.log_every == 0 or step == 1:
                rec = {"step": step, "epoch": round(step / steps_per_epoch, 3), "loss": round(loss.item() * a.grad_accum, 4),
                       "lr": sched.get_last_lr()[0], "elapsed_s": round(time.time() - t0, 1),
                       "rss_gb": round(psutil.Process(os.getpid()).memory_info().rss / 1e9, 2)}
                log.write(json.dumps(rec) + "\n")
                log.flush()
                print(rec, flush=True)
            if step >= total_steps:
                done = True
                break
        epoch += 1
        ev = evaluate(model, tok, dev, a.eval_bs, a.max_in, a.max_out)
        ev.update({"epoch": epoch, "step": step, "elapsed_s": round(time.time() - t0, 1)})
        history.append(ev)
        log.write(json.dumps({"eval": ev}) + "\n")
        log.flush()
        print("EVAL", ev, flush=True)
        if ev["verified_em"] > best:
            best = ev["verified_em"]
            model.save_pretrained(out, safe_serialization=True)
            tok.save_pretrained(out)
            cfg = json.loads((out / "config.json").read_text())
            cfg["tie_word_embeddings"] = False
            (out / "config.json").write_text(json.dumps(cfg, indent=2))
            print("saved best ->", out, flush=True)
    summary = {**info, "finished": time.strftime("%Y-%m-%dT%H:%M:%S"), "wall_s": round(time.time() - t0, 1),
               "steps": step, "epochs_done": epoch, "dev_history": history, "best_dev_verified_em": best}
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print("DONE", json.dumps({k: summary[k] for k in ["wall_s", "steps", "best_dev_verified_em"]}))


if __name__ == "__main__":
    main()
