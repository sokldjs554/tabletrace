# GRPO RL, reward v1 — kept as evidence, NOT the reported RL result

This run used the first reward function, which paid +1.0 for any final status `abstained` on a no-answer prompt.
Degenerate programs rejected by the verifier therefore scored like a deliberate `op: abstain`.
Over the 60 steps the share of status-abstained samples rose 61% -> 68% while explicit `op: abstain` rose only
7% -> 11% and the policy drifted from `lookup` (57%) to `diff` (45%) with flat mean reward.
Reward v2 (src/tabletrace/training/rl_grpo.py, `reward()`) gives full abstention credit only to `op: abstain`.
The evaluated checkpoint was step 20 (best dev). Its path at evaluation time was experiments/rl_ko/model
(recorded in experiments/eval/rl_ko_v1_*/metrics.json); the directory was renamed afterwards.
