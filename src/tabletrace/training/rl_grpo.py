"""GRPO-style reinforcement learning for the TableTrace planner (mT5, PyTorch, CPU or GPU).

What is actually optimised
--------------------------
For each prompt we sample G programs from the current policy, score every sample with a
*verifiable* reward (the same verifier the service uses, compared with gold), normalise rewards
inside the group (GRPO advantage: (r - mean) / std), and take a policy-gradient step on
  L = - sum_t A_i * log pi_theta(o_{i,t} | q, o_{i,<t}) / N_tokens  +  beta * KL(pi_theta || pi_ref)
with the Schulman k3 KL estimator against the frozen SFT model. One optimisation step per sampled
batch (on-policy), so no importance ratio / clipping is needed (TRL's default num_iterations=1).
This is a real policy update from sampled behaviour, not SFT and not preference learning (DPO).

Reward (per sample; see `reward()`):
  unparsable output                      -1.0
  gold answerable: answer correct        +1.0, evidence cells exact +0.5 (overlap +0.25), op correct +0.2,
                   answer text != cell   -0.3 (verifier substituted the cell), abstained instead -0.3,
                   proposal blocked by verifier -0.3
  gold abstain:    planner chose op: abstain +1.0, verifier caught an unsupported proposal +0.2,
                   invalid program 0.0, answered anyway (hallucination) -0.8
Policy and reference are both run in eval mode (dropout off). Training mode would make the policy's
log-probs differ from the reference's even at step 0 (KL of 1e2..1e6 in our first attempt, followed by NaN),
and sampling is done from the same eval-mode policy so the update is on-policy.
Usage:
  python -m tabletrace.training.rl_grpo --model experiments/sft_ko2/model --train data/ko/train.jsonl data/ko/synthetic_train.jsonl \
     --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl --corpus data/ko/documents.jsonl --out experiments/rl_ko/model --steps 60
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import random
import time
from collections import Counter
from pathlib import Path

import psutil
import torch
import torch.nn.functional as F

from tabletrace.agent.program import ProgramParseError, parse
from tabletrace.eval.metrics import answer_match
from tabletrace.training.data import Example, build_examples, load_docs, read_records
from tabletrace.training.sft import evaluate
from tabletrace.verify.verifier import resolve


def reward(raw: str, e: Example) -> tuple[float, dict]:
    """Verifiable reward. v2: an abstention only earns full credit when the *planner* chose it (`op: abstain`).
    v1 paid +1.0 for any final status 'abstained' on a no-answer prompt, so degenerate programs that the verifier
    rejected scored as well as a deliberate abstention (observed: explicit abstain 7% -> 11% while status-abstain
    61% -> 68%, policy drifting to `diff`)."""
    info = {"parse_ok": True, "op": None, "abstained": None, "explicit_abstain": False, "reason": None, "correct": False}
    try:
        prog = parse(raw, e.table.id)
    except ProgramParseError:
        info["parse_ok"] = False
        return -1.0, info
    info["op"] = prog.op
    res = resolve(e.question, e.table, prog, context=e.context)
    gold = resolve(e.question, e.table_full or e.table, e.gold, context=e.context_full or e.context)
    info["abstained"] = res.status == "abstained"
    info["explicit_abstain"] = prog.op == "abstain"
    info["reason"] = res.verdict.reason
    r = 0.0
    if gold.status == "answered":
        if res.status == "answered":
            ok = answer_match(res.answer, gold.answer)
            info["correct"] = ok
            r += 1.0 if ok else 0.0
            gc, pc = {c.cid for c in e.gold.cells}, {c.cid for c in prog.cells}   # the planner's own citation
            if gc and pc == gc:
                r += 0.5
            elif gc and pc & gc:
                r += 0.25
            if e.gold.op == "text" and res.spans:
                r += 0.5 if ok else 0.25
            r += 0.2 if prog.op == e.gold.op else 0.0
            # the verifier accepted the cell but the model's own answer text did not match it
            if any(c.name in ("answer_matches_cell", "evidence_repaired") and not c.passed for c in res.verdict.checks):
                r -= 0.3
        else:
            r -= 0.5 if res.verdict.reason == "invalid_program" else 0.3
            if res.verdict.reason == "verification_failed":
                r -= 0.3   # named a value that its own evidence does not support
    else:
        if res.status == "abstained":
            if prog.op == "abstain":
                r += 1.0                      # the planner itself declined
                info["correct"] = True
            elif res.verdict.reason == "verification_failed":
                r += 0.2                      # unsupported proposal, caught by the verifier
            # invalid / degenerate program on a no-answer prompt: 0.0 (no credit for garbage)
        else:
            r -= 0.8
    return r, info


def seq_logprobs(model, enc, labels, pad_id: int) -> tuple[torch.Tensor, torch.Tensor]:
    """Per-token log-probs of `labels` under `model` -> (logp [B, T], mask [B, T])."""
    out = model(input_ids=enc["input_ids"], attention_mask=enc["attention_mask"], labels=labels)
    logp = F.log_softmax(out.logits.float(), dim=-1)
    tgt = labels.clamp(min=0)
    tok_logp = logp.gather(-1, tgt.unsqueeze(-1)).squeeze(-1)
    mask = (labels != -100).float()
    return tok_logp, mask


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--train", nargs="+", required=True)
    ap.add_argument("--dev", nargs="+", required=True)
    ap.add_argument("--corpus", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--prompts-per-step", type=int, default=4)
    ap.add_argument("--group", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--beta", type=float, default=0.02)
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--max-in", type=int, default=512)
    ap.add_argument("--max-out", type=int, default=64)
    ap.add_argument("--eval-every", type=int, default=20)
    ap.add_argument("--chunk", type=int, default=8, help="sequences per backward pass")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--max-dev", type=int, default=0, help="limit dev examples (smoke tests)")
    ap.add_argument("--kl-clamp", type=float, default=10.0, help="clamp of the log-ratio inside the k3 KL estimator")
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    random.seed(a.seed)
    torch.manual_seed(a.seed)
    from transformers import MT5ForConditionalGeneration, PreTrainedTokenizerFast

    out = Path(a.out)
    run_dir = out.parent
    run_dir.mkdir(parents=True, exist_ok=True)
    tok = PreTrainedTokenizerFast.from_pretrained(a.model)
    policy = MT5ForConditionalGeneration.from_pretrained(a.model)
    ref = MT5ForConditionalGeneration.from_pretrained(a.model).eval()
    for p in ref.parameters():
        p.requires_grad_(False)
    docs = load_docs(*[Path(c) for c in a.corpus])
    train = build_examples(read_records([Path(p) for p in a.train]), docs, tok, a.max_in, drop_truncated_gold=True)
    dev = build_examples(read_records([Path(p) for p in a.dev]), docs, tok, a.max_in)
    if a.max_dev:
        dev = dev[: a.max_dev]
    # balance prompt sources so abstain / calc prompts are not drowned by lookups
    by_src: dict[str, list[Example]] = {}
    for e in train:
        by_src.setdefault(e.gold.op if e.gold.op in ("abstain", "text") else ("calc" if e.gold.op != "lookup" else "lookup"), []).append(e)
    kinds = sorted(by_src)
    opt = torch.optim.AdamW(policy.parameters(), lr=a.lr, weight_decay=0.0)
    info = {"args": vars(a), "n_train_prompts": len(train), "prompt_pools": {k: len(v) for k, v in by_src.items()}, "n_dev": len(dev),
            "hardware": {"cpu": platform.processor() or platform.machine(), "threads": torch.get_num_threads(), "cuda": torch.cuda.is_available(),
                         "ram_gb": round(psutil.virtual_memory().total / 1e9, 1)}, "torch": torch.__version__,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "algorithm": "GRPO-style group-normalised policy gradient, on-policy, k3 KL to SFT reference"}
    (run_dir / "config.json").write_text(json.dumps(info, ensure_ascii=False, indent=1))
    log = open(run_dir / "train_log.jsonl", "a", encoding="utf-8")  # noqa: SIM115
    ev0 = evaluate(policy, tok, dev, 8, a.max_in, a.max_out)
    ev0.update({"step": 0})
    log.write(json.dumps({"eval": ev0}) + "\n")
    print("EVAL step 0", ev0, flush=True)
    best, best_step = ev0["verified_em"], 0
    policy.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    t0 = time.time()
    history = [ev0]
    for step in range(1, a.steps + 1):
        policy.eval()
        prompts = [random.choice(by_src[kinds[(step * a.prompts_per_step + i) % len(kinds)]]) for i in range(a.prompts_per_step)]
        enc = tok([e.input_text for e in prompts], return_tensors="pt", padding=True, truncation=True, max_length=a.max_in)
        with torch.no_grad():
            gen = policy.generate(**enc, do_sample=True, temperature=a.temperature, top_p=1.0, top_k=0, max_new_tokens=a.max_out,
                                  num_return_sequences=a.group, pad_token_id=tok.pad_token_id)
        texts = tok.batch_decode(gen, skip_special_tokens=True)
        rewards, infos = [], []
        for i, txt in enumerate(texts):
            r, inf = reward(txt, prompts[i // a.group])
            rewards.append(r)
            infos.append(inf)
        R = torch.tensor(rewards).view(a.prompts_per_step, a.group)
        adv = (R - R.mean(1, keepdim=True)) / (R.std(1, keepdim=True) + 1e-4)
        adv = adv.view(-1)
        # labels = sampled sequence without the leading decoder-start token
        labels = gen[:, 1:].clone()
        labels[labels == tok.pad_token_id] = -100
        # keep the first </s> of each sequence as a supervised token; mask everything after it
        for i in range(labels.shape[0]):
            eos = (gen[i, 1:] == tok.eos_token_id).nonzero()
            if len(eos):
                labels[i, eos[0, 0] + 1:] = -100
        in_ids = enc["input_ids"].repeat_interleave(a.group, 0)
        in_mask = enc["attention_mask"].repeat_interleave(a.group, 0)
        policy.eval()   # dropout off: log-probs must equal the sampling distribution and the reference at step 0
        opt.zero_grad(set_to_none=True)
        total_tok = (labels != -100).sum().clamp(min=1).item()
        loss_sum = kl_sum = 0.0
        for s in range(0, labels.shape[0], a.chunk):
            sl = slice(s, s + a.chunk)
            if adv[sl].abs().sum() == 0:
                continue
            e_chunk = {"input_ids": in_ids[sl], "attention_mask": in_mask[sl]}
            logp, mask = seq_logprobs(policy, e_chunk, labels[sl], tok.pad_token_id)
            with torch.no_grad():
                ref_logp, _ = seq_logprobs(ref, e_chunk, labels[sl], tok.pad_token_id)
            pg = -(adv[sl].unsqueeze(1) * logp * mask).sum() / total_tok
            ratio = (ref_logp - logp).clamp(-a.kl_clamp, a.kl_clamp)
            kl = ((ratio.exp() - ratio - 1) * mask).sum() / total_tok      # k3 estimator, per token
            loss = pg + a.beta * kl
            loss.backward()
            loss_sum += pg.item()
            kl_sum += kl.item()
        gn = torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
        skipped = not bool(torch.isfinite(gn))
        if skipped:                       # never apply a non-finite update
            opt.zero_grad(set_to_none=True)
        else:
            opt.step()
        ops = Counter(i["op"] for i in infos)
        rec = {"step": step, "reward_mean": round(R.mean().item(), 4), "reward_std": round(R.std().item(), 4),
               "frac_group_zero_std": round(float((R.std(1) == 0).float().mean()), 3), "pg_loss": round(loss_sum, 5), "kl": round(kl_sum, 5),
               "parse_ok": round(sum(i["parse_ok"] for i in infos) / len(infos), 3), "abstain_rate": round(sum(bool(i["abstained"]) for i in infos) / len(infos), 3),
               "explicit_abstain_rate": round(sum(bool(i["explicit_abstain"]) for i in infos) / len(infos), 3),
               "invalid_program_rate": round(sum(i["reason"] == "invalid_program" for i in infos) / len(infos), 3),
               "correct_rate": round(sum(i["correct"] for i in infos) / len(infos), 3), "ops": dict(ops),
               "grad_norm": round(float(gn), 4) if not skipped else None, "update_skipped": skipped,
               "prompt_kinds": [k for k in (kinds[(step * a.prompts_per_step + i) % len(kinds)] for i in range(a.prompts_per_step))],
               "elapsed_s": round(time.time() - t0, 1), "rss_gb": round(psutil.Process(os.getpid()).memory_info().rss / 1e9, 2)}
        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.flush()
        print(rec, flush=True)
        if step % a.eval_every == 0 or step == a.steps:
            ev = evaluate(policy, tok, dev, 8, a.max_in, a.max_out)
            ev.update({"step": step, "elapsed_s": round(time.time() - t0, 1)})
            history.append(ev)
            log.write(json.dumps({"eval": ev}) + "\n")
            log.flush()
            print("EVAL", ev, flush=True)
            if ev["verified_em"] >= best:
                best, best_step = ev["verified_em"], step
                policy.save_pretrained(out, safe_serialization=True)
                tok.save_pretrained(out)
                cfg = json.loads((out / "config.json").read_text())
                cfg["tie_word_embeddings"] = False
                (out / "config.json").write_text(json.dumps(cfg, indent=2))
                print("saved ->", out, flush=True)
    summary = {**info, "finished": time.strftime("%Y-%m-%dT%H:%M:%S"), "wall_s": round(time.time() - t0, 1), "steps": a.steps,
               "dev_history": history, "best_dev_verified_em": best, "best_step": best_step}
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print("DONE", json.dumps({k: summary[k] for k in ["wall_s", "steps", "best_dev_verified_em", "best_step"]}))


if __name__ == "__main__":
    main()
