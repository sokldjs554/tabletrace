"""GRPO for a LoRA-tuned causal LM (EXAONE) with the verifier's outcome as the reward. GPU script; a CPU smoke test
runs it on a tiny random model (tests/test_exaone_grpo_smoke.py).

Division of work
----------------
This script loads the model and the data, samples programs, keeps the log and saves the adapter. The parts that decide
what is learned are imported from modules the repository owner writes (docs/rewrite/06_training_code.md):

    tabletrace.training.evidence_reward.evidence_reward     reward of one sampled program
    tabletrace.training.grpo.group_advantages               (r - group mean) / (group std + eps)
    tabletrace.training.grpo.completion_logprobs            log-probabilities of the sampled tokens
    tabletrace.training.grpo.policy_gradient_loss           -sum(A * logp) / tokens
    tabletrace.training.grpo.kl_k3                          distance to the starting adapter (only when --beta > 0)

One step: pick P prompts, sample G programs for each from the current policy, score them, normalise the rewards inside
each group, and take one policy-gradient step on those samples (on-policy, no importance ratio).

    python scripts/train/exaone_grpo.py --model LGAI-EXAONE/EXAONE-4.0-1.2B --adapter experiments/exaone_lora_300 \
        --train data/ko/train.jsonl data/ko/synthetic_train.jsonl --corpus data/ko/documents.jsonl \
        --dev data/ko/dev.jsonl --out experiments/exaone_grpo --steps 200 --merge
"""
from __future__ import annotations

import argparse
import importlib
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "serving"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from exaone_lora_sft import pick_dtype
from fix_tokenizer_config import portable_model_dir

from tabletrace.model.serialize import TABLE_FORMATS, set_table_format
from tabletrace.service.engines import SYSTEM_PROMPT
from tabletrace.training.data import Example, build_examples, load_docs, read_records
from tabletrace.verify.verifier import resolve

LEVELS = ("correct", "repaired", "withheld", "wrong", "unparsable")


def owner_code():
    try:
        reward = importlib.import_module("tabletrace.training.evidence_reward")
        grpo = importlib.import_module("tabletrace.training.grpo")
    except ModuleNotFoundError as e:
        raise SystemExit(f"{e.name} is missing. The reward and the GRPO loss are written by the repository owner: "
                         "see docs/rewrite/06_training_code.md, then run this script again.") from e
    return reward.evidence_reward, grpo


def kind(e: Example) -> str:
    return e.gold.op if e.gold.op in ("abstain", "text", "lookup") else "calc"


def gold_answer(e: Example) -> str | None:
    if e.gold.op == "abstain":
        return None
    if e.gold_answer:
        return e.gold_answer
    return resolve(e.question, e.table_full or e.table, e.gold, context=e.context_full or e.context, entity_check=False).answer


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", default=None, help="LoRA adapter to start from (the SFT model). Without it a new adapter is created")
    ap.add_argument("--tokenizer", default=None)
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--dev", nargs="+", default=[])
    ap.add_argument("--corpus", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dtype", choices=["auto", "bf16", "fp16", "fp32"], default="auto")
    ap.add_argument("--trust-remote-code", action="store_true")
    ap.add_argument("--steps", type=int, default=200)
    ap.add_argument("--prompts", type=int, default=4, help="prompts per step (P)")
    ap.add_argument("--group", type=int, default=8, help="samples per prompt (G)")
    ap.add_argument("--chunk", type=int, default=2, help="sequences per backward pass (memory)")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--beta", type=float, default=0.0, help="weight of the KL term to the starting adapter (0: no reference pass)")
    ap.add_argument("--max-len", type=int, default=768)
    ap.add_argument("--max-new", type=int, default=64)
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--dev-n", type=int, default=64, help="dev questions scored greedily every --eval-every steps")
    ap.add_argument("--eval-every", type=int, default=25)
    ap.add_argument("--entity-check", action="store_true", help="reward with the stricter verifier (subject check on)")
    ap.add_argument("--table-format", choices=TABLE_FORMATS, default="plain")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--reward", choices=["verifier", "random"], default="verifier",
                    help="random: smoke tests only. A seeded random level replaces the reward so that the update path runs on a model that cannot write programs")
    a = ap.parse_args()
    evidence_reward, grpo = owner_code()
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(a.seed)
    torch.manual_seed(a.seed)
    rnd = random.Random(a.seed)
    dtype = pick_dtype(a.dtype)
    cuda = torch.cuda.is_available()
    tok = AutoTokenizer.from_pretrained(a.tokenizer or a.adapter or a.model, trust_remote_code=a.trust_remote_code)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=dtype, device_map="auto" if cuda else None, trust_remote_code=a.trust_remote_code)
    if a.adapter:
        model = PeftModel.from_pretrained(base, a.adapter, is_trainable=True)
        if a.beta > 0:
            model.load_adapter(a.adapter, adapter_name="ref")           # frozen copy of the starting point
    else:
        model = get_peft_model(base, LoraConfig(r=a.lora_r, lora_alpha=2 * a.lora_r, lora_dropout=0.0,
                                                target_modules=["q_proj", "k_proj", "v_proj", "o_proj"], task_type="CAUSAL_LM"))
    model.eval()                                                         # dropout off: the scored log-probs are those sampled from
    params = [p for n, p in model.named_parameters() if p.requires_grad and ".ref." not in n]
    opt = torch.optim.AdamW(params, lr=a.lr, weight_decay=0.0)
    scaler = torch.amp.GradScaler("cuda") if dtype == torch.float16 and cuda else None
    device = next(model.parameters()).device

    docs = load_docs(*[Path(c) for c in a.corpus])
    set_table_format(a.table_format)
    train = build_examples(read_records([Path(p) for p in a.train]), docs, tok, a.max_len - 96, drop_truncated_gold=True)
    dev = build_examples(read_records([Path(p) for p in a.dev]), docs, tok, a.max_len - 96, drop_truncated_gold=True)[: a.dev_n] if a.dev else []
    pools: dict[str, list[Example]] = {}
    for e in train:
        pools.setdefault(kind(e), []).append(e)
    kinds = sorted(pools)

    def prompt_ids(e: Example) -> list[int]:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": e.input_text}]
        return tok(tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True), add_special_tokens=False).input_ids[-(a.max_len - 8):]

    def left_pad(seqs: list[list[int]]) -> tuple[torch.Tensor, torch.Tensor]:
        n = max(len(s) for s in seqs)
        ids = torch.tensor([[tok.pad_token_id] * (n - len(s)) + s for s in seqs], device=device)
        att = torch.tensor([[0] * (n - len(s)) + [1] * len(s) for s in seqs], device=device)
        return ids, att

    def sample(batch: list[Example], n: int, greedy: bool) -> tuple[list[list[int]], list[list[int]]]:
        """-> (prompt ids, completion ids) for every sample, group by group. A completion ends with its first EOS."""
        prompts = [prompt_ids(e) for e in batch]
        ids, att = left_pad(prompts)
        with torch.no_grad(), torch.autocast(device_type=device.type, dtype=dtype, enabled=dtype != torch.float32):
            gen = model.generate(input_ids=ids, attention_mask=att, max_new_tokens=a.max_new, pad_token_id=tok.pad_token_id,
                                 **({"do_sample": False} if greedy else {"do_sample": True, "temperature": a.temperature, "top_p": 1.0, "top_k": 0, "num_return_sequences": n}))
        out_p, out_c = [], []
        for i, row in enumerate(gen[:, ids.size(1):].tolist()):
            cut = row.index(tok.eos_token_id) + 1 if tok.eos_token_id in row else len(row)
            while cut and row[cut - 1] == tok.pad_token_id and tok.pad_token_id != tok.eos_token_id:
                cut -= 1
            out_p.append(prompts[i // (1 if greedy else n)])
            out_c.append(row[:cut] or [tok.eos_token_id])
        return out_p, out_c

    def reference_logits(ids: torch.Tensor, att: torch.Tensor) -> torch.Tensor:
        """Logits of the model the run started from: the frozen copy of the starting adapter, or the base model when
        the adapter was created here (a new LoRA adapter starts as the base model)."""
        with torch.no_grad():
            if a.adapter:
                model.set_adapter("ref")
                try:
                    return model(input_ids=ids, attention_mask=att).logits
                finally:
                    model.set_adapter("default")
            with model.disable_adapter():
                return model(input_ids=ids, attention_mask=att).logits

    def score(e: Example, completion: list[int]) -> tuple[float, dict]:
        text = tok.decode(completion, skip_special_tokens=True).strip()
        if a.reward == "random":
            level = rnd.choice(LEVELS)
            return {"correct": 1.0, "repaired": 0.3, "withheld": 0.0, "wrong": -0.5, "unparsable": -1.0}[level], {"level": level, "parse_ok": True, "op": None}
        return evidence_reward(text, e.question, e.table, gold_answer(e), context=e.context, entity_check=a.entity_check)

    def dev_check() -> dict:
        levels: Counter = Counter()
        total = 0.0
        for i in range(0, len(dev), 8):
            chunk = dev[i:i + 8]
            _, comps = sample(chunk, 1, greedy=True)
            for e, c in zip(chunk, comps, strict=True):
                r, info = score(e, c)
                total += r
                levels[info["level"]] += 1
        return {"n": len(dev), "mean_reward": round(total / max(1, len(dev)), 4), **{k: levels.get(k, 0) for k in LEVELS}}

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "train_log.jsonl", "w", encoding="utf-8")
    history = []
    best = None
    if dev:
        history.append({"step": 0, **dev_check()})
        best = history[-1]["mean_reward"]
        log.write(json.dumps({"dev": history[-1]}) + "\n")
        print("DEV", history[-1], flush=True)
    model.save_pretrained(out, selected_adapters=["default"])            # step 0: if nothing improves, the output is the start
    t0 = time.time()
    updates = 0
    for step in range(1, a.steps + 1):
        batch = [rnd.choice(pools[kinds[(step * a.prompts + i) % len(kinds)]]) for i in range(a.prompts)]
        prompts, comps = sample(batch, a.group, greedy=False)
        scored = [score(batch[i // a.group], c) for i, c in enumerate(comps)]
        rewards = torch.tensor([r for r, _ in scored], dtype=torch.float32).view(a.prompts, a.group)
        adv = grpo.group_advantages(rewards).view(-1).to(device)
        seqs = [p + c for p, c in zip(prompts, comps, strict=True)]
        total_tokens = sum(len(c) for c in comps)
        opt.zero_grad(set_to_none=True)
        pg_sum = kl_sum = 0.0
        for s in range(0, len(seqs), a.chunk):
            sl = slice(s, s + a.chunk)
            if float(adv[sl].abs().sum()) == 0.0 and a.beta == 0:
                continue                                                 # every sample of these groups scored the same: nothing to learn
            n = max(len(x) for x in seqs[sl])
            ids = torch.tensor([x + [tok.pad_token_id] * (n - len(x)) for x in seqs[sl]], device=device)
            att = torch.tensor([[1] * len(x) + [0] * (n - len(x)) for x in seqs[sl]], device=device)
            cmask = torch.tensor([[0] * len(p) + [1] * len(c) + [0] * (n - len(p) - len(c)) for p, c in zip(prompts[sl], comps[sl], strict=True)], device=device)
            with torch.autocast(device_type=device.type, dtype=dtype, enabled=dtype != torch.float32):
                logp, mask = grpo.completion_logprobs(model(input_ids=ids, attention_mask=att).logits.float(), ids, cmask)   # float32 whatever the model's precision
                share = mask.sum() / max(1, total_tokens)                # the loss functions average over their own tokens
                loss = grpo.policy_gradient_loss(logp, mask, adv[sl]) * share
                pg_sum += float(loss)
                if a.beta > 0:
                    ref_logp, _ = grpo.completion_logprobs(reference_logits(ids, att).float(), ids, cmask)
                    kl = grpo.kl_k3(logp, ref_logp, mask) * share
                    kl_sum += float(kl)
                    loss = loss + a.beta * kl
            (scaler.scale(loss) if scaler else loss).backward()
        if scaler:
            scaler.unscale_(opt)
        norm = torch.nn.utils.clip_grad_norm_(params, 1.0)
        applied = bool(torch.isfinite(norm)) and float(norm) > 0
        if applied:
            if scaler:
                scaler.step(opt)
            else:
                opt.step()
            updates += 1
        if scaler:
            scaler.update()
        levels = Counter(info["level"] for _, info in scored)
        rec = {"step": step, "reward_mean": round(float(rewards.mean()), 4), "groups_all_equal": round(float((rewards.std(1) == 0).float().mean()), 3),
               "pg_loss": round(pg_sum, 5), "kl": round(kl_sum, 5), "grad_norm": round(float(norm), 4) if bool(torch.isfinite(norm)) else None,
               "update_applied": applied, **{k: levels.get(k, 0) for k in LEVELS}, "minutes": round((time.time() - t0) / 60, 2)}
        log.write(json.dumps(rec) + "\n")
        log.flush()
        print(rec, flush=True)
        if dev and (step % a.eval_every == 0 or step == a.steps):
            history.append({"step": step, **dev_check()})
            log.write(json.dumps({"dev": history[-1]}) + "\n")
            print("DEV", history[-1], flush=True)
            if history[-1]["mean_reward"] > best:
                best = history[-1]["mean_reward"]
                model.save_pretrained(out, selected_adapters=["default"])
    if not dev:
        model.save_pretrained(out, selected_adapters=["default"])
    log.close()
    tok.save_pretrained(out)
    kept = max(history, key=lambda h: (h["mean_reward"], -h["step"]))["step"] if history else a.steps
    if a.merge:
        merged = PeftModel.from_pretrained(AutoModelForCausalLM.from_pretrained(a.model, torch_dtype=dtype, trust_remote_code=a.trust_remote_code), out).merge_and_unload()
        merged.save_pretrained(out / "merged", safe_serialization=True)
        tok.save_pretrained(out / "merged")
        portable_model_dir(out / "merged")
    portable_model_dir(out)
    (out / "train_info.json").write_text(json.dumps({
        "algorithm": "GRPO-style group-normalised policy gradient, on-policy, one update per sampled batch",
        "reward": "tabletrace.training.evidence_reward (owner-written)" if a.reward == "verifier" else "random (smoke test)",
        "steps": a.steps, "updates_applied": updates, "kept_step": kept, "dev_history": history, "train_prompts": {k: len(v) for k, v in pools.items()},
        "dtype": str(dtype), "gpu": torch.cuda.get_device_name(0) if cuda else "cpu", "wall_s": round(time.time() - t0, 1), "args": vars(a)}, indent=1))


if __name__ == "__main__":
    main()
