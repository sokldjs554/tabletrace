"""LoRA SFT for a causal-LM planner (EXAONE 3.5 / 4.0) on the TableTrace program format.

Written for a single Colab / Kaggle GPU. Not run on a real EXAONE model in the CPU container (no GPU, huggingface.co
blocked); the training loop itself is smoke-tested on a tiny random causal LM (tests/test_lora_sft_smoke.py).

  python scripts/train/exaone_lora_sft.py --model LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct --trust-remote-code \
      --train data/ko/train.jsonl data/ko/synthetic_train.jsonl data/ko/text2_train.jsonl --corpus data/ko/documents.jsonl \
      --out experiments/exaone_lora --merge

dtype: bf16 on Ampere or newer (A100, L4, H100), fp16 + loss scaling on a T4 (Colab free tier, Kaggle). `--dtype auto` picks.
Output: the LoRA adapter in --out, and with --merge a plain merged model in --out/merged that `vllm serve` / SGLang load directly.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "serving"))
from fix_tokenizer_config import portable_model_dir

from tabletrace.model.serialize import TABLE_FORMATS, set_table_format
from tabletrace.service.engines import SYSTEM_PROMPT
from tabletrace.training.data import build_examples, load_docs, read_records


def pick_dtype(name: str) -> torch.dtype:
    if name == "auto":
        # torch.cuda.is_bf16_supported() counts emulated bf16 on Turing (T4) as supported, so an owner's T4 run trained in
        # emulated bf16 (train_info.json: dtype torch.bfloat16). Decide by compute capability instead: bf16 on sm80+, fp16 below.
        if torch.cuda.is_available():
            name = "bf16" if torch.cuda.get_device_capability(0)[0] >= 8 else "fp16"
        else:
            name = "fp32"
    return {"bf16": torch.bfloat16, "fp16": torch.float16, "fp32": torch.float32}[name]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--corpus", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dtype", choices=["auto", "bf16", "fp16", "fp32"], default="auto")
    ap.add_argument("--trust-remote-code", action="store_true", help="EXAONE 3.5 ships its own modeling code")
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--bs", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-len", type=int, default=768)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--grad-ckpt", action="store_true", help="gradient checkpointing: less memory, slower")
    ap.add_argument("--merge", action="store_true", help="also save the merged model to <out>/merged")
    ap.add_argument("--limit", type=int, default=0, help="use only the first N training examples (smoke tests)")
    ap.add_argument("--tokenizer", default=None, help="defaults to --model")
    ap.add_argument("--table-format", choices=TABLE_FORMATS, default="plain",
                    help="plain: cells separated by ' | ' (all stored results). colid: every cell carries its column index "
                         "(about 26%% more tokens: use --max-len 896 for the same row budget as plain at 768)")
    ap.add_argument("--seed", type=int, default=0, help="shuffling, the sample of --extra-train and the adapter initialisation")
    ap.add_argument("--extra-train", nargs="*", default=[], help="more training files (e.g. data/ko/pool_train.jsonl.gz); not affected by --limit")
    ap.add_argument("--extra-n", type=int, default=0, help="use a random sample of this many examples from --extra-train (0: all)")
    ap.add_argument("--loop", choices=["builtin", "owner"], default="builtin",
                    help="owner: label masking, learning-rate schedule and the loop come from tabletrace.training.lm_loop, "
                         "written by the repository owner (docs/rewrite/06_training_code.md). builtin: the loop below (constant rate)")
    ap.add_argument("--warmup-steps", type=int, default=0, help="--loop owner only: linear warm-up, then linear decay to zero")
    a = ap.parse_args()
    lm_loop = None
    if a.loop == "owner":
        try:
            from tabletrace.training import lm_loop
        except ImportError as e:
            raise SystemExit("tabletrace/training/lm_loop.py is missing. --loop owner uses the training loop written by the repository "
                             "owner: see docs/rewrite/06_training_code.md, or run with --loop builtin.") from e
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    # Multi-GPU: started with `torchrun --nproc_per_node N`, every process trains on its own shard of the data and
    # DistributedDataParallel averages the gradients. Rank 0 logs and saves.
    world, rank, local_rank = (int(os.environ.get(k, d)) for k, d in (("WORLD_SIZE", "1"), ("RANK", "0"), ("LOCAL_RANK", "0")))
    ddp = world > 1
    if ddp:
        torch.distributed.init_process_group("nccl" if torch.cuda.is_available() else "gloo")
    main_rank = rank == 0
    torch.manual_seed(a.seed)
    dtype = pick_dtype(a.dtype)
    use_scaler = dtype == torch.float16 and torch.cuda.is_available()
    tok = AutoTokenizer.from_pretrained(a.tokenizer or a.model, trust_remote_code=a.trust_remote_code)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    device_map = ({"": local_rank} if ddp else "auto") if torch.cuda.is_available() else None
    model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=dtype, device_map=device_map, trust_remote_code=a.trust_remote_code)
    if a.grad_ckpt:
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
    try:
        model = get_peft_model(model, LoraConfig(r=a.lora_r, lora_alpha=2 * a.lora_r, lora_dropout=0.05,
                                                 target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], task_type="CAUSAL_LM"))
    except ImportError as e:
        if "torchao" in str(e):
            raise SystemExit("peft found an old torchao (Colab ships 0.10.0, peft needs >= 0.16). This project does not use torchao: run `pip uninstall -y torchao` and start again.") from e
        raise
    if main_rank:
        model.print_trainable_parameters()
    docs = load_docs(*[Path(c) for c in a.corpus])
    set_table_format(a.table_format)
    exs = build_examples(read_records([Path(p) for p in a.train]), docs, tok, a.max_len - 96, drop_truncated_gold=True)
    if a.limit:
        exs = exs[: a.limit]
    if a.extra_train:
        extra = build_examples(read_records([Path(p) for p in a.extra_train]), docs, tok, a.max_len - 96, drop_truncated_gold=True)
        if a.extra_n and a.extra_n < len(extra):
            extra = random.Random(a.seed).sample(extra, a.extra_n)
        exs = exs + extra

    def encode(e):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": e.input_text}]
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        p_ids = tok(prompt, add_special_tokens=False).input_ids
        t_ids = tok(e.target_text + tok.eos_token, add_special_tokens=False).input_ids
        return (p_ids + t_ids)[: a.max_len], ([-100] * len(p_ids) + t_ids)[: a.max_len], min(len(p_ids), a.max_len)

    data = [encode(e) for e in exs]
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr)
    scaler = torch.amp.GradScaler("cuda") if use_scaler else None
    dev = next(model.parameters()).device
    n_examples = len(data)
    total = max(1, int(len(data) / world / (a.bs * a.grad_accum) * a.epochs))
    rnd = random.Random(a.seed)
    model.train()
    net = torch.nn.parallel.DistributedDataParallel(model, device_ids=[local_rank] if torch.cuda.is_available() else None) if ddp else model

    def shard(items):
        """This process's part of the freshly shuffled data. Every rank shuffles with the same generator, so the shards
        of one epoch never overlap."""
        return items[rank::world] if ddp else items

    step = micro = 0
    log = []
    t0 = time.time()
    if lm_loop is not None:
        def owner_batches():
            for _epoch in range(int(a.epochs + 0.999)):
                rnd.shuffle(data)
                part = shard(data)
                for i in range(0, len(part), a.bs):
                    batch = part[i:i + a.bs]
                    n = max(len(x[0]) for x in batch)
                    ids = torch.tensor([x[0] + [tok.pad_token_id] * (n - len(x[0])) for x in batch]).to(dev)
                    att = torch.tensor([[1] * len(x[0]) + [0] * (n - len(x[0])) for x in batch]).to(dev)
                    yield {"input_ids": ids, "attention_mask": att, "labels": lm_loop.mask_labels(ids, [x[2] for x in batch], att)}

        def forward(**batch):                      # mixed precision stays here; the loop itself knows nothing about it
            with torch.autocast(device_type=dev.type, dtype=dtype, enabled=dtype != torch.float32):
                return net(**batch)

        def on_step(i, loss, lr):
            log.append({"step": i + 1, "of": total, "loss": round(loss, 4), "lr": lr})
            if main_rank and ((i + 1) % 10 == 0 or i + 1 == total):
                print(log[-1], flush=True)

        step = len(lm_loop.train(forward, owner_batches(), opt, total_steps=total, base_lr=a.lr, warmup_steps=a.warmup_steps,
                                 grad_accum=a.grad_accum, max_grad_norm=1.0, scaler=scaler, on_step=on_step))
    for _epoch in range(int(a.epochs + 0.999) if lm_loop is None else 0):
        rnd.shuffle(data)
        part = shard(data)
        for i in range(0, len(part), a.bs):
            batch = part[i:i + a.bs]
            n = max(len(x[0]) for x in batch)
            ids = torch.tensor([x[0] + [tok.pad_token_id] * (n - len(x[0])) for x in batch]).to(dev)
            lab = torch.tensor([x[1] + [-100] * (n - len(x[1])) for x in batch]).to(dev)
            att = torch.tensor([[1] * len(x[0]) + [0] * (n - len(x[0])) for x in batch]).to(dev)
            with torch.autocast(device_type=dev.type, dtype=dtype, enabled=dtype != torch.float32):
                loss = net(input_ids=ids, attention_mask=att, labels=lab).loss / a.grad_accum
            (scaler.scale(loss) if scaler else loss).backward()
            micro += 1
            if micro % a.grad_accum == 0:
                if scaler:
                    scaler.unscale_(opt)
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                if scaler:
                    scaler.step(opt)
                    scaler.update()
                else:
                    opt.step()
                opt.zero_grad(set_to_none=True)
                step += 1
                log.append({"step": step, "of": total, "loss": round(loss.item() * a.grad_accum, 4)})
                if main_rank and (step % 10 == 0 or step == total):
                    print(log[-1], flush=True)
                if step >= total:
                    break
        if step >= total:
            break
    if ddp:
        torch.distributed.destroy_process_group()
    if not main_rank:
        return
    out = Path(a.out)
    model.save_pretrained(out)
    tok.save_pretrained(out)
    if a.merge:
        merged = model.merge_and_unload()
        merged.save_pretrained(out / "merged", safe_serialization=True)
        tok.save_pretrained(out / "merged")
        portable_model_dir(out / "merged")     # SGLang pins transformers 4.57, which cannot read the 5.x tokenizer_config.json
    portable_model_dir(out)
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    (out / "train_info.json").write_text(json.dumps({"n_examples": n_examples, "world_size": world, "steps": step, "dtype": str(dtype), "wall_s": round(time.time() - t0, 1), "gpu": gpu,
                                                    "loop": "tabletrace.training.lm_loop (owner-written)" if lm_loop is not None else "builtin",
                                                    "args": vars(a), "loss_log": log}, indent=1))


if __name__ == "__main__":
    main()
