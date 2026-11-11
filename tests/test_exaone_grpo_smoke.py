"""Smoke test of scripts/train/exaone_grpo.py on a tiny random Llama (CPU, fp32).

Skipped until the owner-written modules exist (docs/rewrite/06_training_code.md): the script only orchestrates, the
reward and the loss are theirs. A random model cannot write programs, so one run uses `--reward random` to push
non-zero advantages through the update path, and one uses the real verifier reward (everything is unparsable there,
all groups score the same, and the step must be skipped rather than divide by zero).
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("peft")
pytest.importorskip("transformers")
pytest.importorskip("torch")

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    any(importlib.util.find_spec(f"tabletrace.training.{m}") is None for m in ("evidence_reward", "grpo")),
    reason="tabletrace/training/evidence_reward.py and grpo.py are not written yet (owner training task, docs/rewrite/06_training_code.md)")


def run(tmp_path, name, *extra):
    from test_lora_sft_smoke import _tiny_model

    model_dir = _tiny_model(tmp_path)
    out = tmp_path / name
    r = subprocess.run([sys.executable, str(ROOT / "scripts/train/exaone_grpo.py"), "--model", str(model_dir), "--dtype", "fp32",
                        "--train", str(ROOT / "data/chem/synthetic_train.jsonl"), "--dev", str(ROOT / "data/chem/synthetic_train.jsonl"),
                        "--corpus", str(ROOT / "data/chem/documents.jsonl"), "--out", str(out), "--steps", "2", "--prompts", "2", "--group", "3",
                        "--chunk", "2", "--max-len", "1536", "--max-new", "8", "--dev-n", "4", "--eval-every", "1", "--lora-r", "4", *extra],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-3000:]
    return out, json.loads((out / "train_info.json").read_text()), [json.loads(x) for x in (out / "train_log.jsonl").read_text().splitlines()]


def test_update_path_runs_with_non_zero_advantages(tmp_path):
    out, info, log = run(tmp_path, "grpo_random", "--reward", "random", "--beta", "0.05", "--merge")
    steps = [x for x in log if "step" in x and "dev" not in x]
    assert len(steps) == 2 and info["steps"] == 2 and info["updates_applied"] >= 1
    assert all(sum(x[k] for k in ("correct", "repaired", "withheld", "wrong", "unparsable")) == 6 for x in steps)     # 2 prompts x 3 samples
    assert any(x["update_applied"] and x["grad_norm"] and x["grad_norm"] > 0 for x in steps)
    assert (out / "adapter_config.json").exists() and list((out / "merged").glob("*.safetensors"))
    assert [h["step"] for h in info["dev_history"]] == [0, 1, 2]


def test_real_reward_on_a_model_that_cannot_write_programs(tmp_path):
    _out, info, log = run(tmp_path, "grpo_verifier")
    steps = [x for x in log if "step" in x and "dev" not in x]
    assert info["reward"].startswith("tabletrace.training.evidence_reward")
    assert all(x["unparsable"] + x["withheld"] + x["wrong"] + x["correct"] + x["repaired"] == 6 for x in steps)
    assert all(x["reward_mean"] <= 0.0 for x in steps)                      # random text earns nothing
    assert all(x["update_applied"] is False for x in steps if x["groups_all_equal"] == 1.0)   # equal rewards: no update, no NaN
