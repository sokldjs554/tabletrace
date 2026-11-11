"""Train and evaluate the structure-aware table encoder (src/tabletrace/encoder) on CPU.

    # self-supervised pretraining on tables only (corrupt-cell detection); dev and test tables are never read
    python scripts/train/table_encoder.py pretrain --out experiments/encoder/pretrain --steps 1500

    # cell selection on the Korean lookup questions; --structure off is the same model without row/column embeddings
    python scripts/train/table_encoder.py finetune --name plain     --structure off
    python scripts/train/table_encoder.py finetune --name structure --structure on
    python scripts/train/table_encoder.py finetune --name structure_pt --structure on --init experiments/encoder/pretrain
    python scripts/train/table_encoder.py finetune --name structure_pool --structure on --train pool --epochs 1

Every finetune run scores the 180 dev and 539 test questions of the main (table-level) split and writes
experiments/encoder/<name>/{metrics.json, test_predictions.jsonl}. Weights go to experiments/encoder/<name>/model/
(not committed).
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_error import wilson  # noqa: E402
from tabletrace.corpus.store import CorpusStore  # noqa: E402
from tabletrace.encoder.corrupt import cell_pool, corrupt_table  # noqa: E402
from tabletrace.encoder.features import Featurizer, collate  # noqa: E402
from tabletrace.encoder.model import TableEncoder, load_backbone  # noqa: E402
from tabletrace.schema import Table  # noqa: E402

BACKBONE = "models/mt5-small-base"
KO = ROOT / "data" / "ko"


def read_jsonl(path: Path) -> list[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def pool_tables() -> dict[str, Table]:
    return {t["id"]: Table(**t) for d in read_jsonl(KO / "pool_documents.jsonl.gz") for t in d["tables"]}


def tokenizer(path: str):
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(ROOT / path)


def groups(model: TableEncoder, lr: float, head_lr: float) -> list[dict]:
    new = [p for n, p in model.named_parameters() if p.requires_grad and not n.startswith("backbone.")]
    old = [p for n, p in model.named_parameters() if p.requires_grad and n.startswith("backbone.")]
    return [{"params": old, "lr": lr}, {"params": new, "lr": head_lr}]


def schedule(opt, total: int, warmup: float = 0.06):
    w = max(1, int(total * warmup))
    return torch.optim.lr_scheduler.LambdaLR(opt, lambda s: (s + 1) / w if s < w else max(0.0, (total - s) / max(1, total - w)))


def batches(n: int, size: int, lengths: list[int], rng: random.Random) -> list[list[int]]:
    """Shuffled batches of similar length: shuffle, cut into chunks of 50 batches, sort each chunk by length."""
    order = list(range(n))
    rng.shuffle(order)
    out = []
    for i in range(0, n, size * 50):
        chunk = sorted(order[i:i + size * 50], key=lambda j: lengths[j])
        out.extend(chunk[k:k + size] for k in range(0, len(chunk), size))
    rng.shuffle(out)
    return out


# ---------------------------------------------------------------- pretraining

def pretrain(a) -> None:
    torch.manual_seed(a.seed)
    rng = random.Random(a.seed)
    store = CorpusStore.from_disk()
    held = {json.loads(line)["table_id"] for s in ("dev", "test") for line in open(KO / f"{s}.jsonl", encoding="utf-8")}
    tables = [t for t in store.tables.values() if t.lang == "ko" and t.id not in held and t.id.startswith("ko_")]
    tables += list(pool_tables().values())
    assert not any(t.id in held for t in tables)
    rng.shuffle(tables)
    probe, tables = tables[:200], tables[200:]
    pool = cell_pool(tables)
    tok = tokenizer(a.backbone)
    fz = Featurizer(tok, max_len=a.max_len)
    model = TableEncoder(load_backbone(ROOT / a.backbone), structure=True)
    opt = torch.optim.AdamW(groups(model, a.lr, a.head_lr), weight_decay=0.01)
    sched = schedule(opt, a.steps)
    probe_rng = random.Random(1)
    probe_items = [corrupt_table(t, pool, probe_rng, a.rate) for t in probe]

    def probe_score() -> dict:
        model.eval()
        tp = fp = fn = tn = 0
        with torch.no_grad():
            for i in range(0, len(probe_items), a.batch):
                chunk = probe_items[i:i + a.batch]
                feats = [fz("", t) for t, _ in chunk]
                b = collate(feats, tok.pad_token_id, cell_labels=[lab[: f.n_cells] for (_, lab), f in zip(chunk, feats, strict=True)])
                pred = model(**b, head="corrupt") > 0
                gold = b["cell_labels"] > 0.5
                m = b["cell_mask"]
                tp += int((pred & gold & m).sum()); fp += int((pred & ~gold & m).sum())
                fn += int((~pred & gold & m).sum()); tn += int((~pred & ~gold & m).sum())
        model.train()
        p, r = tp / max(1, tp + fp), tp / max(1, tp + fn)
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / max(1e-9, p + r), 4),
                "cells": tp + fp + fn + tn, "corrupted": tp + fn}

    log = [{"step": 0, **probe_score()}]
    print(log[-1], flush=True)
    model.train()
    t0 = time.time()
    pos_weight = torch.tensor((1 - a.rate) / a.rate)
    for step in range(1, a.steps + 1):
        chunk = [corrupt_table(t, pool, rng, a.rate) for t in rng.sample(tables, a.batch)]
        feats = [fz("", t) for t, _ in chunk]
        b = collate(feats, tok.pad_token_id, cell_labels=[lab[: f.n_cells] for (_, lab), f in zip(chunk, feats, strict=True)])
        logits = model(**b, head="corrupt")
        loss = torch.nn.functional.binary_cross_entropy_with_logits(logits[b["cell_mask"]], b["cell_labels"][b["cell_mask"]], pos_weight=pos_weight)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); sched.step(); opt.zero_grad()
        if step % a.log_every == 0 or step == a.steps:
            log.append({"step": step, "loss": round(loss.item(), 4), "minutes": round((time.time() - t0) / 60, 1), **probe_score()})
            print(log[-1], flush=True)
    out = ROOT / a.out
    model.save(out / "model", {"backbone": a.backbone, "stage": "pretrain"})
    (out / "metrics.json").write_text(json.dumps({
        "objective": "corrupt-cell detection", "backbone": a.backbone, "tables": len(tables), "probe_tables": len(probe),
        "steps": a.steps, "batch": a.batch, "rate": a.rate, "seed": a.seed, "minutes": round((time.time() - t0) / 60, 1),
        "probe_before": log[0], "probe_after": log[-1], "log": log}, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- cell selection

def examples(rows: list[dict], tables: dict[str, Table], fz: Featurizer) -> tuple[list, list[int], int]:
    feats, targets, lost = [], [], 0
    for r in rows:
        f = fz(r["question"], tables[r["table_id"]])
        target = f.cell_of(*r["gold_cells"][0])
        if target is None:
            lost += 1                      # the gold row did not fit; kept for scoring (counts as wrong), skipped in training
        feats.append(f)
        targets.append(-1 if target is None else target)
    return feats, targets, lost


def score(model: TableEncoder, tok, rows: list[dict], feats: list, targets: list[int], batch: int) -> tuple[dict, list[dict]]:
    model.eval()
    preds = []
    order = sorted(range(len(rows)), key=lambda i: len(feats[i].input_ids))
    with torch.no_grad():
        for i in range(0, len(order), batch):
            idx = order[i:i + batch]
            b = collate([feats[j] for j in idx], tok.pad_token_id)
            logits = model(**b)
            top = logits.topk(2, dim=1)
            for k, j in enumerate(idx):
                row, col = feats[j].position(int(top.indices[k, 0]))
                gr, gc = rows[j]["gold_cells"][0]
                preds.append({"qid": rows[j]["qid"], "gold": [gr, gc], "pred": [row, col], "cell": [row, col] == [gr, gc],
                              "row": row == gr, "col": col == gc, "margin": round(float(top.values[k, 0] - top.values[k, 1]), 4),
                              "gold_row_dropped": targets[j] < 0})
    model.train()
    n = len(preds)
    out = {"n": n, "cell": wilson(sum(p["cell"] for p in preds), n), "row": wilson(sum(p["row"] for p in preds), n),
           "col": wilson(sum(p["col"] for p in preds), n), "gold_row_dropped": sum(p["gold_row_dropped"] for p in preds)}
    return out, sorted(preds, key=lambda p: p["qid"])


def finetune(a) -> None:
    torch.manual_seed(a.seed)
    rng = random.Random(a.seed)
    store = CorpusStore.from_disk()
    tables = dict(store.tables)
    train_rows = read_jsonl(KO / "train.jsonl")
    if a.train == "pool":
        tables.update(pool_tables())
        extra = read_jsonl(KO / "pool_train.jsonl.gz")
        if a.pool_n and a.pool_n < len(extra):
            extra = random.Random(a.seed).sample(extra, a.pool_n)
        train_rows = train_rows + extra
    if a.limit:
        train_rows = train_rows[: a.limit]
    tok = tokenizer(a.backbone)
    fz = Featurizer(tok, max_len=a.max_len)
    if a.init:
        model = TableEncoder.load(ROOT / a.init / "model", ROOT / a.backbone)
        if a.structure == "off":
            raise SystemExit("--init carries row/column embeddings; use it with --structure on")
    else:
        model = TableEncoder(load_backbone(ROOT / a.backbone), structure=a.structure == "on")
    tr_feats, tr_targets, tr_lost = examples(train_rows, tables, fz)
    usable = [i for i, t in enumerate(tr_targets) if t >= 0]
    sets = {s: read_jsonl(KO / f"{s}.jsonl") for s in ("dev", "test")}
    if a.limit:
        sets = {s: rows[: max(16, a.limit // 4)] for s, rows in sets.items()}
    packed = {s: examples(rows, tables, fz) for s, rows in sets.items()}
    steps = (len(usable) + a.batch - 1) // a.batch * a.epochs
    opt = torch.optim.AdamW(groups(model, a.lr, a.head_lr), weight_decay=0.01)
    sched = schedule(opt, steps)
    model.train()
    t0, step, log = time.time(), 0, []
    for epoch in range(a.epochs):
        for idx in batches(len(usable), a.batch, [len(tr_feats[i].input_ids) for i in usable], rng):
            ids = [usable[i] for i in idx]
            b = collate([tr_feats[i] for i in ids], tok.pad_token_id, targets=[tr_targets[i] for i in ids])
            loss = torch.nn.functional.cross_entropy(model(**b), b["targets"])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad()
            step += 1
            if step % a.log_every == 0:
                print({"step": step, "of": steps, "loss": round(loss.item(), 4), "minutes": round((time.time() - t0) / 60, 1)}, flush=True)
        dev, _ = score(model, tok, sets["dev"], packed["dev"][0], packed["dev"][1], a.batch)
        log.append({"epoch": epoch + 1, "dev_cell": dev["cell"]["rate"], "minutes": round((time.time() - t0) / 60, 1)})
        print(log[-1], flush=True)
    out = ROOT / "experiments" / "encoder" / a.name
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    for s in ("dev", "test"):
        results[s], preds = score(model, tok, sets[s], packed[s][0], packed[s][1], a.batch)
        if s == "test":
            with open(out / "test_predictions.jsonl", "w", encoding="utf-8") as f:
                for p in preds:
                    f.write(json.dumps(p, ensure_ascii=False) + "\n")
    row_norm = float(model.row_emb.weight.detach().norm()) if model.structure else None
    col_norm = float(model.col_emb.weight.detach().norm()) if model.structure else None
    (out / "metrics.json").write_text(json.dumps({
        "name": a.name, "backbone": a.backbone, "structure_embeddings": model.structure, "init": a.init, "train_set": a.train, "pool_n": a.pool_n if a.train == "pool" else None,
        "train_questions": len(usable), "train_questions_gold_row_did_not_fit": tr_lost, "epochs": a.epochs, "steps": step, "batch": a.batch,
        "lr": a.lr, "head_lr": a.head_lr, "max_len": a.max_len, "seed": a.seed, "minutes": round((time.time() - t0) / 60, 1),
        "trainable_parameters": sum(p.numel() for p in model.parameters() if p.requires_grad),
        "row_embedding_norm": row_norm, "col_embedding_norm": col_norm, "dev_by_epoch": log, **results}, ensure_ascii=False, indent=1), encoding="utf-8")
    model.save(out / "model", {"backbone": a.backbone, "stage": "finetune", "name": a.name})
    print(json.dumps({s: {k: (v["rate"] if isinstance(v, dict) else v) for k, v in results[s].items()} for s in results}, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("pretrain", "finetune"):
        p = sub.add_parser(name)
        p.add_argument("--backbone", default=BACKBONE)
        p.add_argument("--batch", type=int, default=16)
        p.add_argument("--lr", type=float, default=1e-4)
        p.add_argument("--head-lr", type=float, default=1e-3)
        p.add_argument("--max-len", type=int, default=512)
        p.add_argument("--seed", type=int, default=13)
        p.add_argument("--threads", type=int, default=0)
        p.add_argument("--log-every", type=int, default=50)
    p = sub.choices["pretrain"]
    p.add_argument("--out", default="experiments/encoder/pretrain")
    p.add_argument("--steps", type=int, default=1500)
    p.add_argument("--rate", type=float, default=0.15)
    p = sub.choices["finetune"]
    p.add_argument("--name", required=True)
    p.add_argument("--structure", choices=["on", "off"], default="on")
    p.add_argument("--init", default=None, help="a pretrain output directory")
    p.add_argument("--train", choices=["main", "pool"], default="main")
    p.add_argument("--pool-n", type=int, default=0, help="--train pool: a random sample of this many pool questions (0: all)")
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--limit", type=int, default=0, help="smoke test: use only the first N training questions")
    a = ap.parse_args()
    if a.threads:
        torch.set_num_threads(a.threads)
    (pretrain if a.cmd == "pretrain" else finetune)(a)


if __name__ == "__main__":
    main()
