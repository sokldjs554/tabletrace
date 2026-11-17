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
import itertools
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


class DryRun:
    """Notebook 2 with its shell lines recorded instead of run, in a fresh working directory under `root`."""

    def __init__(self, root: Path, monkeypatch, backup: Path | None = None, n_gpu: int = 2, run_32b: bool = False, dies: str | None = None,
                 remote: Path | None = None, control: bool = False, repeat: bool = False, cloned_results: bool | str = False, old_setting: bool = True):
        self.calls: list[tuple[str, str]] = []
        self.packs: list[int] = []
        self.dies = dies                  # evaluations whose output path contains this never finish (the server died)
        self.root = root
        self.repo = repo = root / "tabletrace"
        for d in ("experiments/eval", "experiments/bench", "src/tabletrace/training"):
            (repo / d).mkdir(parents=True)
        for m in ("evidence_reward", "grpo", "lm_loop"):
            (repo / "src/tabletrace/training" / f"{m}.py").write_text("")
        (repo / "data/ko").mkdir(parents=True)
        (repo / "data/ko/owner_eval.jsonl").write_text("")                 # the owner's questions are part of main since 2026-11-16 (section L reads them)
        bindir = root / "bin"
        bindir.mkdir()
        (bindir / "nvidia-smi").write_text("#!/bin/sh\necho 1000\necho 1000\n")
        (bindir / "nvidia-smi").chmod(0o755)
        monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.chdir(repo)
        if cloned_results:                # a fresh clone of main: it holds the result files of earlier sessions, and no weights
            for f in [*(ROOT / "experiments").glob("eval/*/metrics.json"), *(ROOT / "experiments").glob("*/train_info.json"), ROOT / "experiments/run_info_2.json"]:
                loop = ("ownloop",)                      # section M (2026-11-16, Colab): the last results that came in
                owner = ("full4", "_ko_owner", *loop)    # section L (2026-11-16)
                later = {"before the control run": ("rlstart2b", "grpo2b", "grpo2c", "full2", "full3", "grpo3", *owner), "before the repeat run": ("grpo2c", "full2", "full3", "grpo3", *owner),
                         "before the full-data rerun": ("full2", "full3", "grpo3", *owner), "before RL on the full-data model": ("full3", "grpo3", *owner),
                         "before EXAONE on the owner's questions": owner, "before the owner-loop run": loop}.get(cloned_results, ())
                if any(x in str(f) for x in later):
                    continue              # the repository as it was when the owner ran that experiment
                dest = repo / f.relative_to(ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, dest)
        if "requests" not in sys.modules:
            try:
                import requests  # noqa: F401
            except ImportError:
                monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace())
        torch = types.SimpleNamespace(cuda=types.SimpleNamespace(get_device_name=lambda i: "Tesla T4", device_count=lambda: n_gpu))
        self.ns = ns = {"_sh": self._sh, "os": os, "subprocess": subprocess, "time": time, "json": json, "glob": glob, "shutil": shutil, "torch": torch,
                        "N_GPU": n_gpu, "ROOT": str(root), "VENV": str(root), "REPO_DIR": str(repo), "BACKUP": str(backup) if backup else None,
                        "ON_COLAB": False,
                        # a local bare repository stands in for GitHub; without one nothing is pushed and nothing is fetched
                        "REPO": str(remote) if remote else "https://example.invalid/none", "GH_TOKEN": "dummy-token" if remote else None,
                        "RESULT_BRANCH": "gpu-results-2", "RESTORE": bool(remote or backup)}
        (_, _setup), (_, helpers), *self.sections = code_cells("notebooks/gpu_experiments_2.ipynb")     # the setup cell needs a GPU and the network
        if run_32b:
            assert sum("RUN_32B = False" in src for _, src in self.sections) == 1
            self.sections = [(i, src.replace("RUN_32B = False", "RUN_32B = True")) for i, src in self.sections]
        if control:
            assert sum("RUN_CONTROL = False" in src for _, src in self.sections) == 1
            self.sections = [(i, src.replace("RUN_CONTROL = False", "RUN_CONTROL = True")) for i, src in self.sections]
        if not old_setting:
            assert sum("RUN_OLD_SETTING = True" in src for _, src in self.sections) == 1
            self.sections = [(i, src.replace("RUN_OLD_SETTING = True", "RUN_OLD_SETTING = False")) for i, src in self.sections]
        if repeat:
            assert sum("RUN_REPEAT = False" in src for _, src in self.sections) == 1
            self.sections = [(i, src.replace("RUN_REPEAT = False", "RUN_REPEAT = True")) for i, src in self.sections]
        exec(compile(to_python(helpers, "call"), "helpers", "exec"), ns)
        real_pack = ns["pack"]
        ns.update(serve=lambda *a, **k: _Proc(), stop_servers=lambda: None, pack=lambda: (self.packs.append(1), real_pack())[1])

    def _sh(self, cmd: str) -> None:
        kind = ("train" if "exaone_lora_sft.py" in cmd else "grpo" if "exaone_grpo.py" in cmd else "eval" if "tabletrace.eval.run" in cmd
                else "bench" if "engine_bench" in cmd else "other")
        self.calls.append((kind, cmd))
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
            if not (self.dies and self.dies in str(out)):
                (out / "metrics.json").write_text("{}")
        elif kind == "bench":
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("{}")

    def run_all(self, only: str | None = None) -> collections.Counter:
        """Run every section, or only the cells whose source holds `only` (the way the owner runs single sections)."""
        self.calls.clear()
        self.packs.clear()
        for i, src in self.sections:
            if only is None or only in src:
                exec(compile(to_python(src, "call"), f"cell {i}", "exec"), self.ns)
        return collections.Counter(kind for kind, _ in self.calls)

    def outputs(self) -> list[str]:
        return sorted({re.search(r"--out (\S+)", c).group(1) for k, c in self.calls if k in ("train", "eval", "grpo")})


class _Proc:
    def terminate(self): pass
    def wait(self): pass


def test_notebook_2_skips_finished_work_and_packs_results(tmp_path, monkeypatch):
    run = DryRun(tmp_path, monkeypatch)
    repo, calls, packs, sections, run_all = run.repo, run.calls, run.packs, run.sections, run.run_all

    first = run_all()
    assert first["train"] == 13 and first["grpo"] == 2 and first["eval"] >= 50               # 8 + the two full-data runs of section I + the models of sections L, M and N; RL in D and in J
    assert len(packs) >= len(sections) - 1                                   # every section ends by packing what exists so far
    assert Path.cwd() == repo                                                # pack() moves away for the download link and must come back
    names = tarfile.open(tmp_path / "gpu_results_2.tgz").getnames()
    assert any(n.endswith("exaone_grpo2/train_info.json") for n in names) and any("exaone_rlstart2_vllm_ko_test" in n for n in names)
    assert any(n.endswith("run_info_2.json") for n in names) and not any("merged" in n for n in names)
    kept = sorted(q.parent.name for q in (repo / "experiments").glob("*/merged"))
    assert kept == ["exaone_lora_pool7000", "exaone_lora_rlstart2"]          # the two that later sections serve again
    rl = [c for k, c in calls if k == "grpo"]
    assert len(rl) == 2 and all(x in c for c in rl for x in ("--sampling natural", "--dev-sample random", "--max-in 672", "--max-len 960", "--chunk 1"))
    assert "--adapter experiments/exaone_lora_rlstart2 " in rl[0] and "--adapter experiments/exaone_lora_full2 " in rl[1]      # section D, then section J
    start = [c for k, c in calls if k == "train" and "exaone_lora_rlstart2" in c]
    assert len(start) == 1 and "--max-in 672" in start[0] and "--max-len 960" in start[0]      # whole prompts and whole targets (issue 66)
    ddp = [c for k, c in calls if k == "train" and "exaone_lora_ddp" in c]
    assert len(ddp) == 2 and not any("--merge" in c.split() for c in ddp)    # the speed runs keep no merged model

    second = run_all()
    assert second["train"] == second["grpo"] == second["eval"] == 0          # nothing finished is done again

    (repo / "experiments/exaone_lora_colid_s2/train_info.json").unlink()     # as if stopped during this training
    shutil.rmtree(repo / "experiments/eval/exaone_colid_s2_vllm_ko_custom_ec")
    shutil.rmtree(repo / "experiments/eval/exaone_grpo2_vllm_ko_test_ec")    # as if stopped during this evaluation
    (repo / "experiments/exaone_grpo2/train_info.json").unlink()
    third = run_all()
    assert third["train"] == 1 and third["grpo"] == 1 and third["eval"] == 4
    assert run.outputs() == ["experiments/eval/exaone_colid_s2_vllm_ko_custom", "experiments/eval/exaone_colid_s2_vllm_ko_custom_ec",
                      "experiments/eval/exaone_grpo2_vllm_ko_test", "experiments/eval/exaone_grpo2_vllm_ko_test_ec",
                      "experiments/exaone_grpo2", "experiments/exaone_lora_colid_s2"]


def test_notebook_2_restores_a_backup_in_a_new_session(tmp_path, monkeypatch):
    """Colab deletes the working directory with the runtime. The result archive is also copied to a backup directory
    (Google Drive there); a new session unpacks it, so finished evaluations are not repeated. The archive holds no
    weights, but with every evaluation finished no model is needed, so nothing is trained either."""
    backup = tmp_path / "drive"
    backup.mkdir()
    (tmp_path / "s1").mkdir()
    first = DryRun(tmp_path / "s1", monkeypatch, backup)
    first.run_all()
    assert (backup / "gpu_results_2.tgz").stat().st_size > 0

    (tmp_path / "s2").mkdir()
    second = DryRun(tmp_path / "s2", monkeypatch, backup)                    # a new session: nothing but the backup
    assert (second.repo / "experiments/run_info_2.json").exists()            # unpacked when the helper cell ran
    counts = second.run_all()
    assert counts["eval"] == 0 and counts["grpo"] == 0 and counts["bench"] == 0
    assert second.outputs() == []


def test_notebook_2_on_a_single_gpu(tmp_path, monkeypatch):
    """Colab's free runtime has one GPU: the 32B models and the two-GPU speed comparison are left out, nothing uses torchrun."""
    run = DryRun(tmp_path, monkeypatch, n_gpu=1)
    counts = run.run_all()
    commands = [c for _, c in run.calls]
    assert counts["grpo"] == 2 and counts["train"] == 11                     # no ddp1 / ddp2
    assert not any("torchrun" in c for c in commands) and not any("32b" in o.lower() for o in run.outputs())
    assert (tmp_path / "gpu_results_2.tgz").exists()


def test_notebook_2_runs_the_32b_models_only_when_asked_and_with_headroom(tmp_path, monkeypatch):
    """The owner's first 32B run died of GPU memory during evaluation (95% preallocated, 8 concurrent requests). It is
    now off by default; switched on, it is served with headroom and small batches and scored on a sample."""
    (tmp_path / "off").mkdir()
    off = DryRun(tmp_path / "off", monkeypatch)
    off.run_all()
    assert not any("32b" in o for o in off.outputs())

    (tmp_path / "on").mkdir()
    on = DryRun(tmp_path / "on", monkeypatch, run_32b=True)
    served = []
    on.ns["serve"] = lambda model, **kw: (served.append((model, kw)), _Proc())[1]
    on.run_all()
    big = [kw for model, kw in served if "32B" in model]
    assert len(big) == 2 and all(kw["gpu_util"] <= 0.90 and "--max-num-seqs 2" in kw["extra"] and "--max-num-batched-tokens" in kw["extra"] for kw in big)
    first_pass = [c for k, c in on.calls if k == "eval" and "32b" in re.search(r"--out (\S+)", c).group(1) and "--replay-from" not in c]
    assert first_pass and all("--concurrency 2 " in c and "--sample" in c for c in first_pass)
    assert any("ref_32b_awq_ko_test" in o for o in on.outputs()) and any("tools_32b_awq_unseen_dev100" in o for o in on.outputs())


def test_notebook_2_goes_on_when_a_server_dies_during_evaluation(tmp_path, monkeypatch):
    run = DryRun(tmp_path, monkeypatch, run_32b=True, dies="ref_32b_awq")
    counts = run.run_all()
    mine = [c for k, c in run.calls if k == "eval" and "ref_32b_awq" in re.search(r"--out (\S+)", c).group(1)]
    assert len(mine) == 1 and "--replay-from" not in mine[0]                 # no second set, no re-verification of a missing file
    assert counts["grpo"] == 2 and counts["train"] == 13                     # the other sections still ran
    assert (tmp_path / "gpu_results_2.tgz").exists()


def test_pack_uses_the_colab_download_only_on_colab(tmp_path, monkeypatch):
    """Kaggle's image also ships the google.colab package. Its files.download() only works in Colab's front end; in a
    Kaggle notebook it showed "Javascript Error: download is not defined" and the download link never appeared. The
    platform is therefore decided by the working directory (ON_COLAB), not by whether the import succeeds."""
    downloads, links = [], []
    colab = types.ModuleType("google.colab")
    colab.files = types.SimpleNamespace(download=downloads.append)
    display = types.ModuleType("IPython.display")
    display.FileLink = lambda path: path
    display.display = links.append
    for name, module in (("google", types.ModuleType("google")), ("google.colab", colab), ("IPython", types.ModuleType("IPython")), ("IPython.display", display)):
        monkeypatch.setitem(sys.modules, name, module)
    run = DryRun(tmp_path, monkeypatch)
    run.ns["pack"]()                                                         # as on Kaggle: the package imports, ON_COLAB is False
    assert links == ["gpu_results_2.tgz"] and not downloads and Path.cwd() == run.repo
    run.ns["ON_COLAB"] = True
    run.ns["pack"]()
    assert downloads == [str(tmp_path / "gpu_results_2.tgz")] and len(links) == 1


def test_notebook_2_pushes_results_to_a_branch_and_a_new_session_restores_them(tmp_path, monkeypatch, capsys):
    """The owner's results were lost twice with the Kaggle session. With a GH_TOKEN secret every pack() also pushes the
    archive to a results branch; a new session fetches it, so finished evaluations are skipped. The token is passed to
    git in a header option and must not appear in what the notebook prints."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    (tmp_path / "s1").mkdir()
    first = DryRun(tmp_path / "s1", monkeypatch, remote=remote)
    first.run_all()
    heads = subprocess.run(["git", "--git-dir", str(remote), "for-each-ref", "--format=%(refname)"], capture_output=True, text=True).stdout.split()
    assert heads == ["refs/heads/gpu-results-2"]
    files = subprocess.run(["git", "--git-dir", str(remote), "ls-tree", "--name-only", "gpu-results-2"], capture_output=True, text=True).stdout.split()
    assert sorted(files) == ["gpu_results_2.tgz", "run_info_2.json"]
    printed = capsys.readouterr().out
    assert "GitHub에 올렸습니다" in printed and "dummy-token" not in printed

    (tmp_path / "s2").mkdir()
    second = DryRun(tmp_path / "s2", monkeypatch, remote=remote)             # a new session: an empty working directory
    assert (second.repo / "experiments/run_info_2.json").exists()
    counts = second.run_all()
    assert counts["eval"] == 0 and counts["grpo"] == 0
    assert second.outputs() == []


def test_a_failed_push_is_reported_without_stopping_or_leaking_the_token(tmp_path, monkeypatch, capsys):
    run = DryRun(tmp_path, monkeypatch, remote=tmp_path / "no-such-remote.git")
    run.ns["RESTORE"] = False
    counts = run.run_all()
    printed = capsys.readouterr().out
    assert counts["grpo"] == 2 and (tmp_path / "gpu_results_2.tgz").exists()
    assert "GitHub에 올리지 못했습니다" in printed and "dummy-token" not in printed


def test_notebook_2_reinforcement_learning_control_run_differs_only_in_sampling(tmp_path, monkeypatch):
    """The second experiment fixes two things at once (whole prompts, natural sampling). The optional control keeps the
    first run's balanced sampling with everything else equal, so the effect of the sampling can be told apart."""
    run = DryRun(tmp_path, monkeypatch, control=True)
    counts = run.run_all()
    rl = [c for k, c in run.calls if k == "grpo"]
    assert counts["grpo"] == 3 and "--sampling natural" in rl[0] and "--sampling balanced" in rl[1]      # the third is section J
    strip = lambda c: re.sub(r"--sampling \w+|--out \S+", "", c)                                  # noqa: E731
    assert strip(rl[0]) == strip(rl[1])
    assert any("exaone_grpo2b_vllm_ko_test" in o for o in run.outputs())


RL_CELLS = "RL_RUNS"            # the two cells of section D
BEFORE = "before the control run"
BEFORE_REPEAT = "before the repeat run"
BEFORE_FULL2 = "before the full-data rerun"
BEFORE_RL3 = "before RL on the full-data model"


def test_control_run_in_a_new_session_trains_and_evaluates_its_own_start_model(tmp_path, monkeypatch):
    """How the control was run on 2026-11-15. The first run's results were in the repository; its weights were not. A
    new session must not compare the control with the stored start model: a model trained again is not the same model.
    So it trains its own start model under an unused name, evaluates it, and starts from it. The finished main
    experiment is not repeated."""
    run = DryRun(tmp_path, monkeypatch, control=True, cloned_results=BEFORE)
    counts = run.run_all(only=RL_CELLS)
    assert counts["train"] == 1 and counts["grpo"] == 1 and counts["eval"] == 8             # (start + control) x (test + custom) x (first pass + subject check)
    assert run.outputs() == [f"experiments/eval/{name}_vllm_ko_{s}{ec}" for name in ("exaone_grpo2b", "exaone_rlstart2b") for s in ("custom", "test") for ec in ("", "_ec")] + [
        "experiments/exaone_grpo2b", "experiments/exaone_lora_rlstart2b"]
    start = next(c for k, c in run.calls if k == "train")
    assert "--limit 300" in start and "--max-in 672" in start and "--max-len 960" in start
    rl = next(c for k, c in run.calls if k == "grpo")
    assert "--adapter experiments/exaone_lora_rlstart2b " in rl and "--sampling balanced" in rl and "--dev-sample random" in rl and "--max-in 672" in rl
    assert [k for k, _ in run.calls if k in ("train", "grpo")] == ["train", "grpo"]         # the start model exists before RL begins
    stored = json.loads((ROOT / "experiments/exaone_lora_rlstart2/train_info.json").read_text())
    assert json.loads((run.repo / "experiments/exaone_lora_rlstart2/train_info.json").read_text()) == stored      # the first run's record is left alone
    names = tarfile.open(tmp_path / "gpu_results_2.tgz").getnames()
    assert any(n.endswith("exaone_grpo2b/train_info.json") for n in names) and any("exaone_rlstart2b_vllm_ko_test_ec" in n for n in names)

    assert run.run_all(only=RL_CELLS) == collections.Counter()                              # run again: nothing left to do


def test_the_recorded_control_run_matches_what_the_notebook_does(tmp_path, monkeypatch):
    """The stored training record of the control names the start model and the sampler the dry run expects."""
    args = json.loads((ROOT / "experiments/exaone_grpo2b/train_info.json").read_text())["args"]
    main = json.loads((ROOT / "experiments/exaone_grpo2/train_info.json").read_text())["args"]
    assert args["adapter"] == "experiments/exaone_lora_rlstart2b" and args["sampling"] == "balanced" and main["sampling"] == "natural"
    assert {k for k in set(args) | set(main) if args.get(k) != main.get(k)} == {"adapter", "out", "sampling"}


def test_without_a_flag_a_new_session_does_nothing_in_the_rl_section(tmp_path, monkeypatch):
    for state in (BEFORE, BEFORE_REPEAT, True):
        (tmp_path / str(state)).mkdir()
        run = DryRun(tmp_path / str(state), monkeypatch, cloned_results=state)
        assert run.run_all(only=RL_CELLS) == collections.Counter()


def test_repeat_in_a_new_session_without_weights_gets_its_own_start_model(tmp_path, monkeypatch):
    """The repository as it was after the control. The control flag has nothing to do. Without the weights of an
    earlier start model the repeat trains one under the next unused name: the stored evaluations of the earlier start
    models belong to other weights and must stay as they are."""
    (tmp_path / "control").mkdir()
    assert DryRun(tmp_path / "control", monkeypatch, control=True, cloned_results=BEFORE_REPEAT).run_all(only=RL_CELLS) == collections.Counter()

    (tmp_path / "repeat").mkdir()
    run = DryRun(tmp_path / "repeat", monkeypatch, repeat=True, cloned_results=BEFORE_REPEAT)
    counts = run.run_all(only=RL_CELLS)
    assert counts["train"] == 1 and counts["grpo"] == 1 and counts["eval"] == 8
    assert run.outputs() == [f"experiments/eval/{name}_vllm_ko_{s}{ec}" for name in ("exaone_grpo2c", "exaone_rlstart2c") for s in ("custom", "test") for ec in ("", "_ec")] + [
        "experiments/exaone_grpo2c", "experiments/exaone_lora_rlstart2c"]
    rl = next(c for k, c in run.calls if k == "grpo")
    assert "--adapter experiments/exaone_lora_rlstart2c " in rl and "--sampling natural" in rl
    for name in ("exaone_rlstart2_vllm", "exaone_rlstart2b_vllm", "exaone_grpo2_vllm", "exaone_grpo2b_vllm"):          # stored results are untouched
        f = f"experiments/eval/{name}_ko_test_ec/metrics.json"
        assert (run.repo / f).read_text() == (ROOT / f).read_text()


def test_repeat_uses_the_control_start_model_when_its_weights_are_still_there(tmp_path, monkeypatch):
    """How the repeat was run on 2026-11-15: the working directory of the control session was still on Kaggle, with the
    weights of the control's start model. The repeat starts from them, trains no start model and evaluates none, so
    repeat and control differ in the sampler only. The stored training record says the same."""
    run = DryRun(tmp_path, monkeypatch, repeat=True, cloned_results=BEFORE_REPEAT)
    start = run.repo / "experiments/exaone_lora_rlstart2b"
    (start / "merged").mkdir(parents=True, exist_ok=True)
    (start / "adapter_config.json").write_text("{}")
    (start / "merged" / "config.json").write_text("{}")
    counts = run.run_all(only=RL_CELLS)
    assert counts["train"] == 0 and counts["grpo"] == 1 and counts["eval"] == 4
    rl = next(c for k, c in run.calls if k == "grpo")
    assert "--adapter experiments/exaone_lora_rlstart2b " in rl and "--sampling natural" in rl and "--out experiments/exaone_grpo2c" in rl
    assert not any("rlstart2" in o for o in run.outputs())
    repeat = json.loads((ROOT / "experiments/exaone_grpo2c/train_info.json").read_text())["args"]
    control = json.loads((ROOT / "experiments/exaone_grpo2b/train_info.json").read_text())["args"]
    assert repeat["adapter"] == control["adapter"] == "experiments/exaone_lora_rlstart2b"
    assert {k for k in set(repeat) | set(control) if repeat.get(k) != control.get(k)} == {"out", "sampling"}


def test_with_everything_stored_no_flag_starts_a_run(tmp_path, monkeypatch):
    """Main experiment, control and repeat are in the repository. Neither flag trains or evaluates anything."""
    run = DryRun(tmp_path, monkeypatch, control=True, repeat=True, cloned_results=True)
    assert run.run_all(only=RL_CELLS) == collections.Counter()


def test_a_fresh_clone_skips_the_sections_whose_results_are_in_the_repository(tmp_path, monkeypatch):
    """Sections A and A2 were finished on 2026-11-15 and their results are committed under dot-free names; the notebook
    must find them under the same names."""
    run = DryRun(tmp_path, monkeypatch, cloned_results=True)
    run.run_all(only="REFS")
    assert [o for o in run.outputs() if "ref_" in o or "tools_" in o] == []


def test_control_and_repeat_start_from_the_same_model_and_differ_only_in_sampling(tmp_path, monkeypatch):
    run = DryRun(tmp_path, monkeypatch, control=True, repeat=True, cloned_results=BEFORE)
    counts = run.run_all(only=RL_CELLS)
    rl = [c for k, c in run.calls if k == "grpo"]
    assert counts["train"] == 1 and len(rl) == 2
    assert "--sampling balanced" in rl[0] and "--out experiments/exaone_grpo2b" in rl[0]    # the control first: it is what was asked for
    assert "--sampling natural" in rl[1] and "--out experiments/exaone_grpo2c" in rl[1]
    strip = lambda c: re.sub(r"--sampling \w+|--out \S+", "", c)                                  # noqa: E731
    assert strip(rl[0]) == strip(rl[1]) and "--adapter experiments/exaone_lora_rlstart2b " in rl[0]


def test_an_interrupted_session_does_not_reuse_the_name_of_a_start_model_whose_weights_are_gone(tmp_path, monkeypatch):
    """If a session dies after its start model was evaluated and before RL finished, the next session has that
    evaluation (restored) but not the weights. It trains a start model under the next unused name and leaves the old
    evaluation alone: an evaluation always belongs to the weights it was made with."""
    run = DryRun(tmp_path, monkeypatch, control=True, cloned_results=BEFORE)
    for s in ("test", "custom"):
        d = run.repo / f"experiments/eval/exaone_rlstart2b_vllm_ko_{s}_ec"
        d.mkdir(parents=True)
        (d / "metrics.json").write_text('{"from": "an earlier session"}')
    counts = run.run_all(only=RL_CELLS)
    assert counts["train"] == 1 and counts["grpo"] == 1 and counts["eval"] == 8
    assert (run.repo / "experiments/eval/exaone_rlstart2b_vllm_ko_test_ec/metrics.json").read_text() == '{"from": "an earlier session"}'
    assert "--adapter experiments/exaone_lora_rlstart2c " in next(c for k, c in run.calls if k == "grpo")
    assert any("exaone_rlstart2c_vllm_ko_test_ec" in o for o in run.outputs())


def test_a_half_finished_start_evaluation_is_made_again_with_the_new_weights(tmp_path, monkeypatch):
    """A name counts as used only when its evaluation is complete. A piece of an evaluation made with other weights
    (one set finished, the other not) is removed before the start model trained now is evaluated."""
    run = DryRun(tmp_path, monkeypatch, control=True, cloned_results=BEFORE)
    d = run.repo / "experiments/eval/exaone_rlstart2b_vllm_ko_test_ec"
    d.mkdir(parents=True)
    (d / "metrics.json").write_text('{"from": "other weights"}')
    counts = run.run_all(only=RL_CELLS)
    assert counts["eval"] == 8 and (d / "metrics.json").read_text() == "{}"


FULL_CELL = "FULL_RUNS"         # the cell of section I


def test_full_data_fine_tuning_is_repeated_with_whole_targets_next_to_the_old_setting(tmp_path, monkeypatch):
    """Every EXAONE fine-tuning so far cut the target of 15% of the training examples (issue 66). Section I trains on
    the full data with a cap that cuts nothing, and once more with the old cap in the same session: two trainings of
    the old setting already differed (84.3% and 87.1%), so the corrected run needs a partner from the same session.
    The two commands must differ in the length options only."""
    run = DryRun(tmp_path, monkeypatch, cloned_results=BEFORE_FULL2)
    counts = run.run_all(only=FULL_CELL)
    assert counts["train"] == 2 and counts["eval"] == 8 and counts["grpo"] == 0
    new, old = [c for k, c in run.calls if k == "train"]
    assert "--limit 0 " in new and "--max-in 672" in new and "--max-len 960" in new and "--out experiments/exaone_lora_full2" in new
    assert "--limit 0 " in old and "--max-in" not in old and "--max-len 768" in old and "--out experiments/exaone_lora_full2old" in old
    strip = lambda c: " ".join(re.sub(r"--max-in \d+|--max-len \d+|--out \S+", "", c).split())          # noqa: E731
    assert strip(new) == strip(old)
    first = json.loads((ROOT / "experiments/exaone_lora_full/train_info.json").read_text())
    assert first["n_examples"] == 3587                                       # what `--limit 0` trains on, as in the first notebook
    assert run.outputs() == [f"experiments/eval/exaone_{tag}_vllm_ko_{s}{ec}" for tag in ("full2", "full2old") for s in ("custom", "test") for ec in ("", "_ec")] + [
        "experiments/exaone_lora_full2", "experiments/exaone_lora_full2old"]
    assert all("--confidence" in c for k, c in run.calls if k == "eval" and "--replay-from" not in c)       # the curve of a full-data model is still missing
    assert [k for k, _ in run.calls if k in ("train", "eval")][:5] == ["train", "eval", "eval", "eval", "eval"]   # the corrected run is finished and packed first
    assert not list((run.repo / "experiments").glob("exaone_lora_full2*/merged"))                            # weights freed after evaluation
    names = tarfile.open(tmp_path / "gpu_results_2.tgz").getnames()
    assert any("exaone_full2_vllm_ko_test_ec" in n for n in names) and any(n.endswith("exaone_lora_full2old/train_info.json") for n in names)
    stored = (ROOT / "experiments/eval/exaone_full_vllm_ko_test/metrics.json").read_text()
    assert (run.repo / "experiments/eval/exaone_full_vllm_ko_test/metrics.json").read_text() == stored      # the first notebook's result keeps its name

    assert run.run_all(only=FULL_CELL) == collections.Counter()                                              # run again: nothing left to do


def test_the_recorded_full_data_runs_match_what_the_notebook_does_and_the_section_is_now_finished(tmp_path, monkeypatch):
    """Section I was run on 2026-11-16. The stored training records carry the options the dry run expects, the old
    setting reproduced the defect exactly as counted with the tokenizer, and with the results in the repository the
    section starts nothing."""
    new = json.loads((ROOT / "experiments/exaone_lora_full2/train_info.json").read_text())
    old = json.loads((ROOT / "experiments/exaone_lora_full2old/train_info.json").read_text())
    assert (new["args"]["max_in"], new["args"]["max_len"], new["targets_missing"], new["targets_cut_short"]) == (672, 960, 0, 0)
    assert (old["args"]["max_in"], old["args"]["max_len"]) == (None, 768)
    counted = json.loads((ROOT / "experiments/gpu2_2026-11-14/length_cap_check.json").read_text())["settings"]["as_run_until_2026_11_14"]["train"]
    assert (old["targets_missing"], old["targets_cut_short"]) == (counted["targets_missing"], counted["targets_cut_short"])
    assert {k for k in set(new["args"]) | set(old["args"]) if new["args"].get(k) != old["args"].get(k)} == {"max_in", "max_len", "out"}
    assert new["n_examples"] == old["n_examples"] == 3587 and new["steps"] == old["steps"]
    run = DryRun(tmp_path, monkeypatch, cloned_results=True)
    assert run.run_all(only=FULL_CELL) == collections.Counter()


def test_full_data_section_can_run_the_corrected_setting_alone(tmp_path, monkeypatch):
    run = DryRun(tmp_path, monkeypatch, cloned_results=BEFORE_FULL2, old_setting=False)
    counts = run.run_all(only=FULL_CELL)
    assert counts["train"] == 1 and counts["eval"] == 4
    assert "--max-in 672" in next(c for k, c in run.calls if k == "train") and not any("full2old" in o for o in run.outputs())


RL3_CELL = "RL3_DIR"            # the cell of section J


def test_rl_on_the_full_data_model_starts_from_the_stored_adapter_when_it_is_still_there(tmp_path, monkeypatch):
    """Section J asks what the same RL adds to a model already fine-tuned on the full data. Section I freed the merged
    weights of that model and kept its adapter; when the working directory is still there, RL starts from it and no
    start model is trained or evaluated again. The RL command is the one of the main experiment apart from the start
    model."""
    run = DryRun(tmp_path, monkeypatch, cloned_results=BEFORE_RL3)
    start = run.repo / "experiments/exaone_lora_full2"
    (start / "adapter_config.json").write_text("{}")                          # what section I leaves behind: the adapter, not merged/
    counts = run.run_all(only=RL3_CELL)
    assert counts["train"] == 0 and counts["grpo"] == 1 and counts["eval"] == 4
    rl = next(c for k, c in run.calls if k == "grpo")
    assert "--adapter experiments/exaone_lora_full2 " in rl and "--out experiments/exaone_grpo3" in rl
    main = json.loads((ROOT / "experiments/exaone_grpo2/train_info.json").read_text())["args"]
    for flag, key in (("--steps", "steps"), ("--prompts", "prompts"), ("--group", "group"), ("--chunk", "chunk"), ("--max-in", "max_in"), ("--max-len", "max_len"),
                      ("--sampling", "sampling"), ("--dev-sample", "dev_sample"), ("--dev-n", "dev_n"), ("--eval-every", "eval_every")):
        assert re.search(rf"{flag} (\S+)", rl).group(1) == str(main[key]), flag            # same settings as the stored main experiment
    assert float(re.search(r"--lr (\S+)", rl).group(1)) == main["lr"]
    assert run.outputs() == [f"experiments/eval/exaone_grpo3_vllm_ko_{s}{ec}" for s in ("custom", "test") for ec in ("", "_ec")] + ["experiments/exaone_grpo3"]
    stored = (ROOT / "experiments/eval/exaone_full2_vllm_ko_test_ec/metrics.json").read_text()
    assert (run.repo / "experiments/eval/exaone_full2_vllm_ko_test_ec/metrics.json").read_text() == stored
    assert not (run.repo / "experiments/exaone_grpo3/merged").exists()                      # weights freed after evaluation
    names = tarfile.open(tmp_path / "gpu_results_2.tgz").getnames()
    assert any(n.endswith("exaone_grpo3/train_log.jsonl") for n in names) and any("exaone_grpo3_vllm_ko_test_ec" in n for n in names)

    assert run.run_all(only=RL3_CELL) == collections.Counter()                              # run again: nothing left to do


def test_rl_on_the_full_data_model_trains_its_own_start_model_when_the_weights_are_gone(tmp_path, monkeypatch):
    """A new session has the evaluation of the full-data model but not its weights. It trains one with the corrected
    length setting under the next unused name, evaluates it, and starts RL from it; the stored evaluation stays."""
    run = DryRun(tmp_path, monkeypatch, cloned_results=BEFORE_RL3)
    counts = run.run_all(only=RL3_CELL)
    assert counts["train"] == 1 and counts["grpo"] == 1 and counts["eval"] == 8
    start = next(c for k, c in run.calls if k == "train")
    assert "--limit 0 " in start and "--max-in 672" in start and "--max-len 960" in start and "--out experiments/exaone_lora_full3" in start
    assert "--adapter experiments/exaone_lora_full3 " in next(c for k, c in run.calls if k == "grpo")
    assert [k for k, _ in run.calls if k in ("train", "grpo")] == ["train", "grpo"]
    assert run.outputs() == [f"experiments/eval/{name}_vllm_ko_{s}{ec}" for name in ("exaone_full3", "exaone_grpo3") for s in ("custom", "test") for ec in ("", "_ec")] + [
        "experiments/exaone_grpo3", "experiments/exaone_lora_full3"]
    stored = (ROOT / "experiments/eval/exaone_full2_vllm_ko_test/metrics.json").read_text()
    assert (run.repo / "experiments/eval/exaone_full2_vllm_ko_test/metrics.json").read_text() == stored
    names = tarfile.open(tmp_path / "gpu_results_2.tgz").getnames()
    assert any("exaone_full3_vllm_ko_test_ec" in n for n in names) and any(n.endswith("exaone_lora_full3/train_info.json") for n in names)


def test_the_recorded_rl_run_on_the_full_data_model_matches_what_the_notebook_does_and_the_section_is_now_finished(tmp_path, monkeypatch):
    """Section J was run on 2026-11-16 in a new session: the notebook trained a start model under the next unused name
    (`exaone_full3`) with the corrected length setting and started RL from it. The stored records carry those options,
    and with the results in the repository the section starts nothing."""
    start = json.loads((ROOT / "experiments/exaone_lora_full3/train_info.json").read_text())
    earlier = json.loads((ROOT / "experiments/exaone_lora_full2/train_info.json").read_text())
    assert (start["args"]["max_in"], start["args"]["max_len"], start["targets_missing"], start["targets_cut_short"], start["n_examples"]) == (672, 960, 0, 0, 3587)
    assert {k for k in set(start["args"]) | set(earlier["args"]) if start["args"].get(k) != earlier["args"].get(k)} == {"out"}
    rl = json.loads((ROOT / "experiments/exaone_grpo3/train_info.json").read_text())["args"]
    main = json.loads((ROOT / "experiments/exaone_grpo2/train_info.json").read_text())["args"]
    assert rl["adapter"] == "experiments/exaone_lora_full3" and rl["out"] == "experiments/exaone_grpo3"
    assert {k for k in set(rl) | set(main) if rl.get(k) != main.get(k)} == {"adapter", "out"}
    info = json.loads((ROOT / "experiments/run_info_2_rl3.json").read_text())
    before = json.loads((ROOT / "experiments/eval/exaone_full3_vllm_ko_test/metrics.json").read_text())["meta"]["finished"]
    after = json.loads((ROOT / "experiments/eval/exaone_grpo3_vllm_ko_custom_ec/metrics.json").read_text())["meta"]["finished"]
    assert before < after <= info["finished"]                                   # start model evaluated first, RL model last, then the archive
    run = DryRun(tmp_path, monkeypatch, cloned_results=True)
    assert run.run_all(only=RL3_CELL) == collections.Counter()


OWNER_CELL = "OWNER_SETS"       # the cell of section L
BEFORE_OWNER = "before EXAONE on the owner's questions"


def test_owner_questions_section_trains_a_full_data_model_in_a_new_session_and_evaluates_three_models(tmp_path, monkeypatch):
    """Section L measures EXAONE on the 30 questions the owner wrote. A new session has no weights, so the full-data
    model is trained again under the next unused name with the corrected length setting and evaluated on the test set,
    the AI-written questions and the owner's questions. The two untuned models get the owner's questions only, with the
    few-shot setting of section A. Stored results stay as they are."""
    run = DryRun(tmp_path, monkeypatch, cloned_results=BEFORE_OWNER)
    counts = run.run_all(only=OWNER_CELL)
    assert counts["train"] == 1 and counts["grpo"] == 0 and counts["eval"] == 10
    train = next(c for k, c in run.calls if k == "train")
    assert "--limit 0 " in train and "--max-in 672" in train and "--max-len 960" in train and "--out experiments/exaone_lora_full4" in train
    assert run.outputs() == sorted([f"experiments/eval/exaone_full4_vllm_ko_{s}{ec}" for s in ("test", "custom", "owner") for ec in ("", "_ec")]
                                   + [f"experiments/eval/{m}_ko_owner{ec}" for m in ("ref_1p2b", "ref_7p8b_awq") for ec in ("", "_ec")] + ["experiments/exaone_lora_full4"])
    owner = [c for k, c in run.calls if k == "eval" and "ko_owner" in c and "--replay-from" not in c]
    assert len(owner) == 3 and all("--data data/ko/owner_eval.jsonl" in c and "--confidence" in c and "--no-entity-check" in c and "--max-in 672" in c for c in owner)
    shots = [c for c in owner if "ref_" in c]
    assert len(shots) == 2 and all("--few-shot data/ko/train.jsonl data/ko/synthetic_train.jsonl --shots-per-kind 2" in c for c in shots)
    assert not any("--few-shot" in c for c in owner if "exaone_full4" in c)                          # the tuned model gets no examples
    stored = (ROOT / "experiments/eval/ref_1p2b_ko_test/metrics.json").read_text()
    assert (run.repo / "experiments/eval/ref_1p2b_ko_test/metrics.json").read_text() == stored      # earlier results untouched
    assert not (run.repo / "experiments/exaone_lora_full4/merged").exists()                         # weights freed after evaluation
    names = tarfile.open(tmp_path / "gpu_results_2.tgz").getnames()
    assert any("exaone_full4_vllm_ko_owner_ec" in n for n in names) and any("ref_7p8b_awq_ko_owner" in n for n in names)
    assert any(n.endswith("exaone_lora_full4/train_info.json") for n in names)

    assert run.run_all(only=OWNER_CELL) == collections.Counter()                                    # run again: nothing left to do


def test_owner_questions_section_uses_merged_weights_that_are_still_there_and_can_skip_the_larger_model(tmp_path, monkeypatch):
    """If the merged weights of an evaluated full-data model are still in the working directory, that model is served
    again and only the owner's questions are evaluated with it. `RUN_7P8B_OWNER = False` leaves the 7.8B model out."""
    run = DryRun(tmp_path, monkeypatch, cloned_results=BEFORE_OWNER)
    assert sum("RUN_7P8B_OWNER = True" in src for _, src in run.sections) == 1
    run.sections = [(i, src.replace("RUN_7P8B_OWNER = True", "RUN_7P8B_OWNER = False")) for i, src in run.sections]
    merged = run.repo / "experiments/exaone_lora_full3/merged"
    merged.mkdir(parents=True)
    (merged / "config.json").write_text("{}")
    counts = run.run_all(only=OWNER_CELL)
    assert counts["train"] == 0 and counts["eval"] == 4
    assert run.outputs() == sorted([f"experiments/eval/{m}_ko_owner{ec}" for m in ("exaone_full3_vllm", "ref_1p2b") for ec in ("", "_ec")])


def test_the_recorded_owner_question_run_matches_what_the_notebook_does_and_the_section_is_now_finished(tmp_path, monkeypatch):
    """Section L was run on 2026-11-16 in a new session: a full-data model was trained under the next unused name with
    the corrected length setting, and the untuned models got the few-shot setting of section A. With the results in the
    repository the section starts nothing."""
    info = json.loads((ROOT / "experiments/exaone_lora_full4/train_info.json").read_text())
    earlier = json.loads((ROOT / "experiments/exaone_lora_full3/train_info.json").read_text())
    assert (info["args"]["max_in"], info["args"]["max_len"], info["targets_missing"], info["targets_cut_short"], info["n_examples"]) == (672, 960, 0, 0, 3587)
    assert {k for k in set(info["args"]) | set(earlier["args"]) if info["args"].get(k) != earlier["args"].get(k)} == {"out"}
    for name, shots in (("exaone_full4_vllm", None), ("ref_1p2b", ["data/ko/train.jsonl", "data/ko/synthetic_train.jsonl"]), ("ref_7p8b_awq", ["data/ko/train.jsonl", "data/ko/synthetic_train.jsonl"])):
        meta = json.loads((ROOT / f"experiments/eval/{name}_ko_owner/metrics.json").read_text())["meta"]
        assert meta["data"] == ["data/ko/owner_eval.jsonl"] and meta["few_shot"] == shots and meta["entity_check"] is False and meta["confidence"] is True
        again = json.loads((ROOT / f"experiments/eval/{name}_ko_owner_ec/metrics.json").read_text())["meta"]
        assert again["entity_check"] is True and again["replay_from"] == f"experiments/eval/{name}_ko_owner"
    run = DryRun(tmp_path, monkeypatch, cloned_results=True)
    assert run.run_all(only=OWNER_CELL) == collections.Counter()


OWNLOOP_CELL = "OWNLOOP_DIR"    # the cell of section M


def test_owner_loop_section_trains_the_full_data_model_with_the_owner_written_loop(tmp_path, monkeypatch):
    """Every stored EXAONE fine-tuning ran with the loop built into the script. Section M trains the full-data model
    once with the loop the owner wrote: the same command as the other full-data trainings plus `--loop owner`, and the
    same three evaluations as section L."""
    run = DryRun(tmp_path, monkeypatch, cloned_results="before the owner-loop run")
    counts = run.run_all(only=OWNLOOP_CELL)
    assert counts["train"] == 1 and counts["grpo"] == 0 and counts["eval"] == 6
    train = next(c for k, c in run.calls if k == "train")
    assert "--loop owner" in train.split("--limit")[1] and "--limit 0 " in train and "--max-in 672" in train and "--max-len 960" in train
    assert "--out experiments/exaone_lora_ownloop" in train and "--merge" in train.split()
    stored = json.loads((ROOT / "experiments/exaone_lora_full4/train_info.json").read_text())["args"]         # the built-in loop, same data and lengths
    for flag, key in (("--epochs", "epochs"), ("--bs", "bs"), ("--grad-accum", "grad_accum"), ("--max-len", "max_len"), ("--max-in", "max_in"), ("--seed", "seed"), ("--limit", "limit")):
        assert float(re.search(rf"{flag} (\S+)", train).group(1)) == float(stored[key]), flag
    assert stored["loop"] == "builtin"
    assert run.outputs() == sorted([f"experiments/eval/exaone_ownloop_vllm_ko_{s}{ec}" for s in ("test", "custom", "owner") for ec in ("", "_ec")] + ["experiments/exaone_lora_ownloop"])
    names = tarfile.open(tmp_path / "gpu_results_2.tgz").getnames()
    assert any("exaone_ownloop_vllm_ko_owner_ec" in n for n in names) and any(n.endswith("exaone_lora_ownloop/train_info.json") for n in names)
    assert not (run.repo / "experiments/exaone_lora_ownloop/merged").exists()
    assert run.run_all(only=OWNLOOP_CELL) == collections.Counter()                                           # run again: nothing left to do
    # the notebook recognises the owner's loop by the text the training script records for it
    src = next(src for _, src in run.sections if OWNLOOP_CELL in src)
    script = (ROOT / "scripts/train/exaone_lora_sft.py").read_text(encoding="utf-8")
    assert '"owner" not in str(t.get("loop"))' in src and "tabletrace.training.lm_loop (owner-written)" in script


def test_the_recorded_owner_loop_run_matches_what_the_notebook_does_and_the_section_is_now_finished(tmp_path, monkeypatch):
    """Section M was run on 2026-11-16 on Colab with one T4. The stored training record names the owner's loop, carries a
    learning rate for every step (only that loop records it) and differs from the built-in run of the same command in
    the loop and the output path only. With the results in the repository the section starts nothing."""
    own = json.loads((ROOT / "experiments/exaone_lora_ownloop/train_info.json").read_text())
    builtin = json.loads((ROOT / "experiments/exaone_lora_full4/train_info.json").read_text())
    assert own["loop"] == "tabletrace.training.lm_loop (owner-written)" and builtin["loop"] == "builtin"
    assert {k for k in set(own["args"]) | set(builtin["args"]) if own["args"].get(k) != builtin["args"].get(k)} == {"loop", "out"}
    assert (own["n_examples"], own["steps"], own["targets_missing"], own["targets_cut_short"]) == (builtin["n_examples"], builtin["steps"], 0, 0)
    lrs = [x["lr"] for x in own["loss_log"]]
    assert len(lrs) == own["steps"] and lrs[0] == own["args"]["lr"] and all(a > b for a, b in itertools.pairwise(lrs)) and lrs[-1] < lrs[0] / 100
    assert not any("lr" in x for x in builtin["loss_log"])
    info = json.loads((ROOT / "experiments/run_info_2_ownloop.json").read_text())
    assert info["platform"] == "colab" and info["gpus"] == ["Tesla T4"]
    run = DryRun(tmp_path, monkeypatch, cloned_results=True)
    assert run.run_all(only=OWNLOOP_CELL) == collections.Counter()


CHEM_CELL = "KOCHEM_DIR, KOCHEM_NAME"


def test_chemistry_section_trains_one_model_and_keeps_per_question_predictions(tmp_path, monkeypatch):
    """Section G's chemistry results (2026-11-14) survive as numbers read off the notebook's output only. Section N runs
    the experiment again so that per-question predictions exist: one model tuned on Korean and chemistry with the
    corrected length setting, scored on three chemistry sets and three Korean sets, and the untuned 1.2B model on the
    chemistry sets with examples drawn from the chemistry training questions."""
    run = DryRun(tmp_path, monkeypatch, cloned_results=True)                 # main as it is today: no chemistry predictions
    counts = run.run_all(only=CHEM_CELL)
    assert counts["train"] == 1 and counts["grpo"] == 0 and counts["eval"] == 2 * (6 + 3)
    train = next(c for k, c in run.calls if k == "train")
    assert "--train data/ko/train.jsonl data/ko/synthetic_train.jsonl data/chem/synthetic_train.jsonl " in train
    assert "--corpus data/ko/documents.jsonl data/chem/documents.jsonl " in train and "--out experiments/exaone_lora_kochem2" in train and "--merge" in train.split()
    assert "--max-in 672" in train and "--max-len 960" in train and "--limit 0 " in train          # whole prompts and whole targets (issue 66)
    stored = json.loads((ROOT / "experiments/exaone_lora_full4/train_info.json").read_text())["args"]   # a full-data training with the same lengths
    for flag, key in (("--epochs", "epochs"), ("--bs", "bs"), ("--grad-accum", "grad_accum"), ("--max-len", "max_len"), ("--max-in", "max_in"), ("--seed", "seed"), ("--limit", "limit")):
        assert float(re.search(rf"{flag} (\S+)", train).group(1)) == float(stored[key]), flag
    first = {re.search(r"--out (\S+)", c).group(1): c for k, c in run.calls if k == "eval" and "--replay-from" not in c}
    tuned, untuned = "experiments/eval/exaone_kochem2_vllm_", "experiments/eval/ref_1p2b_"
    assert sorted(first) == sorted([tuned + s for s in ("chem_custom", "chem_syndev", "chem_papers", "ko_test", "ko_custom", "ko_owner")]
                                   + [untuned + s for s in ("chem_custom", "chem_syndev", "chem_papers")])
    for out, cmd in first.items():
        assert ("--row-select overlap" in cmd) == out.endswith("chem_papers"), out            # the paper tables: rows chosen by overlap, as in section G
        assert ("--few-shot data/chem/synthetic_train.jsonl --shots-per-kind 2" in cmd) == out.startswith(untuned), out
        assert "--confidence" in cmd and "--no-entity-check" in cmd and "--max-in 672" in cmd
    assert "--corpus data/chem/documents.jsonl --data data/chem/custom_eval.jsonl" in first[tuned + "chem_custom"]
    assert "--corpus data/chem_papers/documents.jsonl --data data/chem_papers/custom_eval.jsonl" in first[tuned + "chem_papers"]
    # the examples of the untuned model come from the textbook documents, so its paper evaluation is given both document files
    assert "--corpus data/chem_papers/documents.jsonl data/chem/documents.jsonl --data data/chem_papers/custom_eval.jsonl" in first[untuned + "chem_papers"]
    assert "--concurrency 8 " in first[untuned + "chem_papers"] and "--data data/ko/owner_eval.jsonl" in first[tuned + "ko_owner"]
    replays = [c for k, c in run.calls if k == "eval" and "--replay-from" in c]
    assert len(replays) == 9 and all(c.split("--out ")[1].strip().endswith("_ec") for c in replays)
    names = tarfile.open(tmp_path / "gpu_results_2.tgz").getnames()
    assert any("exaone_kochem2_vllm_chem_papers_ec" in n for n in names) and any("ref_1p2b_chem_custom_ec" in n for n in names)
    assert any(n.endswith("exaone_lora_kochem2/train_info.json") for n in names) and not any("merged" in n for n in names)
    assert not (run.repo / "experiments/exaone_lora_kochem2/merged").exists()
    assert run.run_all(only=CHEM_CELL) == collections.Counter()                                # run again: nothing left to do


def test_chemistry_section_can_leave_out_the_untuned_model_and_does_not_repeat_stored_evaluations(tmp_path, monkeypatch):
    run = DryRun(tmp_path, monkeypatch, cloned_results=True)
    assert sum("RUN_UNTUNED_ON_CHEM = True" in src for _, src in run.sections) == 1
    run.sections = [(i, src.replace("RUN_UNTUNED_ON_CHEM = True", "RUN_UNTUNED_ON_CHEM = False")) for i, src in run.sections]
    counts = run.run_all(only=CHEM_CELL)
    assert counts["train"] == 1 and counts["eval"] == 12
    outs = run.outputs()
    assert not any("ref_1p2b" in o for o in outs)                                              # the stored Korean evaluations of the untuned model are left alone
    assert all("kochem2" in o for o in outs)


def test_the_chemistry_examples_can_be_drawn_and_the_earlier_run_is_only_a_recovered_record():
    """Six examples for the untuned model need a lookup, a calculation and a withheld answer twice over in the chemistry
    training questions. The earlier run of the same experiment (section G) left numbers but no predictions."""
    ops = collections.Counter(json.loads(line)["op"] for line in (ROOT / "data/chem/synthetic_train.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
    assert ops["lookup"] >= 2 and ops["abstain"] >= 2 and sum(n for op, n in ops.items() if op not in ("lookup", "abstain", "text")) >= 2
    assert not list((ROOT / "experiments/eval").glob("exaone_kochem_vllm_*"))
    recovered = json.loads((ROOT / "experiments/gpu2_2026-11-14/recovered.json").read_text(encoding="utf-8"))["evals"]
    assert "exaone_kochem_vllm_chem_papers" in recovered
    intro = "".join(json.loads((ROOT / "notebooks/gpu_experiments_2.ipynb").read_text(encoding="utf-8"))["cells"][0]["source"])
    if not list((ROOT / "experiments/eval").glob("exaone_kochem2_vllm_*")):
        assert "지금 돌릴 것은 N절 하나입니다" in intro and "아직 돌리지 않음" in intro


def test_setup_cell_updates_a_stale_clone_even_when_old_result_files_are_in_the_way(tmp_path):
    """Results of an earlier session lie untracked in the working directory; the same paths are tracked in the newer
    main. `git pull` stops there, and the notebook used to go on with the old code without saying so."""
    setup = code_cells("notebooks/gpu_experiments_2.ipynb")[0][1]
    update = [line[1:] for line in setup.splitlines() if line.startswith("!git fetch")]
    assert len(update) == 1 and not [line for line in setup.splitlines() if line.startswith("!git pull")]

    def git(cwd, *args):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout.strip()

    origin, clone = tmp_path / "origin", tmp_path / "clone"
    origin.mkdir()
    git(origin, "init", "-q", "-b", "main")
    (origin / "code.py").write_text("old\n")
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "one")
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    (clone / "results").mkdir()
    (clone / "results" / "metrics.json").write_text("made in the earlier session\n")       # untracked here
    (clone / "weights.bin").write_text("large\n")                                           # untracked, not in the repository
    (origin / "code.py").write_text("new\n")
    (origin / "results").mkdir()
    (origin / "results" / "metrics.json").write_text("committed\n")                        # the same path, now tracked
    git(origin, "add", "-A")
    git(origin, "commit", "-q", "-m", "two")
    assert subprocess.run(["git", "pull", "-q"], cwd=clone, capture_output=True).returncode != 0      # what used to happen
    r = subprocess.run(["bash", "-c", update[0]], cwd=clone, capture_output=True, text=True)
    assert "갱신하지 못했습니다" not in r.stdout, r.stdout + r.stderr
    assert (clone / "code.py").read_text() == "new\n" and git(clone, "rev-parse", "HEAD") == git(origin, "rev-parse", "HEAD")
    assert (clone / "results" / "metrics.json").read_text() == "committed\n" and (clone / "weights.bin").read_text() == "large\n"

