"""The GPU notebooks cannot be run here. Two things can still be checked without a GPU.

1. Every code cell is valid Python once its shell lines (`!command`) are taken out.
2. Notebook 2 is run "dry": shell lines become calls to a recorder that writes the files the real command writes last
   (train_info.json, merged/config.json, metrics.json). This checks what the owner's lost Kaggle session showed to be
   missing: a second run skips finished training and evaluation, an interrupted piece is redone, every section packs the
   result archive, model weights are not packed, and evaluated models' weights are removed (the Kaggle working directory
   holds 20 GB; the notebook would otherwise leave about ten 2.5 GB models there).
"""
import collections
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def to_python(src: str, shell: str = "pass") -> str:
    """Replace `!command` lines (with their backslash continuations). shell="call" turns them into _sh(f"command")."""
    out, lines, i = [], src.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("!"):
            indent = line[: len(line) - len(stripped)]
            cmd = stripped[1:]
            while cmd.rstrip().endswith("\\"):
                i += 1
                cmd = cmd.rstrip()[:-1] + " " + lines[i].strip()
            out.append(f"{indent}_sh(f{cmd!r})" if shell == "call" else f"{indent}pass")
        else:
            out.append(line)
        i += 1
    return "\n".join(out)


def code_cells(notebook: str) -> list[tuple[int, str]]:
    nb = json.loads((ROOT / notebook).read_text(encoding="utf-8"))
    return [(i, "".join(c["source"])) for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code"]


@pytest.mark.parametrize("notebook", ["notebooks/gpu_experiments.ipynb", "notebooks/gpu_experiments_2.ipynb"])
def test_every_code_cell_is_valid_python(notebook):
    for i, src in code_cells(notebook):
        compile(to_python(src), f"{notebook} cell {i}", "exec")


def test_notebook_2_skips_finished_work_and_packs_results(tmp_path, monkeypatch):
    calls: list[tuple[str, str]] = []

    def _sh(cmd: str) -> None:
        kind = ("train" if "exaone_lora_sft.py" in cmd else "grpo" if "exaone_grpo.py" in cmd else "eval" if "tabletrace.eval.run" in cmd
                else "bench" if "engine_bench" in cmd else "other")
        calls.append((kind, cmd))
        m = re.search(r"--out (\S+)", cmd)
        if not m:
            return
        out = Path(m.group(1))
        if kind in ("train", "grpo"):
            out.mkdir(parents=True, exist_ok=True)
            (out / "adapter_config.json").write_text("{}")
            if "--merge" in cmd.split():                                   # the real scripts write merged/ only with --merge
                (out / "merged").mkdir(exist_ok=True)
                (out / "merged" / "config.json").write_text("{}")
            info = {"wall_s": 60.0, "n_examples": 300, "steps": 18, "world_size": 2 if "torchrun" in cmd else 1}
            if kind == "grpo":
                (out / "train_log.jsonl").write_text("{}\n")
                info = {"updates_applied": 150, "steps": 200, "kept_step": 100, "dev_history": [{"step": 0, "mean_reward": 0.1, "correct": 3}]}
            (out / "train_info.json").write_text(json.dumps(info))             # written last, as in the real scripts
        elif kind == "eval":
            out.mkdir(parents=True, exist_ok=True)
            (out / "metrics.json").write_text("{}")
        elif kind == "bench":
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("{}")

    class Proc:
        def terminate(self): pass
        def wait(self): pass

    repo = tmp_path / "tabletrace"
    for d in ("experiments/eval", "experiments/bench", "src/tabletrace/training"):
        (repo / d).mkdir(parents=True)
    for m in ("evidence_reward", "grpo"):
        (repo / "src/tabletrace/training" / f"{m}.py").write_text("")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "nvidia-smi").write_text("#!/bin/sh\necho 1000\necho 1000\n")
    (bindir / "nvidia-smi").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(repo)
    if "requests" not in sys.modules:
        try:
            import requests  # noqa: F401
        except ImportError:
            monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace())
    torch = types.SimpleNamespace(cuda=types.SimpleNamespace(get_device_name=lambda i: "Tesla T4", device_count=lambda: 2))
    ns = {"_sh": _sh, "os": os, "subprocess": subprocess, "time": time, "json": json, "glob": glob, "shutil": shutil, "torch": torch, "N_GPU": 2,
          "ROOT": str(tmp_path), "VENV": str(tmp_path), "REPO_DIR": str(repo)}
    (_, _setup), (_, helpers), *sections = code_cells("notebooks/gpu_experiments_2.ipynb")     # the setup cell needs a GPU and the network
    exec(compile(to_python(helpers, "call"), "helpers", "exec"), ns)
    real_pack, packs = ns["pack"], []
    ns.update(serve=lambda *a, **k: Proc(), stop_servers=lambda: None, pack=lambda: (packs.append(1), real_pack())[1])

    def run_all() -> collections.Counter:
        calls.clear()
        packs.clear()
        for i, src in sections:
            exec(compile(to_python(src, "call"), f"cell {i}", "exec"), ns)
        return collections.Counter(kind for kind, _ in calls)

    first = run_all()
    assert first["train"] == 8 and first["grpo"] == 1 and first["eval"] >= 60
    assert len(packs) >= len(sections) - 1                                   # every section ends by packing what exists so far
    assert Path.cwd() == repo                                                # pack() moves away for the download link and must come back
    names = tarfile.open(tmp_path / "gpu_results_2.tgz").getnames()
    assert any(n.endswith("exaone_grpo/train_info.json") for n in names) and any("exaone_rlstart_vllm_ko_test" in n for n in names)
    assert any(n.endswith("run_info_2.json") for n in names) and not any("merged" in n for n in names)
    kept = sorted(q.parent.name for q in (repo / "experiments").glob("*/merged"))
    assert kept == ["exaone_lora_pool7000", "exaone_lora_rlstart"]           # the two that later sections serve again
    ddp = [c for k, c in calls if k == "train" and "exaone_lora_ddp" in c]
    assert len(ddp) == 2 and not any("--merge" in c.split() for c in ddp)    # the speed runs keep no merged model

    second = run_all()
    assert second["train"] == second["grpo"] == second["eval"] == 0          # nothing finished is done again

    (repo / "experiments/exaone_lora_colid_s2/train_info.json").unlink()     # as if stopped during this training
    shutil.rmtree(repo / "experiments/eval/exaone_colid_s2_vllm_ko_custom_ec")
    shutil.rmtree(repo / "experiments/eval/exaone_grpo_vllm_ko_test_ec")     # as if stopped during this evaluation
    (repo / "experiments/exaone_grpo/train_info.json").unlink()
    third = run_all()
    redone = sorted({re.search(r"--out (\S+)", c).group(1) for k, c in calls if k in ("train", "eval", "grpo")})
    assert third["train"] == 1 and third["grpo"] == 1 and third["eval"] == 4
    assert redone == ["experiments/eval/exaone_colid_s2_vllm_ko_custom", "experiments/eval/exaone_colid_s2_vllm_ko_custom_ec",
                      "experiments/eval/exaone_grpo_vllm_ko_test", "experiments/eval/exaone_grpo_vllm_ko_test_ec",
                      "experiments/exaone_grpo", "experiments/exaone_lora_colid_s2"]
