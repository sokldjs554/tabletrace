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


@pytest.mark.parametrize("script, out", [("rl2_analysis.py", "rl2_analysis.json"), ("rl2_analysis.py", "rl2_control_analysis.json"), ("rl2_analysis.py", "rl2_repeat_analysis.json"),
                                         ("gpu3_summary.py", "gpu3_summary.json"), ("length_fix_analysis.py", "length_fix_analysis.json"),
                                         ("rl3_analysis.py", "rl3_analysis.json")])
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


@pytest.mark.parametrize("session, replays", [("gpu3", 22), ("control", 8), ("repeat", 4), ("full2", 8), ("rl3", 8)])
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




def test_repeat_run_reproduces_the_main_experiment_and_separates_from_the_control_on_the_same_start_model():
    """The main experiment was run once more, from the control's start model. The documents say three things; each must
    follow from the stored predictions: the result came out again, the comparison with the control needs no correction
    for the start model, and verified EM still does not separate the two samplers."""
    r = json.loads((EVAL / "rl2_repeat_analysis.json").read_text(encoding="utf-8"))
    a = json.loads((EVAL / "rl2_analysis.json").read_text(encoding="utf-8"))
    c = json.loads((EVAL / "rl2_control_analysis.json").read_text(encoding="utf-8"))
    assert r["start"] == c["start"] and r["same_start_model_as_control"] and r["training_args_that_differ_from_control"] == ["out", "sampling"]
    assert r["training"]["dev_first"] == c["training"]["dev_first"]                         # the same model before RL, checked on the same dev questions
    # the result came out again
    assert r["raw"]["sign_test_cited_gold_cell_lookup"]["p_two_sided"] < 0.001 and r["first_pass"]["sign_tests"]["correct_all"]["p_two_sided"] < 0.01
    assert r["raw"]["rl"]["lookup_cited_gold_cell"] > 1.5 * r["raw"]["start"]["lookup_cited_gold_cell"]
    assert r["main_minus_repeat"]["first_pass"]["verified_correct_all"]["p_two_sided"] > 0.05
    # against the control, same start model: cited cells differ, verified EM does not
    d = r["repeat_minus_control"]["first_pass"]
    assert d["cited_gold_cell_lookup"]["p_two_sided"] < 0.001 and d["wrong_answer_all"]["p_two_sided"] < 0.001
    assert d["verified_correct_all"]["p_two_sided"] > 0.05
    b, k = rows(RL.replace("grpo2", "grpo2c")), rows("exaone_grpo2b_vllm_ko_test")              # the direct comparison, recomputed
    lookup = [q for q in b if b[q]["gold_status"] == "answered" and b[q]["gold_op"] == "lookup"]
    assert d["cited_gold_cell_lookup"]["questions_changed_more_in_repeat"] == sum(bool(b[q]["cells_exact_raw"]) and not k[q]["cells_exact_raw"] for q in lookup)
    assert d["cited_gold_cell_lookup"]["questions_changed_more_in_control"] == sum(bool(k[q]["cells_exact_raw"]) and not b[q]["cells_exact_raw"] for q in lookup)
    # what did not improve stays stated
    assert r["first_pass"]["outcomes"]["rl"]["calc"]["correct"] == 0 and a["first_pass"]["outcomes"]["rl"]["calc"]["correct"] == 0
    report = (ROOT / "docs" / "REPORT.md").read_text(encoding="utf-8")
    sec = report[report.index("### 22.8 본 실험의 반복"):]
    for needle in ("본 실험은 두 번, 대조군은 한 번이다", "강화학습의 시드는 같았다", "여전히 대조군과 유의하게 다르지 않다", "계산과 보류는 이번에도 배우지 못했다"):
        assert needle in sec, needle


def test_fixing_the_length_cap_made_no_detectable_difference_and_the_documents_say_so():
    """The full-data model was trained again with the cap that cuts no target and, in the same session, with the old
    cap. The documents must report what the predictions show: no detectable difference, none on the long questions
    either, a spread between trainings that is larger than the difference, and the headline number left at the lowest
    of the four trainings."""
    d = json.loads((EVAL / "length_fix_analysis.json").read_text(encoding="utf-8"))
    fp = d["first_pass"]
    fixed, old = rows("exaone_full2_vllm_ko_test"), rows("exaone_full2old_vllm_ko_test")
    v = fp["fixed_vs_old_same_session"]["all"]["verified_correct"]
    assert v["only_first"] == sum(fixed[q]["verified_correct"] and not old[q]["verified_correct"] for q in fixed)      # recomputed from the predictions
    assert v["only_second"] == sum(old[q]["verified_correct"] and not fixed[q]["verified_correct"] for q in fixed)
    assert v["p_two_sided"] > 0.05 and v["ci95_low"] < 0 < v["ci95_high"]
    long = fp["fixed_vs_old_same_session"]["over_old_cap"]["verified_correct"]
    assert long["p_two_sided"] > 0.05 and d["test_questions"]["over_old_cap"] + d["test_questions"]["fits_old_cap"] == d["test_questions"]["all"] == 699
    lengths = json.loads((EVAL / "ko_test_prompt_lengths.json").read_text(encoding="utf-8"))["questions"]
    assert set(lengths) == set(fixed) and d["test_questions"]["over_old_cap"] == sum(x["prompt_tokens"] + x["target_tokens"] > 768 for x in lengths.values())
    three = fp["old_cap_trained_three_times"]
    assert three["verified_em_spread"] > abs(v["difference"]) and fp["fixed_inside_the_spread_of_the_old_cap"]
    t = d["training"]
    assert (t["fixed"]["targets_missing"], t["fixed"]["targets_cut_short"]) == (0, 0) and t["old_same_session"]["targets_cut_share"] == 0.15
    assert t["args_that_differ_between_fixed_and_old_same_session"] == ["max_in", "max_len", "out"]
    # the headline stays the first training, the lowest of the four
    ems = [fp["verified_em"][k]["all"]["rate"] for k in ("old_run1", "old_run2", "old_same_session", "fixed")]
    assert min(ems) == fp["verified_em"]["old_run1"]["all"]["rate"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "대표 수치로는 가장 낮은 1회째 값을 그대로 씁니다" in readme
    report = (ROOT / "docs" / "REPORT.md").read_text(encoding="utf-8")
    sec = report[report.index("## 23. 길이 결함을 고친 설정으로"):]
    for needle in ("그 예상은 틀렸다", "한 쌍이다", "가장 높은 값을 골라 쓰지 않으려는 것이다", "예전 설정으로 학습한 그대로다"):
        assert needle in sec, needle


def test_rl_on_the_full_data_model_changed_no_accuracy_and_the_documents_say_so():
    """The same RL was run from a model fine-tuned on all the data. The documents must report what the predictions
    show: no detectable change in accuracy, little signal during training, a model that moved less than a second
    fine-tuning moves it, and a confidence that separates right from wrong answers less well. The last one was found
    after the fact in one run, and the documents must say that too."""
    d = json.loads((EVAL / "rl3_analysis.json").read_text(encoding="utf-8"))
    a, b = rows("exaone_full3_vllm_ko_test"), rows("exaone_grpo3_vllm_ko_test")
    v = d["first_pass"]["sign_tests"]["correct_all"]
    assert v["only_rl"] == sum(b[q]["verified_correct"] and not a[q]["verified_correct"] for q in a)                 # recomputed from the predictions
    assert v["only_start"] == sum(a[q]["verified_correct"] and not b[q]["verified_correct"] for q in a)
    assert all(t["p_two_sided"] > 0.05 for t in d["first_pass"]["sign_tests"].values()) and all(t["p_two_sided"] > 0.05 for t in d["subject_check"]["sign_tests"].values())
    assert d["raw"]["sign_test_cited_gold_cell_lookup"]["p_two_sided"] > 0.05 and d["unanswerable_first_pass"]["p_two_sided"] > 0.05
    same = sum((a[q]["raw_output"] or "") == (b[q]["raw_output"] or "") for q in a)
    assert d["outputs"]["same_raw_output"] == same and d["outputs"]["questions"] == len(a) == 699
    assert d["retraining"]["outputs"]["same_raw_output"] < same and d["retraining"]["outputs"]["different_outcome"] > d["outputs"]["different_outcome"]
    # the training record: same options as the second experiment apart from the start model; few steps had anything to learn from
    info = json.loads((ROOT / "experiments" / "exaone_grpo3" / "train_info.json").read_text(encoding="utf-8"))
    assert d["training_args_that_differ_from_second_experiment"] == ["adapter", "out"] and info["args"]["adapter"] == "experiments/exaone_lora_full3"
    sig = d["signal"]["from_full_data_model"]
    assert sig["updates_applied"] == info["updates_applied"] and sig["updates_applied"] + sig["steps_without_signal"] + sig["steps_gradient_not_usable"] == info["steps"] == 200
    assert sig["samples_correct_rate"] > 0.8 > 0.3 > d["signal"]["second_experiment"]["samples_correct_rate"]
    assert sig["groups_with_equal_rewards"] > 2 * d["signal"]["second_experiment"]["groups_with_equal_rewards"]
    assert info["prompts_cut"] == {"train": 0, "dev": 0} and d["start_sft"]["targets_missing"] == d["start_sft"]["targets_cut_short"] == 0
    # the dev set chose the checkpoint; its gain is not on the test set
    assert d["training"]["dev_kept"]["correct"] > d["training"]["dev_first"]["correct"] and abs(v["only_rl"] - v["only_start"]) <= 2
    # confidence: the stored curves and the bootstrap agree on the direction, for every signal
    rc = json.loads((EVAL / "risk_coverage.json").read_text(encoding="utf-8"))["runs"]
    for sig_name in ("sum_logprob", "mean_logprob", "min_logprob"):
        c = d["confidence"][sig_name]
        assert round(c["auroc"]["start"], 4) == rc["exaone_full3_vllm_ko_test"]["curves"][f"verifier/{sig_name}"]["auroc_right_vs_wrong"]
        assert round(c["auroc"]["rl"], 4) == rc["exaone_grpo3_vllm_ko_test"]["curves"][f"verifier/{sig_name}"]["auroc_right_vs_wrong"]
        assert c["auroc"]["ci95_hi"] < 0 < c["aurc"]["ci95_lo"]
    # the headline stays the first full-data training, now the lowest of five
    ems = {r: json.loads((EVAL / r / "metrics.json").read_text(encoding="utf-8"))["metrics"]["verified_em"]
           for r in ("exaone_full_vllm_ko_test", "exaone_full_vllm_ko_test_run2", "exaone_full2old_vllm_ko_test", "exaone_full2_vllm_ko_test", "exaone_full3_vllm_ko_test")}
    assert min(ems, key=ems.get) == "exaone_full_vllm_ko_test"
    report = (ROOT / "docs" / "REPORT.md").read_text(encoding="utf-8")
    sec = report[report.index("## 24. 전체 데이터 모델에서 시작한 강화학습"):]
    for needle in ("실행 전에 노트북과 런북에 예상을 적어 두었다", "한 번의 실행이다", "확신도 결과는 탐색에서 나온 것이다", "통제된 시험은 아니다", "개발셋의 향상은 test에 나타나지 않았다"):
        assert needle in sec, needle
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sec = readme[readme.index("### 9.11 전체 데이터 모델에서 시작한 강화학습"):readme.index("## 10. 추론 최적화")]
    for needle in ("정답률에 검출되는 차이가 없습니다", "한 번의 실행이고 시드를 바꾸지 않았습니다", "결과를 본 뒤에 찾은 것입니다"):
        assert needle in sec, needle
    handoff = (ROOT / "docs" / "HANDOFF.md").read_text(encoding="utf-8")
    assert '"미세조정한 모델에 강화학습을 더해 더 좋아졌다"도 틀린 말이다' in handoff and '"강화학습이 모델의 확신도를 망친다"' in handoff
