"""The GPU notebooks cannot be run here, so at least every command-line flag they pass must exist.

Collects the `--flags` that the notebook cells give to this repository's scripts and checks each against the script's
own --help output. A typo in a notebook would otherwise only show up on the owner's GPU session.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {                                   # marker in the notebook source -> command that prints the help
    "tabletrace.eval.run": [sys.executable, "-m", "tabletrace.eval.run", "--help"],
    "scripts/train/exaone_lora_sft.py": [sys.executable, "scripts/train/exaone_lora_sft.py", "--help"],
    "scripts/train/exaone_grpo.py": [sys.executable, "scripts/train/exaone_grpo.py", "--help"],
    "tabletrace.bench.engine_bench": [sys.executable, "-m", "tabletrace.bench.engine_bench", "--help"],
}
VLLM_FLAGS = {"--trust-remote-code", "--enable-auto-tool-choice", "--tool-call-parser", "--quantization", "--enforce-eager", "--disable-custom-all-reduce",
              "--nproc_per_node", "--query-gpu", "--format", "--short", "--oneline", "--clear", "--python"}     # belong to vllm / torchrun / nvidia-smi / git / uv


def flags_by_target(nb_path: Path) -> dict[str, set[str]]:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    src = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    src = re.sub(r"\\\n", " ", src)                                    # join shell continuations
    found: dict[str, set[str]] = {k: set() for k in TARGETS}
    for line in src.splitlines():
        for marker in TARGETS:
            if marker in line:
                found[marker] |= set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", line.split(marker, 1)[1]))
    # flags that reach eval.run through helper arguments (extra=..., SHOTS = ...) are written as string literals
    for literal in re.findall(r"""(?:extra|SHOTS|more|common|pool)\s*=\s*(?:""\s+if[^\n]*else\s+)?f?["']([^"']*--[^"']*)["']""", src):
        flags = set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", literal)) - VLLM_FLAGS
        if "--loop" in flags or "--extra-train" in flags:
            found["scripts/train/exaone_lora_sft.py"] |= flags
        else:
            found["tabletrace.eval.run"] |= flags
    return found


@pytest.mark.parametrize("notebook", ["notebooks/gpu_experiments.ipynb", "notebooks/gpu_experiments_2.ipynb"])
def test_every_flag_in_the_notebook_exists(notebook):
    pytest.importorskip("torch")                   # the training scripts import torch before they parse arguments
    pytest.importorskip("peft")
    found = flags_by_target(ROOT / notebook)
    assert any(found.values()), "no commands found: the notebook layout changed and this test needs updating"
    for marker, flags in found.items():
        if not flags:
            continue
        r = subprocess.run(TARGETS[marker], cwd=ROOT, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-800:]
        missing = sorted(f for f in flags - VLLM_FLAGS if not re.search(rf"(?<![\w-]){re.escape(f)}(?![\w-])", r.stdout))
        assert not missing, f"{notebook}: {marker} has no option {missing}"


def test_second_notebook_cells_are_valid_python():
    nb = json.loads((ROOT / "notebooks/gpu_experiments_2.ipynb").read_text(encoding="utf-8"))
    import ast

    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] != "code":
            continue
        out, skip = [], False
        for ln in "".join(c["source"]).split("\n"):
            if skip:
                skip = ln.rstrip().endswith("\\")
                continue
            if ln.lstrip().startswith("!"):               # IPython shell line: syntax-check as `pass`
                out.append(ln[: len(ln) - len(ln.lstrip())] + "pass")
                skip = ln.rstrip().endswith("\\")
                continue
            out.append(ln)
        ast.parse("\n".join(out), filename=f"cell {i}")
