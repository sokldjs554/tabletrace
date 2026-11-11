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
            rows.append([label, f"{m['train_questions']:,}", m["steps"], ci(t["cell"]), pct(t["row"]["rate"]), pct(t["col"]["rate"]), f"{m['minutes']:.0f}분"])
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
                    "columns": ["설정", "학습 질문", "step", "셀 정확도 (95% 구간)", "행 정확도", "열 정확도", "학습 시간"], "rows": rows, "notes": notes,
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
        for label, run in [("mT5-small 최종", "rl_v3_conf_ko_test")] + [(k, k) for k in rc["runs"] if k != "rl_v3_conf_ko_test"]:
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
                    "notes": ["작은 모델에서는 확신도가 약한 신호다. 가장 확신하는 답만 내보내도 위험이 크게 줄지 않는다.", "EXAONE은 GPU 평가에서 로그 확률을 저장해야 그릴 수 있다."],
                    "artifact": "experiments/eval/risk_coverage.json (scripts/risk_coverage.py)"})
    out.append({"title": "준비만 한 것 — GPU에서 돌려야 하는 실험", "status": "prep",
                "description": "notebooks/gpu_experiments_2.ipynb: 튜닝하지 않은 EXAONE 7.8B·32B 참고선, 모델이 도구를 스스로 고르는 방식(Tool Calling), 학습 데이터 확대(약 1만, 3.4만 문항), "
                               "멀티 GPU 학습(DDP) 속도, EXAONE 강화학습(GRPO), 4비트 서빙, 열 번호 형식의 전체 데이터·시드 추가, 화학, 큰 표. "
                               "스크립트는 작은 무작위 모델과 모의 서버로 CPU에서 시험했다. 강화학습의 보상과 손실은 저장소 소유자가 직접 쓰도록 명세와 테스트만 두었다(docs/rewrite/06_training_code.md)."})
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
