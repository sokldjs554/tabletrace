# 강화학습(GRPO 방식) 예비 실험 — 설계

결과: README §9.4 / docs/REPORT.md §7. 코드: `src/tabletrace/training/rl_grpo.py`.

## 목표

정답만이 아니라 **올바른 근거 셀·연산·보류 판단**을 함께 내는 출력에 보상을 주어, SFT 모델이 검증기를 통과하는 프로그램을 더 자주 내도록 한다.

## 왜 GRPO 방식인가

- 보상이 결정적·검증 가능(정답 EM, 셀 일치, 계산 일치, 보류 적절성)하므로 보상 모델이 필요 없다.
- 가치 함수(critic) 없이 같은 프롬프트의 샘플 그룹 평균을 베이스라인으로 쓰므로 300M 모델·CPU에서도 돌아간다.
- TRL의 GRPOTrainer는 causal LM 기준으로 알려져 있어 mT5(encoder-decoder)로 시험하지 않고 같은 수식을 직접 구현했다(TRL을 mT5에 적용해 보지는 않았다).

## 알고리즘 (실제 구현)

1. 프롬프트 4개(lookup / calc / abstain / text 풀을 번갈아) × 샘플 G=4, temperature 1.0, top-p 1.0.
2. 보상 r(샘플) — `reward()`: 파싱 실패 −1.0; 답 있는 문항에서 정답 +1.0, 근거 셀 정확 +0.5(부분 +0.25), 연산 일치 +0.2, 모델 답 텍스트≠셀 −0.3, 보류 −0.3, 검증 차단 −0.3; 답 없는 문항에서 보류 +1.0, 답하면 −0.8.
3. 이점 A = (r − 그룹 평균) / (그룹 표준편차 + 1e-4).
4. 손실 = −Σ A·log π(토큰) / 토큰 수 + β·KL_k3(π‖π_SFT), β=0.02. on-policy 1회 업데이트(중요도 비율 없음). AdamW lr 1e-5, clip 1.0.
5. 60 step, 20 step마다 dev(245) verified EM 평가, best 저장.

## 기록하는 것

`experiments/rl_ko/train_log.jsonl`: step별 평균 보상·표준편차·그룹 분산 0 비율·정책 손실·KL·파싱 성공률·샘플 보류율·정답률·연산 분포·프롬프트 종류. `summary.json`: 조건·하드웨어·시간·dev 추이.

## 보상 해킹 점검

- 샘플 보류율이 올라가면서 정답률이 떨어지는지(보류로 점수 따기).
- 연산 분포가 한 종류로 쏠리는지.
- 파싱 성공률이 유지되는지(형식 붕괴).
- test에서 `false_abstain_rate`, `abstain_recall`, `verifier_corrections`를 SFT와 비교.

규모(60 step × 16 샘플 = 960 샘플)가 작아 **예비 실험**이며, 통계적 유의성을 주장하지 않는다.
