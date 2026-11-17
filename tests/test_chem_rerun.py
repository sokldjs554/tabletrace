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
    for needle in ("예전 실행의 수치보다 낮습니다", "학습 한 번입니다", "소유자가 검수하지 않았습니다", "화학 문항을 더한 몫은 가르지 못합니다"):
        assert needle in sec, needle
    # wherever the earlier number is still quoted, the same line says where it comes from
    for name in ("README.md", "docs/ONE_PAGE.md"):
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
            if "exaone_kochem_vllm_chem_papers" in line and f">{old}<" in line:
                assert "결과 파일" in line or "재실행" in line, (name, line[:80])
    handoff = (ROOT / "docs/HANDOFF.md").read_text(encoding="utf-8")
    quoted = [line for line in handoff.splitlines() if f"{old}%" in line]
    assert quoted and all("결과 파일" in line or "예전" in line for line in quoted)
    assert f"\"화학 논문 표에서 {old}%\"(결과 파일이 없는 예전 실행의 수치다" in handoff and "아직 돌리지 않았다" not in handoff.split("### 9.2")[1].split("### 9.3")[0]
