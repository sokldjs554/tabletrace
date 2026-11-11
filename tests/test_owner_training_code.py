"""Training code the repository owner writes himself (docs/rewrite/06_training_code.md).

Three small modules, each tested on its own and skipped until its file exists:

    tabletrace/training/evidence_reward.py   the reward for reinforcement learning (what the verifier makes of a sample)
    tabletrace/training/grpo.py              group advantages, completion log-probabilities, policy-gradient loss, KL term
    tabletrace/training/lm_loop.py           label masking, learning-rate schedule and the training loop

The expected numbers below were worked out by hand from the definitions in the spec, not copied from an implementation.
"""
from __future__ import annotations

import importlib
import importlib.util
import math

import pytest


def owner_module(name: str):
    if importlib.util.find_spec(f"tabletrace.training.{name}") is None:
        pytest.skip(f"tabletrace/training/{name}.py is not written yet (owner training task, docs/rewrite/06_training_code.md)")
    return importlib.import_module(f"tabletrace.training.{name}")


# ------------------------------------------------------------------ A. evidence_reward

Q = "러시아가 획득한 메달은 몇 개입니까?"
LEVEL_VALUE = {"correct": 1.0, "repaired": 0.3, "withheld": 0.0, "wrong": -0.5, "unparsable": -1.0}
ANSWERABLE = [
    # (model output, gold answer, expected level, why)
    ("op: lookup ; cells: r2c5 ; answer: 60", "60", "correct", "the cited cell holds the gold answer"),
    ("op: lookup ; cells: r2c1 ; answer: 60", "60", "repaired", "right answer text, but r2c1 holds 러시아; only evidence repair finds r2c5"),
    ("op: lookup ; cells: r1c5 ; answer: 112", "60", "wrong", "the answer agrees with its cell, the verifier passes it, and it is not the gold answer"),
    ("op: lookup ; cells: r2c1 ; answer: 112", "60", "wrong", "repair re-points the evidence to r1c5 and a wrong answer goes out"),
    ("op: lookup ; cells: r2c1 ; answer: 61", "60", "withheld", "61 is in no cell: the verifier rejects the proposal"),
    ("op: lookup ; cells: r2c1 ; answer: 13", "13", "withheld", "13 is in two cells: repair is ambiguous, so nothing is answered"),
    ("op: lookup ; cells: r9c9 ; answer: 60", "60", "withheld", "the cited cell does not exist"),
    ("op: abstain ; cells: ; answer: ", "60", "withheld", "declined although the table has the answer"),
    ("op: diff ; cells: r1c5, r0c5 ; answer: 12", "12", "correct", "the calculator reproduces the answer from the cited cells"),
    ("op: diff ; cells: r1c5, r0c5 ; answer: 15", "12", "correct", "the system sends the calculated 12, not the model's 15; the reward follows what is sent"),
    ("op: diff ; cells: r1c5, r2c5 ; answer: 52", "12", "wrong", "a consistent calculation over the wrong cells"),
    ("op: sum ; cells: r0c2, r1c2 ; answer: 84", "84", "correct", "sum of two cited cells"),
    ("안녕하세요", "60", "unparsable", "not a program"),
    ("", "60", "unparsable", "empty output"),
]
UNANSWERABLE = [
    ("op: abstain ; cells: ; answer: ", "correct", "the model itself declined"),
    ("op: lookup ; cells: r2c5 ; answer: 60", "wrong", "answered a question that has no answer"),
    ("op: lookup ; cells: r2c1 ; answer: 60", "wrong", "with repair on, the service would still answer"),
    ("op: lookup ; cells: r2c1 ; answer: 61", "withheld", "rejected by the verifier: no answer goes out, but the model earns nothing for it"),
    ("op: lookup ; cells: r9c9 ; answer: 60", "withheld", "a broken program is not a deliberate abstention"),
    ("???", "unparsable", "not a program"),
]


@pytest.mark.parametrize(("raw", "gold", "level", "why"), ANSWERABLE)
def test_reward_levels_when_the_question_has_an_answer(medal_table, raw, gold, level, why):
    reward, info = owner_module("evidence_reward").evidence_reward(raw, Q, medal_table, gold)
    assert (info["level"], reward) == (level, LEVEL_VALUE[level]), why


@pytest.mark.parametrize(("raw", "level", "why"), UNANSWERABLE)
def test_reward_levels_when_the_question_has_no_answer(medal_table, raw, level, why):
    reward, info = owner_module("evidence_reward").evidence_reward(raw, Q, medal_table, None)
    assert (info["level"], reward) == (level, LEVEL_VALUE[level]), why


def test_reward_reports_what_it_saw_and_never_raises(medal_table):
    fn = owner_module("evidence_reward").evidence_reward
    reward, info = fn("op: lookup ; cells: r2c5 ; answer: 60", Q, medal_table, "60")
    assert isinstance(reward, float) and info["parse_ok"] is True and info["op"] == "lookup"
    reward, info = fn("op: nonsense ; cells: r2c5", Q, medal_table, "60")
    assert reward == -1.0 and info["parse_ok"] is False and info["op"] is None
    for junk in ("op: lookup ; cells: r-1c0 ; answer: 1", "op: ratio ; cells: r0c5 ; answer: 1", "cells: r0c0", "op: diff ; cells: r0c1, r1c1 ; answer: 3",
                 "op: lookup ; cells: r2c5 ; answer: " + "9" * 500, "\x00\n\n;;;"):
        r, i = fn(junk, Q, medal_table, "60")
        assert r in LEVEL_VALUE.values() and i["level"] in LEVEL_VALUE


def test_reward_is_deterministic_and_keeps_the_table(medal_table):
    fn = owner_module("evidence_reward").evidence_reward
    before = medal_table.model_dump()
    first = fn("op: lookup ; cells: r2c1 ; answer: 60", Q, medal_table, "60")
    assert fn("op: lookup ; cells: r2c1 ; answer: 60", Q, medal_table, "60") == first
    assert medal_table.model_dump() == before


def test_reward_can_use_the_subject_check(medal_table):
    """entity_check=True is the stricter verifier (v2). A lookup about 러시아 that cites the 미국 row is then withheld
    instead of going out wrong; the default (False) keeps the v1 verifier that the stored results use."""
    fn = owner_module("evidence_reward").evidence_reward
    raw = "op: lookup ; cells: r1c5 ; answer: 112"
    assert fn(raw, Q, medal_table, "60")[1]["level"] == "wrong"
    assert fn(raw, Q, medal_table, "60", entity_check=True)[1]["level"] == "withheld"


# ------------------------------------------------------------------ B. grpo

def test_group_advantages_are_normalised_inside_each_group():
    torch = pytest.importorskip("torch")
    g = owner_module("grpo")
    adv = g.group_advantages(torch.tensor([[1.0, 0.0], [0.5, 0.5], [1.0, -1.0]]))
    s = 0.5 / (math.sqrt(0.5) + 1e-4)                      # group 1: mean 0.5, sample std sqrt(0.5)
    t = 1.0 / (math.sqrt(2.0) + 1e-4)                      # group 3: mean 0, sample std sqrt(2)
    assert adv.shape == (3, 2)
    assert torch.allclose(adv, torch.tensor([[s, -s], [0.0, 0.0], [t, -t]]), atol=1e-6)
    four = g.group_advantages(torch.tensor([[1.0, 1.0, 1.0, -1.0]]))
    assert torch.allclose(four.sum(), torch.tensor(0.0), atol=1e-6) and four[0, 3] < 0 < four[0, 0]
    assert torch.equal(g.group_advantages(torch.zeros(2, 4)), torch.zeros(2, 4))     # equal rewards teach nothing, and do not divide by zero


def test_completion_logprobs_score_each_token_from_the_position_before_it():
    torch = pytest.importorskip("torch")
    g = owner_module("grpo")
    logits = torch.tensor([[[0.0, 0.0, 0.0, 0.0], [2.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 9.0]]])      # (1 sequence, 3 positions, 4 words)
    ids = torch.tensor([[3, 1, 0]])
    logp, mask = g.completion_logprobs(logits, ids, torch.tensor([[0, 1, 1]]))
    assert logp.shape == (1, 2) and mask.tolist() == [[1.0, 1.0]]
    expect0 = math.log(0.25)                                   # position 0 predicts token 1: uniform over 4 words
    expect1 = 2.0 - math.log(math.exp(2.0) + 3.0)              # position 1 predicts token 0, whose logit is 2
    assert torch.allclose(logp, torch.tensor([[expect0, expect1]]), atol=1e-6)
    _, only_last = g.completion_logprobs(logits, ids, torch.tensor([[0, 0, 1]]))
    assert only_last.tolist() == [[0.0, 1.0]]                  # prompt tokens are never scored


def test_policy_gradient_loss_matches_the_formula():
    torch = pytest.importorskip("torch")
    g = owner_module("grpo")
    logp = torch.tensor([[-1.0, -2.0], [-3.0, -4.0]])
    mask = torch.tensor([[1.0, 1.0], [1.0, 0.0]])
    loss = g.policy_gradient_loss(logp, mask, torch.tensor([2.0, -1.0]))
    assert loss.item() == pytest.approx(-(2.0 * (-1.0 - 2.0) + (-1.0) * (-3.0)) / 3)       # = 1.0; the masked -4 does not count
    assert g.policy_gradient_loss(logp, torch.zeros(2, 2), torch.tensor([2.0, -1.0])).item() == 0.0   # nothing to score: 0, not NaN


def test_one_policy_gradient_step_prefers_the_rewarded_sample():
    torch = pytest.importorskip("torch")
    g = owner_module("grpo")
    theta = torch.zeros(2, requires_grad=True)                 # a two-word "policy": one group, two samples, one token each
    logits = theta.view(1, 1, 2).expand(2, 2, 2)               # the same distribution at every position
    ids = torch.tensor([[0, 0], [0, 1]])                       # sample 0 wrote word 0 (reward 1), sample 1 wrote word 1 (reward 0)
    logp, mask = g.completion_logprobs(logits, ids, torch.tensor([[0, 1], [0, 1]]))
    adv = g.group_advantages(torch.tensor([[1.0, 0.0]])).view(-1)
    g.policy_gradient_loss(logp, mask, adv).backward()
    with torch.no_grad():
        after = torch.softmax(theta - 0.5 * theta.grad, dim=0)
    assert after[0] > 0.5 > after[1]


def test_kl_term_is_zero_at_the_reference_and_bounded_far_from_it():
    torch = pytest.importorskip("torch")
    g = owner_module("grpo")
    logp = torch.tensor([[-1.0, -2.0]])
    mask = torch.ones(1, 2)
    assert g.kl_k3(logp, logp.clone(), mask).item() == pytest.approx(0.0, abs=1e-7)
    d = 0.5
    one = g.kl_k3(logp, logp + d, torch.tensor([[1.0, 0.0]]))
    assert one.item() == pytest.approx(math.exp(d) - d - 1, rel=1e-5)
    far = g.kl_k3(logp, logp + 1000.0, mask, clamp=10.0)
    assert torch.isfinite(far) and far.item() == pytest.approx(math.exp(10.0) - 11.0, rel=1e-5)
    assert g.kl_k3(logp, logp - 0.3, mask).item() > 0


# ------------------------------------------------------------------ C. lm_loop

def tiny_lm(torch, seed: int = 0):
    class Out:
        def __init__(self, loss, logits):
            self.loss, self.logits = loss, logits

    class TinyLM(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = torch.nn.Embedding(12, 8)
            self.out = torch.nn.Linear(8, 12)

        def forward(self, input_ids, attention_mask=None, labels=None):
            logits = self.out(self.emb(input_ids))
            loss = None
            if labels is not None:          # next-token loss, the way causal LMs in transformers compute it
                loss = torch.nn.functional.cross_entropy(logits[:, :-1].reshape(-1, 12), labels[:, 1:].reshape(-1), ignore_index=-100)
            return Out(loss, logits)

    torch.manual_seed(seed)
    return TinyLM()


def lm_batch(torch, rows):
    ids = torch.tensor(rows)
    return {"input_ids": ids, "attention_mask": torch.ones_like(ids), "labels": ids.clone()}


def test_mask_labels_hides_the_prompt_and_the_padding():
    torch = pytest.importorskip("torch")
    loop = owner_module("lm_loop")
    ids = torch.tensor([[5, 6, 7, 8, 0], [5, 9, 0, 0, 0]])
    att = torch.tensor([[1, 1, 1, 1, 0], [1, 1, 0, 0, 0]])
    labels = loop.mask_labels(ids, [2, 1], att)
    assert labels.tolist() == [[-100, -100, 7, 8, -100], [-100, 9, -100, -100, -100]]
    assert ids.tolist() == [[5, 6, 7, 8, 0], [5, 9, 0, 0, 0]]            # the input is not changed in place


def test_learning_rate_warms_up_then_decays_to_zero():
    loop = owner_module("lm_loop")
    lr = [loop.lr_at(s, total_steps=10, base_lr=1.0, warmup_steps=4) for s in range(12)]
    assert lr[:4] == pytest.approx([0.25, 0.5, 0.75, 1.0])                # step 0 already trains
    assert lr[4:10] == pytest.approx([1.0, 5 / 6, 4 / 6, 3 / 6, 2 / 6, 1 / 6])
    assert lr[10] == lr[11] == 0.0
    assert loop.lr_at(0, total_steps=5, base_lr=2.0, warmup_steps=0) == pytest.approx(2.0)


def test_training_loop_overfits_a_tiny_model():
    torch = pytest.importorskip("torch")
    loop = owner_module("lm_loop")
    model = tiny_lm(torch)
    batch = lm_batch(torch, [[1, 2, 3, 4, 5, 6], [6, 5, 4, 3, 2, 1], [1, 3, 5, 7, 9, 11], [2, 4, 6, 8, 10, 0]])
    opt = torch.optim.Adam(model.parameters(), lr=123.0)                  # the loop must overwrite this
    losses = loop.train(model, [batch] * 80, opt, total_steps=80, base_lr=0.05, warmup_steps=5)
    assert len(losses) == 80 and all(isinstance(x, float) for x in losses)
    assert losses[-1] < 0.5 * losses[0]


def test_loop_sets_the_scheduled_rate_and_stops_at_total_steps():
    torch = pytest.importorskip("torch")
    loop = owner_module("lm_loop")
    model = tiny_lm(torch)
    seen = []
    opt = torch.optim.SGD(model.parameters(), lr=999.0)
    losses = loop.train(model, [lm_batch(torch, [[1, 2, 3, 4]])] * 10, opt, total_steps=3, base_lr=0.1, warmup_steps=2,
                        on_step=lambda step, loss, lr: seen.append((step, lr, opt.param_groups[0]["lr"])))
    assert len(losses) == 3
    assert [s for s, _, _ in seen] == [0, 1, 2]
    for step, lr, in_optimizer in seen:
        assert lr == pytest.approx(loop.lr_at(step, 3, 0.1, 2)) and in_optimizer == pytest.approx(lr)


def test_gradient_accumulation_equals_one_large_batch():
    torch = pytest.importorskip("torch")
    loop = owner_module("lm_loop")
    rows = [[1, 2, 3, 4], [4, 3, 2, 1], [5, 6, 7, 8], [8, 7, 6, 5]]
    whole, halves = tiny_lm(torch, seed=1), tiny_lm(torch, seed=1)
    one = loop.train(whole, [lm_batch(torch, rows)], torch.optim.SGD(whole.parameters(), lr=1.0), total_steps=1, base_lr=0.1, max_grad_norm=1e9)
    two = loop.train(halves, [lm_batch(torch, rows[:2]), lm_batch(torch, rows[2:])], torch.optim.SGD(halves.parameters(), lr=1.0),
                     total_steps=1, base_lr=0.1, grad_accum=2, max_grad_norm=1e9)
    assert len(one) == len(two) == 1 and one[0] == pytest.approx(two[0], rel=1e-5)      # the logged loss is the mean over the step
    for p, q in zip(whole.parameters(), halves.parameters(), strict=True):
        assert torch.allclose(p, q, atol=1e-6)
    leftover = loop.train(tiny_lm(torch), [lm_batch(torch, rows[:2])] * 3, torch.optim.SGD(tiny_lm(torch).parameters(), lr=1.0),
                          total_steps=5, base_lr=0.1, grad_accum=2)
    assert len(leftover) == 1                                              # three micro-batches make one full step; the odd one is dropped


def test_gradients_are_clipped_before_the_step():
    torch = pytest.importorskip("torch")
    loop = owner_module("lm_loop")
    model = tiny_lm(torch, seed=2)
    before = [p.detach().clone() for p in model.parameters()]
    loop.train(model, [lm_batch(torch, [[1, 2, 3, 4], [4, 3, 2, 1]])], torch.optim.SGD(model.parameters(), lr=1.0),
               total_steps=1, base_lr=1.0, max_grad_norm=1e-3)
    moved = math.sqrt(sum(float(((p.detach() - b) ** 2).sum()) for p, b in zip(model.parameters(), before, strict=True)))
    assert 0 < moved <= 1e-3 * 1.0001                                      # SGD with lr 1: the update is the clipped gradient


def test_loop_drives_a_gradient_scaler_in_the_right_order():
    torch = pytest.importorskip("torch")
    loop = owner_module("lm_loop")
    calls = []

    class Scaler:                                                           # stands in for torch.amp.GradScaler on a GPU
        def scale(self, loss):
            calls.append("scale")
            return loss

        def unscale_(self, optimizer):
            calls.append("unscale_")

        def step(self, optimizer):
            calls.append("step")
            optimizer.step()

        def update(self):
            calls.append("update")

    model = tiny_lm(torch)
    b = lm_batch(torch, [[1, 2, 3, 4]])
    loop.train(model, [b, b], torch.optim.SGD(model.parameters(), lr=1.0), total_steps=1, base_lr=0.1, grad_accum=2, scaler=Scaler())
    assert calls == ["scale", "scale", "unscale_", "step", "update"]
