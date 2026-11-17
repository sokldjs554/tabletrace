"""The top layer of the 연구 결과 view: a few conclusions, each with one small chart, and the grouping of the detail
sections below them. Used by scripts/build_research.py.

Every number and every conclusion sentence is built from result files. A sentence that states a comparison is only
produced when the files bear it out (the `assert`s below); nothing here is typed in.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "experiments" / "eval"


def _load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _n(run: str) -> int:
    return _load(f"experiments/eval/{run}/metrics.json")["metrics"]["n"]


def _em(run: str) -> float:
    return _load(f"experiments/eval/{run}/metrics.json")["metrics"]["verified_em"]


def _metric(run: str, key: str) -> float:
    return _load(f"experiments/eval/{run}/metrics.json")["metrics"][key]


def p1(x: float) -> str:
    return f"{100 * x:.1f}%"


def accuracy() -> dict:
    """Korean test: the planners side by side. The full-data model was trained seven times; the bar is the first
    (lowest) training, which is the number the documents lead with, and the other six are drawn as ticks."""
    full = [_em("exaone_full_vllm_ko_test"), _em("exaone_full_vllm_ko_test_run2"), _em("exaone_full2old_vllm_ko_test"),
            _em("exaone_full2_vllm_ko_test"), _em("exaone_full3_vllm_ko_test"), _em("exaone_full4_vllm_ko_test"),
            _em("exaone_ownloop_vllm_ko_test")]
    small = [_em("exaone_vllm_ko_test_run1"), _em("exaone_vllm_ko_test_run2"), _em("exaone_vllm_ko_test")]
    b32 = _load("experiments/gpu2_2026-11-14/recovered.json")["evals"]["ref_32b_awq_ko_test"]["v1"]["metrics"]["verified_em"]
    rows = [
        {"label": "휴리스틱 기준선 (모델 아님)", "value": _em("heuristic_ko_test")},
        {"label": "mT5-small 최종 (3억 파라미터, 튜닝)", "value": _em("rl_v3_ko_test")},
        {"label": "EXAONE 1.2B, 튜닝 없음", "value": _em("ref_1p2b_ko_test")},
        {"label": "EXAONE 7.8B, 튜닝 없음", "value": _em("ref_7p8b_awq_ko_test")},
        {"label": "EXAONE 32B, 튜닝 없음", "value": b32},
        {"label": "EXAONE 1.2B LoRA, 300문항 튜닝", "value": min(small), "ticks": sorted(small)[1:]},
        {"label": "EXAONE 1.2B LoRA, 전체 데이터 튜닝", "value": min(full), "ticks": sorted(full)[1:], "emphasis": True},
    ]
    assert full[0] == min(full) and min(full) > b32 > rows[3]["value"] > rows[2]["value"]
    for r in rows:
        r["text"] = p1(r["value"])
    return {"id": "accuracy", "kind": "bars", "max": 1.0, "rows": rows,
            "title": f"전체 데이터로 튜닝한 12억 파라미터 EXAONE이 {p1(min(full))}로, 튜닝하지 않은 32B({p1(b32)})보다 높다",
            "caption": f"한국어 test {_n('exaone_full_vllm_ko_test')}문항의 정답률(verified EM, 주어 검사 없이). 전체 데이터 튜닝은 같은 설정으로 {len(full)}번 학습했다. "
                       f"막대는 가장 낮은 첫 학습이고, 나머지 {len(full) - 1}번은 {p1(sorted(full)[1])}~{p1(max(full))}이다. 300문항 튜닝은 {len(small)}번이고 막대는 가장 낮은 값이다. "
                       "튜닝 없는 모델은 프롬프트에 예시를 몇 개 넣었다.",
            "more": "한국어 표 QA — 독립 test", "tick_label": "같은 설정의 다른 학습"}


def evidence() -> dict:
    ev = _load("experiments/eval/evidence_error.json")
    rows = [{"label": "mT5-small 최종", "value": ev["rl_v3_ko_test"]["strict"]["rate"]},
            {"label": "EXAONE 1.2B LoRA, 300문항 튜닝", "value": ev["exaone_vllm_ko_test"]["strict"]["rate"]},
            {"label": "같은 300문항, 표 입력에 열 번호", "value": ev["exaone_colid_vllm_ko_test"]["strict"]["rate"]},
            {"label": "EXAONE 1.2B LoRA, 전체 데이터 튜닝", "value": ev["exaone_full_vllm_ko_test"]["strict"]["rate"]}]
    assert rows[0]["value"] > 0.5 and rows[1]["value"] > 0.5 and rows[3]["value"] < 0.05
    for r in rows:
        r["text"] = p1(r["value"])
    return {"id": "evidence", "kind": "bars", "max": 1.0, "rows": rows,
            "title": "약한 모델은 맞힌 답의 절반 이상에서 답이 없는 셀을 근거로 댄다",
            "caption": "한국어 test의 조회 문항 가운데 모델이 쓴 답이 정답과 같은 것만 골라, 모델이 인용한 셀(검증기가 손대기 전)에 그 답이 없는 비율을 셌다. "
                       "낮을수록 좋다. 전체 데이터로 튜닝하면 1%대로 내려가고, 300문항 튜닝에서도 표에 열 번호를 붙이면 3%대가 된다.",
            "more": "답은 맞는데 근거 셀이 틀린 비율"}


def verifier() -> dict:
    o = _load("experiments/eval/evidence_error.json")["exaone_full_vllm_ko_test"]
    bars = []
    for label, key in (("모델 출력 그대로", "raw"), ("검증기를 거친 뒤 (주어 검사 포함)", "verifier_subject_check")):
        v, n = o[key], o[key]["n"]
        bars.append({"label": label, "parts": [{"name": "맞는 답", "value": v["answered_correct"] / n, "role": "good"},
                                               {"name": "답하지 않음", "value": (n - v["answered"]) / n, "role": "none"},
                                               {"name": "틀린 답", "value": v["answered_wrong"] / n, "role": "bad"}]})
    raw, ver = o["raw"], o["verifier_subject_check"]
    assert ver["wrong_answer_rate"]["rate"] < raw["wrong_answer_rate"]["rate"] and ver["coverage"] < raw["coverage"]
    return {"id": "verifier", "kind": "stack", "bars": bars,
            "title": f"검증기를 거치면 틀린 답이 {p1(raw['wrong_answer_rate']['rate'])}에서 {p1(ver['wrong_answer_rate']['rate'])}로 줄고, "
                     f"답하는 비율은 {p1(raw['coverage'])}에서 {p1(ver['coverage'])}로 준다",
            "caption": f"전체 데이터로 튜닝한 EXAONE 1.2B의 한국어 test {raw['n']}문항. 세 부분의 합이 {raw['n']}문항이다. 답이 없는 질문에 답하지 않은 것도 \"답하지 않음\"에 든다. "
                       f"검증기를 거쳐도 {raw['n']}문항 가운데 {ver['answered_wrong']}문항에는 틀린 답이 나간다.",
            "more": "검증기 앞뒤의 운영점"}


def rl() -> dict:
    key = "evidence_cells_exact_raw"
    pairs = [("두 번째 실험 (300문항 모델에서 시작)", "exaone_rlstart2_vllm_ko_test", "exaone_grpo2_vllm_ko_test"),
             ("같은 실험을 한 번 더", "exaone_rlstart2b_vllm_ko_test", "exaone_grpo2c_vllm_ko_test"),
             ("대조군: 배치 구성만 첫 실험처럼", "exaone_rlstart2b_vllm_ko_test", "exaone_grpo2b_vllm_ko_test"),
             ("전체 데이터 모델에서 시작", "exaone_full3_vllm_ko_test", "exaone_grpo3_vllm_ko_test")]
    rows = [{"label": lab, "before": _metric(a, key), "after": _metric(b, key)} for lab, a, b in pairs]
    for r in rows:
        r["text"] = f"{p1(r['before'])} → {p1(r['after'])}"
    assert rows[0]["after"] - rows[0]["before"] > 0.1 and rows[1]["after"] - rows[1]["before"] > 0.1
    assert abs(rows[2]["after"] - rows[2]["before"]) < 0.03 and abs(rows[3]["after"] - rows[3]["before"]) < 0.03
    return {"id": "rl", "kind": "dumbbell", "max": 1.0, "rows": rows, "before_label": "강화학습 전", "after_label": "강화학습 뒤",
            "title": "강화학습은 약한 시작 모델의 인용 셀 정확도만 올렸다",
            "caption": f"한국어 test {_n('exaone_grpo2_vllm_ko_test')}문항에서 모델이 인용한 셀이 정답 셀과 같은 비율(검증기가 손대기 전). 보상과 손실은 저장소 소유자가 직접 쓴 코드다. "
                       "배치 구성만 첫 실험처럼 되돌린 대조군에서는 오르지 않았고, 이미 인용 셀이 정확한 전체 데이터 모델에서는 더 오를 자리가 없었다. 알고리즘 하나, 시드 하나의 결과다.",
            "more": "EXAONE 강화학습, 두 번째 실험"}


def owner() -> dict:
    idx = _load("console/data/recorded/index.json")
    rows = []
    for k in idx["planner_order"]:
        t = idx["planners"][k]["totals"]["ko_owner"]
        rows.append({"label": idx["planners"][k]["short"], "value": t["right"], "of": t["n"], "text": f"{t['right']}/{t['n']}"})
    assert rows[0]["value"] == max(r["value"] for r in rows) and rows[-1]["label"] == "휴리스틱"
    n = rows[0]["of"]
    ci = _load("experiments/eval/owner_eval_analysis.json")["gpu_planners"]["exaone_full_data"]["owner_first_pass"]
    assert ci["correct"] == rows[0]["value"] and ci["n"] == n
    return {"id": "owner", "kind": "meter", "rows": rows,
            "title": f"소유자가 직접 쓴 {n}문항에서 전체 데이터 EXAONE은 {rows[0]['value']}개, 휴리스틱 기준선은 {rows[-1]['value']}개를 맞혔다",
            "caption": f"저장소 소유자가 시험 분할의 표를 보고 직접 쓴 {n}문항 전체. 평가와 같은 조건이다. {n}문항이라 구간이 넓다"
                       f"(전체 데이터 EXAONE의 95% 구간 {p1(ci['ci95']['lo'])}~{p1(ci['ci95']['hi'])}). 문항마다의 결과는 \"문항별 결과\" 탭에 있다.",
            "more": "소유자가 쓴 30문항에서의 EXAONE", "link": {"href": "#matrix", "text": "문항별 결과 보기"}}


def chem() -> dict:
    """The chemistry paper tables, from the run that kept per-question predictions (notebook 2, section N)."""
    a = _load("experiments/eval/chem_rerun_analysis.json")
    p, before = a["chemistry"]["chem_papers"], a["earlier_run_without_predictions"]["chem_papers"]
    tuned, plain = p["tuned"], p["untuned_six_examples"]
    rows = [{"label": "휴리스틱 기준선 (모델 아님)", "value": p["heuristic"]["rate"]},
            {"label": "mT5-small 최종", "value": p["mt5_small_final"]["rate"]},
            {"label": "EXAONE 1.2B, 튜닝 없음 (화학 예시 6개)", "value": plain["rate"]},
            {"label": "EXAONE 1.2B LoRA, 한국어와 화학을 함께 튜닝", "value": tuned["rate"], "emphasis": True}]
    assert tuned["rate"] > p["heuristic"]["rate"] > plain["rate"]
    assert p["tuned_vs_untuned"]["p_two_sided"] < 0.001 and p["tuned_vs_heuristic"]["p_two_sided"] < 0.001
    assert tuned["correct"] - before["correct"] == before["this_run_minus_earlier_in_questions"] < 0      # said in the caption
    for r in rows:
        r["text"] = p1(r["value"])
    n = tuned["n"]
    idx = _load("console/data/recorded/index.json")
    shown = idx["planners"]["kochem"]["totals"]["chem_papers"]
    assert (shown["right"], shown["n"]) == (tuned["correct"], n)                  # the demo shows the same run
    one = next(r for r in idx["planners"]["kochem"]["runs"] if r["set"] == "chem_papers" and r["mark"] == "correct" and r["result"]["calculation"])
    return {"id": "chem", "kind": "bars", "max": 1.0, "rows": rows,
            "title": f"영어 화학 논문 표에서 화학을 함께 튜닝한 EXAONE은 {p1(tuned['rate'])}, 튜닝하지 않은 같은 모델은 {p1(plain['rate'])}다",
            "caption": f"공개 논문의 표에 대한 {n}문항의 정답률(verified EM, 주어 검사 없이). 논문 표는 학습에 쓰지 않았고, 학습에 더한 화학 문항은 교과서 표로 만든 합성 문항이다. "
                       f"같은 문항에서 튜닝한 모델만 맞힌 것이 {p['tuned_vs_untuned']['only_candidate']}개, 튜닝하지 않은 모델만 맞힌 것이 {p['tuned_vs_untuned']['only_reference']}개다. "
                       "한국어만 튜닝한 모델은 화학 문항으로 재지 않아서, 이 차이에서 화학 문항을 더한 몫이 얼마인지는 알 수 없다. "
                       f"학습 한 번의 결과이고 95% 구간은 {p1(tuned['ci95']['lo'])}~{p1(tuned['ci95']['hi'])}다. 문항은 AI 도구가 썼고 소유자가 검수하지 않았다. "
                       f"결과 파일이 남지 않은 예전 실행에서는 {p1(before['verified_em'])}였고, 이번이 {-before['this_run_minus_earlier_in_questions']}문항 낮다.",
            "more": "영어 화학에서의 EXAONE", "link": {"href": f"#workbench/{one['id']}/kochem", "text": "논문 표 문항 하나 보기"}}


def risk() -> dict:
    run = _load("experiments/eval/risk_coverage.json")["runs"]["exaone_full2_vllm_ko_test"]
    series = []
    for name, key in (("모델만 (확신도 문턱)", "model/sum_logprob"), ("검증기 + 확신도 문턱", "verifier/sum_logprob")):
        c = run["curves"][key]
        pts = [[int(k) / 100, v] for k, v in sorted(c["risk_at_coverage_pct"].items(), key=lambda kv: int(kv[0]))]
        pts.append([c["no_threshold"]["coverage"], c["no_threshold"]["risk"]])
        series.append({"name": name, "points": pts})
    ver = run["curves"]["verifier/sum_logprob"]
    at10, end = ver["max_coverage_with_risk_under_pct"]["10"], ver["no_threshold"]
    assert at10["coverage"] < end["coverage"] and at10["risk"] < end["risk"]
    return {"id": "risk", "kind": "line", "series": series, "x_label": "답하는 비율", "y_label": "답한 것 가운데 틀린 비율", "x_max": 1.0, "y_max": 0.2,
            "title": f"틀린 답을 10% 아래로 두려면 답하는 비율을 {p1(end['coverage'])}에서 {p1(at10['coverage'])}로 낮춰야 한다",
            "caption": f"전체 데이터로 튜닝한 EXAONE 1.2B(길이 결함을 고친 학습), 한국어 test {run['questions']}문항. 모델이 답에 매긴 로그 확률의 합이 문턱보다 낮으면 답하지 않는다. "
                       "문턱을 올릴수록 왼쪽으로 간다. 오른쪽 끝은 문턱이 없을 때다. 같은 응답률에서 검증기를 거친 쪽이 덜 틀린다.",
            "more": "확신도 문턱 — 위험·응답률 곡선"}


def unexpected() -> list[dict]:
    """Results that went against what was hoped for, said as plainly as the others."""
    rl3 = _load("experiments/eval/rl3_analysis.json")
    conf = rl3["confidence"]["sum_logprob"]["auroc"]       # the signal the documents report
    own = _load("console/data/recorded/index.json")["planners"]["exaone"]["runs"]
    text = [r for r in own if r["set"] == "ko_owner" and r["id"] in _text_ids()]
    out = [
        {"text": f"mT5-small은 미세조정과 강화학습을 다 거치고도 {p1(_em('rl_v3_ko_test'))}로, 휴리스틱 기준선 {p1(_em('heuristic_ko_test'))}를 넘지 못했다.",
         "more": "한국어 표 QA — 독립 test"},
        {"text": f"전체 데이터 모델에서 시작한 강화학습은 정답률을 바꾸지 못했다({p1(_em('exaone_full3_vllm_ko_test'))}와 {p1(_em('exaone_grpo3_vllm_ko_test'))}). "
                 f"확신도가 맞는 답과 틀린 답을 가르는 정도(AUROC)는 {conf['start']:.3f}에서 {conf['rl']:.3f}으로 나빠졌다.",
         "more": "전체 데이터 모델에서 시작한 강화학습"},
        {"text": f"튜닝하지 않은 1.2B 모델에게 도구를 스스로 고르게 하면 {p1(_em('tools_1p2b_ko_test'))}로, 프로그램을 한 번에 제안하게 할 때({p1(_em('ref_1p2b_ko_test'))})보다 낮았다.",
         "more": "튜닝하지 않은 EXAONE, 크기별"},
        {"text": f"소유자가 쓴 문항 가운데 답이 본문에 있는 {len(text)}문항은 전체 데이터 EXAONE이 {sum(r['mark'] == 'correct' for r in text)}개를 맞혔다.",
         "more": "소유자가 쓴 30문항에서의 EXAONE"},
    ]
    assert _em("rl_v3_ko_test") < _em("heuristic_ko_test") and conf["rl"] < conf["start"]
    assert _em("tools_1p2b_ko_test") < _em("ref_1p2b_ko_test")
    return out


def _text_ids() -> set[str]:
    return {e["id"] for e in _load("console/data/examples.json")["examples"] if e["set"] == "ko_owner" and e["category"] == "text_table"}


def highlights() -> list[dict]:
    return [accuracy(), evidence(), verifier(), rl(), owner(), chem(), risk()]


# The detail sections, grouped. A section belongs to the first group one of whose keys occurs in its title.
GROUPS = [
    ("근거 셀과 검증기", ["근거 셀이 틀린", "검증기 앞뒤", "검증기를 통과한 오답", "확신도 문턱", "구조 이해 표 인코더"]),
    ("모델 비교와 평가 문항", ["독립 test", "수작업 평가 30문항", "소유자가 쓴", "튜닝하지 않은 EXAONE", "큰 EXAONE을 튜닝 없이", "길이 결함", "표가 겹치는 분할",
                       "큰 표 —", "큰 표,", "본문 답변", "학습 실행 기록"]),
    ("강화학습", ["강화학습"]),
    ("영어 화학", ["영어 화학"]),
    ("서비스와 에이전트", ["여러 턴 대화", "Tool Calling"]),
    ("추론 최적화, 서빙, 멀티 GPU", ["추론 최적화", "멀티 GPU", "vLLM / SGLang"]),
    ("재지 못한 것", ["재지 못한 것"]),
]


def group_sections(sections: list[dict]) -> list[dict]:
    """Assign every section to a group (section["group"]) and return the groups in order with their section counts."""
    counts = {name: 0 for name, _ in GROUPS}
    for s in sections:
        name = next((name for name, keys in GROUPS if any(k in s["title"] for k in keys)), None)
        assert name is not None, f"section without a group: {s['title']}"
        s["group"] = name
        counts[name] += 1
    return [{"name": name, "sections": n} for name, n in counts.items() if n]


def check_links(items: list[dict], sections: list[dict]) -> None:
    """Every "more" must name exactly one section (by the start of its title)."""
    for h in items:
        hits = [s["title"] for s in sections if s["title"].startswith(h["more"])]
        assert len(hits) == 1, (h["more"], hits)
