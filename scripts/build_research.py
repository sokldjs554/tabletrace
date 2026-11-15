"""Compile experiment artifacts into console/data/research.json (what the 연구 결과 view shows).

Reads experiments/eval/*/metrics.json, experiments/eval/{evidence_error,leak_effect}.json,
experiments/sft_*/summary.json, experiments/rl_ko/summary.json, experiments/exaone_lora*/train_info.json and
experiments/bench/*.json. Missing artifacts are reported as 'prep' (prepared, not run), never invented.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pct(x):
    return "-" if x is None else f"{100 * x:.1f}%"


def eval_row(name: str, key: str) -> list | None:
    m = load(EXP / "eval" / key / "metrics.json")
    if not m:
        return None
    mm = m["metrics"]
    return [name, mm["n"], pct(mm["verified_em"]), pct(mm["lookup_em"]), pct(mm["calc_em"]), pct(mm["evidence_cells_exact"]),
            pct(mm.get("evidence_cells_exact_raw")), pct(mm["abstain_recall"]), pct(mm["false_abstain_rate"]), pct(mm["parse_fail_rate"]), f"{mm['mean_ms_per_example']:.0f}"]


def ci(w: dict | None) -> str:
    return "-" if not w or w.get("rate") is None else f"{100 * w['rate']:.1f}% ({100 * w['lo']:.1f}–{100 * w['hi']:.1f})"


def measurement_sections() -> list[dict]:
    """The three measurements of docs/REPORT.md §19, from the same artifacts as the README tables."""
    out = []
    ev = load(EXP / "eval" / "evidence_error.json")
    if ev:
        names = [("mT5-small SFT stage2", "sft_ko2_ko_test"), ("mT5-small 최종 (RL v3)", "rl_v3_ko_test"),
                 ("EXAONE-4.0-1.2B LoRA 300개, 1번째 학습", "exaone_vllm_ko_test_run1"), ("같은 설정, 2번째 학습", "exaone_vllm_ko_test_run2"),
                 ("같은 설정, 3번째 학습", "exaone_vllm_ko_test"), ("같은 300개, 표 입력에 열 번호(colid)", "exaone_colid_vllm_ko_test"),
                 ("EXAONE-4.0-1.2B LoRA 전체 데이터, 1번째 학습", "exaone_full_vllm_ko_test"),
                 ("같은 설정, 2번째 학습", "exaone_full_vllm_ko_test_run2")]
        rows = [[n, o["correct_lookup_answers"], o["cited_gold"], o["no_answer_in_cell"], ci(o["strict"]), o["strict_where"].get("same_row", 0),
                 pct(o["verified_em"]), pct(o["verified_em_no_repair"])] for n, k in names if (o := ev.get(k))]
        out.append({"title": "답은 맞는데 근거 셀이 틀린 비율 (한국어 test 조회 539문항)", "status": "done",
                    "description": "모델이 쓴 답 텍스트가 정답과 같은 조회 답만 골라, 모델이 인용한 셀(검증기가 손대기 전)에 그 답이 들어 있는지 셌다. 구간은 Wilson 95%. "
                                   "마지막 두 열은 test 699문항 전체의 verified EM과, 인용 셀에 답이 없을 때 근거를 고치지 않고 보류로 채점한 값이다.",
                    "columns": ["모델", "답이 맞은 조회 답", "인용 셀 = 정답 셀", "인용 셀에 답이 없음", "비율 (95% 구간)", "그중 행은 맞고 열이 틀림", "verified EM", "근거 복구 없이"],
                    "rows": rows,
                    "notes": ["약한 모델은 맞힌 답의 절반 이상에서 답이 없는 셀을 인용한다. 거의 전부 행은 맞고 열이 틀린 경우다.",
                              "같은 300개 학습에서 표의 셀마다 열 번호를 붙여 주면(colid) 이 비율이 3%대로 내려간다. 답 정확도는 오르지 않았다(1회 실행).",
                              "전체 데이터로 학습한 EXAONE은 두 번의 학습 모두 1%대다.",
                              "검증기는 이 경우 답 텍스트와 같은 셀을 찾아 근거를 고친다. 워크벤치에서는 그런 답에 \"근거를 고쳐 답함\" 배지가 붙고, 모델이 인용한 셀이 점선으로 따로 표시된다."],
                    "artifact": "experiments/eval/evidence_error.json (scripts/evidence_error.py)"})
        rows = []
        for n, k in [("휴리스틱 기준선", "heuristic_ko_test"), ("mT5-small 최종 (RL v3)", "rl_v3_ko_test"), ("EXAONE LoRA 300개 (3번째 학습)", "exaone_vllm_ko_test"),
                     ("EXAONE LoRA 300개, 열 번호 형식(colid)", "exaone_colid_vllm_ko_test"), ("EXAONE LoRA 전체 데이터 (1번째 학습)", "exaone_full_vllm_ko_test"), ("EXAONE LoRA 전체 데이터 (2번째 학습)", "exaone_full_vllm_ko_test_run2")]:
            o = ev.get(k)
            for label, pt in (("모델 출력 그대로", "raw"), ("검증기 v1", "verifier"), ("검증기 v2(개체 일치 검사)", "verifier_subject_check"), ("검증기 v1, 근거 복구 없이 보류", "verifier_no_repair")):
                if o and o.get(pt):
                    q = o[pt]
                    rows.append([n, label, pct(q["coverage"]), ci(q["accuracy_when_answered"]), pct(q["wrong_answer_rate"]["rate"]), f"{q['answered_correct']} / {q['answered_wrong']}"])
        out.append({"title": "검증기 앞뒤의 운영점 (한국어 test 699문항)", "status": "done",
                    "description": "같은 모델 출력을 네 조건에서 채점했다. 검증기는 답하는 비율을 조금 내주고 오답 유출을 줄인다. 계산 문항은 인용 셀로 다시 계산하므로 정답 수가 늘 수 있다.",
                    "columns": ["모델", "조건", "답한 비율", "답한 것 중 정답 (95% 구간)", "오답이 그대로 나간 비율", "정답 수 / 오답 수"], "rows": rows,
                    "artifact": "experiments/eval/evidence_error.json"})
    leak, prof = load(EXP / "eval" / "leak_effect.json"), load(ROOT / "data" / "ko" / "official_split_profile.json")
    if leak and prof:
        rows = []
        for n, k in [("휴리스틱 기준선 (학습 없음, 대조군)", "heuristic"), ("mT5-small SFT stage2", "sft_ko2"), ("mT5-small 최종 (RL v3)", "rl_v3")]:
            x = (leak["planners"].get(k) or {}).get("verified_em")
            if x:
                rows.append([n, ci(x["seen"]), ci(x["unseen"]), f"{100 * x['diff']:+.1f}%p ({100 * x['diff_lo']:+.1f} ~ {100 * x['diff_hi']:+.1f})"])
        d = prof["dev_on_train_table"]
        out.append({"title": "표가 겹치는 분할의 효과 — 학습 때 본 표와 처음 보는 표", "status": "done",
                    "description": f"KorWikiTQ 공개 train/dev 파일에는 셀까지 같은 표 {prof['shared_tables_by_url_and_content']:,}개가 함께 들어 있고, 공개 dev 질문 {d['of']:,}개 중 {d['examples']:,}개({pct(d['rate'])})가 train에도 있는 표를 묻는다. "
                                   "이 프로젝트는 표 단위로 다시 나눴다. 겹침이 점수에 주는 영향을 재려고 학습에 쓴 표의 새 질문과 처음 보는 표의 질문을 같은 규칙으로 1,497개씩 골라 비교했다.",
                    "columns": ["모델", "학습 때 본 표의 새 질문 (95% 구간)", "처음 보는 표의 질문 (95% 구간)", "차이 (95% 구간, 표 단위 부트스트랩)"], "rows": rows,
                    "notes": ["mT5에서는 학습 때 본 표라고 점수가 오르지 않았다. 겹침은 데이터의 사실이지만, 점수를 부풀린다는 것은 보이지 못했다.",
                              "EXAONE에서는 GPU가 필요해 재지 않았다. 질문 세트는 data/ko/leak_probe_*.jsonl에 있다."],
                    "artifact": "experiments/eval/leak_effect.json (scripts/data/build_leak_probe.py, scripts/leak_effect.py)"})
    return out


def supplement_sections() -> list[dict]:
    """What was added after comparing the project with the job posting (docs/REPORT.md §20). Every section is skipped when
    its artifact is missing, so the page never shows a run that did not happen."""
    out = []
    enc_dir = EXP / "encoder"
    variants = [("structure", "mT5-small의 인코더 + 행·열 임베딩"), ("ko_plain", "KoELECTRA-small, 구조 임베딩 없음 (같은 토큰, 대조군)"),
                ("ko_structure", "KoELECTRA-small + 행·열 임베딩"), ("ko_structure_pt", "KoELECTRA-small + 행·열 임베딩 + 표 사전학습(바뀐 셀 찾기)"),
                ("ko_structure_pool", "KoELECTRA-small + 행·열 임베딩, 학습 질문을 풀에서 8,000개 더 (1 epoch)")]
    rows = []
    for key, label in variants:
        m = load(enc_dir / key / "metrics.json")
        if m:
            t = m["test"]
            rows.append([label, f"{m['train_questions']:,}", m["steps"], ci(t["cell"]), pct(t["row"]["rate"]), pct(t["col"]["rate"])])
    if rows:
        cited = []
        for label, run in (("mT5-small 최종", "rl_v3_ko_test"), ("EXAONE-4.0-1.2B LoRA 300개", "exaone_vllm_ko_test"), ("같은 300개에 열 번호 형식", "exaone_colid_vllm_ko_test"),
                           ("전체 데이터", "exaone_full_vllm_ko_test")):
            f = EXP / "eval" / run / "predictions.jsonl"
            if f.exists():
                lookups = [r for r in map(json.loads, open(f, encoding="utf-8")) if r["source"] == "korwikitq"]
                cited.append(f"{label} {pct(sum(r['cells_exact_raw'] for r in lookups) / len(lookups))}")
        notes = [f"같은 539문항에서 생성 모델이 인용한 셀이 정답 셀인 비율(검증기가 손대기 전): {', '.join(cited)}.",
                 "인코더는 조회(셀 하나 고르기)만 한다. 계산, 보류, 본문 답은 하지 못한다.",
                 "바탕 모델은 둘이다. 생성 플래너와 같은 mT5-small의 인코더, 그리고 한국어 PLM인 KoELECTRA-small. 각 설정은 한 번씩 돌렸다."]
        pre = load(enc_dir / "ko_pretrain" / "metrics.json")
        if pre:
            notes.append(f"표 사전학습: 표 {pre['tables']:,}개에서 셀의 15%를 다른 셀로 바꾸고 바뀐 셀을 찾게 했다({pre['steps']} step). "
                         f"따로 떼어 둔 표 {pre['probe_tables']}개에서 바뀐 셀 찾기 F1 {pre['probe_before']['f1']:.2f} → {pre['probe_after']['f1']:.2f}.")
        out.append({"title": "구조 이해 표 인코더 — 사전학습 모델에 행·열 임베딩과 셀 선택 헤드 (CPU 학습)", "status": "done",
                    "description": "표를 글로 풀어 생성 모델에 넣는 대신, 토큰마다 행 번호와 열 번호 임베딩을 더하고 셀마다 점수를 매겨 답이 든 셀을 고른다. "
                                   "행·열 임베딩은 0에서 시작하므로 학습 전에는 원래 사전학습 모델과 같다. 시험은 한국어 test의 조회 539문항(표 단위 분할)이다.",
                    "columns": ["설정", "학습 질문", "step", "셀 정확도 (95% 구간)", "행 정확도", "열 정확도"], "rows": rows, "notes": notes,
                    "artifact": "experiments/encoder/*/metrics.json (scripts/train/table_encoder.py)"})
    ag = load(enc_dir / "agreement.json")
    if ag:
        summ = load(enc_dir / "summary.json") or {"variants": {}}
        ranked = sorted((k for k in ag["encoders"] if k in summ["variants"]), key=lambda k: -summ["variants"][k]["test"]["cell"]["rate"])
        name = ranked[0] if ranked else next(iter(ag["encoders"]), None)
        if name:
            rows = []
            for label, run in [("mT5-small 최종", "rl_v3_ko_test"), ("EXAONE LoRA 300개", "exaone_vllm_ko_test"), ("EXAONE LoRA 300개, 열 번호 형식", "exaone_colid_vllm_ko_test"),
                               ("EXAONE LoRA 전체 데이터", "exaone_full_vllm_ko_test"), ("EXAONE LoRA 전체 데이터, 2번째 학습", "exaone_full_vllm_ko_test_run2")]:
                r = ag["encoders"][name]["runs"].get(run)
                if r:
                    for cond, key in (("검증기만", "verifier"), ("+ 인코더가 같은 행을 고를 때만", "verifier_and_same_row"), ("+ 인코더가 같은 셀을 고를 때만", "verifier_and_same_cell")):
                        q = r[key]
                        rows.append([label, cond, pct(q["coverage"]["rate"]), pct(q["risk"]["rate"]), f"{q['right_sent']['k']} / {q['wrong_sent']['k']}"])
            out.append({"title": "검증기를 통과한 오답 줄이기 — 표 인코더를 두 번째 의견으로 (저장된 예측 재분석)", "status": "done",
                        "description": "검증기는 답과 근거 셀이 서로 맞는지만 본다. 엉뚱한 행의 셀을 일관되게 고른 답은 통과한다. 표 인코더는 생성 모델의 출력을 보지 않고 질문과 표만으로 셀을 고른다. "
                                       "인코더가 다른 곳을 가리키면 답을 보류하는 규칙을, 저장된 예측(조회 539문항)에 적용했다. 응답률은 내보낸 답 ÷ 문항, 위험은 틀린 답 ÷ 내보낸 답이다.",
                        "columns": ["생성 모델", "조건", "응답률", "위험", "정답 수 / 오답 수"], "rows": rows,
                        "notes": ["오답은 크게 줄지만 정답도 함께 잃는다. 어느 지점을 쓸지는 서비스가 정한다(TABLETRACE_SECOND_OPINION, 모드 row 또는 cell).",
                                  "모델을 새로 돌린 것이 아니라 저장된 출력에 규칙을 적용한 계산이다."],
                        "artifact": "experiments/encoder/agreement.json (scripts/encoder_agreement.py)"})
    lt = load(EXP / "eval" / "large_tables.json")
    if lt:
        rows = []
        for label, key in [("휴리스틱, 표 전체", "heuristic_whole_table"), ("휴리스틱, 512토큰, 앞에서 자름", "heuristic_first512"), ("휴리스틱, 512토큰, 행 선별", "heuristic_overlap512"),
                           ("mT5-small 최종, 512토큰, 앞에서 자름", "mt5_first512"), ("mT5-small 최종, 512토큰, 행 선별", "mt5_overlap512"),
                           ("EXAONE 전체 데이터, 672토큰, 앞에서 자름", "exaone_first672"), ("EXAONE 전체 데이터, 672토큰, 행 선별", "exaone_overlap672"),
                           ("EXAONE 전체 데이터, 1,500토큰, 앞에서 자름", "exaone_first1500")]:
            r = (lt["runs"].get(key) or {}).get("all")
            if r:
                rows.append([label, f"{r['n']:,}", pct(r["gold_row_shown"]["rate"]), ci(r["verified_em"]), pct(r["withheld"]["rate"]), pct(r["wrong_answer_sent"]["rate"])])
        st = lt["set"]
        out.append({"title": "큰 표 — 공개 dev 분할에서 학습에 없던 표", "status": "done",
                    "description": f"공개 dev {st['official_dev_questions']:,}문항에서 학습에 쓰인 표를 빼고 남은 {st['questions']:,}문항(표 {st['tables']}개). 그중 {st['by_size']['large']:,}문항이 16행·7열·900자를 넘는 표다. "
                                   "표가 입력에 다 들어가지 않을 때 앞에서부터 자르는 방식과, 질문의 낱말이 든 행을 골라 원래 행 번호 그대로 보여 주는 방식을 비교했다.",
                    "columns": ["실행", "문항", "정답 행이 입력에 있음", "verified EM (95% 구간)", "보류", "오답 내보냄"], "rows": rows,
                    "notes": ["mT5는 시드로 뽑은 1,000문항이다. 작은 표로만 학습한 3억 파라미터 모델이라 절대 수준은 낮다.",
                              "학습에 없던 표만 골랐고 근거 셀까지 채점하므로, 논문에 실린 EM 수치와 나란히 놓을 수 없다."],
                    "artifact": "experiments/eval/large_tables.json (scripts/large_tables.py), data/ko/unseen_dev.jsonl"})
    dh, dn = load(EXP / "eval" / "dialog" / "heuristic.json"), load(EXP / "eval" / "dialog" / "neural.json")
    if dh:
        rows = [[label, pct(d["first_turn_correct"]["rate"]), pct(d["no_memory"]["all"]["rate"]), ci(d["memory"]["all"]), pct(d["memory_when_first_turn_correct"]["rate"]), pct(d["oracle_memory"]["all"]["rate"])]
                for label, d in (("휴리스틱", dh), ("mT5-small 최종", dn)) if d]
        out.append({"title": "여러 턴 대화 — 기억이 후속 질문을 채우는가", "status": "done",
                    "description": f"시험 표의 원래 질문 뒤에 \"그럼 ○○은?\" 형태의 후속 질문을 틀로 붙인 2턴 대화 {dh['dialogs']}개. 둘째 턴만 채점했다. "
                                   "기억은 이전 턴의 표와 근거 셀이고, 후속 질문은 규칙으로 완성한다. 답은 같은 검증 파이프라인이 낸다.",
                    "columns": ["플래너", "첫 턴 정답", "기억 없이", "기억 사용 (95% 구간)", "첫 턴이 정답일 때", "상한 (정답 근거를 기억에 넣음)"], "rows": rows,
                    "notes": ["후속 질문은 틀 두 가지(행 바꾸기, 열 바꾸기)로 만든 것이다. 사람이 나눈 대화가 아니다.",
                              "언어모델이 대화를 관리하지 않는다. 무엇을 채웠는지는 응답과 실행 추적에 남는다."],
                    "artifact": "experiments/eval/dialog/*.json (scripts/eval_dialog.py)"})
    tc = load(EXP / "eval" / "tool_calling_cpu.json")
    if tc and tc["runs"].get("tools"):
        rows = []
        for label, r in [("EXAONE-4.0-1.2B 미튜닝, 도구 호출", tc["runs"]["tools"]), ("EXAONE-4.0-1.2B 미튜닝, 예시 3개 + 한 줄 답", tc["runs"].get("fewshot")),
                         ("(참고) 어휘 겹침 휴리스틱", tc["reference"].get("heuristic")), ("(참고) mT5-small 최종", tc["reference"].get("mt5_final")),
                         ("(참고) EXAONE-4.0-1.2B 전체 데이터 LoRA", tc["reference"].get("exaone_tuned_full"))]:
            if r:
                rows.append([label, f"{pct(r['verified_em']['rate'])} ({r['verified_em']['k']}/{r['verified_em']['n']})", pct(r["withheld"]["rate"]), pct(r["wrong_answer_sent"]["rate"])])
        t = tc["runs"]["tools"]["tool_calling"]
        out.append({"title": "모델이 도구를 고르는 방식 (Tool Calling) — 실제 모델 30문항, CPU", "status": "done",
                    "description": "모델은 표 본문을 받지 않고 제목·열 이름·행 수만 받는다. 셀 찾기, 행 읽기, 열 읽기, 계산 도구를 스스로 골라 호출하고 제출 또는 보류로 끝낸다. 제출은 같은 검증기를 거친다. "
                                   "GPU가 없어 같은 API를 CPU에서 여는 서버로 튜닝하지 않은 EXAONE-4.0-1.2B를 돌렸다. 한국어 수작업 30문항.",
                    "columns": ["실행", "verified EM", "보류", "오답 내보냄"], "rows": rows,
                    "notes": [f"경로는 실제 모델로 끝까지 돌았다. 30문항 중 {t['episodes_that_read_the_table']}문항에서 모델이 도구로 표를 읽었고 인자 오류는 {t['tool_errors']}건이다.",
                              "튜닝하지 않은 1.2B 모델은 셀을 한 번 찾아본 뒤 대부분 보류를 골랐다. 맞힌 것은 답 없는 질문의 보류뿐이다.",
                              "30문항, 한 모델, 한 번이다. 튜닝한 모델과 큰 모델로는 GPU에서 재야 한다."],
                    "artifact": "experiments/eval/tool_calling_cpu.json (scripts/tool_calling_summary.py, scripts/serving/hf_cpu_server.py)"})
    rows = []
    for label, d in [("휴리스틱", "heuristic_chem_papers"), ("mT5-small 화학 튜닝", "sft_chem2_chem_papers"), ("mT5-small 최종", "rl_v3_chem_papers"), ("EXAONE LoRA (한국어+화학)", "exaone_kochem_vllm_chem_papers")]:
        m = load(EXP / "eval" / d / "metrics.json")
        if m:
            c = m["metrics"]["by_category"]
            rows.append([label, pct(m["metrics"]["verified_em"]), pct(c["cell"]["verified_em"]), pct(c["calc"]["verified_em"]), pct(c["abstain"]["verified_em"])])
    if rows:
        out.append({"title": "영어 화학 — 논문 표 (arXiv, CC BY 4.0, 12편·표 20개·62문항)", "status": "done",
                    "description": "교과서 표가 아닌 실제 논문의 표다. 단위가 따로 행으로 있고, 기호가 수식이고, 셀에 불확도가 섞여 있다. 어떤 학습에도 쓰지 않았다. "
                                   "질문은 AI 도구가 표를 읽고 썼고, 답은 표와 계산기에서 채워 기계로 대조한다.",
                    "columns": ["플래너", "verified EM", "조회 (33)", "계산 (19)", "보류 (10)"], "rows": rows,
                    "notes": ["62문항이라 구간이 넓다. 논문별 출처와 라이선스는 data/chem_papers/SOURCES.md에 있다."],
                    "artifact": "experiments/eval/*_chem_papers/metrics.json, data/chem_papers/"})
    rc = load(EXP / "eval" / "risk_coverage.json")
    if rc:
        rows = []
        names = {"rl_v3_conf_ko_test": "mT5-small 최종", "ref_1p2b_ko_test": "EXAONE 1.2B, 튜닝 없음", "ref_7p8b_awq_ko_test": "EXAONE 7.8B(AWQ), 튜닝 없음",
                 "exaone_rlstart2_vllm_ko_test": "EXAONE 1.2B, 300문항 튜닝", "exaone_grpo2_vllm_ko_test": "그 모델에 강화학습"}
        for label, run in [(names.get(k, k), k) for k in names if k in rc["runs"]] + [(k, k) for k in rc["runs"] if k not in names]:
            r = rc["runs"].get(run)
            if not r:
                continue
            sig = r["best_signal_for_verifier"]
            for cond, key in (("모델만", f"model/{sig}"), ("검증기 통과분", f"verifier/{sig}")):
                c = r["curves"][key]
                at = c["risk_at_coverage_pct"]
                rows.append([label, cond, pct(c["no_threshold"]["coverage"]), pct(c["no_threshold"]["risk"])] + [pct(at[k]) if at.get(k) is not None else "–" for k in ("10", "30", "50", "70")] + [c["auroc_right_vs_wrong"]])
        out.append({"title": "확신도 문턱 — 위험·응답률 곡선 (한국어 test 699문항)", "status": "done",
                    "description": "모델이 생성한 토큰의 로그 확률을 확신도로 써서, 확신도가 문턱 이상일 때만 답하게 했을 때의 위험(틀린 답 ÷ 내보낸 답)이다. 답 없는 질문에 답하면 틀린 것으로 센다.",
                    "columns": ["모델", "조건", "문턱 없음: 응답률", "문턱 없음: 위험", "응답률 10%에서 위험", "30%", "50%", "70%", "AUROC"], "rows": rows,
                    "notes": ["mT5-small에서는 확신도가 약한 신호다. 가장 확신하는 답만 내보내도 위험이 크게 줄지 않는다.",
                              "EXAONE의 네 줄은 3차 GPU 실행(2026-11-15)의 평가가 저장한 로그 확률로 그렸다. 네 모델 모두에서 검증기 통과분의 위험이 모델만의 위험보다 낮고, 응답률을 10%로 낮추면 위험이 더 내려간다.",
                              "전체 데이터로 튜닝한 EXAONE의 곡선은 없다. 그 평가는 로그 확률을 저장하지 않았다."],
                    "artifact": "experiments/eval/risk_coverage.json (scripts/risk_coverage.py)"})
    g2 = load(EXP / "gpu2_2026-11-14" / "recovered.json")
    if g2:
        E = g2["evals"]

        def em(name, which="v1", key="verified_em"):
            e = E.get(name, {}).get(which)
            return e["metrics"][key] if e else None

        def p_(v):
            return pct(v) if v is not None else "–"

        src = ("experiments/gpu2_2026-11-14/recovered.json (scripts/recover_gpu2_from_notebook.py). 소유자가 2026-11-14에 Kaggle T4 두 장에서 실행. "
               "결과 파일은 세션과 함께 사라져, 노트북에 남은 출력에서 읽어 낸 값이다. 문항별 예측이 없어 대응 검정은 없다")
        st, gr = "exaone_rlstart_vllm_ko_test", "exaone_grpo_vllm_ko_test"
        rows = [[label, p_(em(st, "ec", k)), p_(em(gr, "ec", k))] for label, k in (
            ("verified EM (주어 검사 포함)", "verified_em"), ("모델이 쓴 답이 맞은 비율", "raw_answer_em_answerable"),
            ("모델이 인용한 셀이 정답 셀과 같은 비율", "evidence_cells_exact_raw"), ("검증기가 근거 셀을 고쳐서 내보낸 비율", "evidence_repaired_rate"),
            ("답할 수 있는 질문을 보류한 비율", "false_abstain_rate"))]
        gd, gi = g2["derived"]["grpo_dev"], g2["grpo"]
        out.append({"title": "EXAONE 강화학습 — 저장소 소유자가 직접 쓴 보상과 손실 (2차 GPU 실험)", "status": "done",
                    "description": f"300문항으로 튜닝한 EXAONE-4.0-1.2B에서 시작해 GRPO {gi['steps']}걸음(걸음마다 프롬프트 4 × 표본 8). 보상은 검증기의 결과다: 복구 없이 통과한 정답 +1.0, "
                                   "근거를 고쳐야 정답 +0.3, 답이 나가지 않음 0, 틀린 답 −0.5, 문법 오류 −1.0. 보상 함수와 GRPO 손실은 소유자가 명세와 테스트만 보고 썼다(docs/rewrite/LOG.md, PR #6). 한국어 test 699문항.",
                    "columns": ["지표", "시작 모델 (300문항 SFT)", f"강화학습 뒤 ({gi['kept_step']}걸음 모델)"], "rows": rows,
                    "notes": ["근거 셀 오류는 줄지 않았다. 인용 셀 정확도와 근거 복구 비율이 그대로다.",
                              f"개발셋 {gd['n']}문항의 평균 보상은 시작 {gd['first_reward']} → {gd['best_step']}걸음 {gd['best_reward']}(최고) → {gi['steps']}걸음 {gd['last_reward']}. "
                              f"학습이 길어질수록 답이 나가지 않은 문항이 {gd['withheld_first']}개에서 {gd['withheld_last']}개로 늘었다.",
                              f"verified EM의 차이는 {g2['derived']['grpo_vs_start']['correct_delta']}문항이다(독립 표본 근사 p {g2['derived']['grpo_vs_start']['unpaired_p']}).",
                              "이 실행 뒤에 학습 스크립트의 결함을 찾았다. 긴 프롬프트의 앞부분이 잘려 들어갔고(학습 프롬프트의 12.2%, 개발셋 64문항 중 16문항), "
                              "미세조정에서는 학습 예제의 15.0%에서 정답이 잘렸다. 이 표는 그 상태로 잰 값이다. 고친 설정으로 다시 한 두 번째 실험은 아래 카드에 있다."],
                    "artifact": src})
        full = load(EXP / "eval" / "exaone_full_vllm_ko_test" / "metrics.json")
        rows = []
        for label, name in (("EXAONE 32B AWQ, 튜닝 없음, 예시 6개", "ref_32b_awq_ko_test"), ("EXAONE 32B AWQ, 도구 호출", "tools_32b_awq_ko_test"),
                            ("EXAONE 1.2B, 튜닝 없음, 도구 호출", "tools_1p2b_ko_test"), ("EXAONE 1.2B, 10,587문항으로 튜닝", "exaone_pool7000_vllm_ko_test")):
            if name in E:
                rows.append([label, p_(em(name)), p_(em(name, "ec")), p_(em(name, "v1", "evidence_repaired_rate")), round(em(name, "v1", "mean_ms_per_example"))])
        if full:
            rows.append(["EXAONE 1.2B, 3,588문항으로 튜닝 (1번 노트북)", pct(full["metrics"]["verified_em"]), "–", pct(full["metrics"]["evidence_repaired_rate"]), round(full["metrics"]["mean_ms_per_example"])])
        out.append({"title": "큰 EXAONE을 튜닝 없이, 그리고 모델이 도구를 고르는 방식 (2차 GPU 실험)", "status": "done",
                    "description": "튜닝하지 않은 EXAONE 32B(4비트 AWQ)를 T4 두 장에 텐서 병렬로 올려 같은 검증기로 채점했다. 한국어 test 699문항.",
                    "columns": ["모델", "verified EM (주어 검사 없음)", "(주어 검사 포함)", "근거 복구 비율", "문항당 시간(ms)"], "rows": rows,
                    "notes": ["튜닝하지 않은 32B는 튜닝한 1.2B보다 낮다. 큰 모델도 답은 맞고 근거 셀이 틀리는 일이 있다.",
                              "같은 32B라도 표를 보여 주고 프로그램 한 줄을 쓰게 하는 쪽이 도구 호출보다 높다.",
                              "튜닝하지 않은 7.8B의 test 평가는 도구 오류로 중단됐고, 1.2B에 예시만 준 기준선은 출력에 남지 않았다. 두 값은 다음 실행에서 채웠다(아래 3차 GPU 실행 카드)."],
                    "artifact": src})
        rows = []
        for label, name, which in (("큰 표 3,072문항: 앞에서부터 (672토큰)", "exaone_pool7000_first672_vllm_unseen_dev", "v1"),
                                   ("큰 표: 질문과 겹치는 행 (672토큰)", "exaone_pool7000_overlap672_vllm_unseen_dev", "v1"),
                                   ("큰 표: 앞에서부터 (1,500토큰)", "exaone_pool7000_first1500_vllm_unseen_dev", "v1"),
                                   ("화학 논문 표 62문항 (한국어+화학 튜닝)", "exaone_kochem_vllm_chem_papers", "ec"),
                                   ("화학 교과서 수작업 32문항", "exaone_kochem_vllm_chem_custom", "ec"),
                                   ("열 번호 형식 300문항 시드 1: 근거 복구 비율", "exaone_colid_s1_vllm_ko_test", "rep"),
                                   ("열 번호 형식 300문항 시드 2: 근거 복구 비율", "exaone_colid_s2_vllm_ko_test", "rep"),
                                   ("plain 형식 300문항 시드 0: 근거 복구 비율", "exaone_rlstart_vllm_ko_test", "rep")):
            if name in E:
                rows.append([label, p_(em(name, "v1", "evidence_repaired_rate") if which == "rep" else em(name, which))])
        if g2.get("ddp"):
            rows.append(["GPU 두 장 학습(DDP), 1,000문항", f"{g2['ddp']['one_gpu_s']}초 → {g2['ddp']['two_gpu_s']}초 ({g2['ddp']['speedup']}배)"])
        out.append({"title": "큰 표, 영어 화학, 열 번호 형식, 학습 병렬 (2차 GPU 실험)", "status": "done",
                    "description": "튜닝한 EXAONE-4.0-1.2B로 잰 나머지 실험이다. 큰 표는 공개 dev 분할에서 학습에 없던 표의 질문이다.",
                    "columns": ["실험", "값"], "rows": rows,
                    "notes": ["행 선별은 EXAONE에서도 통한다. 화학 논문 표에서 EXAONE은 휴리스틱(43.5%)을 넘었다.",
                              "열 번호 형식이 근거 복구를 없애는 효과는 시드 셋에서 같다."],
                    "artifact": src})
    out.extend(gpu3_cards())
    out.append({"title": "재지 못한 것", "status": "prep",
                "description": "풀 전부(약 3.4만 문항) 학습, 큰 모델의 튜닝, 도구 호출 형식으로 튜닝한 모델, 튜닝 모델의 4비트 서빙(bitsandbytes는 그 vLLM 버전에 없는 방식이었다). "
                               "두 번째 강화학습과 대조군의 반복 실행(실험마다 한 번씩이다), 같은 시작 모델에서 둘을 나란히 돌린 실행, 길이 결함을 고친 설정의 전체 데이터 미세조정, 전체 데이터 모델의 확신도 곡선. "
                               "2차 GPU 실험은 결과 파일이 남지 않아 그 실험들의 문항별 분석이 없다."})
    return out


def gpu3_cards() -> list[dict]:
    """Third GPU session (2026-11-15): result files with per-question predictions, re-verified with scripts/replay_check.py."""
    a = load(EXP / "eval" / "rl2_analysis.json")
    pt = load(EXP / "eval" / "paired_tests.json")
    rp = load(EXP / "eval" / "replay_check_gpu3.json")
    nr = load(EXP / "eval" / "no_repair_check.json")
    if not (a and pt and rp and nr):
        return []

    def m(run: str) -> dict:
        return load(EXP / "eval" / run / "metrics.json")["metrics"]

    def pair(name: str) -> str:
        v = pt[name]
        return f"{v['candidate_better']} 대 {v['reference_better']}, p {v['p_display']}"

    src = (f"experiments/eval/ (평가 {rp['replays']}건의 지표와 문항별 예측). 소유자가 2026-11-15에 Kaggle T4 두 장에서 실행. 저장된 모델 출력 {rp['questions_checked']:,}문항을 "
           f"이 저장소의 검증기로 다시 검증했고 판정이 다른 문항은 {rp['questions_that_differ']}개다(scripts/replay_check.py)")
    st, rl = a["start"], a["rl"]
    s1, r1, fp, tr = m(st), m(rl), a["first_pass"], a["training"]
    o_s, o_r = fp["outcomes"]["start"], fp["outcomes"]["rl"]
    wrong = fp["sign_tests"]["wrong_all"]
    cited = a["raw"]["sign_test_cited_gold_cell_lookup"]

    def three(o: dict) -> str:
        return f"{o['correct']} / {o['wrong']} / {o['withheld']}"

    rows = [
        ["verified EM (주어 검사 없음)", pct(s1["verified_em"]), pct(r1["verified_em"]), pair("grpo2_vs_rlstart2_ko_test")],
        ["verified EM (주어 검사 포함)", pct(m(st + "_ec")["verified_em"]), pct(m(rl + "_ec")["verified_em"]), pair("grpo2_vs_rlstart2_ko_test_ec")],
        ["모델이 인용한 셀이 정답 셀과 같은 비율", pct(s1["evidence_cells_exact_raw"]), pct(r1["evidence_cells_exact_raw"]), f"조회 문항 {cited['only_rl']} 대 {cited['only_start']}, p {cited['p_display']}"],
        ["검증기가 근거 셀을 고쳐서 내보낸 비율", pct(s1["evidence_repaired_rate"]), pct(r1["evidence_repaired_rate"]), ""],
        ["근거 복구를 끈 verified EM", pct(nr["runs"][st]["verified_em_replayed"]), pct(nr["runs"][rl]["verified_em_replayed"]), ""],
        ["틀린 답이 나간 문항", o_s["all"]["wrong"], o_r["all"]["wrong"], f"{wrong['only_rl']} 대 {wrong['only_start']}, p {wrong['p_display']}"],
        [f"조회 {o_s['lookup']['n']}문항: 정답 / 틀린 답 / 안 나감", three(o_s["lookup"]), three(o_r["lookup"]), ""],
        [f"계산 {o_s['calc']['n']}문항: 정답 / 틀린 답 / 안 나감", three(o_s["calc"]), three(o_r["calc"]), ""],
        [f"답 없는 질문 {o_s['unanswerable']['n']}개 가운데 알아본 수", o_s["unanswerable"]["correct"], o_r["unanswerable"]["correct"], ""],
        ["수작업 30문항 verified EM (주어 검사 포함)", pct(m("exaone_rlstart2_vllm_ko_custom_ec")["verified_em"]), pct(m("exaone_grpo2_vllm_ko_custom_ec")["verified_em"]), pair("grpo2_vs_rlstart2_ko_custom_ec")],
    ]
    full = m("exaone_full_vllm_ko_test")
    out = [{"title": "EXAONE 강화학습, 두 번째 실험 — 결함을 고친 뒤 (3차 GPU 실행)", "status": "done",
            "description": f"첫 실험과 같은 보상과 손실(소유자 작성)로 {tr['steps']}걸음. 달라진 것은 넷이다. 프롬프트가 잘리지 않는다. 시작 모델(300문항)을 정답이 잘리지 않는 길이로 다시 학습했다. "
                           f"배치를 학습 문항 전체에서 고르게 뽑는다. 개발 문항을 무작위 {tr['dev_first']['n']}개로 늘렸다. 남긴 모델은 개발셋 보상이 가장 높았던 {tr['kept_step']}걸음째다. 한국어 test 699문항.",
            "columns": ["지표", "시작 모델 (300문항 SFT)", f"강화학습 뒤 ({tr['kept_step']}걸음 모델)", "같은 문항 대응 검정 (강화학습 모델만 대 시작 모델만)"], "rows": rows,
            "notes": ["근거 셀 오류가 줄었다. 보상은 정답 셀 표시를 쓰지 않는다. 복구 없이 통과한 정답에 1.0점, 검증기가 근거를 고쳐야 했던 정답에 0.3점을 주는 차이만으로 모델이 답이 든 셀을 인용하는 쪽으로 움직였다.",
                      "계산 문항은 풀게 된 것이 아니다. 두 모델 모두 계산 프로그램을 한 번도 쓰지 않았다. 시작 모델은 셀 값 하나를 답으로 내서 틀린 답이 나갔고, 강화학습 뒤에는 스스로 계산한 수를 답으로 써서 검증기가 내보내지 않는다. 보류가 늘어난 것은 거의 전부 여기서 왔다.",
                      f"개발셋 {tr['dev_first']['n']}문항의 평균 보상은 시작 {tr['dev_first']['mean_reward']} → {tr['kept_step']}걸음 {tr['dev_kept']['mean_reward']}(최고) → {tr['steps']}걸음 {tr['dev_last']['mean_reward']}. 문법 오류는 모든 점검에서 {tr['dev_first']['unparsable']}개다(첫 실험에서는 매번 16개).",
                      f"한계. 한 번 돌렸고 시드가 하나다. 넷을 한꺼번에 바꿨고, 무엇이 효과를 냈는지는 아래 대조군 카드가 가른다. 같은 학습 풀 전체로 미세조정한 모델({pct(full['verified_em'])})이 훨씬 높고 학습도 빠르다"
                      f"({a['cost']['sft_full_data_minutes']}분 대 {a['cost']['rl_200_steps_minutes']}분). 수작업 30문항에서는 차이가 유의하지 않다.",
                      "역할. 보상 함수와 GRPO 손실의 구현, GPU 실행(첫 실험, 두 번째 실험, 대조군)은 소유자가 했다. 첫 실험의 기록에서 결함을 찾아 학습 스크립트를 고친 것, 대조군의 설계, 결과 분석은 AI 도구가 했다."],
            "artifact": src + ". 분석: experiments/eval/rl2_analysis.json (scripts/rl2_analysis.py), paired_tests.json, no_repair_check.json"}]
    c = load(EXP / "eval" / "rl2_control_analysis.json")
    rpc = load(EXP / "eval" / "replay_check_control.json")
    if c and rpc:
        sb, gb = c["start"], c["rl"]
        cs, cr, ct = m(sb), m(gb), c["training"]
        dd = c["main_minus_control"]["first_pass"]

        def arrow(x, y, f=pct):
            return f"{f(x)} → {f(y)}"

        def diff(key: str) -> str:
            v = dd[key]
            return f"{v['questions_changed_more_in_main']} 대 {v['questions_changed_more_in_control']}, p {v['p_display']}"

        plain = str
        co_s, co_r = c["first_pass"]["outcomes"]["start"], c["first_pass"]["outcomes"]["rl"]
        rows = [
            [f"조회 {a['raw']['start']['lookup_questions']}문항에서 인용한 셀이 정답 셀인 문항", arrow(a["raw"]["start"]["lookup_cited_gold_cell"], a["raw"]["rl"]["lookup_cited_gold_cell"], plain),
             arrow(c["raw"]["start"]["lookup_cited_gold_cell"], c["raw"]["rl"]["lookup_cited_gold_cell"], plain) + f" (p {c['raw']['sign_test_cited_gold_cell_lookup']['p_display']})", diff("cited_gold_cell_lookup")],
            ["검증기가 근거 셀을 고쳐서 내보낸 비율", arrow(s1["evidence_repaired_rate"], r1["evidence_repaired_rate"]), arrow(cs["evidence_repaired_rate"], cr["evidence_repaired_rate"]), ""],
            ["verified EM (주어 검사 없음)", arrow(s1["verified_em"], r1["verified_em"]), arrow(cs["verified_em"], cr["verified_em"]) + f" ({pair('grpo2b_vs_rlstart2b_ko_test')})", diff("verified_correct_all")],
            ["틀린 답이 나간 문항", arrow(o_s["all"]["wrong"], o_r["all"]["wrong"], plain), arrow(co_s["all"]["wrong"], co_r["all"]["wrong"], plain), f"p {dd['wrong_answer_all']['p_display']}"],
            ["답이 나가지 않은 문항", arrow(o_s["all"]["withheld"], o_r["all"]["withheld"], plain), arrow(co_s["all"]["withheld"], co_r["all"]["withheld"], plain), f"p {dd['withheld_all']['p_display']}"],
            ["남긴 모델", f"{tr['kept_step']}걸음째", f"{ct['kept_step']}걸음째", ""],
            [f"갱신한 걸음 ({tr['steps']}걸음 중)", tr["updates_applied"], ct["updates_applied"], ""],
            [f"학습 마지막 50걸음의 표본 {ct['phases']['p4']['samples']:,}개 중 답이 나가지 않은 것", f"{tr['phases']['p4']['withheld']:,}", f"{ct['phases']['p4']['withheld']:,}", ""],
            [f"개발 {ct['dev_first']['n']}문항에서 복구 없이 정답: 시작 → 끝", arrow(tr["dev_first"]["correct"], tr["dev_last"]["correct"], plain), arrow(ct["dev_first"]["correct"], ct["dev_last"]["correct"], plain), ""],
        ]
        mix = c["prompt_mix"]
        out.append({"title": "EXAONE 강화학습, 대조군 — 배치 구성만 첫 실험처럼 되돌리면 (2026-11-15 뒤의 세션)", "status": "done",
                    "description": "두 번째 실험에서 무엇이 효과를 냈는지 가르는 실행이다. 학습 프롬프트를 조회·계산·보류 질문에서 같은 수로 뽑는 것(첫 실험의 방식)만 다르고 나머지는 두 번째 실험과 같다. "
                                   "새 세션에는 앞 실험의 시작 모델 가중치가 없어서 시작 모델을 같은 설정으로 다시 학습해 따로 평가했다. 그래서 두 실험을 각자의 시작 모델과 견주고, 마지막 열은 문항마다 두 실험의 변화가 다른 문항에서 부호 검정을 한 것이다.",
                    "columns": ["지표", "두 번째 실험 (실제 비율): 시작 → 뒤", "대조군 (같은 수): 시작 → 뒤", "변화의 차이 (두 번째 실험 쪽 대 대조군 쪽)"], "rows": rows,
                    "notes": ["근거 셀의 개선은 배치를 실제 문항 비율로 뽑았을 때만 나타났다. 대조군은 프롬프트가 잘리지 않았는데도 첫 실험처럼 무너졌다. 50걸음을 지나면서 모델이 거의 모든 질문에 검증되지 않는 답을 썼다.",
                              "프롬프트 잘림을 고친 것만으로는 효과가 나지 않았다. 첫 실험이 듣지 않은 까닭은 프롬프트 잘림이 아니라 배치 구성이었다. 프롬프트 수정이 따로 필요했는지는 재지 않았다.",
                              "verified EM의 증가폭은 두 실험이 유의하게 다르지 않다. 두 번째 실험이 분명히 나은 것은 근거 셀과 틀린 답의 수다.",
                              f"해석. 300문항 모델은 계산 프로그램과 abstain을 쓰지 않는다. 그런 질문에서 받을 수 있는 가장 높은 점수는 0점이고, 그 길은 검증되지 않는 답을 쓰는 것이다. 같은 수로 뽑으면 배치의 {pct(mix['balanced_share_without_lookup'])}가 그런 질문이고, 실제 비율로 뽑으면 {pct(mix['natural']['lookup'])}가 조회 질문이다.",
                              f"한계. 두 실험 모두 한 번씩이고 세션과 시작 모델이 다르다(시작 모델의 verified EM {pct(s1['verified_em'])} 대 {pct(cs['verified_em'])}). 같은 시작 모델에서 둘을 나란히 돌린 실행은 없다."],
                    "artifact": f"experiments/eval/rl2_control_analysis.json (scripts/rl2_analysis.py), experiments/exaone_grpo2b/. 소유자가 Kaggle T4 두 장에서 실행. 평가 {rpc['replays']}건을 다시 검증했고({rpc['questions_checked']:,}문항) 판정이 다른 문항은 {rpc['questions_that_differ']}개다"})
    g2 = load(EXP / "gpu2_2026-11-14" / "recovered.json")
    big = g2["evals"]["ref_32b_awq_ko_test"]["v1"]["metrics"] if g2 else None
    rows = []
    for label, run in (("EXAONE 4.0 1.2B, 튜닝 없음, 예시 6개", "ref_1p2b_ko_test"), ("EXAONE 3.5 7.8B AWQ, 튜닝 없음, 예시 6개", "ref_7p8b_awq_ko_test")):
        x = m(run)
        rows.append([label, pct(x["verified_em"]), pct(m(run + "_ec")["verified_em"]), pct(x["evidence_cells_exact_raw"]), pct(x["evidence_repaired_rate"]), round(x["mean_ms_per_example"])])
    if big:
        rows.append(["EXAONE 4.0 32B AWQ, 튜닝 없음, 예시 6개 (지난 실행)", pct(big["verified_em"]), pct(g2["evals"]["ref_32b_awq_ko_test"]["ec"]["metrics"]["verified_em"]),
                     pct(big["evidence_cells_exact_raw"]), pct(big["evidence_repaired_rate"]), round(big["mean_ms_per_example"])])
    x = m("tools_1p2b_ko_test")
    rows.append(["EXAONE 4.0 1.2B, 튜닝 없음, 도구 호출", pct(x["verified_em"]), pct(m("tools_1p2b_ko_test_ec")["verified_em"]), pct(x["evidence_cells_exact_raw"]), pct(x["evidence_repaired_rate"]), round(x["mean_ms_per_example"])])
    rows.append(["EXAONE 4.0 1.2B, 3,587문항으로 튜닝 (1번 노트북)", pct(full["verified_em"]), pct(m("exaone_full_vllm_ko_test_ec")["verified_em"]), pct(full["evidence_cells_exact_raw"]), pct(full["evidence_repaired_rate"]), round(full["mean_ms_per_example"])])
    out.append({"title": "튜닝하지 않은 EXAONE, 크기별. 그리고 도구 호출과 프로그램 제안 (3차 GPU 실행)", "status": "done",
                "description": "첫 실행에서 빠졌던 두 값(예시만 준 1.2B, 7.8B의 test)을 채웠다. 같은 프롬프트, 같은 검증기, 한국어 test 699문항.",
                "columns": ["모델", "verified EM (주어 검사 없음)", "(주어 검사 포함)", "인용 셀 정확", "근거 복구 비율", "문항당 시간(ms)"], "rows": rows,
                "notes": [f"튜닝 없이는 모델이 클수록 높지만 셋 다 튜닝한 1.2B보다 낮다. 7.8B 대 1.2B는 같은 문항 대응으로 {pair('ref_7p8b_vs_ref_1p2b_ko_test')}.",
                          "크기만 바꾼 비교가 아니다. 7.8B는 3.5 세대이고, 7.8B와 32B는 4비트 AWQ이며, 32B는 다른 세션의 값이라 대응 검정을 할 수 없다.",
                          "인용 셀을 정확히 짚는 것은 크기보다 학습에 달려 있었다.",
                          f"같은 1.2B에서 도구를 고르게 하는 쪽이 프로그램을 한 번 제안하게 하는 쪽보다 낮다(도구 쪽만 맞힘 대 프로그램 쪽만 맞힘: {pair('tools_vs_program_1p2b_ko_test')})."],
                "artifact": src})
    return out


def gpu_sections() -> list[dict]:
    """GPU runs by the repository owner on Kaggle / Colab T4 (files taken from the uploaded result archives)."""
    out = []
    rows = []
    for label, tag in (("LoRA 300개 · vLLM, GPU 1장", "vllm"), ("LoRA 300개 · vLLM 텐서 병렬 TP=2, GPU 2장", "vllm_tp2"), ("LoRA 300개 · SGLang + T4 우회 모듈, GPU 1장", "sglang"),
                       ("LoRA 전체 데이터 · vLLM, GPU 1장", "full_vllm"), ("LoRA 전체 데이터 · vLLM TP=2, GPU 2장", "full_vllm_tp2"), ("LoRA 전체 데이터 · SGLang + T4 우회 모듈", "full_sglang")):
        for c in (1, 8, 32):
            b = load(EXP / "bench" / f"engine_{tag}_c{c}.json")
            if b:
                rows.append([label, b["concurrency"], b["n"], b["throughput_req_per_s"], b["p50_ms"], b["p95_ms"], pct(b["parse_ok_rate"])])
    if rows:
        out.append({"title": "vLLM / SGLang 서빙 — EXAONE-4.0-1.2B LoRA (Kaggle Tesla T4, 저장소 소유자 실행)", "status": "done",
                    "description": "mT5는 두 엔진이 지원하지 않아(experiments/serving/engine_support.json) 같은 데이터로 EXAONE-4.0-1.2B를 LoRA 튜닝해 병합한 모델을 띄웠다. "
                                   "OpenAI 호환 API로 ko test 앞 64문항을 동시 요청 1/8/32로 보낸 왕복 지연이다. SGLang은 T4용 커널이 없어 우회 모듈로 돌렸으므로 느리다. 두 엔진의 속도 비교가 아니다.",
                    "columns": ["구성", "동시 요청 수", "n", "처리량 (요청/s)", "p50 ms", "p95 ms", "프로그램 파싱 성공"], "rows": rows,
                    "notes": ["vLLM과 SGLang은 같은 답을 냈다(ko test 699문항 중 1문항 차이).", "정확도는 위 한국어 표 QA 표의 EXAONE 행에 있다."],
                    "artifact": "experiments/bench/engine_*.json, experiments/eval/PROVENANCE_exaone.md, experiments/serving/sglang_t4_failure.md"})
    else:
        out.append({"title": "vLLM / SGLang 서빙", "status": "prep", "description": "EXAONE/vLLM 산출물 없음. scripts/serving/*.sh, notebooks/gpu_experiments.ipynb 준비."})
    g1, g2 = load(EXP / "bench" / "pp_single_gpu.json"), load(EXP / "bench" / "pp_2stage_gpu.json")
    if g1 and g2:
        same = g1.get("outputs") == g2.get("outputs")
        rows = [["단일 GPU(전체 모델)", g1["device"], f"{g1['params_total']:,}", g1["throughput_ex_per_s"], f"{g1['mem_mb']:.0f}", "-"]]
        for st in g2["stages"]:
            rows.append([f"파이프라인 rank{st['rank']} ({st['stage']})", st["device"], f"{st['stage_params']:,}", g2["throughput_ex_per_s"] if st["rank"] == 0 else "", f"{st['mem_mb']:.0f}", "출력 동일" if same else "출력 다름"])
        out.append({"title": "멀티 GPU Model Parallelism — 2-스테이지 파이프라인 (Kaggle Tesla T4 ×2, NCCL, 저장소 소유자 실행)", "status": "done",
                    "description": "mT5-small을 rank0=인코더, rank1=디코더+lm_head로 두 GPU에 나눠 실행했다. 출력은 단일 GPU와 같고 장치당 메모리가 나뉜다. "
                                   "단일 GPU 측정이 세션마다 달라(네 세션 5.9~14.6 예제/s) 처리량 이득은 주장하지 않는다. 처리량이 오른 것은 vLLM 텐서 병렬(위 표의 TP=2)이다.",
                    "columns": ["구성", "장치", "파라미터", "처리량 (예제/s)", "메모리 MB", "검증"], "rows": rows,
                    "artifact": "experiments/bench/pp_*_gpu*.json"})
    return out


def main() -> None:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        commit = "unknown"
    env = load(ROOT / "docs" / "research" / "environment.json") or {}
    sections = measurement_sections() + supplement_sections()
    cols = ["플래너 / 모델", "n", "verified EM", "lookup EM", "calc EM", "근거 셀 일치(최종)", "근거 셀 일치(모델 인용)", "보류 재현율", "오보류율", "파싱 실패", "ms/예제"]
    models = [("휴리스틱(어휘 겹침) 기준선", "heuristic", False), ("mT5-small 기본(변환만)", "base", False), ("SFT stage1(표)", "sft_ko", False),
              ("SFT stage2(+본문, 1차)", "sft_ko2", False), ("GRPO RL v2(1차)", "rl_ko", False), ("화학 SFT(1차 최종)", "sft_chem", False),
              ("[2차] 화학 SFT v2", "sft_chem2", False), ("[2차] GRPO RL v3 (mT5 최종)", "rl_v3", False), ("[2차] RL v3 + 검증기 v2(개체 일치 검사)", "rl_v3", True),
              ("[GPU] EXAONE-4.0-1.2B LoRA 300개 (Kaggle T4, vLLM)", "exaone_vllm", False),
              ("[GPU] 같은 300개, 표 입력에 열 번호(colid)", "exaone_colid_vllm", False),
              ("[GPU] EXAONE-4.0-1.2B LoRA 전체 데이터 (Kaggle T4, vLLM)", "exaone_full_vllm", False),
              ("[GPU] EXAONE 전체 데이터 + 검증기 v2(개체 일치 검사)", "exaone_full_vllm", True)]
    for title, suffix, desc in [("한국어 표 QA — 독립 test (KorWikiTQ 표 단위 분할 539 + 합성 160)", "ko_test", "표가 학습 분할과 겹치지 않는 539문항(원 데이터, lookup) + 합성 160문항(계산·보류)."),
                                ("한국어 표 QA — 수작업 평가 30문항", "ko_custom", "셀·계산·본문+표·단위/기간·보류 범주. 표본이 작아 참고치."),
                                ("영어 화학 문서 — 수작업 평가 32문항 (test 분할 문서)", "chem_custom", "물질 상수·실험 조건·수치/단위·본문·보류 범주."),
                                ("본문 답변·근거 없음 — 실제 표 옆 KorQuAD 150문항", "text2_test", "본문 100문항(답이 본문에만 있음) + 근거 없음 50문항. 표는 test 분할의 표(학습에 쓰이지 않음). 2차에서 새로 만든 평가셋.")]:
        rows = [r for r in (eval_row(n, f"{k}_{suffix}{'_ec' if ec else ''}") for n, k, ec in models) if r]
        done = any(r[0] != models[0][0] for r in rows)
        sec = {"title": title, "description": desc, "columns": cols, "rows": rows, "status": "done" if done else "prep",
               "artifact": f"experiments/eval/*_{suffix}/metrics.json"}
        cats = {}
        for n, k, ec in models:
            m = load(EXP / "eval" / f"{k}_{suffix}{'_ec' if ec else ''}" / "metrics.json")
            if m and m["metrics"].get("by_category"):
                cats[n] = m["metrics"]["by_category"]
        if cats:
            catnames = sorted({c for v in cats.values() for c in v})
            sec["notes"] = [f"{n}: " + ", ".join(f"{c} {pct(v[c]['verified_em'])} (n={v[c]['n']})" for c in catnames if c in v) for n, v in cats.items()]
        sections.append(sec)
    # training runs
    rows = []
    for name, d in [("SFT stage1 (ko)", "sft_ko"), ("SFT stage2 (ko+text, 1차)", "sft_ko2"), ("SFT chem (1차)", "sft_chem"), ("GRPO RL v2 (1차)", "rl_ko"),
                    ("[2차] SFT stage2 재학습", "sft_ko3"), ("[2차] 표 조회 보강 epoch", "sft_ko4"), ("[2차] SFT chem v2", "sft_chem2"), ("[2차] GRPO RL v3", "rl_v3")]:
        s = load(EXP / d / "summary.json") or load(EXP / d / "config.json")
        if not s:
            continue
        ev = (s.get("dev_history") or [{}])[-1]
        rows.append([name, s.get("n_train", s.get("n_train_prompts", "-")), s.get("steps", "-"), f"{s.get('wall_s', 0) / 60:.0f} min" if s.get("wall_s") else "(진행 중)",
                     f"{s['hardware']['threads']} threads CPU" if s.get("hardware") else "-", pct(s.get("best_dev_verified_em")), str(ev.get("step", "-"))])
    for name, d in [("[GPU] EXAONE-4.0-1.2B LoRA 300개", "exaone_lora"), ("[GPU] EXAONE-4.0-1.2B LoRA 전체 데이터", "exaone_lora_full")]:
        t = load(EXP / d / "train_info.json")
        if t:
            rows.append([name, t["n_examples"], t["steps"], f"{t['wall_s'] / 60:.0f} min" if t.get("wall_s") else "(기록 없음)", t.get("gpu", "Tesla T4") + " (Kaggle, 소유자 실행)", "-", "-"])
    sections.append({"title": "학습 실행 기록", "columns": ["실행", "학습 예제", "스텝", "소요", "하드웨어", "best dev verified EM", "best step"], "rows": rows,
                     "status": "done" if rows else "prep", "artifact": "experiments/*/summary.json, train_log.jsonl",
                     "conditions": {"모델": "mT5-small 300M (gs://t5-data 체크포인트를 직접 변환)", "최적화기": "AdamW, 선형 워밍업 5% + 선형 감쇠, clip 1.0", "입력": "question + title + context(≤300자) + 표 직렬화 ≤512 토큰"}})
    for rl_dir, rl_title in (("rl_ko", "강화학습(GRPO 방식) 1차 v2 보상 추이"), ("rl_v3", "강화학습(GRPO 방식) 2차 v3 보상 추이 (한국어+화학+본문 프롬프트)")):
        rl = load(EXP / rl_dir / "summary.json")
        rl_log = EXP / rl_dir / "train_log.jsonl"
        if rl_log.exists():
            steps = [json.loads(line) for line in rl_log.read_text(encoding="utf-8").splitlines() if line.strip() and '"eval"' not in line]
            if steps:
                first, last = steps[: max(1, len(steps) // 5)], steps[-max(1, len(steps) // 5):]
                avg = lambda xs, k: sum(x[k] for x in xs) / len(xs)  # noqa: E731
                sections.append({"title": rl_title, "status": "done",
                                 "description": "그룹 정규화 이점으로 정책 경사 업데이트. 보상은 검증기 기반(정답·근거 셀·보류 적절성).",
                                 "columns": ["구간", "평균 보상", "정답률(샘플)", "보류율(샘플)", "파싱 성공", "KL"],
                                 "rows": [[f"처음 {len(first)} step", f"{avg(first, 'reward_mean'):.3f}", pct(avg(first, 'correct_rate')), pct(avg(first, 'abstain_rate')), pct(avg(first, 'parse_ok')), f"{avg(first, 'kl'):.4f}"],
                                          [f"마지막 {len(last)} step", f"{avg(last, 'reward_mean'):.3f}", pct(avg(last, 'correct_rate')), pct(avg(last, 'abstain_rate')), pct(avg(last, 'parse_ok')), f"{avg(last, 'kl'):.4f}"]],
                                 "conditions": (rl or {}).get("args", {}), "artifact": f"experiments/{rl_dir}/train_log.jsonl"})
    b = load(EXP / "bench" / "inference.json")
    if b:
        sections.append({"title": "추론 최적화 (CPU 실측)", "status": "done", "conditions": b["meta"],
                         "columns": ["설정", "p50 ms", "p95 ms", "처리량 (예제/s)", "최대 RSS GB", "모델 파일 MB", "fp32 bs=1과 출력 일치"],
                         "rows": [[r["config"], r["p50_ms"], r["p95_ms"], r["throughput_ex_per_s"], r.get("peak_rss_gb", "–"), r.get("state_dict_mb", "–"), pct(r["agreement_with_fp32_bs1"])] for r in b["results"]],
                         "artifact": "experiments/bench/inference.json"})
    else:
        sections.append({"title": "추론 최적화 (CPU 실측)", "status": "prep", "description": "src/tabletrace/bench/inference.py — fp32/int8/배치/KV 캐시 비교. 아직 실행 전."})
    for r2_file, r2_title in (("inference_r2.json", "추론 최적화 2차 — 최종 모델(RL v3)의 int8 범위별 측정 (CPU)"),
                              ("inference_r2b.json", "추론 최적화 2차 — fp32 대 lm_head만 int8 (같은 측정 안에서 비교)")):
        b2 = load(EXP / "bench" / r2_file)
        if not b2:
            continue
        sections.append({"title": r2_title, "status": "done", "conditions": b2["meta"],
                         "description": "int8 = 모든 Linear(lm_head 포함), int8-<범위> = 일부 Linear만. 정확도(ko test verified EM)는 README §10.1과 보고서 §8에 있다.",
                         "columns": ["설정", "p50 ms", "p95 ms", "처리량 (예제/s)", "최대 RSS GB", "모델 파일 MB", "fp32 bs=1과 출력 일치"],
                         "rows": [[r["config"], r["p50_ms"], r["p95_ms"], r["throughput_ex_per_s"], r.get("peak_rss_gb", "–"), r.get("state_dict_mb", "–"), pct(r["agreement_with_fp32_bs1"])] for r in b2["results"]],
                         "artifact": f"experiments/bench/{r2_file}"})
    pp1, pp2 = load(EXP / "bench" / "pp_single.json"), load(EXP / "bench" / "pp_2stage.json")
    if pp1 and pp2:
        same = pp1.get("outputs") == pp2.get("outputs")
        rows = [["단일 프로세스(전체 모델)", pp1["device"], f"{pp1['params_total']:,}", f"{pp1['throughput_ex_per_s']}", f"{pp1['mem_mb']:.0f}", "-"]]
        for st in pp2["stages"]:
            rows.append([f"파이프라인 rank{st['rank']} ({st['stage']})", st["device"], f"{st['stage_params']:,}", f"{pp2['throughput_ex_per_s']}" if st["rank"] == 0 else "", f"{st['mem_mb']:.0f}", "출력 동일" if same else "출력 다름"])
        sections.append({"title": "멀티 GPU Model Parallelism — 2-스테이지 파이프라인 (CPU gloo 기능 검증)", "status": "done",
                         "description": "rank0=인코더, rank1=디코더+lm_head로 모델을 분할. 개발 환경에는 GPU가 없어 먼저 CPU 2프로세스(gloo)로 분할·통신·출력 동일성을 검증했다. GPU 실측은 아래 항목에 있다.",
                         "columns": ["구성", "장치", "파라미터", "처리량 (예제/s)", "메모리 MB", "검증"], "rows": rows,
                         "notes": ["동일 입력에 대해 단일 프로세스와 2-스테이지의 생성 결과가 " + ("완전히 일치" if same else "일치하지 않음 (확인 필요)"),
                                   "GPU 실행 명령: torchrun --nproc_per_node=2 -m tabletrace.bench.pipeline_parallel --backend nccl (docs/experiments/parallel.md)"],
                         "artifact": "experiments/bench/pp_*.json"})
    else:
        sections.append({"title": "멀티 GPU Model Parallelism", "status": "prep", "description": "src/tabletrace/bench/pipeline_parallel.py 준비, 실행 전."})
    sections += gpu_sections()
    data = {"generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "commit": commit,
            "summary": "모든 수치는 이 저장소의 experiments/ 산출물에서 그대로 가져왔다. CPU 실험(mT5-small 학습·평가·양자화)은 4 vCPU Intel Xeon 2.10GHz, 15 GB RAM, GPU 없는 개발 환경에서 실행했다. "
                       "[GPU] 표시가 있는 실험(EXAONE LoRA, vLLM·SGLang 서빙, 멀티 GPU)은 저장소 소유자가 Kaggle·Colab의 Tesla T4에서 실행해 결과 파일을 받은 것이다. "
                       "해석과 한계는 저장소의 README와 docs/REPORT.md에 있다." + (" " + json.dumps(env, ensure_ascii=False) if env else ""),
            "sections": sections}
    out = ROOT / "console" / "data" / "research.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out, "sections:", [s["title"][:30] + " " + s["status"] for s in sections])


if __name__ == "__main__":
    main()
