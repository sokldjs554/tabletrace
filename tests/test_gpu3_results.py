"""The third GPU run (2026-11-15) came back as result files with per-question predictions. These tests keep the stored
analysis tied to those predictions: the derived files must be what the scripts produce, the headline comparison must
follow from the predictions, and a stored run must give the same verdicts when its outputs are verified again."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "experiments" / "eval"
START, RL = "exaone_rlstart2_vllm_ko_test", "exaone_grpo2_vllm_ko_test"
TOKENIZER = ROOT / "models" / "exaone-4.0-1.2b"


def rows(run: str) -> dict[str, dict]:
    with open(EVAL / run / "predictions.jsonl", encoding="utf-8") as f:
        return {r["qid"]: r for r in map(json.loads, f)}


def test_run_names_hold_no_dots():
    """Documents cite results as dotted paths, so a run called `ref_1.2b` cannot be cited."""
    assert [d.name for d in EVAL.iterdir() if d.is_dir() and "." in d.name] == []
    nb = json.loads((ROOT / "notebooks" / "gpu_experiments_2.ipynb").read_text(encoding="utf-8"))
    src = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    names = re.findall(r'\("((?:ref|tools)_[^"]+)",', src)
    assert {"ref_1p2b", "ref_7p8b_awq", "tools_1p2b"} <= set(names)
    assert [n for n in names if "." in n] == []


@pytest.mark.parametrize("script, out", [("rl2_analysis.py", "rl2_analysis.json"), ("gpu3_summary.py", "gpu3_summary.json")])
def test_derived_files_are_reproduced_from_the_predictions(script, out):
    stored = (EVAL / out).read_text(encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    assert (EVAL / out).read_text(encoding="utf-8") == stored


def test_headline_comparison_follows_from_the_predictions():
    a, b = rows(START), rows(RL)
    assert set(a) == set(b) and len(a) == 699
    only_rl = sum(b[q]["verified_correct"] and not a[q]["verified_correct"] for q in a)
    only_start = sum(a[q]["verified_correct"] and not b[q]["verified_correct"] for q in a)
    pt = json.loads((EVAL / "paired_tests.json").read_text(encoding="utf-8"))["grpo2_vs_rlstart2_ko_test"]
    assert (pt["candidate_better"], pt["reference_better"]) == (only_rl, only_start)
    assert only_rl > only_start and pt["p_two_sided"] < 0.001
    for run, preds in ((START, a), (RL, b)):                                   # the metrics file agrees with its own predictions
        m = json.loads((EVAL / run / "metrics.json").read_text(encoding="utf-8"))["metrics"]
        assert m["verified_em"] == pytest.approx(sum(r["verified_correct"] for r in preds.values()) / len(preds), abs=5e-5)


def test_analysis_says_what_did_not_improve():
    """The write-up must not turn into "RL solved it": calculation questions and unanswerable questions did not improve."""
    d = json.loads((EVAL / "rl2_analysis.json").read_text(encoding="utf-8"))
    fp = d["first_pass"]["outcomes"]
    for model in ("start", "rl"):
        for kind in ("all", "lookup", "calc", "unanswerable"):
            o = fp[model][kind]
            assert o["correct"] + o["wrong"] + o["withheld"] == o["n"]
        assert sum(fp[model][k]["n"] for k in ("lookup", "calc", "unanswerable")) == fp[model]["all"]["n"] == 699
    assert fp["rl"]["calc"]["correct"] <= fp["start"]["calc"]["correct"] <= 1          # no calculation question was solved
    assert d["raw"]["rl"]["calc_written_as_lookup"] == d["raw"]["rl"]["calc_questions"]    # the model never writes a calculation program
    assert fp["rl"]["unanswerable"]["correct"] == fp["start"]["unanswerable"]["correct"]
    assert fp["rl"]["lookup"]["correct"] > fp["start"]["lookup"]["correct"]
    assert d["raw"]["rl"]["lookup_cited_gold_cell"] > d["raw"]["start"]["lookup_cited_gold_cell"]
    t = d["training"]
    assert t["prompts_cut_train"] == t["prompts_cut_dev"] == 0 and t["kept_step"] == t["best_dev_step"]
    assert all(v["unparsable"] == 0 for v in t["dev"].values())


def test_replay_record_covers_every_run_of_the_session():
    d = json.loads((EVAL / "replay_check_gpu3.json").read_text(encoding="utf-8"))
    assert d["replays"] == 2 * len(d["runs"]) == 22 and d["questions_that_differ"] == 0
    for run, res in d["runs"].items():
        n = len(rows(run))
        assert res["first_pass"]["questions"] == res["subject_check"]["questions"] == n == len(rows(run + "_ec"))
    assert d["questions_checked"] == sum(2 * len(rows(run)) for run in d["runs"])


@pytest.mark.skipif(not TOKENIZER.exists(), reason="needs the EXAONE tokenizer (models/exaone-4.0-1.2b is not in git)")
def test_a_stored_run_gives_the_same_verdicts_when_verified_again(tmp_path):
    run = "exaone_grpo2_vllm_ko_custom"
    meta = json.loads((EVAL / run / "metrics.json").read_text(encoding="utf-8"))["meta"]
    cmd = [sys.executable, "-m", "tabletrace.eval.run", "--planner", "engine", "--replay-from", str(EVAL / run), "--no-entity-check",
           "--tokenizer", str(TOKENIZER), "--max-in", "672", "--corpus", *meta["corpus"], "--data", *meta["data"], "--out", str(tmp_path / "again")]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    with open(tmp_path / "again" / "predictions.jsonl", encoding="utf-8") as f:
        again = {x["qid"]: x for x in map(json.loads, f)}
    stored = rows(run)
    assert set(again) == set(stored)
    for q, s in stored.items():
        assert [again[q][k] for k in ("pred_status", "pred_answer", "pred_cells", "verified_correct")] == [s[k] for k in ("pred_status", "pred_answer", "pred_cells", "verified_correct")]
