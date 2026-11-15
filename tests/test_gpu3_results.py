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


@pytest.mark.parametrize("script, out", [("rl2_analysis.py", "rl2_analysis.json"), ("rl2_analysis.py", "rl2_control_analysis.json"), ("gpu3_summary.py", "gpu3_summary.json")])
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


@pytest.mark.parametrize("session, replays", [("gpu3", 22), ("control", 8)])
def test_replay_record_covers_every_run_of_the_session(session, replays):
    d = json.loads((EVAL / f"replay_check_{session}.json").read_text(encoding="utf-8"))
    assert d["replays"] == 2 * len(d["runs"]) == replays and d["questions_that_differ"] == 0
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


def test_control_run_shows_that_the_batch_mix_decides_and_the_write_up_keeps_the_limits():
    """The control keeps the first experiment's balanced sampling and changes nothing else. What the documents say about
    it must follow from the stored predictions and training record."""
    c = json.loads((EVAL / "rl2_control_analysis.json").read_text(encoding="utf-8"))
    a = json.loads((EVAL / "rl2_analysis.json").read_text(encoding="utf-8"))
    # cited cells: no change in the control, a clear change in the main experiment, and the two changes differ
    assert c["raw"]["sign_test_cited_gold_cell_lookup"]["p_two_sided"] > 0.05 and a["raw"]["sign_test_cited_gold_cell_lookup"]["p_two_sided"] < 0.001
    dd = c["main_minus_control"]["first_pass"]
    assert dd["cited_gold_cell_lookup"]["p_two_sided"] < 0.001 and dd["cited_gold_cell_lookup"]["net_change_main"] > 10 * max(1, dd["cited_gold_cell_lookup"]["net_change_control"])
    # verified EM: the gains of the two arms do NOT differ significantly; a document must not say they do
    assert dd["verified_correct_all"]["p_two_sided"] > 0.05
    # the control collapsed during training although no prompt was cut
    t = c["training"]
    assert t["sampling"] == "balanced" and t["prompts_cut_train"] == t["prompts_cut_dev"] == 0
    assert t["kept_step"] == 25 and t["phases"]["p4"]["withheld_rate"] > 0.95 and t["dev_last"]["correct"] < t["dev_first"]["correct"]
    assert a["training"]["phases"]["p4"]["correct"] > a["training"]["phases"]["p1"]["correct"]
    # the two arms have different start models, and the comparison says so
    assert c["start"] != a["start"] and c["start_models"]["same_raw_output"] < c["start_models"]["questions"]
    report = (ROOT / "docs" / "REPORT.md").read_text(encoding="utf-8")
    sec = report[report.index("### 22.7 대조군"):]
    for needle in ("세션과 시작 모델이 다르다", "프롬프트 수정이 필요했는지는 모른다", "유의하게 다르지 않다", "한 번, 시드 하나"):
        assert needle in sec, needle
    handoff = (ROOT / "docs" / "HANDOFF.md").read_text(encoding="utf-8")
    assert "까닭이 학습 스크립트가 프롬프트를 자르는 결함으로 밝혀져 고친 뒤 다시 돌렸다. 두 번째" not in handoff      # the sentence the control refuted


def test_control_headline_numbers_follow_from_the_predictions():
    a, b = rows("exaone_rlstart2b_vllm_ko_test"), rows("exaone_grpo2b_vllm_ko_test")
    assert set(a) == set(b) == set(rows(START))
    lookup = [q for q in a if a[q]["gold_status"] == "answered" and a[q]["gold_op"] == "lookup"]
    c = json.loads((EVAL / "rl2_control_analysis.json").read_text(encoding="utf-8"))
    assert c["raw"]["start"]["lookup_cited_gold_cell"] == sum(bool(a[q]["cells_exact_raw"]) for q in lookup)
    assert c["raw"]["rl"]["lookup_cited_gold_cell"] == sum(bool(b[q]["cells_exact_raw"]) for q in lookup)
    pt = json.loads((EVAL / "paired_tests.json").read_text(encoding="utf-8"))["grpo2b_vs_rlstart2b_ko_test"]
    assert pt["candidate_better"] == sum(b[q]["verified_correct"] and not a[q]["verified_correct"] for q in a)
    assert pt["reference_better"] == sum(a[q]["verified_correct"] and not b[q]["verified_correct"] for q in a)

