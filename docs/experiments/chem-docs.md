# 영어 화학 문서 실험 — 설정과 산출물 위치

결과 표: README §9.2 / docs/REPORT.md §6.

## 과제

OpenStax *Chemistry 2e* 문서(본문 문단 + 실험 데이터 표)에서 물질·실험 조건·측정값·단위를 묻는 질문에 셀 또는 문장을 근거로 답하고, 없으면 보류. 수치 답에는 셀의 단위(kPa, K, °C, L/mol, g/mol)가 붙는다.

## 데이터

- 문서 56개(표 113, 문단 3,780), 문서 단위 분할 train 40 / dev 5 / test 11 (`data/chem/split.json`).
- 학습: 합성 lookup 420 / diff 120 / ratio 60 / sum 60 / abstain 160 (train 분할 표) + 한국어 표 150 재생 = 970.
- 평가: 수작업 32문항(test 분할 문서; cell 10, calc 7, text_table 6, unit_period 5, abstain 5) + 합성 dev 80(참고).

## 모델·조건

stage 2 한국어 모델에서 계속 학습: lr 1.5e-4, batch 8, 2 epoch(약 243 step). "튜닝 전"은 같은 입력 형식의 stage 2 모델(영어 화학 데이터를 보지 않음), "튜닝 후"는 화학 SFT 모델. 둘 다 같은 32문항·같은 검증기·같은 CPU에서 평가.

## 추가로 보는 것

- 단위 오류율(`unit_error_rate`): 계산 결과의 단위가 gold와 다른 비율.
- 텍스트 근거(`text_table` 범주): 답이 본문 문장에 있는지 검증기가 확인(`answer_in_passage`).
- 보류: 표·본문에 없는 상수(argon의 van der Waals 상수, HOCl의 끓는점 등).
