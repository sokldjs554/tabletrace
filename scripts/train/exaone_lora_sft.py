"""LoRA SFT for a causal LM planner (EXAONE 3.5 / 4.0) on the TableTrace program format.

NOT RUN in this project: the container has no GPU and huggingface.co is blocked (docs/experiments/exaone.md).
Prepared so the same data / grammar can be used with a decoder-only model. Expected: 1x A100 80GB,
2.4B model, ~30 min for 2 epochs over data/ko/train.jsonl + synthetic_train.jsonl.

  python scripts/train/exaone_lora_sft.py --model LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct \
      --train data/ko/train.jsonl data/ko/synthetic_train.jsonl --corpus data/ko/documents.jsonl --out experiments/exaone_lora
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from tabletrace.service.engines import SYSTEM_PROMPT
from tabletrace.training.data import build_examples, load_docs, read_records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--corpus", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--bs", type=int, default=4)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-len", type=int, default=768)
    ap.add_argument("--lora-r", type=int, default=16)
    a = ap.parse_args()
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=torch.bfloat16, device_map="auto")
    model = get_peft_model(model, LoraConfig(r=a.lora_r, lora_alpha=2 * a.lora_r, lora_dropout=0.05, target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], task_type="CAUSAL_LM"))
    model.print_trainable_parameters()
    docs = load_docs(*[Path(c) for c in a.corpus])
    exs = build_examples(read_records([Path(p) for p in a.train]), docs, tok, a.max_len - 96, drop_truncated_gold=True)

    def encode(e):
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": e.input_text}]
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        p_ids = tok(prompt, add_special_tokens=False).input_ids
        t_ids = tok(e.target_text + tok.eos_token, add_special_tokens=False).input_ids
        ids = (p_ids + t_ids)[: a.max_len]
        labels = ([-100] * len(p_ids) + t_ids)[: a.max_len]
        return ids, labels

    data = [encode(e) for e in exs]
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=a.lr)
    model.train()
    step = 0
    total = int(len(data) / (a.bs * a.grad_accum) * a.epochs)
    for _epoch in range(int(a.epochs + 0.999)):
        for i in range(0, len(data), a.bs):
            batch = data[i:i + a.bs]
            L = max(len(x[0]) for x in batch)
            ids = torch.tensor([x[0] + [tok.pad_token_id] * (L - len(x[0])) for x in batch]).to(model.device)
            lab = torch.tensor([x[1] + [-100] * (L - len(x[1])) for x in batch]).to(model.device)
            loss = model(input_ids=ids, attention_mask=(ids != tok.pad_token_id), labels=lab).loss / a.grad_accum
            loss.backward()
            if ((i // a.bs) + 1) % a.grad_accum == 0:
                opt.step()
                opt.zero_grad()
                step += 1
                if step % 10 == 0:
                    print({"step": step, "of": total, "loss": round(loss.item() * a.grad_accum, 4)}, flush=True)
                if step >= total:
                    break
    model.save_pretrained(a.out)
    tok.save_pretrained(a.out)
    Path(a.out, "train_info.json").write_text(json.dumps({"n_examples": len(data), "steps": step, "args": vars(a)}, indent=1))


if __name__ == "__main__":
    main()
