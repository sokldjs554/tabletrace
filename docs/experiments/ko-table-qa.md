# 한국어 표 QA 실험 — 설정과 산출물 위치

결과 표는 README §9.1 / docs/REPORT.md §5 (`scripts/render_results.py`가 산출물에서 생성). 이 문서는 **무엇을 어떻게 돌렸는지**를 적는다.

## 과제 정의

입력: 질문 + 표 제목 + 본문 스니펫(≤300자) + 표 직렬화(헤더, `r{i}: 셀 | 셀 …`). 출력: 프로그램 한 줄(`op / cells / answer`). 정답은 **검증기를 통과한 최종 답변 또는 보류**가 gold와 일치할 때(verified EM).

## 데이터

| 세트 | 출처 | 건수 | 용도 |
|---|---|---:|---|
| train | KorWikiTQ 표 단위 재분할(900표) + 합성 계산/보류 960 | 2,694 + 960 (512 토큰 초과로 정답 행이 잘린 223건 제외 → 3,431) | stage 1 SFT |
| stage2_train | train 600 + 합성 300 + KorQuAD 텍스트 700 | 1,600 | stage 2 SFT (`op: text`) |
| dev | 60표 180문항 + 합성 65 (+ 텍스트 100) | 245 / 345 | 체크포인트 선택 |
| test | 180표 539문항 + 합성 160 | 699 | 독립 평가 |
| custom_eval | 수작업 30 | 30 | 범주 평가 |

## 모델·학습 조건

- mT5-small (300,176,768 파라미터), `models/mt5-small-base` (GCS 체크포인트 직접 변환).
- stage 1: AdamW lr 3e-4, warmup 5 %, 선형 감쇠, batch 8, 2 epoch(858 step), max_in 512, max_out 64, dropout 0.1, grad clip 1.0, seed 0, CPU 4 스레드.
- stage 2: stage 1 best에서 lr 1.5e-4, 1 epoch(200 step).
- 로그: `experiments/sft_ko/train_log.jsonl`(10 step마다 loss·lr·RSS), `summary.json`(epoch별 dev 지표, wall time, 하드웨어).

## 평가 명령

`scripts/train/README.md` §5. 결과: `experiments/eval/{heuristic,base,sft_ko,sft_ko2,rl_ko,sft_chem}_ko_{test,custom}/metrics.json`, 문항별 `predictions.jsonl`(원문 출력·예측 셀·검사 결과 포함).

## 읽는 법

- `verified_em`이 핵심. `raw_answer_em_answerable`과의 차이가 검증기의 기여(모델 답을 셀/계산값으로 교정하거나 차단).
- `false_abstain_rate`가 높으면 지나치게 보수적, `abstain_recall`이 낮으면 근거 없는 답을 냄.
- `truncated_gold_rate`: 512 토큰 예산 때문에 정답 행이 입력에서 잘린 비율(모델이 맞힐 수 없는 문항).

## 2차 추가 평가

- `text2_test`: 실제 표 옆에 본문 100문항 + 근거 없음 50문항(`scripts/data/build_text_v2.py`). 1차 모델은 `op: text`를 0문항에서 냈다. 지표: `analysis.json`의 `text_answers`(선택률·정답 수), `abstain_breakdown`(직접 보류 vs 검증기가 막은 보류), `selective`(답한 문항의 정밀도·오답 비율).
- 검증기 v2(개체 일치 검사)와 v1의 비교는 같은 모델 출력을 `--replay-from`으로 다시 검증해 얻는다(`*_ec`). 정답 프로그램이 검사에 걸리는 비율(`gold_subject_fail_rate`)이 검사의 오탐률이다.
- 모델 간 차이는 `scripts/paired_tests.py`의 문항별 쌍 비교(정확 부호 검정)로 읽는다. 699문항에서 몇 %p 차이는 표본 잡음 안에 있을 수 있다.
