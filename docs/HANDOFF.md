# 자소서·포트폴리오 작성용 전달 문서 (TableTrace)

이 문서는 자기소개서와 포트폴리오를 쓰는 사람(또는 AI 도구)에게 넘기는 사실 정리다. **여기 없는 숫자는 쓰지 말고, 여기 있는 숫자도 괄호의 출처 파일로 다시 확인한 뒤 쓴다.** 저장소에서 `python scripts/check_numbers.py --strict`와 `python scripts/render_results.py --check`를 돌리면 README·보고서의 모든 숫자가 산출물과 일치하는지 검사된다(2026-11-08 기준 815개 일치).

## 0. 반드시 지킬 규칙

1. **역할을 사실대로 적는다.** 역할은 다음과 같이 나뉜다.
   - **지원자**: 문제 정의와 핵심 설계. 모델이 답을 바로 내지 않고 프로그램(`op ; cells ; answer`)을 제안하면 도구가 실행하고 검증기가 확인해 틀리면 보류하는 구조, 한국어 표(KorWikiTQ)와 영어 화학 문서라는 두 영역, FastAPI·LangGraph·Docker·CI 스택, "실행한 것과 준비만 한 것을 나누고 숫자를 지어내지 않는다"는 보고 원칙과 공고 대조표 형식을 처음 작업 지시에서 정했다. 이후 어떤 실험을 더 하고 무엇을 건너뛸지(전체 데이터 재학습, 수작업 평가, Ampere 비교 생략)를 결정했고, GPU가 필요한 실험(EXAONE LoRA, vLLM·SGLang 서빙, 멀티 GPU)을 Kaggle·Colab에서 직접 실행해 결과를 수집했으며, 결과와 문서를 검토했다.
   - **AI 코딩 도구(Claude Code)**: 그 설계를 채우는 세부 실험 설계(표 단위 재분할, 지표, 휴리스틱 기준선, 합성 데이터 템플릿, SFT 단계, RL 보상 설계와 수정, int8 범위 실험, 검증기 v2, 쌍 비교 검정, GPU 노트북과 T4 우회 모듈)와 구현, 테스트, 문서 작성, 오류 진단.
   - **소유자가 직접 다시 작성한 코드** (2026-11-10부터, `docs/rewrite/LOG.md`가 기준): AI 도구가 쓴 원본을 소유자가 명세와 테스트만 보고 처음부터 다시 쓰고, 원본과 실제 데이터에서 동작이 같은지 검사(`scripts/rewrite_parity.py`)를 통과한 뒤 소유자 계정으로 커밋·병합한 모듈. 현재: **숫자·단위 파서와 제한 계산기**(`src/tabletrace/tools/numbers.py`, `calculator.py`, PR #1). 이 과정에서 원본 결함 2건을 찾아 기록했다(`docs/dev/issues-log.md` 40·41). 이 목록에 없는 코드는 AI 도구가 작성한 것이다.
   "혼자 다 구현했다"고 쓰면 안 되고, 반대로 "설계는 AI가 했다"고 써도 틀리다. 설계를 정하고 AI 도구를 지휘·검증한 과정, 그리고 직접 다시 쓴 모듈과 그때 찾은 결함이 내용이 된다. 직접 작성했다고 쓸 수 있는 범위는 위 목록의 모듈뿐이다.
2. **수치는 출처 파일에서만.** 모든 수치는 `experiments/` 아래 JSON에서 나오고, README와 `docs/REPORT.md`에 `<!-- num:파일:키 -->` 표식으로 묶여 있다.
3. **"주장하면 안 되는 것"(§5)을 쓰지 않는다.** 특히 "mT5로 기준선을 넘었다", "강화학습으로 점수를 올렸다", "SGLang과 vLLM 속도를 비교했다"는 틀린 말이다.
4. 실패와 수정 과정(§4)은 숨기지 말고 쓴다. 이 프로젝트의 가장 강한 재료다.
5. 공고 원문은 이 프로젝트에서 읽지 못했고(네트워크 차단) 지원자가 준 역량 목록 15개를 기준으로 했다(`docs/research/job-posting.md`). 원문과 다르면 원문이 우선이다.

## 1. 링크와 위치

| 항목 | 값 |
|---|---|
| 저장소 (공개) | <https://github.com/sokldjs554/tabletrace> (`main`) |
| 공개 데모 (GitHub Pages, 저장된 실행 결과 모드) | <https://sokldjs554.github.io/tabletrace/> — 소유자가 2026-11-08 브라우저에서 열리는 것을 확인 |
| 최종 보고서 | `docs/REPORT.md` (공고 대조표 §3, 확인 가능한 사실 §17, 2차 시도 §18) |
| README | `README.md` (결과 표 §9·§10, 수행/미수행 표 §14) |
| 발견한 문제와 수정 기록 | `docs/dev/issues-log.md` (39건) |
| GPU 실험 출처 | `experiments/eval/PROVENANCE_exaone.md`, `experiments/serving/sglang_t4_failure.md` |
| 로컬 실행 | `docker compose up --build` → <http://localhost:8000> |

## 2. 프로젝트 한 문단 (사실만)

TableTrace는 한국어 위키 표(KorWikiTQ)와 영어 화학 교과서 표(OpenStax)에서 질문에 답할 때, 모델이 답을 바로 말하는 대신 **프로그램(`op: lookup|sum|avg|diff|text|abstain ; cells: r{i}c{j} ; answer: …`)을 제안**하고, 도구가 그 셀을 읽고 계산을 실행하고, 검증기가 답과 근거 셀이 맞는지 확인해 틀리면 **보류**하는 파이프라인이다. 검색(BM25, Kiwi 형태소) → 모델 제안 → 도구 실행 → 검증 → 보류 정책 → 트레이스 기록까지를 FastAPI 서비스와 LangGraph 그래프로 묶었고, 비동기 작업 러너, Docker, GitHub Actions CI, GitHub Pages 데모가 있다. 모델은 두 갈래다. (가) mT5-small(300M)을 CPU에서 SFT 2단계와 GRPO 방식 RL로 튜닝했고 기준선을 넘지 못했다. (나) 같은 데이터로 EXAONE-4.0-1.2B를 LoRA 튜닝해 GPU(Kaggle T4)에서 vLLM·SGLang·텐서 병렬로 서빙한 모델은 기준선을 크게 넘었다.

## 3. 확인 가능한 수치 (출처와 함께)

한국어 독립 test = 699문항(KorWikiTQ 원본 539 + 합성 160), 표 단위로 재분할해 학습과 표가 겹치지 않음. verified EM = 검증기를 통과한 정답(답 없는 문항은 보류가 정답).

| 사실 | 수치 | 출처 |
|---|---|---|
| 공개 분할의 표 누수를 측정하고 재분할 | 공유 표 1,755개 → 0 | `data/ko/official_split_profile.json` |
| 휴리스틱 기준선 verified EM | 36.2% | `experiments/eval/heuristic_ko_test/metrics.json` |
| mT5-small 미튜닝 → 1차 최종 → 2차 최종(RL v3) | 7.1% → 29.8% → 32.8% (기준선 미달) | `experiments/eval/{base,sft_chem,rl_v3}_ko_test/metrics.json` |
| RL v3가 배운 것 | 본문 근거 없음 50문항에서 모델이 직접 보류 0% → 90% (p=0.020) | `experiments/eval/rl_v3_text2_test/analysis.json`, `experiments/eval/paired_tests.json` |
| RL v1의 보상 편법 발견 | 같은 셀을 두 번 쓰는 퇴화 계산 160건 → v3 0건 | `experiments/eval/rl_ko_v1_ko_test/analysis.json`, `rl_v3_ko_test/analysis.json` |
| int8 동적 양자화 범위별 측정 | lm_head만 int8: 정확도 손실 검출 안 됨(32.2%, p=0.636), 처리량 약 1.5배(같은 측정 안 bs=8: 2.12 → 3.21 예제/s) / 모든 층 int8: 21.2%로 하락 | `experiments/eval/final_int8_*_ko_test/metrics.json`, `experiments/bench/inference_r2*.json` |
| 검색 | 표 검색 hit@1 80.0%, hit@5 95.7% (1,140표) | `experiments/eval/retrieval/metrics.json` |
| EXAONE-4.0-1.2B LoRA, 300개 예제·18 step (T4) | verified EM 53.1% (세 번 학습 52.2 / 53.2 / 53.1) | `experiments/eval/exaone_vllm_ko_test*/metrics.json` |
| EXAONE LoRA, 전체 3,587개·224 step, T4 31분 | **verified EM 84.3%** (두 번째 학습 87.1%; 기준선 대비 문항 344 대 25, p<0.001) | `experiments/eval/exaone_full_vllm_ko_test*/metrics.json`, `experiments/exaone_lora_full/train_info.json`, `paired_tests.json` |
| 전체 모델의 보류 | 답 없는 50문항 중 32건을 모델이 직접 보류, 정답 문항 오보류 0건 | `experiments/eval/exaone_full_vllm_ko_test/analysis.json` |
| 수작업 30문항(실제 표·본문, 5범주) | 휴리스틱 50.0%, mT5 13.3%, EXAONE 전체 66.7% (본문 0/5: 본문 예제 없이 학습) | `experiments/eval/*_ko_custom*/metrics.json` |
| vLLM 서빙 (T4 1장, 동시 32요청) | 25.7 요청/s, p50 1,073 ms | `experiments/bench/engine_vllm_c32.json` |
| vLLM 텐서 병렬 TP=2 (T4 2장) | 41.0 요청/s, p50 678 ms; 점수는 1장과 같음 | `experiments/bench/engine_vllm_tp2_c32.json`, `experiments/eval/exaone_vllm_tp2_ko_test/metrics.json` |
| SGLang (T4, 우회 모듈) | vLLM과 같은 답(699문항 중 1개 차이), 속도는 8.3 요청/s | `experiments/eval/exaone_sglang_ko_test/metrics.json`, `experiments/bench/engine_sglang_c32.json` |
| mT5 2-스테이지 파이프라인 병렬 (T4 2장, NCCL) | 출력 일치, 처리량 이득 없음(설계상 겹치지 않음), 장치당 메모리 분할 | `experiments/bench/pp_*_gpu.json` |
| 테스트·검증 | pytest 102개 통과, E2E 실시간 16/16·정적 13/13, CI(test·docker)와 Pages 배포 성공 | `experiments/tests/summary.json`, GitHub Actions |

## 4. 포트폴리오에 쓸 만한 과정 (전부 기록이 있음)

1. **보상 편법을 찾아 고친 RL**: v1 보상이 "같은 셀 두 번 쓰는 계산"에 점수를 줘서 퇴화 출력 160건이 나왔다. 보상을 고친 v2는 개선이 없었고, 2차 v3(프롬프트 5,130개, 검증기 v2 보상)가 "모델이 스스로 보류"를 배웠지만 전체 점수는 그대로였다. 세 결과를 다 적었다. (`docs/REPORT.md` §7, §18)
2. **학습 데이터의 지름길 발견**: 본문 예제가 전부 빈 표와 함께 있어 모델이 "표가 비면 text"를 배운 것을 찾아 재학습했고, 반대편 지름길(표 질문을 text로 보냄)까지 겪고 고쳤다. (§18.1)
3. **검증기 v2(개체 일치 검사)**: 표에 없는 대상에도 셀을 인용해 답하는 문제를 검증기 단계에서 잡았고, 정답을 오탐 보류하는 비용(4.3%)을 함께 측정했다. 잘하는 모델(EXAONE 전체)에서는 순효과가 음수에 가깝다는 것도 적었다.
4. **int8 "lm_head는 fp32"라는 문서의 오류를 스스로 발견**하고 양자화 범위별로 다시 측정해, 속도 이득은 lm_head에서 나오고 정확도 붕괴는 전체 양자화에서만 난다는 것을 보였다. (§8, §18.2)
5. **SGLang을 미지원 GPU(T4)에서 돌림**: sgl_kernel에 sm75 커널이 없어 두 번 실패 → 소스를 읽고 `MultiPlatformOp`를 PyTorch 구현으로 돌리는 우회 모듈 작성 → 세 번째는 transformers 5.x가 저장한 config.json의 RoPE 키를 4.57이 못 읽어 엉뚱한 답 → 설정 복원 → 네 번째 성공, vLLM과 답 일치. (`experiments/serving/sglang_t4_failure.md`, 이슈 37~39)
6. **숫자 정합성 도구**: 문서의 모든 숫자를 산출물 JSON에 묶는 표식과 검사 스크립트(`scripts/check_numbers.py`, `scripts/render_results.py`)로 815개 숫자를 자동 검증한다.
7. **학습 실행 간 변동을 측정**: 같은 설정의 LoRA를 300개 3회, 전체 2회 돌려 300개는 1점 안, 전체는 약 3점(p=0.013) 움직임을 기록하고 점수를 범위로 적었다.

## 5. 주장하면 안 되는 것

- "mT5로 기준선보다 좋은 모델을 만들었다" (32.8% 대 36.2%, 못 넘었다).
- "강화학습으로 ko test 점수를 올렸다" (v3도 그대로. 배운 것은 보류 행동).
- "EXAONE이 실제 표의 계산을 잘한다" (계산·보류 평가 문항은 학습과 같은 템플릿의 합성 데이터. 실제 표 문항은 전부 조회).
- "SGLang과 vLLM의 성능을 비교했다" (T4의 SGLang은 우회 모듈 탓에 느림. Ampere 이상에서의 비교는 비용 때문에 하지 않음).
- "멀티 GPU로 속도를 올렸다" (파이프라인 병렬은 이득 없음. TP=2만 처리량 약 1.6배).
- "화학 논문 데이터" (교과서 표다), "DDP를 했다" (안 했다), "혼자 코드를 짰다" (AI 도구가 작성).
- 공고 원문을 읽고 맞췄다는 식의 표현 (원문은 읽지 못함).

## 6. 공고 역량 15개 항목과 대응 (상태는 전부 완료, 근거는 `docs/REPORT.md` §3)

한국어 LM 튜닝 / 한국어 벤치마크 구축 / 표 이해·Table MRC / 추론 엔진 최적화 / 영어 화학 데이터·튜닝 / 강화학습 / LLM Agent·도구 연결 / FastAPI 서빙 / 비동기·워크플로우 / 프롬프트·컨텍스트·검색 / Linux·Python·HF·PyTorch / 멀티 GPU Model Parallelism / vLLM 또는 SGLang / Docker / LangChain 또는 LangGraph. 각 항목의 "적용 방식·증거·평가 결과" 열을 그대로 가져다 쓰면 된다. 강화학습 항목은 "완료(부분 개선)"이고 그 뜻은 §4의 1번이다.
