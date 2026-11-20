"""Section P of notebook 2 repeats three experiments that ran once (docs/REPORT.md §31). What each repeat is checked for
was written down before it ran; when a check does not hold, the documents change the conclusion and keep the headline
numbers. These tests tie what the documents say to experiments/eval/repeat_once_analysis.json."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import chem_rerun_analysis as cr  # noqa: E402
import repeat_once_analysis as analysis  # noqa: E402
import rl2_analysis as rl2  # noqa: E402

STORED = json.loads((ROOT / "experiments/eval/repeat_once_analysis.json").read_text(encoding="utf-8"))
P1 = STORED["P1_korean_only"]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_the_stored_analysis_is_what_the_script_gives():
    assert analysis.analyse() == STORED


def test_the_checks_are_counted_as_written_down():
    """1a: the Korean-and-chemistry repeat against the new Korean-only model on the 31 unanswerable chemistry questions.
    1b: the new Korean-only model against the untuned model on the 62 paper-table questions."""
    new, repeat = analysis.unanswerable("exaone_koonly2_vllm"), analysis.unanswerable("exaone_kochem3_vllm")
    assert len(new) == len(repeat) == P1["1a_unanswerable_repeat_vs_new_korean_only"]["n"] == 31
    a = P1["1a_unanswerable_repeat_vs_new_korean_only"]
    assert a["only_candidate"] == sum(bool(repeat[q]["verified_correct"]) and not new[q]["verified_correct"] for q in new)
    assert a["only_reference"] == sum(bool(new[q]["verified_correct"]) and not repeat[q]["verified_correct"] for q in new)
    assert a["holds"] is (a["only_candidate"] > a["only_reference"] and a["p_two_sided"] < 0.05)
    b = P1["1b_papers_new_korean_only_vs_untuned"]
    assert b["holds"] is (b["only_candidate"] > b["only_reference"] and b["p_two_sided"] < 0.05)
    assert P1["training"]["args_that_differ_from_the_first_training"] == ["out"] and P1["training"]["targets_cut_short"] == 0
    assert cr.right(rl2.load("exaone_koonly2_vllm_chem_papers")) == P1["scores"]["chem_papers"]["new_korean_only"]


P3 = STORED["P3_owner_loop"]


def test_p3_is_counted_as_written_down_and_the_training_inputs_did_not_change():
    """3a: the two trainings with the owner's loop, p >= 0.05. 3b: the new one against the built-in loop with the same
    command (exaone_full4), p >= 0.05. Next to them: the score against the range of the eight trainings before section P,
    and the check that the training examples are the same before the 2026-11-20 data fix and after it."""
    new, first, builtin = (rl2.load(f"{r}_vllm_ko_test") for r in ("exaone_ownloop2", "exaone_ownloop", "exaone_full4"))
    for key, ref in (("3a_new_vs_first_owner_loop", first), ("3b_new_owner_loop_vs_builtin_loop_same_command", builtin)):
        c = P3[key]
        assert c["only_candidate"] == sum(bool(new[q]["verified_correct"]) and not ref[q]["verified_correct"] for q in new)
        assert c["only_reference"] == sum(bool(ref[q]["verified_correct"]) and not new[q]["verified_correct"] for q in new)
        assert c["holds"] is (c["p_two_sided"] >= 0.05)
    assert P3["training"]["args_that_differ_from_the_first_time"] == ["out"] and "owner-written" in P3["training"]["loop"]
    assert P3["above_their_range"] is True and P3["inside_their_range"] is False and len(P3["earlier_full_data_korean_only_trainings"]) == 8
    assert all(v > max(P3["earlier_full_data_korean_only_trainings"].values()) for v in P3["section_p_trainings"].values())
    inputs = json.loads((ROOT / "experiments/eval/training_inputs_check.json").read_text(encoding="utf-8"))
    assert inputs["same"] is True and inputs["before"]["examples"] == inputs["now"]["examples"] == P3["training"]["examples"]
    assert inputs["run"] == "experiments/exaone_lora_ownloop2/train_info.json"


def test_the_documents_report_p3_and_the_whole_of_section_p():
    a, b = P3["3a_new_vs_first_owner_loop"], P3["3b_new_owner_loop_vs_builtin_loop_same_command"]
    assert a["holds"] and b["holds"] and max(a["p_two_sided"], b["p_two_sided"]) < 0.1        # "close to the line"
    report = _read("docs/REPORT.md")
    sec = report[report.index("### 31.3 P3의 결과"):report.index("## 32.")]
    for needle in ("**(3a) 남았다.**", "**(3b) 남았다.**", "경계에 가깝고", "**들지 않는다.**", "**학습 입력은 같다.**", "원인은 찾지 못했다",
                   "### 31.4 P절의 정리", "다섯 확인 가운데 넷이 남았고 하나가 남지 않았다"):
        assert needle in sec, needle
    assert f">{a['p_display']}<" in sec and f">{b['p_display']}<" in sec
    assert "87.5%로 이 범위보다 높았고" in report                                             # the dated note in §27.3
    readme = _read("README.md")
    sec = readme[readme.index("### 9.16 한 번씩만 돌린 실험의 반복"):readme.index("## 10. 추론 최적화")]
    assert "**P3." in sec and "**범위 밖입니다.**" in sec and "셋 다 돌렸습니다(2026-11-20)" in sec and "아직입니다" not in sec
    handoff = _read("docs/HANDOFF.md")
    assert "**같은 명령으로 다시**(2026-11-20, P절의 `P_OWNLOOP`" in handoff and "직접 쓴 루프로 한 학습의 반복" not in handoff
    assert '"모든 미세조정을 직접 쓴 루프로 했다"(두 번이다.' in handoff and "직접 쓴 학습 루프로 한 학습은 두 번이고" in handoff


P2 = STORED["P2_rl_from_full_data"]


def test_p2_is_counted_as_written_down():
    """2: RL against its start model on the Korean test, p >= 0.05."""
    start, rl = rl2.load("exaone_full5_vllm_ko_test"), rl2.load("exaone_grpo4_vllm_ko_test")
    c = P2["2_rl_vs_start_on_the_korean_test"]
    assert c["only_candidate"] == sum(bool(rl[q]["verified_correct"]) and not start[q]["verified_correct"] for q in start)
    assert c["only_reference"] == sum(bool(start[q]["verified_correct"]) and not rl[q]["verified_correct"] for q in start)
    assert c["holds"] is (c["p_two_sided"] >= 0.05)
    assert P2["training"]["start_model"]["args_that_differ_from_the_first_time"] == ["out"]
    assert P2["training"]["rl"]["args_that_differ_from_the_first_time"] == ["adapter", "out"]
    first = P2["added_after_the_run"]["confidence_first_time"]["auroc"]
    stored_first = json.loads((ROOT / "experiments/eval/rl3_analysis.json").read_text(encoding="utf-8"))["confidence"]["sum_logprob"]["auroc"]
    assert first == stored_first                                              # the same measure as the first time, computed the same way


def test_the_documents_report_p2_as_it_came_out():
    """2 held: nothing to change, the repeat is set beside the first result. The confidence finding is not a check
    written down before the run; where it is reported, the documents say so."""
    c, a = P2["2_rl_vs_start_on_the_korean_test"], P2["added_after_the_run"]["confidence"]["auroc"]
    assert c["holds"] and a["rl"] < a["start"] and a["ci95_hi"] < 0
    report = _read("docs/REPORT.md")
    sec = report[report.index("### 31.2 P2의 결과"):report.index("## 32.")]
    for needle in ("**(2) 남았다.**", "실행 전에 적지 않았다", "두 번 모두 같은 시드다", "바꾸는 결론은 없다"):
        assert needle in sec, needle
    assert f">{c['only_candidate']}<" in sec and f">{a['rl']:.3f}<" in sec
    assert report.count("§31.2)") >= 2                                         # the dated notes in §24.5
    readme = _read("README.md")
    sec = readme[readme.index("### 9.16 한 번씩만 돌린 실험의 반복"):readme.index("## 10. 추론 최적화")]
    assert "**P2." in sec and "실행 전에 적지 않은 비교입니다" in sec
    handoff = _read("docs/HANDOFF.md")
    assert "**같은 명령으로 다시**(2026-11-20, P절의 `P_RL`" in handoff and "**끝났다(2026-11-20, 9.1i, 9.1e, 9.1g).**" in handoff
    assert "한 번의 실행이고 결과를 본 뒤에 찾은 것이라 확인이 더 필요하다" not in handoff


def test_the_check_that_did_not_hold_changes_the_conclusion_in_every_document():
    """1a did not hold (7 to 1, p 0.070). The report says so in §31.1 and changes the reading; README, the one-page
    summary and the handoff no longer say the difference came from withholding; the headline numbers stay."""
    a, b = P1["1a_unanswerable_repeat_vs_new_korean_only"], P1["1b_papers_new_korean_only_vs_untuned"]
    assert not a["holds"] and b["holds"] and a["only_candidate"] > a["only_reference"]     # what the sentences below rest on
    report = _read("docs/REPORT.md")
    sec = report[report.index("### 31.1 P1의 결과"):report.index("## 32.")]
    for needle in ("**(1a) 남지 않았다.**", "**(1b) 남았다.**", "**고친 결론.**", "결과를 본 뒤에 더 본 것", "실행 전에 적지 않았다",
                   '"화학 문항이 보탠 것은 보류다"라고 단정하지 않는다', "대표 수치(논문 표 74.2%, 한국어 전용 67.7%)는 바꾸지 않는다"):
        assert needle in sec, needle
    assert f">{a['only_candidate']}<" in sec and f">{a['p_display']}<" in sec
    assert report.count("이 읽기는 §31.1에서 고쳤다") == 2                                  # the dated notes in §29.7 and §29.8
    readme = _read("README.md")
    sec = readme[readme.index("### 9.16 한 번씩만 돌린 실험의 반복"):readme.index("## 10. 추론 최적화")]
    assert "**남지 않았습니다**" in sec and "**고친 결론.**" in sec and "P2" in sec
    top = readme[:readme.index("## 목차")]
    assert "화학 문항이 보탠 것이 보류라고 단정하지 않습니다" in top and "#916-한-번씩만-돌린-실험의-반복" in top
    assert "두 모델이 갈리는 곳이 이런 답 없는 질문입니다" not in readme and "**갈리는 곳은 답 없는 질문입니다.**" not in readme
    one = _read("docs/ONE_PAGE.md")
    assert "답 없는 질문에서 갈렸고" not in one and "화학 문항이 보탠 것을 단정하지 않는다" in one
    handoff = _read("docs/HANDOFF.md")
    assert "두 모델의 차이는 답이 없는 질문을 보류하는 데서 나왔다" not in handoff
    assert "**답 없는 질문에 대해 쓸 수 있는 문장.**" in handoff and "**(1a) 남지 않았다**" in handoff and "**끝났다(2026-11-20, 9.1i, 9.1e, 9.1g).**" in handoff
    assert '"화학 문항이 보탠 것은 답 없는 질문을 보류하는 것이다"' in handoff                  # listed among what must not be written
    assert f"{a['only_candidate']} 대 {a['only_reference']}(p {a['p_display']})" in handoff
