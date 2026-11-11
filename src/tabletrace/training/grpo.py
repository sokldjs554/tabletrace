import torch
from torch import Tensor


def group_advantages(rewards: Tensor, eps: float = 1e-4) -> Tensor:
    centered = rewards - rewards.mean(dim=-1, keepdim=True)
    if rewards.shape[-1] < 2:
        return torch.zeros_like(rewards)
    return centered / (rewards.std(dim=-1, keepdim=True) + eps)


def completion_logprobs(logits: Tensor, input_ids: Tensor, completion_mask: Tensor) -> tuple[Tensor, Tensor]:
    distribution = torch.log_softmax(logits[:, :-1, :], dim=-1)
    token_logp = distribution.gather(-1, input_ids[:, 1:].unsqueeze(-1)).squeeze(-1)
    return token_logp, completion_mask[:, 1:].to(dtype=token_logp.dtype)


def policy_gradient_loss(token_logp: Tensor, mask: Tensor, advantages: Tensor) -> Tensor:
    return -(token_logp * mask * advantages.unsqueeze(-1)).sum() / mask.sum().clamp_min(1)


def kl_k3(token_logp: Tensor, ref_logp: Tensor, mask: Tensor, clamp: float = 10.0) -> Tensor:
    delta = (ref_logp - token_logp).clamp(min=-clamp, max=clamp)
    return ((delta.exp() - delta - 1) * mask).sum() / mask.sum().clamp_min(1)
