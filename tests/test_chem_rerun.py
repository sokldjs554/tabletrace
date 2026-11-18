"""EXAONE on the chemistry questions, run again so that per-question predictions exist (notebook 2, section N; the owner
ran it on Colab on 2026-11-17). The analysis must follow from the stored predictions, and the documents must use this
run, which came out lower on the paper tables than the earlier run whose files were lost, and say so."""
import collections
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "experiments" / "eval"
A = json.loads((EVAL / "chem_rerun_analysis.json").read_text(encoding="utf-8"))
CHEM = ("chem_custom", "chem_syndev", "chem_papers")
RUNS = {"tuned": "exaone_kochem2_vllm", "untuned_six_examples": "ref_1p2b", "heuristic": "heuristic", "mt5_small_final": "rl_v3"}


def rows(run: str) -> dict[str, dict]:
    with open(EVAL / run / "predictions.jsonl", encoding="utf-8") as f:
        return {r["qid"]: r for r in map(json.loads, f)}


def test_the_reported_numbers_are_counted_from_the_predictions():
    for s in CHEM:
        entry = A["chemistry"][s]
        for who, prefix in RUNS.items():
            if who not in entry:
                assert not (EVAL / f"{prefix}_{s}").exists()                     # "not measured", not left out
                continue
            preds, e = rows(f"{prefix}_{s}"), entry[who]
            assert (e["n"], e["correct"]) == (len(preds), sum(bool(r["verified_correct"]) for r in preds.values())), (s, who)
            m = json.loads((EVAL / f"{prefix}_{s}" / "metrics.json").read_text(encoding="utf-8"))["metrics"]
            assert m["verified_em"] == pytest.approx(e["correct"] / e["n"], abs=5e-5) and e["ci95"]["lo"] < e["rate"] < e["ci95"]["hi"]
        tuned, plain = rows(f"exaone_kochem2_vllm_{s}"), rows(f"ref_1p2b_{s}")
        assert set(tuned) == set(plain)
        t = entry["tuned_vs_untuned"]
        assert t["only_candidate"] == sum(bool(tuned[q]["verified_correct"]) and not plain[q]["verified_correct"] for q in tuned)
        assert t["only_reference"] == sum(bool(plain[q]["verified_correct"]) and not tuned[q]["verified_correct"] for q in tuned)
    for s in ("ko_test", "ko_custom", "ko_owner"):
        both, only = rows(f"exaone_kochem2_vllm_{s}"), rows(f"exaone_full4_vllm_{s}")
        e = A["korean"][s]
        assert e["with_chemistry"]["correct"] == sum(bool(r["verified_correct"]) for r in both.values())
        assert e["korean_only_same_lengths"]["correct"] == sum(bool(r["verified_correct"]) for r in only.values())
        assert e["with_chemistry_vs_korean_only"]["p_two_sided"] > 0.05           # no detectable difference on the Korean side


def test_question_kinds_follow_the_gold_program_and_agree_with_the_question_file():
    """Issue 83: the first version of the analysis used the Korean classification, which knows three calculations, and
    counted the chemistry ratios and percentage changes as lookups."""
    for s in CHEM:
        preds = rows(f"exaone_kochem2_vllm_{s}")
        ops = collections.Counter("unanswerable" if r["gold_status"] != "answered" else r["gold_op"] if r["gold_op"] in ("lookup", "text") else "calc" for r in preds.values())
        kinds = A["chemistry"][s]["tuned"]["by_kind"]
        assert {k: v["n"] for k, v in kinds.items()} == dict(ops)
        assert all(v["correct"] + v["wrong"] + v["withheld"] == v["n"] for v in kinds.values())
        assert A["chemistry"][s]["tuned"]["cited"]["lookup_questions"] == ops["lookup"]
    assert {r["gold_op"] for r in rows("exaone_kochem2_vllm_chem_papers").values()} >= {"ratio", "pct_change"}      # the operations the Korean data lacks
    papers = A["chemistry"]["chem_papers"]["tuned"]
    questions = [json.loads(x) for x in (ROOT / "data/chem_papers/custom_eval.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    file_counts = collections.Counter(q["category"] for q in questions)
    assert {k: v["n"] for k, v in papers["by_category"].items()} == dict(file_counts)
    assert (papers["by_kind"]["lookup"]["n"], papers["by_kind"]["calc"]["n"]) == (file_counts["cell"], file_counts["calc"])


def test_the_training_is_the_korean_training_plus_the_chemistry_questions_that_fit():
    t = A["training"]
    assert t["args_that_differ_from_the_korean_only_training"] == ["corpus", "out", "train"]
    assert t["examples"] == t["korean_examples_in_the_full_data_training"] + t["chemistry_examples_added"]
    assert t["chemistry_questions_in_the_file"] - t["chemistry_questions_left_out"] == t["chemistry_examples_added"] > 0
    assert t["targets_missing"] == t["targets_cut_short"] == 0 and t["loop"] == "builtin" and t["loss_last_20_steps"] < t["loss_first_20_steps"]
    train = [json.loads(x) for x in (ROOT / "data/chem/synthetic_train.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(train) == t["chemistry_questions_in_the_file"] and not any(q.get("needs_text") for q in train)      # no passage questions in training


def test_no_planner_answers_the_textbook_questions_that_need_the_passage():
    """The documents say so; it explains most of the tuned model's errors on the textbook set."""
    book = A["chemistry"]["chem_custom"]
    assert all(book[who]["by_kind"]["text"]["correct"] == 0 for who in RUNS)
    tuned = book["tuned"]
    assert tuned["n"] - tuned["correct"] - tuned["by_kind"]["text"]["n"] == 1


def test_the_documents_use_the_run_that_kept_its_files_and_say_it_came_out_lower():
    earlier, now = A["earlier_run_without_predictions"]["chem_papers"], A["chemistry"]["chem_papers"]["tuned"]
    assert now["correct"] < earlier["correct"] and earlier["this_run_minus_earlier_in_questions"] == now["correct"] - earlier["correct"]
    new, old = f"{100 * now['rate']:.1f}", f"{100 * earlier['verified_em']:.1f}"
    report = (ROOT / "docs/REPORT.md").read_text(encoding="utf-8")
    sec = report[report.index("## 29. 화학 문항에서의 EXAONE"):]
    for needle in ("학습 한 번이다", "소유자가 검수하지 않았다", "화학 문항을 더한 몫은 가르지 못한다", "높은 쪽을 고르지 않는다", "짝 검정도 할 수 없다", "하나도 못 맞혔다"):
        assert needle in sec, needle
    assert f">{new}<" in sec and f">{old}<" in sec
    earlier_sec = report[report.index("### 21.8 영어 화학에서의 EXAONE"):report.index("### 21.9")]
    assert "§29" in earlier_sec and "결과 파일이 남지 않은 실행" in earlier_sec
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sec = readme[readme.index("### 9.14 화학 문항에서의 EXAONE"):readme.index("## 10. 추론 최적화")]
    for needle in ("예전 실행의 수치보다 낮습니다", "한국어 전용 모델은 학습 한 번입니다", "소유자가 검수하지 않았습니다"):
        assert needle in sec, needle
    # wherever the earlier number is still quoted, the same line says where it comes from
    for name in ("README.md", "docs/ONE_PAGE.md"):
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            if "exaone_kochem_vllm_chem_papers" in line and f">{old}<" in line:
                assert "결과 파일" in line or "재실행" in line, (name, line[:80])
    handoff = (ROOT / "docs/HANDOFF.md").read_text(encoding="utf-8")
    quoted = [line for line in handoff.splitlines() if f"{old}%" in line]
    assert quoted and all("결과 파일" in line or "예전" in line for line in quoted)
    assert f"\"화학 논문 표에서 {old}%\"(결과 파일이 없는 예전 실행의 수치다" in handoff and "노트북 2의 N절, 2026-11-17 준비" not in handoff.split("### 9.2")[1].split("### 9.3")[0]


# ---- section O: a model tuned on Korean only on the same questions (what the chemistry training questions add)
SHARE = json.loads((EVAL / "chem_share_analysis.json").read_text(encoding="utf-8"))


def test_the_korean_only_numbers_are_counted_from_the_predictions():
    for s in CHEM:
        ko, both, plain = rows(f"exaone_koonly_vllm_{s}"), rows(f"exaone_kochem2_vllm_{s}"), rows(f"ref_1p2b_{s}")
        e = SHARE["chemistry"][s]
        assert (e["korean_only"]["n"], e["korean_only"]["correct"]) == (len(ko), sum(bool(r["verified_correct"]) for r in ko.values()))
        assert e["korean_and_chemistry"]["correct"] == A["chemistry"][s]["tuned"]["correct"] and e["untuned_six_examples"]["correct"] == A["chemistry"][s]["untuned_six_examples"]["correct"]
        t = e["with_chemistry_vs_korean_only"]
        assert t["only_candidate"] == sum(bool(both[q]["verified_correct"]) and not ko[q]["verified_correct"] for q in ko)
        assert t["only_reference"] == sum(bool(ko[q]["verified_correct"]) and not both[q]["verified_correct"] for q in ko)
        u = e["korean_only_vs_untuned"]
        assert u["only_candidate"] == sum(bool(ko[q]["verified_correct"]) and not plain[q]["verified_correct"] for q in ko)
        m = json.loads((EVAL / f"exaone_koonly_vllm_{s}" / "metrics.json").read_text(encoding="utf-8"))["metrics"]
        assert m["verified_em"] == pytest.approx(e["korean_only"]["correct"] / e["korean_only"]["n"], abs=5e-5)
    t = SHARE["training"]
    assert t["args_that_differ_from_the_stored_korean_only_training"] == ["out"] and t["chemistry_questions_in_training"] == 0
    assert t["args_that_differ_from_the_korean_and_chemistry_training"] == ["corpus", "out", "train"] and t["targets_cut_short"] == 0


def test_what_the_chemistry_questions_add_is_reported_without_overreading():
    """The comparison fixed before the run (each set, question by question) is not significant anywhere; the split by
    kind of question and the pooling of the two hand-written sets were made after the result and are marked so."""
    planned = [SHARE["chemistry"][s]["with_chemistry_vs_korean_only"] for s in CHEM]
    assert all(t["p_two_sided"] > 0.05 and t["only_candidate"] > t["only_reference"] for t in planned)
    three, hand = SHARE["chemistry_three_sets_by_kind"], SHARE["chemistry_hand_written_together"]
    assert three["planned_before_the_result"] is False and hand["planned_before_the_result"] is False
    assert three["questions"] == sum(len(rows(f"exaone_koonly_vllm_{s}")) for s in CHEM)
    for who, prefix in (("korean_only", "exaone_koonly_vllm"), ("korean_and_chemistry", "exaone_kochem2_vllm")):
        un = [r for s in CHEM for r in rows(f"{prefix}_{s}").values() if r["gold_status"] != "answered"]
        k = three[who]["unanswerable"]
        assert (k["n"], k["correct"], k["wrong"]) == (len(un), sum(bool(r["verified_correct"]) for r in un), sum(not r["verified_correct"] and r["pred_status"] != "abstained" for r in un))
    hold, rest = three["with_chemistry_vs_korean_only"]["unanswerable"], three["with_chemistry_vs_korean_only_on_answerable_questions"]
    assert hold["only_reference"] == 0 and hold["p_two_sided"] < 0.001 and rest["p_two_sided"] > 0.05
    assert three["korean_only_unanswerable_errors"]["answer_sent"] == three["korean_only"]["unanswerable"]["wrong"]
    ko, plain = SHARE["chemistry"]["chem_papers"]["korean_only"], SHARE["chemistry"]["chem_papers"]["untuned_six_examples"]
    report = (ROOT / "docs/REPORT.md").read_text(encoding="utf-8")
    sec = report[report.index("### 29.7 화학 문항을 더한 몫"):]
    for needle in ("실행 전에 적어 둔 것", "실행 전에 정한 세 비교는 어느 것도 유의하지 않다", "실행 전에 정한 검정이 아니다", "다른 세션에서 한 번씩 학습했다", "다음 날 한 번 더 했다(§29.8)",
                   "소유자가 검수하지 않았다", "말은 이 결과와 맞지 않는다"):
        assert needle in sec, needle
    assert f">{100 * ko['rate']:.1f}<" in sec and ko["rate"] - plain["rate"] > 0.3
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sec = readme[readme.index("### 9.14 화학 문항에서의 EXAONE"):readme.index("## 10. 추론 최적화")]
    for needle in ("화학 문항을 한 번도 보지 않았습니다", "실행 전에 정한 비교는 유의하지 않습니다", "실행 전에 정한 검정이 아닙니다", "모두 다른 세션에서 학습했고"):
        assert needle in sec, needle
    assert f">{100 * ko['rate']:.1f}<" in readme[:readme.index("## 목차")]                      # the top of the README gives the Korean-only number next to the other
    handoff = (ROOT / "docs/HANDOFF.md").read_text(encoding="utf-8")
    assert f"화학 문항 없이도 {100 * ko['rate']:.1f}%다" in handoff and "\"화학 도메인 튜닝으로" in handoff.split("**쓰면 안 되는 것.**")[-1] + handoff
    assert "한국어만 튜닝한 EXAONE의 화학 평가**(노트북 2의 O절, 2026-11-17 준비)" not in handoff


# ---- section O's repeat: the Korean-and-chemistry training once more, checked against what was written down before it
REPEAT = json.loads((EVAL / "chem_repeat_analysis.json").read_text(encoding="utf-8"))


def test_the_repeat_checks_are_counted_from_the_predictions():
    new = {s: rows(f"exaone_kochem3_vllm_{s}") for s in CHEM}
    ko = {s: rows(f"exaone_koonly_vllm_{s}") for s in CHEM}
    for s in CHEM:
        e = REPEAT["chemistry"][s]
        assert (e["repeat"]["n"], e["repeat"]["correct"]) == (len(new[s]), sum(bool(r["verified_correct"]) for r in new[s].values()))
        assert e["first_training"]["correct"] == A["chemistry"][s]["tuned"]["correct"] and e["korean_only"]["correct"] == SHARE["chemistry"][s]["korean_only"]["correct"]
    un = [(new[s][q], ko[s][q]) for s in CHEM for q in new[s] if new[s][q]["gold_status"] != "answered"]
    an = [(new[s][q], ko[s][q]) for s in CHEM for q in new[s] if new[s][q]["gold_status"] == "answered"]
    for key, pairs_ in (("unanswerable", un), ("answerable", an)):
        t = REPEAT["checks"][key]["repeat_vs_korean_only"]
        assert REPEAT["checks"][key]["n"] == len(pairs_)
        assert t["only_candidate"] == sum(bool(a["verified_correct"]) and not b["verified_correct"] for a, b in pairs_)
        assert t["only_reference"] == sum(bool(b["verified_correct"]) and not a["verified_correct"] for a, b in pairs_)
    # what was written down before the run, and how it came out
    assert REPEAT["written_down_before_the_run"]["commit"] == "b3bffd2" and REPEAT["training"]["args_that_differ_from_the_first_training"] == ["out"]
    assert REPEAT["checks"]["unanswerable"]["holds"] and REPEAT["checks"]["answerable"]["as_expected"]
    assert REPEAT["paper_tables"]["headline_stays"] == "first_run_with_files" and REPEAT["paper_tables"]["first_run_with_files"] == A["chemistry"]["chem_papers"]["tuned"]["correct"]


def test_the_documents_report_the_repeat_as_written_down_before_it():
    report = (ROOT / "docs/REPORT.md").read_text(encoding="utf-8")
    before = report[report.index("**반복 학습을 돌리기 전에 적어 둔다 (2026-11-17).**"):report.index("### 29.8")]
    assert "대표 수치는" in before and "새 값이 높든 낮든 바꾸지 않는다" in before and "유의하게 더 많이 보류한다" in before      # the plan is kept as it was written
    sec = report[report.index("### 29.8"):]
    for needle in ("미리 적어 둔 네 가지", "성립했다", "예상대로 유의한 차이가 없다", "대표 수치는 문항별 파일이 있는 첫 실행의", "한국어 전용 모델은 한 번만 학습했다", "다른 문항이나 다른 분야에서도 성립하는지는 모른다"):
        assert needle in sec, needle
    t = REPEAT["checks"]["unanswerable"]["repeat_vs_korean_only"]
    assert f">{t['only_candidate']}<" in sec and f">{t['p_display']}<" in sec
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "미리 적어 두고 다시 확인했습니다(2026-11-18)" in readme and "다시 학습한 모델에서도 같았습니다" in readme[:readme.index("## 목차")]
    handoff = (ROOT / "docs/HANDOFF.md").read_text(encoding="utf-8")
    assert "미리 적어 두고 다시 확인" in handoff and "**성립했다.**" in handoff and "결과를 본 뒤에 나눠 본 것이고 모델마다 학습 한 번" not in handoff
    nb = json.loads((ROOT / "notebooks/gpu_experiments_2.ipynb").read_text(encoding="utf-8"))
    o = next("".join(c["source"]) for c in nb["cells"] if "".join(c["source"]).startswith("## O."))
    assert "반복 학습의 결과" in o and f"{REPEAT['paper_tables']['repeat']}/{REPEAT['paper_tables']['n']}" in o
