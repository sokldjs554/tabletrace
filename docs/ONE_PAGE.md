# TableTrace 한 장 요약

**무엇인가.** 한국어 표 질의응답에서 모델이 답과 **근거 셀**을 함께 내고, 규칙으로 된 검증기가 그 셀로 답을 다시 확인해 맞지 않으면 답을 보류하는 연구 프로젝트다. 데이터는 LG AI연구원이 공개한 KorWikiTQ이고, 공고의 테이블이해(Table MRC) 업무에 맞췄다. 저장소 <https://github.com/sokldjs554/tabletrace>, 데모 <https://sokldjs554.github.io/tabletrace/>.

## 잰 것 (한국어 시험 699문항, 표 단위로 다시 나눈 분할)

| 측정 | 결과 |
|---|---|
| 답은 맞는데 근거 셀이 틀린 비율 | mT5-small <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.strict.rate:pct -->52.6<!-- /num -->%, EXAONE-4.0-1.2B를 300문항으로 튜닝 <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.strict.rate:pct -->65.2<!-- /num -->%, 전체 데이터로 튜닝 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.strict.rate:pct -->1.3<!-- /num -->%. 표 입력에 열 번호만 붙여도 300문항 설정에서 <!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.strict.rate:pct -->3.2<!-- /num -->% |
| 검증기가 줄이는 오답 | EXAONE 전체 데이터: 그대로 내보내면 오답 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.raw.wrong_answer_rate.rate:pct -->21.6<!-- /num -->%, 검증기를 거치면 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_subject_check.wrong_answer_rate.rate:pct -->12.0<!-- /num -->%. 답하는 비율은 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.raw.coverage:pct -->95.3<!-- /num -->% → <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_subject_check.coverage:pct -->88.7<!-- /num -->% |
| 정답률(verified EM) | 어휘 겹침 기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->%, mT5-small <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->%(기준선 미달), EXAONE 전체 데이터 LoRA <!-- num:experiments/eval/exaone_full_vllm_ko_test/metrics.json:metrics.verified_em:pct -->84.3<!-- /num -->% |
| 공개 분할의 표 겹침 | 공개 dev 질문의 <!-- num:data/ko/official_split_profile.json:dev_on_train_table.rate:pct -->42.9<!-- /num -->%가 train에도 있는 표를 묻는다. 표 단위로 다시 나눴다 |
| 강화학습 | 점수를 올리지 못했다. 검증기가 거부한 쓰레기 출력이 보류와 같은 보상을 받던 허점을 찾아 고쳤다 |
| 큰 표(공개 dev, 학습에 없던 표 <!-- num:experiments/eval/large_tables.json:set.questions:int -->3,072<!-- /num -->문항) | 표가 입력에 안 들어갈 때 질문과 겹치는 행을 고르면 mT5-small <!-- num:experiments/eval/large_tables.json:runs.mt5_first512.all.verified_em.rate:pct -->29.0<!-- /num -->% → <!-- num:experiments/eval/large_tables.json:runs.mt5_overlap512.all.verified_em.rate:pct -->37.8<!-- /num -->% |
| 구조 이해 표 인코더 | 사전학습 모델(KoELECTRA-small, mT5-small의 인코더)에 행·열 임베딩과 셀 선택 헤드를 붙이고 표 사전학습(바뀐 셀 찾기)까지 구현해 CPU에서 학습. 조회 539문항에서 답이 든 셀을 맞히는 비율이 최고 <!-- num:experiments/encoder/summary.json:variants.ko_structure_pool.test.cell.rate:pct -->59.7<!-- /num -->%(생성 mT5-small의 인용 셀 정확도 <!-- num:experiments/encoder/summary.json:generative.mt5_final.cited_gold_cell.rate:pct -->22.8<!-- /num -->%, 전체 데이터 EXAONE <!-- num:experiments/encoder/summary.json:generative.exaone_full.cited_gold_cell.rate:pct -->85.0<!-- /num -->%). 학습 질문을 늘린 것만 유의하게 도움이 됐고(p <!-- num:experiments/encoder/summary.json:paired.pool_vs_main.p_display -->0.013<!-- /num -->), 행·열 임베딩과 표 사전학습의 효과는 검출되지 않았다 |
| 인코더를 검증의 두 번째 의견으로 | EXAONE 전체 데이터의 조회 답: 위험 <!-- num:experiments/encoder/agreement.json:encoders.ko_structure_pool.runs.exaone_full_vllm_ko_test.verifier.risk.rate:pct -->13.3<!-- /num -->%(응답률 <!-- num:experiments/encoder/agreement.json:encoders.ko_structure_pool.runs.exaone_full_vllm_ko_test.verifier.coverage.rate:pct -->98.0<!-- /num -->%) → 인코더가 같은 행을 고를 때만 답하면 <!-- num:experiments/encoder/agreement.json:encoders.ko_structure_pool.runs.exaone_full_vllm_ko_test.verifier_and_same_row.risk.rate:pct -->8.1<!-- /num -->%(응답률 <!-- num:experiments/encoder/agreement.json:encoders.ko_structure_pool.runs.exaone_full_vllm_ko_test.verifier_and_same_row.coverage.rate:pct -->82.8<!-- /num -->%) |
| 여러 턴 대화의 기억 | 2턴 대화 <!-- num:experiments/eval/dialog/heuristic.json:dialogs:int -->681<!-- /num -->개의 둘째 턴: 기억 없이 <!-- num:experiments/eval/dialog/heuristic.json:no_memory.all.rate:pct -->1.0<!-- /num -->% → 기억 <!-- num:experiments/eval/dialog/heuristic.json:memory.all.rate:pct -->35.5<!-- /num -->%(휴리스틱, 후속 질문은 틀로 만든 것) |
| 화학 논문 표 62문항 | 휴리스틱 <!-- num:experiments/eval/heuristic_chem_papers/metrics.json:metrics.verified_em:pct -->43.5<!-- /num -->%, mT5-small <!-- num:experiments/eval/rl_v3_chem_papers/metrics.json:metrics.verified_em:pct -->22.6<!-- /num -->% |

## 누가 무엇을 했나

| | 범위 |
|---|---|
| 지원자 | 문제 정의와 핵심 설계(모델이 프로그램을 제안 → 도구가 실행 → 검증기가 확인 → 틀리면 보류). 검증 파이프라인의 다섯 모듈(숫자·단위 파서, 계산기, 프로그램 문법, 셀 도구, 검증기)과 근거 복구 끄기 옵션을 명세와 테스트만 보고 **직접 다시 작성**(PR 1~5, `docs/rewrite/LOG.md`). GPU 실험 실행(Kaggle T4) |
| AI 코딩 도구 | 그 밖의 구현, 실험 설계 세부, 테스트, 문서. 커밋에 공동 작성 표식이 있다 |
| 아직 지원자 몫으로 남은 것 | 학습 코드 직접 쓰기(강화학습 보상, GRPO 손실, 학습 루프: 명세와 테스트 35개가 준비됨), GPU 보강 실험 실행 |

## 공고의 다섯 묶음과 대응

| 묶음 | 한 것 | 아직 아닌 것 |
|---|---|---|
| 테이블이해 (중심) | 한국어 표 QA 튜닝, 근거 셀 오류 측정, 검증기, 열 번호 형식, 큰 표 행 선별, 행·열 임베딩 표 인코더와 표 사전학습(작은 규모) | 대규모 표 사전학습, 구조 임베딩이 실제로 도움이 된다는 증거 |
| 강화학습 | 검증기 보상 GRPO(mT5-small), 보상 허점 추적 | EXAONE 강화학습은 스크립트와 노트북까지 |
| 초거대 언어모델 | EXAONE-4.0-1.2B LoRA, 재분할 평가셋, vLLM·SGLang 서빙과 텐서 병렬 | 7.8B·32B 참고선, 학습 데이터 확대, 4비트 서빙은 노트북까지 |
| 심층문서이해(영어 화학) | 교과서 표 튜닝, 화학 논문 표 평가 세트 | 논문 표로 학습, 특허, EXAONE 평가 |
| LLM 서비스·Agent | FastAPI, gRPC(단계별 스트리밍), LangGraph, 비동기 작업, Docker, 여러 턴 대화와 기억, 모델이 도구를 고르는 플래너 | 도구 호출 플래너의 실제 모델 측정, 대화를 언어모델이 관리하는 방식 |

## 한계

- 모델이 작다(3억, 12억). GPU는 무료 T4 한두 장이고 대부분의 설정을 한두 번만 돌렸다.
- 검증기를 거쳐도 가장 좋은 모델에서 오답이 약 열에 하나 나간다. 일관되게 틀린 답은 규칙만으로 잡지 못한다.
- 계산·보류 문항은 틀로 만든 합성 데이터이고, 수작업 문항은 AI 도구가 썼으며 여러 사람이 검수하지 않았다.
- 비슷한 문제를 다룬 연구가 이미 있다(TrustTable, RSAT, Reasoning-Table, 국내의 CReSt 등). 이 저장소가 보태는 것은 한국어 표에서의 측정이다.

더 읽을 것: [README](../README.md) §9, [보고서](REPORT.md) §19~§20, [자소서용 전달 문서](HANDOFF.md), [관련 연구](research/papers.md).
