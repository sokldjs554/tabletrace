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
import random
from pathlib import Path

import torch

from tabletrace.service.engines import SYSTEM_PROMPT
from tabletrace.training.data import build_examples, load_docs, read_records


def pick_dtype(name: str) -> torch.dtype:
    if name == "auto":
        name = "bf16" if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else ("fp16" if torch.cuda.is_available() else "fp32")
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
    a = ap.parse_args()
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    dtype = pick_dtype(a.dtype)
    use_scaler = dtype == torch.float16 and torch.cuda.is_available()
    tok = AutoTokenizer.from_pretrained(a.tokenizer or a.model, trust_remote_code=a.trust_remote_code)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=dtype, device_map="auto" if torch.cuda.is_available() else None,
                                                 trust_remote_code=a.trust_remote_code)
    if a.grad_ckpt:
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=a.lora_r, lora_alpha=2 * a.lora_r, lora_dropout=0.05,
                                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], task_type="CAUSAL_LM"))
    model.print_trainable_parameters()
    docs = load_docs(*[Path(c) for c in a.corpus])
    exs = build_examples(read_records([Path(p) for p in a.train]), docs, tok, a.max_len - 96, drop_truncated_gold=True)
    if a.limit:
        exs = exs[: a.limit]

    def encode(e):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": e.input_text}]
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        p_ids = tok(prompt, add_special_tokens=False).input_ids
        t_ids = tok(e.target_text + tok.eos_token, add_special_tokens=False).input_ids
        return (p_ids + t_ids)[: a.max_len], ([-100] * len(p_ids) + t_ids)[: a.max_len]

    data = [encode(e) for e in exs]
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=a.lr)
    scaler = torch.amp.GradScaler("cuda") if use_scaler else None
    dev = next(model.parameters()).device
    total = max(1, int(len(data) / (a.bs * a.grad_accum) * a.epochs))
    rnd = random.Random(0)
    model.train()
    step = micro = 0
    log = []
    for _epoch in range(int(a.epochs + 0.999)):
        rnd.shuffle(data)
        for i in range(0, len(data), a.bs):
            batch = data[i:i + a.bs]
            n = max(len(x[0]) for x in batch)
            ids = torch.tensor([x[0] + [tok.pad_token_id] * (n - len(x[0])) for x in batch]).to(dev)
            lab = torch.tensor([x[1] + [-100] * (n - len(x[1])) for x in batch]).to(dev)
            att = torch.tensor([[1] * len(x[0]) + [0] * (n - len(x[0])) for x in batch]).to(dev)
            with torch.autocast(device_type=dev.type, dtype=dtype, enabled=dtype != torch.float32):
                loss = model(input_ids=ids, attention_mask=att, labels=lab).loss / a.grad_accum
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
                if step % 10 == 0 or step == total:
                    print(log[-1], flush=True)
                if step >= total:
                    break
        if step >= total:
            break
    out = Path(a.out)
    model.save_pretrained(out)
    tok.save_pretrained(out)
    if a.merge:
        merged = model.merge_and_unload()
        merged.save_pretrained(out / "merged", safe_serialization=True)
        tok.save_pretrained(out / "merged")
    (out / "train_info.json").write_text(json.dumps({"n_examples": len(data), "steps": step, "dtype": str(dtype), "args": vars(a), "loss_log": log}, indent=1))


if __name__ == "__main__":
    main()
