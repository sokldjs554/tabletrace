"""The repository owner reviews the 30 hand-made questions the AI tool wrote and writes new ones by hand
(docs/rewrite/07_owner_eval_questions.md). The helper only shows tables and checks files; these tests pin what the
check accepts and rejects. When the owner's files are in the repository they must pass the same check."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("owner_eval_tool", ROOT / "scripts" / "owner_eval_tool.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

TABLE = "ko_29fbd6328d"          # a test-split table with numbers and a passage
DOC = "doc_ko_29fbd6328d"


def rec(**kw) -> dict:
    base = {"qid": "ko_owner_01", "category": "cell", "question": "이 표에서 순위가 가장 높은 영화의 개봉일자를 알려 주세요.", "answer": "8월 1일", "doc_id": DOC, "table_id": TABLE,
            "op": "lookup", "gold_cells": [[0, 2]], "source": "owner", "needs_text": False}
    return {**base, **kw}


@pytest.fixture(scope="module")
def docs():
    return tool.documents()


def test_a_well_formed_set_passes(docs):
    good = [
        rec(),
        rec(qid="ko_owner_02", category="calc", op="diff", question="1위 영화와 2위 영화는 관객수가 몇 명 차이 납니까?", answer="1,062,201 명", gold_cells=[[0, 4], [1, 4]], unit="명"),
        rec(qid="ko_owner_03", category="text_table", op="text", question="이 순위표는 며칠부터의 통계로 만든 것입니까?", answer="2018년 1월 1일", gold_cells=[], needs_text=True),
        rec(qid="ko_owner_04", category="abstain", op="abstain", question="이 표에서 2019년에 개봉한 영화의 관객수는 얼마입니까?", answer=None, gold_cells=[], reason="not_in_document"),
    ]
    assert tool.check_owner(good, docs) == []


@pytest.mark.parametrize("change, needle", [
    (dict(answer="8월 2일"), "lookup answer"),                                             # the gold cell does not hold the answer
    (dict(table_id="ko_does_not_exist"), "시험 분할의 표가 아닙니다"),
    (dict(source="custom"), "source"),
    (dict(category="calc"), "맞지 않습니다"),                                              # category calc with op lookup
    (dict(qid="custom_01"), "ko_owner_"),
    (dict(question="2018년 박스오피스에서 안시성의 관객수는 몇 명입니까?", answer="5,436,789", gold_cells=[[6, 4]]), "글자까지 같은 질문"),      # copied from the AI-written set
    (dict(op="abstain", category="abstain", gold_cells=[], answer="8월 1일"), "answer가 null"),
    (dict(op="abstain", category="abstain", gold_cells=[], answer=None), "not_in_document"),
    (dict(gold_cells=[[0, 2], [1, 2]]), "셀 하나"),
    (dict(needs_text=True), "needs_text"),
])
def test_the_check_names_what_is_wrong(docs, change, needle):
    errs = tool.check_owner([rec(**change)], docs)
    assert any(needle in e for e in errs), errs


def test_a_table_used_for_training_is_refused(docs):
    train_table = json.loads((ROOT / "data/ko/train.jsonl").read_text(encoding="utf-8").splitlines()[0])
    errs = tool.check_owner([rec(table_id=train_table["table_id"], doc_id=train_table["doc_id"], answer=train_table["answer"], gold_cells=train_table["gold_cells"])], docs)
    assert any("시험 분할의 표가 아닙니다" in e for e in errs)


def test_missing_fields_and_repeated_questions_are_reported(docs):
    broken = rec()
    del broken["gold_cells"]
    assert any("빠진 항목" in e for e in tool.check_owner([broken], docs))
    assert any("두 번" in e for e in tool.check_owner([rec(), rec(qid="ko_owner_02")], docs))


def test_review_needs_one_verdict_per_question_and_a_reason_for_every_objection():
    qids = [json.loads(line)["qid"] for line in (ROOT / "data/ko/custom_eval.jsonl").read_text(encoding="utf-8").splitlines()]
    full = [{"qid": q, "verdict": "ok", "comment": ""} for q in qids]
    assert len(qids) == 30 and tool.check_review(full) == []
    assert any("판정이 없습니다" in e for e in tool.check_review(full[:-1]))
    assert any("2번" in e for e in tool.check_review([*full, full[0]]))
    assert any("까닭" in e for e in tool.check_review([{**full[0], "verdict": "fix"}, *full[1:]]))
    assert tool.check_review([{**full[0], "verdict": "fix", "comment": "질문이 두 행에 다 맞는다"}, *full[1:]]) == []
    assert any("verdict" in e for e in tool.check_review([{**full[0], "verdict": "good"}, *full[1:]]))


def test_the_review_template_leaves_every_verdict_empty_and_does_not_pass_until_filled_in(tmp_path, monkeypatch):
    """The template saves typing the 30 ids. It must not decide anything: an empty verdict fails the check."""
    monkeypatch.setattr(tool, "REVIEW_FILE", tmp_path / "custom_eval_review.jsonl")
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    assert tool.cmd_template(None) == 0
    recs = tool.load(tmp_path / "custom_eval_review.jsonl")
    assert len(recs) == 30 and all(r["verdict"] == "" and r["comment"] == "" for r in recs)
    assert len(tool.check_review(recs)) == 30                                      # nothing is reviewed yet
    assert tool.cmd_template(None) == 1 and tool.load(tmp_path / "custom_eval_review.jsonl") == recs      # never overwrites what the owner wrote


def test_the_calculator_answer_shown_to_the_owner_is_the_one_the_check_expects(docs, capsys):
    class A:
        table_id, op, cells = TABLE, "diff", ["0,4", "r1c4"]
    tool.cmd_calc(A)
    out = capsys.readouterr().out
    assert "1,062,201 명" in out and "[[0, 4], [1, 4]]" in out


def test_the_owner_files_in_the_repository_pass_the_check(docs):
    """Skipped until the owner has committed them."""
    if not tool.OWNER_FILE.exists() and not tool.REVIEW_FILE.exists():
        pytest.skip("the owner has not committed data/ko/owner_eval.jsonl or data/ko/custom_eval_review.jsonl yet")
    if tool.OWNER_FILE.exists():
        assert tool.check_owner(tool.load(tool.OWNER_FILE), docs) == []
    if tool.REVIEW_FILE.exists():
        assert tool.check_review(tool.load(tool.REVIEW_FILE)) == []


EVAL = ROOT / "experiments" / "eval"


def predictions(run: str) -> dict[str, dict]:
    return {r["qid"]: r for r in map(json.loads, (EVAL / run / "predictions.jsonl").read_text(encoding="utf-8").splitlines())}


def test_the_stored_analysis_is_what_the_script_produces_and_follows_from_the_files():
    """The numbers the documents cite about the owner's questions and the review come from stored predictions and from
    the owner's two files. Nothing in them may be typed by hand."""
    import subprocess

    stored = (EVAL / "owner_eval_analysis.json").read_text(encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "owner_eval_analysis.py")], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    assert (EVAL / "owner_eval_analysis.json").read_text(encoding="utf-8") == stored
    d = json.loads(stored)
    review = tool.load(tool.REVIEW_FILE)
    flagged = sorted(x["qid"] for x in review if x["verdict"] != "ok")
    assert d["review"]["flagged"] == flagged and d["review"]["ok"] + d["review"]["fix"] + d["review"]["drop"] == 30 == d["review"]["questions"]
    assert all(x["comment"].strip() for x in review if x["verdict"] != "ok")                          # every objection carries its reason
    for run in ("heuristic_ko_custom", "rl_v3_ko_custom", "exaone_full_vllm_ko_custom"):               # recomputed from the predictions
        p = predictions(run)
        res = d["runs_on_the_ai_written_set"][run]
        assert res["all"]["correct"] == sum(x["verified_correct"] for x in p.values())
        assert res["without_flagged"] == {"n": 30 - len(flagged), "correct": sum(x["verified_correct"] for q, x in p.items() if q not in flagged),
                                          "rate": round(sum(x["verified_correct"] for q, x in p.items() if q not in flagged) / (30 - len(flagged)), 4)}
    owner = {q["qid"]: q for q in tool.load(tool.OWNER_FILE)}
    for label, prefix in (("heuristic", "heuristic"), ("mt5_small_final", "rl_v3")):
        p = predictions(f"{prefix}_ko_owner")
        assert set(p) == set(owner)
        res = d["cpu_planners"][label]["owner_first_pass"]
        assert res["correct"] == sum(x["verified_correct"] for x in p.values()) and res["n"] == 30
        calc = [q for q in owner if owner[q]["category"] == "calc"]
        assert res["by_category"]["calc"] == {"n": len(calc), "correct": sum(p[q]["verified_correct"] for q in calc), "rate": round(sum(p[q]["verified_correct"] for q in calc) / len(calc), 4)}
    assert d["owner_set"]["tables_also_used_by_the_ai_written_set"] == 0 and d["owner_set"]["questions"] == 30


def test_the_owner_evaluations_were_made_like_the_earlier_ones():
    """First pass without the subject check, then the same raw outputs verified again with it."""
    for prefix in ("heuristic", "rl_v3"):
        first = json.loads((EVAL / f"{prefix}_ko_owner" / "metrics.json").read_text(encoding="utf-8"))
        again = json.loads((EVAL / f"{prefix}_ko_owner_ec" / "metrics.json").read_text(encoding="utf-8"))
        assert first["meta"]["data"] == again["meta"]["data"] == ["data/ko/owner_eval.jsonl"] and first["metrics"]["n"] == again["metrics"]["n"] == 30
        assert first["meta"]["entity_check"] is False and again["meta"]["entity_check"] is True
        assert again["meta"]["replay_from"] == f"experiments/eval/{prefix}_ko_owner"
        a, b = predictions(f"{prefix}_ko_owner"), predictions(f"{prefix}_ko_owner_ec")
        assert all(a[q]["raw_output"] == b[q]["raw_output"] for q in a)


def test_the_documents_say_who_wrote_the_questions_and_what_is_still_missing():
    report = (ROOT / "docs" / "REPORT.md").read_text(encoding="utf-8")
    sec = report[report.index("## 25. 소유자가 쓴 평가 문항"):]
    for needle in ("AI 도구는 문항을 쓰거나 고치지 않았다", "문항은 고치지 않고 그대로 둔다", "EXAONE은 전체 데이터 모델 하나와 튜닝하지 않은 두 크기만 쟀다", "한 사람이 썼고 다른 사람이 검수하지 않았다",
                   "기존 test 문항과 같은 셀을 묻는 문항이 있다", "구간이 겹친다", "그 가운데 한 문항은 계산기가 답을 냈다", "검증기는 그 셀이 질문이 묻는 것인지는 보지 않는다",
                   "세트의 난이도를 견줄 근거는 아니다"):
        assert needle in sec, needle
    handoff = (ROOT / "docs" / "HANDOFF.md").read_text(encoding="utf-8")
    sec = handoff[handoff.index("### 9.1f"):handoff.index("### 9.2 ")]
    for needle in ('"벤치마크를 구축했다"', '"여러 사람이 검수한 평가셋"', '"직접 쓴 문항에서 80%이므로 실제 표에서도 80%다"', "이 약점을 숨기지 않는다", "문항은 그대로 올라갔다"):
        assert needle in sec, needle
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    sec = readme[readme.index("### 9.12 소유자가 쓴 평가 문항"):readme.index("## 10. 추론 최적화")]
    assert "평가한 전체 데이터 모델은 하나입니다" in sec and "문항을 쓰거나 고치지 않았습니다" in sec and "검증기는 그 셀이 질문이 묻는 것인지는 보지 않습니다" in sec
    # nothing claims an EXAONE result on the owner's questions while no such run is stored
    if not list(EVAL.glob("exaone_*_ko_owner")):
        nb = (ROOT / "notebooks" / "gpu_experiments_2.ipynb").read_text(encoding="utf-8")
        assert "OWNER_SETS" in nb and "아직 돌리지 않았다" in (ROOT / "docs" / "experiments" / "gpu-runbook.md").read_text(encoding="utf-8")



def test_the_exaone_results_on_the_owner_questions_follow_from_the_stored_predictions():
    """The owner ran EXAONE on the 30 questions on Kaggle. What the documents say about it (the score, the calculation
    questions, the question the calculator answered, the unanswerable questions that got an answer) is recomputed here
    from the stored outputs."""
    d = json.loads((EVAL / "owner_eval_analysis.json").read_text(encoding="utf-8"))["gpu_planners"]
    owner = {q["qid"]: q for q in tool.load(tool.OWNER_FILE)}
    p = predictions("exaone_full4_vllm_ko_owner")
    res = d["exaone_full_data"]
    assert set(p) == set(owner) and res["owner_first_pass"]["correct"] == sum(x["verified_correct"] for x in p.values())
    calc = [q for q in owner if owner[q]["category"] == "calc"]
    assert all(p[q]["verified_correct"] and p[q]["pred_op"] == owner[q]["op"] and p[q]["pred_cells"] == [f"r{i}c{j}" for i, j in owner[q]["gold_cells"]] for q in calc)      # right operation, right cells
    wrong_number = [q for q in calc if not p[q]["raw_correct"]]
    assert wrong_number == ["ko_owner_17"] and "189.55" in p["ko_owner_17"]["raw_output"] and p["ko_owner_17"]["pred_answer"] == owner["ko_owner_17"]["answer"]
    assert res["owner_calc_questions"]["right_only_because_the_calculator_recomputed"] == len(wrong_number)
    unans = [q for q in owner if owner[q]["category"] == "abstain"]
    sent = [q for q in unans if p[q]["pred_status"] == "answered"]
    assert res["owner_unanswerable_questions"] == {"n": len(unans), "withheld": len(unans) - len(sent), "answer_sent": len(sent)} and len(sent) == 2
    assert all(not p[q]["verified_correct"] for q in owner if owner[q]["category"] == "text_table")                 # trained without text examples
    h = predictions("heuristic_ko_owner")
    pt = json.loads((EVAL / "paired_tests.json").read_text(encoding="utf-8"))["full4_vs_heuristic_ko_owner"]
    assert pt["candidate_better"] == sum(p[q]["verified_correct"] and not h[q]["verified_correct"] for q in owner)
    assert pt["reference_better"] == sum(h[q]["verified_correct"] and not p[q]["verified_correct"] for q in owner) == 0
    big = json.loads((EVAL / "paired_tests.json").read_text(encoding="utf-8"))["full4_vs_ref_7p8b_ko_owner"]
    assert big["p_two_sided"] > 0.05                                                # the documents must not call this difference significant
    # the full-data model of that session sits inside the range of the earlier trainings
    ems = [json.loads((EVAL / r / "metrics.json").read_text(encoding="utf-8"))["metrics"]["verified_em"]
           for r in ("exaone_full_vllm_ko_test", "exaone_full_vllm_ko_test_run2", "exaone_full2old_vllm_ko_test", "exaone_full2_vllm_ko_test", "exaone_full3_vllm_ko_test")]
    new = json.loads((EVAL / "exaone_full4_vllm_ko_test" / "metrics.json").read_text(encoding="utf-8"))["metrics"]["verified_em"]
    assert min(ems) <= new <= max(ems)
