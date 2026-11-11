from collections.abc import Sequence

import torch
from torch import Tensor


def mask_labels(input_ids: Tensor, prompt_lengths: Sequence[int], attention_mask: Tensor) -> Tensor:
    labels = input_ids.clone()
    for row, length in enumerate(prompt_lengths):
        labels[row, :length] = -100
    labels.masked_fill_(attention_mask == 0, -100)
    return labels


def lr_at(step: int, total_steps: int, base_lr: float, warmup_steps: int = 0) -> float:
    if step >= total_steps:
        return 0.0
    if step < warmup_steps:
        return base_lr * (step + 1) / warmup_steps
    return base_lr * (total_steps - step) / (total_steps - warmup_steps)


def train(
    model, batches, optimizer, *, total_steps: int, base_lr: float, warmup_steps: int = 0,
    grad_accum: int = 1, max_grad_norm: float = 1.0, scaler=None, on_step=None,
) -> list[float]:
    if grad_accum < 1:
        raise ValueError("grad_accum must be positive")
    losses: list[float] = []
    optimizer.zero_grad()
    if total_steps <= 0:
        return losses
    micro_count = 0
    step_loss = 0.0
    params = [param for group in optimizer.param_groups for param in group["params"]]
    for batch in batches:
        loss = model(**batch).loss / grad_accum
        step_loss += float(loss.detach())
        if scaler is None:
            loss.backward()
        else:
            scaler.scale(loss).backward()
        micro_count += 1
        if micro_count < grad_accum:
            continue
        step = len(losses)
        lr = lr_at(step, total_steps, base_lr, warmup_steps)
        for group in optimizer.param_groups:
            group["lr"] = lr
        if scaler is not None:
            scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(params, max_grad_norm)
        if scaler is None:
            optimizer.step()
        else:
            scaler.step(optimizer)
            scaler.update()
        optimizer.zero_grad()
        losses.append(step_loss)
        if on_step is not None:
            on_step(step, step_loss, lr)
        if len(losses) >= total_steps:
            return losses
        micro_count = 0
        step_loss = 0.0
    if micro_count:
        optimizer.zero_grad()
    return losses
