# TableTrace 최종 보고서

작성 기준: 이 저장소의 커밋과 `experiments/` 산출물. 본문의 수치는 산출물 JSON을 가리키는 `<!-- num:… -->` 표식으로 묶여 있고 `scripts/check_numbers.py --strict`가 값을 대조한다. 결과 표는 `scripts/render_results.py`가 산출물에서 생성하며 `--check`가 낡은 표를 잡는다. 실행하지 않은 것은 "구현 후 미실행"으로 적는다.

## 1. 저장소와 공개 데모

| 항목 | 값 |
|---|---|
| 목표 저장소 | <https://github.com/sokldjs554/tabletrace> — **푸시하지 못했다.** git 푸시와 GitHub API 푸시가 모두 `403`(`Claude doesn't have GitHub access … for your organization`, `Resource not accessible by integration`). 이 계정에 Claude GitHub App이 설치되어 있지 않다. 사용자 요청으로 재시도했으나 같은 결과였고, 최종 커밋 뒤에 한 번 더 시도한 `git push`(두 저장소)와 API 브랜치 생성도 모두 403이었다. 읽기 API는 동작하며 tabletrace는 브랜치 목록이 비어 있다(저장소가 비어 있는지 없는지는 확인하지 못함). |
| chartwire 지정 브랜치 | <https://github.com/sokldjs554/chartwire> `claude/bold-carson-ix16u0` — **여기도 푸시하지 못했다.** 로컬에는 `tabletrace/` 복사본과 전체 이력 번들(`tabletrace-history.bundle`)을 커밋해 두었다. |
| 지금 코드가 있는 곳 | 컨테이너의 `/home/user/tabletrace`(git 저장소 원본), `/home/user/chartwire/tabletrace/`(복사본), `/home/user/chartwire/tabletrace-history.bundle`(전체 이력) |
| 공개 데모 | **배포하지 못했다.** Pages 워크플로(`pages.yml`)는 작성했으나 원격에 푸시되지 않아 한 번도 실행되지 않았다. 배포 예정 주소 <https://sokldjs554.github.io/tabletrace/>는 지금 열리지 않을 수 있다. |
| 로컬 실시간 데모 | `docker compose up --build` → http://localhost:8000 (Docker 빌드·컨테이너 smoke는 이 세션에서 실행해 통과) |
| 정적 데모 | 로컬에서 `scripts/build_static_site.py`로 빌드해 Playwright로 검증(§10) |

푸시를 가능하게 하려면 https://claude.ai/connect-github 에서 GitHub 계정을 다시 연결하고 Claude GitHub App을 해당 저장소에 설치한 뒤, 저장소가 선택된 새 세션을 시작해야 한다(이 세션에서는 저장소 선택을 바꿀 수 없다).

## 2. 최종 커밋과 배포 버전

| 항목 | 값 |
|---|---|
| 최종 커밋(tabletrace 로컬 저장소) | `799d528`(코드·모델 평가·정적 데모 기록의 기준 커밋). 이후 변경은 `src/`·`Dockerfile`·`.github/`를 건드리지 않고 문서, 숫자 표식, 결과 표, 저장된 실행 결과 재기록(`console/data`), E2E 스크린샷·요약, 테스트 린트 정리(8줄)뿐이다(`git diff --stat 799d528 HEAD -- src scripts tests console data Dockerfile .github` 로 확인 가능). 이 보고서를 포함한 **최종 커밋의 SHA는 자기 참조라 파일에 적을 수 없으며** `git log -1`과 최종 응답에 있다 |
| 패키지 버전 | 0.1.0 (`src/tabletrace/__init__.py`) |
| 정적 데모에 기록된 커밋 | `799d528` (`console/data/recorded/index.json`) |
| 배포된 버전 | 없음(배포하지 못함) |

## 3. 공고 대조표

공고 원문은 네트워크 차단으로 읽지 못했다(docs/research/job-posting.md). 사용자가 제시한 역량 목록을 기준으로 한다. 상태는 **완료 / 실행했으나 실패 / 구현 후 미실행 / 미구현** 넷 중 하나이며, 상태 판단의 단서는 "평가 결과" 열에 적었다. 이 표는 프로젝트 결과만을 대상으로 하며 개인의 역량이나 근무 가능 여부를 검증했다고 주장하지 않는다.

| 공고 항목 | 프로젝트 적용 방식 | 구현·실행 증거 | 평가 결과 | 상태 |
|---|---|---|---|---|
| 한국어 언어모델 튜닝 | mT5-small(300M)을 KorWikiTQ 표 QA 프로그램 생성 과제로 SFT 2단계 | `training/sft.py`, `experiments/sft_ko*/summary.json`, `train_log.jsonl` | 독립 test verified EM 미튜닝 <!-- num:experiments/eval/base_ko_test/metrics.json:metrics.verified_em:pct -->7.1<!-- /num -->% → 튜닝 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->%. 그러나 어휘 겹침 기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->%에는 미달(§5) | 완료 |
| 한국어 언어모델 벤치마크 구축 | 표 단위 재분할 test <!-- num:data/ko/build_report.json:test_examples -->539<!-- /num -->문항 + 합성 160 + 수작업 30(5범주), verified EM·근거 셀 일치·보류 재현율 등 지표, 자동 검수 | `data/ko/`, `eval/metrics.py`, `scripts/check_data.py` | 공개 분할의 표 누수를 측정하고 제거(공유 표 0). 수작업 30·합성 160은 표본이 작거나 편향이 있음(§5) | 완료 |
| 표 이해 및 Table MRC | 표 직렬화(r/c 좌표) → 셀·연산 프로그램 생성 → 검증기 | `model/serialize.py`, `verify/verifier.py` | 원본 KorWikiTQ 539문항에서 튜닝 모델 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->37.1<!-- /num -->% vs 기준선 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->26.2<!-- /num -->% | 완료 |
| 추론 엔진 최적화 | CPU에서 fp32 / int8 동적 양자화 / 배치 / KV 캐시를 정밀도별 별도 프로세스로 실측, 양자화 모델의 정확도도 평가 | `bench/inference.py`, `experiments/bench/inference.json`, `experiments/eval/sft_chem_int8_*` | 처리량 fp32 bs=1 <!-- num:experiments/bench/inference.json:results.0.throughput_ex_per_s -->0.985<!-- /num --> → int8 bs=8 <!-- num:experiments/bench/inference.json:results.4.throughput_ex_per_s -->3.7<!-- /num --> 예제/s. 그러나 int8은 한국어 test 정확도를 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->% → <!-- num:experiments/eval/sft_chem_int8_ko_test/metrics.json:metrics.verified_em:pct -->17.7<!-- /num -->%로 떨어뜨림(§8) | 완료 |
| 영어 화학 도메인 데이터 처리·모델 튜닝 | OpenStax Chemistry 2e CNXML 파싱(문서 <!-- num:data/chem/build_report.json:documents_with_tables -->56<!-- /num -->, 표 <!-- num:data/chem/build_report.json:tables -->113<!-- /num -->), 합성 QA, 화학 SFT, 수작업 32문항 | `scripts/data/build_chem.py`, `experiments/sft_chem/` | 합성 dev <!-- num:experiments/eval/sft_ko2_chem_syndev/metrics.json:metrics.verified_em:pct -->22.5<!-- /num -->% → <!-- num:experiments/eval/sft_chem_chem_syndev/metrics.json:metrics.verified_em:pct -->41.2<!-- /num -->%, 수작업 32문항 <!-- num:experiments/eval/sft_ko2_chem_custom/metrics.json:metrics.verified_em:pct -->9.4<!-- /num -->% → <!-- num:experiments/eval/sft_chem_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num -->%(2문항 차이, 잡음 수준. 전부 보류하는 미튜닝 모델도 <!-- num:experiments/eval/base_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num -->%라 이 값을 넘지 못함), 기준선 <!-- num:experiments/eval/heuristic_chem_custom/metrics.json:metrics.verified_em:pct -->56.2<!-- /num -->%(§6) | 완료 |
| 강화학습 기반 언어모델 개발 | GRPO 방식 정책 경사(검증기 보상, 그룹 정규화, KL) | `training/rl_grpo.py`, `experiments/rl_ko_v1/`, `experiments/rl_ko/` | 정책 갱신 60 step 예비 실험 2회. v1은 보상 편법 발견(§7.2), v2(수정 보상)도 독립 test verified EM이 SFT stage 2 <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.verified_em:pct -->27.5<!-- /num -->% → <!-- num:experiments/eval/rl_ko_ko_test/metrics.json:metrics.verified_em:pct -->27.0<!-- /num -->%로 개선 없음(1 표준오차 약 1.7%p), 오보류율 <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.false_abstain_rate:pct -->31.0<!-- /num -->% → <!-- num:experiments/eval/rl_ko_ko_test/metrics.json:metrics.false_abstain_rate:pct -->35.9<!-- /num -->%로 악화(§7.5) | 실행했으나 실패 |
| LLM Agent와 외부 도구 연결 | LangGraph 그래프 + 타입 검증 도구 레지스트리(셀 조회·검색·제한 계산) | `agent/graph.py`, `tools/registry.py`, `tests/test_api.py` | API·도구·신뢰 경계 테스트 통과(§10) | 완료 |
| FastAPI 기반 서비스 및 모델 서빙 | REST API, 프로세스 내 모델 서빙, 작업 큐, 정적 콘솔 | `service/app.py`, `service/jobs.py` | API 테스트 통과, 컨테이너 smoke 통과, 모델 플래너 E2E 통과 | 완료 |
| 비동기 처리와 워크플로우 설계 | asyncio 작업 러너(세마포어·큐 제한·타임아웃·상태), LangGraph 분기 | `service/jobs.py`, `agent/graph.py` | 동시 5건·타임아웃·큐 초과(429)·실패 상태 테스트 통과 | 완료 |
| 프롬프트·컨텍스트 엔지니어링과 검색 결합 | BM25(Kiwi 형태소) 검색, 본문 스니펫+표 직렬화, 컨텍스트→행 예산 | `retrieval/`, `model/serialize.py` | 표 검색 hit@1 <!-- num:experiments/eval/retrieval/metrics.json:ko_test_lookup.hit_at_1:pct -->80.0<!-- /num -->% / hit@5 <!-- num:experiments/eval/retrieval/metrics.json:ko_test_lookup.hit_at_5:pct -->95.7<!-- /num -->%(한국어 <!-- num:experiments/eval/retrieval/metrics.json:ko_test_lookup.n_tables_searched -->1,140<!-- /num -->표), 화학 hit@1 <!-- num:experiments/eval/retrieval/metrics.json:chem_custom.hit_at_1:pct -->65.6<!-- /num -->%. 컨텍스트 유무의 모델 정확도 효과는 분리 측정하지 않음 | 완료 |
| Linux, Python, Hugging Face, PyTorch | Python 3.13 / PyTorch 2.15 / **Hugging Face Transformers·tokenizers 라이브러리**(Hub는 차단되어 사용하지 못함), 자체 학습 루프 | 저장소 전체 | — | 완료 |
| 멀티 GPU Model Parallelism | 2-스테이지 파이프라인 병렬(인코더 / 디코더+lm_head), torch.distributed | `bench/pipeline_parallel.py`, `experiments/bench/pp_*.json` | GPU 없음. CPU 2프로세스(gloo)로 분할·통신·출력 일치만 검증, 처리량 이득 없음(§9) | 구현 후 미실행 |
| vLLM 또는 SGLang | OpenAI 호환 EnginePlanner + TP/PP 서빙 스크립트 + 엔진 벤치 | `service/engines.py`, `scripts/serving/`, `tests/test_engines.py` | 모의 서버 왕복 테스트만 통과. 실제 엔진 미실행 | 구현 후 미실행 |
| Docker | API+콘솔 이미지, compose, 헬스체크 | `Dockerfile`, `docker-compose.yml`, `experiments/docker/smoke.json` | 이 세션에서 이미지 빌드(786 MB) + 컨테이너 smoke 통과(Docker Hub 429로 MCR 베이스 이미지 사용) | 완료 |
| LangChain 또는 LangGraph | 위 Agent 항목(LangGraph) | `agent/graph.py` | `GET /v1/graph` 가 Mermaid 반환, 조건부 재시도 분기 | 완료 |
| GitHub Actions | `ci.yml`(린트·테스트·데이터·수치·Docker smoke), `pages.yml` | `.github/workflows/` | 원격 실행 없음(푸시 불가). 같은 명령을 로컬에서 실행해 통과 | 구현 후 미실행 |
| 공개 데모 배포 | GitHub Pages 정적 데모 | `pages.yml`, `scripts/build_static_site.py` | 배포하지 못함. 로컬 정적 빌드는 Playwright로 검증 | 구현 후 미실행 |

## 4. 사용한 기술과 실제 역할

| 기술 | 실제 역할 | 실행 여부 |
|---|---|---|
| PyTorch 2.15 / Transformers 5.21 | mT5-small 변환·SFT·RL·추론; 자체 학습 루프(Trainer 미사용) | 실행 |
| tokenizers / SentencePiece | mT5 토크나이저를 spm proto에서 재구성(transformers 5가 spm 직접 로드를 지원하지 않음) | 실행 |
| Kiwi (kiwipiepy) | 한국어 형태소 분석으로 BM25 토큰화 | 실행 |
| LangGraph | retrieve→propose→verify→finalize 상태 그래프, 조건부 재시도 | 실행 |
| FastAPI / uvicorn / pydantic | API, 입력 검증, 비동기 작업 | 실행 |
| Playwright | 콘솔 E2E 검사·스크린샷 | 실행 |
| Docker | 이미지 빌드·컨테이너 smoke | 실행 |
| torch.distributed (gloo) | 파이프라인 병렬 기능 검증(CPU) | 실행(CPU) |
| TensorFlow (별도 venv) | mesh-TF 체크포인트 읽기 전용(변환 시 1회) | 실행 |
| GitHub Actions | CI·Pages 워크플로 | 작성만, 원격 실행 없음 |
| vLLM / SGLang | 서빙 스크립트·클라이언트 | 미실행(GPU 없음) |
| Hugging Face Hub / EXAONE | — | 사용 못함(`huggingface.co` 차단) |

## 5. 한국어 표 QA — 데이터·모델·평가

### 5.1 데이터

- **출처·라이선스**: KorWikiTQ(LG AI연구원, CC BY-SA 4.0). 공개 분할은 train <!-- num:data/ko/official_split_profile.json:train.examples:int -->58,221<!-- /num --> / dev <!-- num:data/ko/official_split_profile.json:dev.examples:int -->11,771<!-- /num -->문항이며 **표 <!-- num:data/ko/official_split_profile.json:shared_tables_by_url:int -->1,755<!-- /num -->개를 공유**한다(질문 단위 분할). 정답이 표의 어떤 셀과 정확히 일치하는 비율은 train <!-- num:data/ko/official_split_profile.json:train.answer_is_cell_pct -->99.6<!-- /num -->%라 "셀 선택" 과제이며 산술·보류 사례는 없다.
- **재분할**: URL+표 내용 해시로 표를 식별해 표 단위로 나눴다. 필터(16행·7열·900자 이하 등)를 통과한 표 <!-- num:data/ko/build_report.json:tables_after_filter:int -->7,294<!-- /num -->개 중 <!-- num:data/ko/build_report.json:tables_used.train:int -->900<!-- /num -->/<!-- num:data/ko/build_report.json:tables_used.dev:int -->60<!-- /num -->/<!-- num:data/ko/build_report.json:tables_used.test:int -->180<!-- /num -->개를 train/dev/test에 배정했고 **분할 간 공유 표는 0**이다(`leak_check_shared_tables`, `scripts/check_data.py`가 CI에서 재검사).
- **문항 수**: train <!-- num:data/ko/build_report.json:train_examples:int -->2,694<!-- /num --> / dev <!-- num:data/ko/build_report.json:dev_examples:int -->180<!-- /num --> / test <!-- num:data/ko/build_report.json:test_examples:int -->539<!-- /num -->(원본 lookup). 합성(템플릿) 계산·보류: train 960 / dev 65 / test 160. 본문 답변 학습용 KorQuAD 700/100. 수작업 평가 30(표 6개 위에 직접 작성, 5범주, 정답은 스크립트가 셀 텍스트·계산기·본문 포함 여부로 자동 검수).
- **학습 입력 예산**: 512 토큰. 본문을 300→150→0자로 줄여서라도 표 전체를 넣고, 그래도 넘으면 뒤 행을 자른다. 학습에서는 정답 행이 잘린 <!-- num:experiments/sft_ko/summary.json:n_train_dropped_truncated:int -->223<!-- /num -->건을 제외했고, 평가에서는 제외하지 않고 `truncated_gold_rate`(<!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.truncated_gold_rate:pct -->8.9<!-- /num -->%)를 따로 보고한다. 즉 test의 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.truncated_gold_rate:pct -->8.9<!-- /num -->%는 입력 예산 때문에 모델이 원리적으로 맞힐 수 없다.

### 5.2 모델·학습 조건

mT5-small 300,176,768 파라미터(GCS 체크포인트를 PyTorch로 직접 변환). 하드웨어: 4 vCPU CPU만 사용. stage 1: <!-- num:experiments/sft_ko/summary.json:n_train:int -->3,431<!-- /num -->예제, <!-- num:experiments/sft_ko/summary.json:steps:int -->858<!-- /num --> step, 약 <!-- num:experiments/sft_ko/summary.json:wall_s:int -->7,219<!-- /num -->초. stage 2(본문 답변 추가): <!-- num:experiments/sft_ko2/summary.json:n_train:int -->1,542<!-- /num -->예제, <!-- num:experiments/sft_ko2/summary.json:steps:int -->193<!-- /num --> step, <!-- num:experiments/sft_ko2/summary.json:wall_s:int -->1,813<!-- /num -->초. 학습 중 dev 지표는 이후 수정한 채점 코드(§13의 25번) 이전 값이라 아래 test 표와 직접 비교하지 않는다.

### 5.3 결과 (동일한 독립 평가셋, 같은 검증기)

<!-- results:ko:start -->
**한국어 표 QA — 독립 test (원본 539 + 합성 160)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 699 | **36.2** | 21.7 | 26.2 | 59.1 | 31.6 | 31.6 | 94.0 | 42.4 | 0.0 | 21 |
| mT5-small 기본(미튜닝) | 699 | **7.1** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 399 |
| SFT stage1 | 699 | **25.0** | 26.7 | 29.9 | 1.8 | 25.4 | 18.5 | 24.0 | 28.8 | 0.0 | 591 |
| SFT stage2(+본문) | 699 | **27.5** | 28.0 | 32.3 | 4.5 | 28.0 | 21.4 | 26.0 | 31.0 | 0.0 | 422 |
| GRPO RL v1 (보상 허점) | 699 | **26.8** | 27.4 | 30.6 | 4.5 | 26.7 | 20.6 | 34.0 | 37.9 | 0.0 | 460 |
| GRPO RL v2 (보상 수정) | 699 | **27.0** | 27.6 | 31.0 | 4.5 | 27.0 | 20.3 | 34.0 | 35.9 | 0.0 | 504 |
| 화학 SFT | 699 | **29.8** | 33.4 | 37.1 | 0.0 | 30.8 | 17.1 | 16.0 | 19.4 | 0.0 | 615 |
| 화학 SFT + int8 동적 양자화 | 699 | **17.7** | 16.0 | 18.6 | 0.0 | 15.4 | 13.6 | 48.0 | 55.3 | 15.0 | 383 |

**한국어 표 QA — 수작업 30문항**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 30 | **50.0** | 20.0 | 38.5 | 41.7 | 44.0 | 44.0 | 100.0 | 40.0 | 0.0 | 133 |
| mT5-small 기본(미튜닝) | 30 | **16.7** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 242 |
| SFT stage1 | 30 | **16.7** | 12.0 | 7.7 | 0.0 | 4.0 | 8.0 | 80.0 | 80.0 | 0.0 | 447 |
| SFT stage2(+본문) | 30 | **23.3** | 8.0 | 7.7 | 8.3 | 8.0 | 12.0 | 100.0 | 80.0 | 0.0 | 480 |
| GRPO RL v1 (보상 허점) | 30 | **20.0** | 8.0 | 7.7 | 0.0 | 4.0 | 12.0 | 100.0 | 84.0 | 0.0 | 437 |
| GRPO RL v2 (보상 수정) | 30 | **20.0** | 8.0 | 7.7 | 0.0 | 4.0 | 12.0 | 100.0 | 76.0 | 0.0 | 525 |
| 화학 SFT | 30 | **3.3** | 8.0 | 7.7 | 0.0 | 4.0 | 4.0 | 0.0 | 48.0 | 0.0 | 536 |
| 화학 SFT + int8 동적 양자화 | 30 | **13.3** | 8.0 | 15.4 | 0.0 | 8.0 | 4.0 | 40.0 | 52.0 | 16.7 | 393 |

**한국어 수작업 — 범주별 verified EM % (n)**

| 범주 | 휴리스틱 기준선 | mT5-small 기본(미튜닝) | SFT stage1 | SFT stage2(+본문) | GRPO RL v1 (보상 허점) | GRPO RL v2 (보상 수정) | 화학 SFT | 화학 SFT + int8 동적 양자화 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| abstain | 100.0 (5) | 100.0 (5) | 80.0 (5) | 100.0 (5) | 100.0 (5) | 100.0 (5) | 0.0 (5) | 40.0 (5) |
| calc | 83.3 (6) | 0.0 (6) | 0.0 (6) | 16.7 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) |
| cell | 44.4 (9) | 0.0 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) |
| text_table | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) |
| unit_period | 20.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 20.0 (5) |


<!-- results:ko:end -->

<!-- results:training:start -->
| 실행 | 학습 예제/프롬프트 | 스텝 | 소요 (CPU 4스레드) | best dev verified EM % | dev 추이 % |
|---|---:|---:|---:|---:|---|
| SFT stage1 (ko 표) | 3431 | 858 | 120 min | 20.8 | 15.1, 20.8 |
| SFT stage2 (ko 표+본문) | 1542 | 193 | 30 min | 29.3 | 29.3 |
| SFT chem | 937 | 236 | 32 min | 42.5 | 38.8, 42.5 |
| GRPO RL v1 (ko) | 3485 | 60 | 29 min | 30.2 | 28.2, 30.2, 26.5, 24.1 |
| GRPO RL v2 (ko) | 3485 | 60 | 32 min | 30.6 | 28.2, 30.2, 30.6, 30.6 |

<!-- results:training:end -->

### 5.4 해석 — 무엇이 되고 무엇이 안 되었나

1. **튜닝은 실제로 효과가 있었다.** 미튜닝 mT5-small은 프로그램 문법을 몰라 출력이 전부 해석 불가(파싱 실패 <!-- num:experiments/eval/base_ko_test/metrics.json:metrics.parse_fail_rate:pct -->100.0<!-- /num -->%)이고, 시스템이 전부 보류한다. 점수 <!-- num:experiments/eval/base_ko_test/metrics.json:metrics.verified_em:pct -->7.1<!-- /num -->%는 정답이 "보류"인 <!-- num:experiments/eval/base_ko_test/metrics.json:metrics.n_gold_abstain:int -->50<!-- /num -->문항을 보류로 맞힌 값뿐이다. SFT stage 1 <!-- num:experiments/eval/sft_ko_ko_test/metrics.json:metrics.verified_em:pct -->25.0<!-- /num -->% → stage 2 <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.verified_em:pct -->27.5<!-- /num -->% → 화학 SFT 후 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->%(n=699, 1 표준오차 약 1.7%p).
2. **그러나 단순한 어휘 겹침 기준선을 전체 점수로는 넘지 못했다.** 기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->% > 최고 모델 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->%. 수작업 30문항에서도 기준선 <!-- num:experiments/eval/heuristic_ko_custom/metrics.json:metrics.verified_em:pct -->50.0<!-- /num -->% > SFT stage 2 <!-- num:experiments/eval/sft_ko2_ko_custom/metrics.json:metrics.verified_em:pct -->23.3<!-- /num -->%(표본 30: 1 표준오차 약 7–9%p).
3. **원본 데이터와 합성 데이터로 쪼개면 그림이 갈린다.** 원본 KorWikiTQ 539문항만 보면 화학 SFT 모델 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->37.1<!-- /num -->%가 기준선 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->26.2<!-- /num -->%를 앞선다. 합성 160문항(계산·보류)에서는 기준선 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:by_source_verified.synthetic.verified_em:pct -->70.0<!-- /num -->% 대 모델 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:by_source_verified.synthetic.verified_em:pct -->5.0<!-- /num -->%다. **이 합성 점수는 독립적인 비교가 아니다**: 합성 질문 템플릿과 기준선의 의도 정규식("차이", "합하면", "평균")을 같은 사람이 썼기 때문에 기준선에 유리하다. 전체 점수의 격차는 이 160문항이 만든 것이다.
4. **약한 고리는 셀 열 좌표다.** 모델이 인용한 셀 중 lookup 문항에서 행이 맞은 비율은 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:lookup_citation.row_correct:pct -->77.7<!-- /num -->%인데 열이 맞은 비율은 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:lookup_citation.col_correct:pct -->27.8<!-- /num -->%에 그친다(기준선은 열 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:lookup_citation.col_correct:pct -->56.7<!-- /num -->%). 질문의 속성어를 헤더와 맞추는 일을 작은 모델이 2 epoch 안에 배우지 못했다.
5. **검증기의 "근거 복구"가 많이 개입한다.** 모델의 답 텍스트는 표 어딘가에 있는 값을 정확히 베껴 쓰는 경우가 많지만 좌표는 틀린다. 답 텍스트가 표에서 유일한 셀이면 그 셀을 근거로 삼고 `evidence_repaired` 검사를 실패로 기록한다. 화학 SFT 모델은 답한 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:pred_status_answerable.answered:int -->523<!-- /num -->문항 중 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:evidence_repaired:int -->386<!-- /num -->건이 복구였다. 그래서 표의 "근거 셀 일치(모델 인용)" 열(<!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.evidence_cells_exact_raw:pct -->17.1<!-- /num -->%)이 "최종" 열(<!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.evidence_cells_exact:pct -->30.8<!-- /num -->%)보다 낮다. **모델 자체가 올바른 근거를 댄 비율은 후자가 아니라 전자**다.
6. **계산은 거의 못 한다.** 모델은 연산 종류(diff/sum/avg)는 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.op_acc:pct -->78.1<!-- /num -->% 맞히지만 서로 다른 두 행의 같은 열 셀을 모두 맞혀야 해서 계산 정답률이 <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.calc_em:pct -->4.5<!-- /num -->%(stage 2) 수준이다. 화학 SFT 후에는 계산 문항을 대부분 lookup으로 처리해 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.calc_em:pct -->0.0<!-- /num -->%가 되었다(치명적 망각 의심: 화학 학습 데이터가 lookup 중심).
7. **보류는 모델의 판단이 아니다.** 답이 없는 문항에서 최종 상태가 보류인 비율(보류 재현율)은 화학 SFT <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.abstain_recall:pct -->16.0<!-- /num -->%, RL v1 <!-- num:experiments/eval/rl_ko_v1_ko_test/metrics.json:metrics.abstain_recall:pct -->34.0<!-- /num -->%로 기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.abstain_recall:pct -->94.0<!-- /num -->%보다 훨씬 낮다. 더 중요한 점은 이 숫자 자체가 우연한 보류를 포함한다는 것이다. 모델이 **직접** `op: abstain`을 낸 비율은 SFT stage 2 <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->0.0<!-- /num -->%, RL v1 <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->0.0<!-- /num -->%이고 기준선은 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->94.0<!-- /num -->%다. 모델의 보류는 해석 불가·퇴화 프로그램(SFT stage 2 <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:abstain_breakdown.abstained_via_invalid_program_recall:pct -->12.0<!-- /num -->%)이나 검증 실패(<!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:abstain_breakdown.abstained_via_verifier_recall:pct -->14.0<!-- /num -->%)로 우연히 일어난 것이다. 같은 셀을 두 번 쓰는 퇴화 계산 출력은 test <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:n:int -->699<!-- /num -->문항 중 SFT stage 2에서 <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:degenerate_calc_outputs:int -->101<!-- /num -->건이었고 RL v1에서 <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:degenerate_calc_outputs:int -->160<!-- /num -->건으로 늘었다. 또한 검증기는 인용한 셀이 질문의 대상에 대한 것인지는 확인하지 않아, 표에 없는 대상에 엉뚱한 셀을 인용해 답해도 통과한다(수작업 `ko_custom_08`, README §11). 따라서 "모델이 근거 부족을 판단해 보류한다"는 주장은 이 실험으로 뒷받침되지 않는다.
8. **본문+표 범주는 실패했고, 원인은 학습 데이터 설계 결함이다.** 어떤 모델도 평가 문항 62개(한국어 수작업 30 + 화학 수작업 32)에서 `op: text`를 **한 번도 내지 않았다**(본문 답변이 정답인 문항은 한국어 6, 화학 7). 그러나 학습과 같은 형식(KorQuAD 본문 + **행이 없는 빈 표**)의 dev 100문항에서는 stage 2 모델이 `op: text`를 <!-- num:experiments/eval/sft_ko2_text_dev/analysis.json:op_confusion_top.0.1:int -->99<!-- /num -->번 내고 <!-- num:experiments/eval/sft_ko2_text_dev/metrics.json:metrics.verified_em:pct -->29.0<!-- /num -->%를 맞힌다. 즉 모델은 "본문에서 답을 베끼는 법"이 아니라 **"표에 행이 없으면 text"라는 형식 지름길**을 배웠다. 학습의 text 예제를 실제 표와 함께 만들고(답이 표가 아닌 본문에 있는 경우) 표 질문과 섞어야 한다. 이 수정은 재학습이 필요해 **하지 않았다**(다음 실험 1순위).
9. **단위·기간 범주도 0에 가깝다.** 연도·기간 조건으로 행을 고르거나 표기 단위가 다른 셀을 구별해야 하는 5문항을 모든 모델이 풀지 못했다(기준선도 <!-- num:experiments/eval/heuristic_ko_custom/metrics.json:metrics.by_category.unit_period.verified_em:pct -->20.0<!-- /num -->%, 5문항 중 1문항).

## 6. 영어 화학 문서 — 데이터·모델·평가

### 6.1 데이터

OpenStax *Chemistry 2e*(Rice University, CC BY-NC-SA 4.0, 비상업 연구 용도) CNXML 원본에서 표가 있는 문서 <!-- num:data/chem/build_report.json:documents_with_tables:int -->56<!-- /num -->개, 표 <!-- num:data/chem/build_report.json:tables:int -->113<!-- /num -->개, 본문 문단 <!-- num:data/chem/build_report.json:passages:int -->3,780<!-- /num -->개를 구축했다. MathML은 평문(`H2O`, `10^−6`)으로 풀었고 헤더에서 단위(`kPa`, `K`, `°C`, `mol/L`)를 파싱한다. 문서(모듈) 단위로 train 40 / dev 5 / test 11로 나눴고(`data/chem/split.json`), 수작업 평가 32문항은 모두 test 문서 8개 위에 작성했다(`check_data.py`가 test 분할 밖의 문서를 거부). 학습에는 train 문서의 표에서 만든 합성 QA(lookup 420, diff 120, ratio 60, sum 60, abstain 160)를 썼다.

논문·특허 사이트(PMC, ChemRxiv, Google Patents 등)가 차단되어 **논문 속 실험 데이터가 아니라 교과서의 데이터 표**를 쓴 것이 한계다. 교과서는 문장이 설명적이고 표가 깨끗해 실제 논문보다 쉽다.

### 6.2 결과 (튜닝 전후 비교)

"튜닝 전"은 영어 화학 데이터를 보지 않은 stage 2 모델, "튜닝 후"는 화학 SFT 모델이며 같은 32문항·같은 검증기·같은 CPU에서 평가했다.

<!-- results:chem:start -->
**영어 화학 문서 — 수작업 32문항 (test 분할 문서)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 32 | **56.2** | 40.7 | 84.6 | 14.3 | 55.6 | 55.6 | 100.0 | 25.9 | 0.0 | 0 |
| mT5-small 기본(미튜닝) | 32 | **15.6** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 138 |
| SFT stage1 | 32 | **12.5** | 18.5 | 7.7 | 0.0 | 3.7 | 7.4 | 60.0 | 70.4 | 0.0 | 399 |
| SFT stage2(+본문) | 32 | **9.4** | 7.4 | 0.0 | 0.0 | 0.0 | 0.0 | 60.0 | 81.5 | 0.0 | 352 |
| GRPO RL v1 (보상 허점) | 32 | **15.6** | 7.4 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 81.5 | 3.1 | 424 |
| GRPO RL v2 (보상 수정) | 32 | **12.5** | 7.4 | 0.0 | 0.0 | 0.0 | 7.4 | 80.0 | 85.2 | 0.0 | 426 |
| 화학 SFT | 32 | **15.6** | 22.2 | 7.7 | 7.1 | 7.4 | 22.2 | 60.0 | 66.7 | 3.1 | 459 |
| 화학 SFT + int8 동적 양자화 | 32 | **25.0** | 14.8 | 30.8 | 0.0 | 14.8 | 11.1 | 80.0 | 59.3 | 21.9 | 328 |

**영어 화학 — 합성 dev 80문항(템플릿, 참고용)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SFT stage2(+본문) | 80 | **22.5** | 26.6 | 22.5 | 0.0 | 14.1 | 23.4 | 56.2 | 57.8 | 0.0 | 442 |
| 화학 SFT | 80 | **41.2** | 39.1 | 57.5 | 8.3 | 26.6 | 29.7 | 50.0 | 35.9 | 2.5 | 521 |

**화학 수작업 — 범주별 verified EM % (n)**

| 범주 | 휴리스틱 기준선 | mT5-small 기본(미튜닝) | SFT stage1 | SFT stage2(+본문) | GRPO RL v1 (보상 허점) | GRPO RL v2 (보상 수정) | 화학 SFT | 화학 SFT + int8 동적 양자화 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| abstain | 100.0 (5) | 100.0 (5) | 60.0 (5) | 60.0 (5) | 100.0 (5) | 80.0 (5) | 60.0 (5) | 80.0 (5) |
| calc | 28.6 (7) | 0.0 (7) | 0.0 (7) | 0.0 (7) | 0.0 (7) | 0.0 (7) | 14.3 (7) | 0.0 (7) |
| cell | 80.0 (10) | 0.0 (10) | 10.0 (10) | 0.0 (10) | 0.0 (10) | 0.0 (10) | 10.0 (10) | 20.0 (10) |
| text_table | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) |
| unit_period | 75.0 (4) | 0.0 (4) | 0.0 (4) | 0.0 (4) | 0.0 (4) | 0.0 (4) | 0.0 (4) | 50.0 (4) |


<!-- results:chem:end -->

### 6.3 해석

1. **분포 안(합성 dev 80)에서는 확실히 올랐다**: <!-- num:experiments/eval/sft_ko2_chem_syndev/metrics.json:metrics.verified_em:pct -->22.5<!-- /num -->% → <!-- num:experiments/eval/sft_chem_chem_syndev/metrics.json:metrics.verified_em:pct -->41.2<!-- /num -->%. 그러나 합성 dev는 학습 데이터와 같은 템플릿이라 일반화 증거가 아니다.
2. **손으로 쓴 32문항에서는 유의한 개선이 아니다**: <!-- num:experiments/eval/sft_ko2_chem_custom/metrics.json:metrics.verified_em:pct -->9.4<!-- /num -->% → <!-- num:experiments/eval/sft_chem_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num -->%(32문항 중 2문항 차이, 1 표준오차 약 6%p). 기준선 <!-- num:experiments/eval/heuristic_chem_custom/metrics.json:metrics.verified_em:pct -->56.2<!-- /num -->%가 모든 모델보다 높다. **참고로 모든 입력을 보류하는 미튜닝 모델도 <!-- num:experiments/eval/base_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num -->%(보류가 정답인 5문항)라, 화학 SFT는 이 자명한 점수와 같은 값이다.** 즉 이 평가셋에서는 화학 SFT가 "아무것도 하지 않는 시스템"보다 낫다는 증거가 없다.
3. **모델이 인용한 근거 셀의 정확도**는 화학 SFT 후 <!-- num:experiments/eval/sft_chem_chem_custom/metrics.json:metrics.evidence_cells_exact_raw:pct -->22.2<!-- /num -->%(32문항 중 답이 있는 문항 기준)로 낮고, 보류 재현율은 <!-- num:experiments/eval/sft_chem_chem_custom/metrics.json:metrics.abstain_recall:pct -->60.0<!-- /num -->%(5문항 중)다.
4. **수치·단위 오류**: 계산 문항에서 단위가 틀린 비율은 정의상 계산 결과가 나온 문항에서만 계산된다(`unit_error_rate` = <!-- num:experiments/eval/sft_chem_chem_custom/metrics.json:metrics.unit_error_rate:pct -->0.0<!-- /num -->%). 계산이 거의 성립하지 않아 이 값은 표본이 너무 작아 의미가 없다. lookup 답은 셀 텍스트와 단위를 그대로 가져오므로 단위 오류는 곧 셀 오류로 나타난다. 단위 환산(원↔억원, kPa↔atm)은 지원하지 않는다.
5. **한국어에 대한 부작용 가능성**: 화학 SFT 후 한국어 수작업 30문항의 점수가 <!-- num:experiments/eval/sft_ko2_ko_custom/metrics.json:metrics.verified_em:pct -->23.3<!-- /num -->% → <!-- num:experiments/eval/sft_chem_ko_custom/metrics.json:metrics.verified_em:pct -->3.3<!-- /num -->%로 떨어지고 보류 재현율이 <!-- num:experiments/eval/sft_chem_ko_custom/metrics.json:metrics.abstain_recall:pct -->0.0<!-- /num -->%가 되었다(표본 30이라 확정은 못 한다). 한국어 독립 test(539+160)는 오히려 올랐다. 보류 행동은 학습 데이터 구성에 민감한 것으로 보인다.
6. **본문 근거(문장)**: `text_table` 범주는 모든 모델이 0%다. 한국어와 마찬가지로 모델은 화학 문서에서 `op: text`를 한 번도 내지 않았다(원인은 §5.4의 8번).

## 7. 강화학습 — 방법·조건·비교

### 7.1 방법

GRPO 방식 정책 경사를 PyTorch로 직접 구현했다(TRL은 쓰지 않았다. GRPOTrainer는 causal LM 기준으로 알려져 있어 mT5에 시험하지 않고 같은 수식을 직접 구현했다). 프롬프트 4개 × 샘플 G=4, 샘플링 temperature 1.0, 보상은 검증기 기반(정답, 근거 셀 일치, 연산 일치, 보류의 적절성). 이점은 그룹 내 평균·표준편차 정규화, 손실은 −A·log π + β·KL(k3 추정, 참조=SFT stage 2 모델), β=0.02, lr 1e-5, 60 step, on-policy 1회 업데이트. 이것은 샘플링→보상→정책 업데이트를 실제로 수행한 강화학습이며 DPO 같은 선호 학습이나 SFT가 아니다. 설계 문서: docs/experiments/rl.md.

### 7.2 실행 이력 — 두 번의 수정

1. **첫 시도(NaN)**: step 1의 KL이 770, 이후 3×10⁶으로 폭발하다 NaN으로 종료. 원인은 정책만 dropout이 켜진 학습 모드로 로그확률을 계산한 것(참조는 평가 모드). 평가 모드로 고쳐 KL이 0.0에서 시작함을 확인(§13의 23번).
2. **보상 편법 발견(v1)**: 수정한 첫 정상 실행(v1)에서 보상이 거의 오르지 않는 동안 정책이 이동했다. 아래 v1 표에서 모델의 명시적 abstain은 소폭 늘었지만 최종 보류율이 더 크게 올랐고, 출력이 lookup에서 diff로 옮겨 갔다. 원인은 보상 함수가 "답 없는 문항에서 최종 상태가 보류면 +1.0"으로 채점해서, **검증기가 거부한 쓰레기 프로그램(같은 셀 두 번, 범위 밖 셀)이 의도적 보류와 같은 점수**를 받은 것이다. v1 산출물은 증거로 보존했다(`experiments/rl_ko_v1/`).
3. **v2 보상**: 모델이 직접 `op: abstain`을 낸 경우만 +1.0, 검증기가 잡은 근거 없는 제안 +0.2, 해석 불가·퇴화 프로그램 0.0(답이 있는 문항에서는 −0.5). 회귀 테스트가 이를 고정한다. v2는 SFT stage 2 모델에서 처음부터 다시 학습했다.

### 7.3 v1 (편법 보상) 학습 곡선

<!-- results:rl_v1:start -->
| 구간(step) | 평균 보상 | 샘플 정답률 % | 샘플 최종 보류율 % | 모델이 명시적으로 abstain한 비율 % | lookup 비율 % | diff 비율 % | KL | 그룹 분산 0 비율 % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1–15 | 0.019 | 28.8 | 63.3 | 7.5 | 59.2 | 26.7 | 0.0008 | 18.3 |
| 16–30 | 0.005 | 24.2 | 57.5 | 5.8 | 45.0 | 40.0 | 0.0041 | 18.3 |
| 31–45 | -0.007 | 25.8 | 60.0 | 5.4 | 41.7 | 44.2 | 0.0116 | 20.0 |
| 46–60 | 0.057 | 28.4 | 70.8 | 12.1 | 35.4 | 45.4 | 0.0157 | 25.0 |

dev verified EM(n=245): step 0: 28.2% → step 20: 30.2% → step 40: 26.5% → step 60: 24.1%

**평가에 쓴 체크포인트: step 20** (dev 최고로 선택; 마지막 step이 아님). 60 step wall time 29 min, CPU 4스레드.

<!-- results:rl_v1:end -->

### 7.4 v2 (수정한 보상) 학습 곡선

<!-- results:rl:start -->
| 구간(step) | 평균 보상 | 샘플 정답률 % | 샘플 최종 보류율 % | 모델이 명시적으로 abstain한 비율 % | lookup 비율 % | diff 비율 % | KL | 그룹 분산 0 비율 % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1–15 | -0.165 | 13.7 | 63.3 | 7.5 | 60.0 | 25.4 | 0.0007 | 13.3 |
| 16–30 | -0.209 | 9.2 | 59.6 | 8.8 | 45.4 | 38.8 | 0.0039 | 13.3 |
| 31–45 | -0.121 | 15.8 | 59.6 | 10.4 | 40.0 | 36.2 | 0.0053 | 10.0 |
| 46–60 | -0.100 | 16.2 | 61.7 | 15.0 | 43.8 | 32.1 | 0.0092 | 8.3 |

dev verified EM(n=245): step 0: 28.2% → step 20: 30.2% → step 40: 30.6% → step 60: 30.6%

**평가에 쓴 체크포인트: step 60** (dev 최고가 마지막 step과 일치). 60 step wall time 32 min, CPU 4스레드.

<!-- results:rl:end -->

### 7.5 비교 — 기본 / SFT / RL (동일 독립 평가셋)

위 §5.3, §6.2 표의 "SFT stage2", "GRPO RL v1", "GRPO RL v2" 행이 같은 평가셋·같은 검증기 결과다. RL의 출발점은 SFT stage 2이므로 비교 대상은 그 행이다.

**v2 결과 요약 — 개선이라고 말할 수 없다.**

| 지표 | SFT stage 2 | RL v1(편법 보상) | RL v2(수정 보상) |
|---|---:|---:|---:|
| 한국어 test 699문항 verified EM % | <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.verified_em:pct -->27.5<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_test/metrics.json:metrics.verified_em:pct -->26.8<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_test/metrics.json:metrics.verified_em:pct -->27.0<!-- /num --> |
| 오보류율 % | <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.false_abstain_rate:pct -->31.0<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_test/metrics.json:metrics.false_abstain_rate:pct -->37.9<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_test/metrics.json:metrics.false_abstain_rate:pct -->35.9<!-- /num --> |
| 퇴화 계산 출력(건) | <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:degenerate_calc_outputs:int -->101<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:degenerate_calc_outputs:int -->160<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_test/analysis.json:degenerate_calc_outputs:int -->146<!-- /num --> |
| 모델이 직접 낸 `op: abstain`(건) | <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->0<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->0<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->6<!-- /num --> |
| └ 그중 답이 있는 문항에서 낸 것(건) | <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:abstain_breakdown.explicit_abstain_on_answerable:int -->0<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:abstain_breakdown.explicit_abstain_on_answerable:int -->0<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_test/analysis.json:abstain_breakdown.explicit_abstain_on_answerable:int -->6<!-- /num --> |
| 한국어 수작업 30문항 verified EM % | <!-- num:experiments/eval/sft_ko2_ko_custom/metrics.json:metrics.verified_em:pct -->23.3<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_custom/metrics.json:metrics.verified_em:pct -->20.0<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_custom/metrics.json:metrics.verified_em:pct -->20.0<!-- /num --> |
| 화학 수작업 32문항 verified EM % | <!-- num:experiments/eval/sft_ko2_chem_custom/metrics.json:metrics.verified_em:pct -->9.4<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num --> | <!-- num:experiments/eval/rl_ko_chem_custom/metrics.json:metrics.verified_em:pct -->12.5<!-- /num --> |

1. **test 차이는 잡음 범위다.** 699문항에서 verified EM의 1 표준오차는 약 1.7%p이고 SFT stage 2와 v2의 차이는 그보다 작다. 수작업 30·32문항의 차이는 1–3문항이다.
2. **오보류가 늘었다.** 답이 있는 문항을 보류하는 비율이 SFT stage 2보다 높다. 원인은 검증하지 않았다.
3. **dev에서는 올랐으나 test로 전이되지 않았다.** dev 245문항(체크포인트 선택에도 사용)의 verified EM <!-- num:experiments/rl_ko/summary.json:dev_history.0.verified_em:pct -->28.2<!-- /num -->% → <!-- num:experiments/rl_ko/summary.json:dev_history.3.verified_em:pct -->30.6<!-- /num -->%. 이 분할의 1 표준오차는 약 2.9%p이고 선택에 쓰였으므로 낙관적이다.
4. **보상 편법 분석.** v1은 쓰레기 프로그램이 보류 점수를 받았다(§7.2). v2는 이를 막았지만 퇴화 계산 출력이 SFT stage 2보다 많고, §7.4 표의 diff 비율이 보여 주듯 lookup에서 diff로의 정책 이동도 남았다. 보상이 검증기 판정에 의존하므로 검증기가 못 보는 것(질문 대상과 셀의 일치, §5.4)은 보상으로도 학습되지 않는다.
5. **보류 학습은 평가로 전이되지 않았다.** 샘플링 중 명시적 abstain 비율은 올랐지만 탐욕 디코딩 평가에서 답 없는 문항에 직접 낸 `op: abstain`은 0건이고, 낸 것은 모두 답이 있는 문항이었다.
6. **원인은 검증하지 않았다(추정).** 총 샘플 960개(60 step × 4 프롬프트 × 4 샘플), 낮은 샘플 정답률로 인한 희박한 보상, 그룹 내 보상이 같아 신호가 없는 그룹(§7.4 표). 더 긴 학습, β·학습률·보상 크기 조정은 하지 않았다.

**상태 판단**: 구현·정책 갱신·동일 평가셋 비교까지 수행했으나 목표(검증된 정답률 향상, 올바른 보류)를 달성하지 못해 공고 대조표에는 **실행했으나 실패**로 적었다. 이 결과는 "강화학습으로 성능을 올렸다"는 주장을 뒷받침하지 않는다.


## 8. 추론 최적화 — 조건과 측정

선택 이유: GPU가 없어 CUDA 전용 엔진(vLLM·SGLang·TensorRT-LLM)을 쓸 수 없다. CPU에서 효과를 기대할 수 있는 방법만 적용·측정했다. (a) **KV 캐시**(디코딩 비용 O(T²)→O(T)), (b) **배치 처리**, (c) **int8 동적 양자화**(`nn.Linear` 가중치). 정밀도마다 **별도 프로세스**에서 측정해 메모리를 분리했다. 모든 값은 `experiments/bench/inference.json`에서 가져온다.

<!-- results:bench:start -->
조건: models/mt5-small-tabletrace(화학 SFT 모델), 입력 48개(ko test), max_new_tokens 48, 워밍업 1라운드 + 측정 2라운드, 4 스레드, 4 cores x86_64, torch 2.15.0+cu132, CUDA False. 정밀도마다 **별도 프로세스**에서 측정(메모리 비교를 위해). int8 준비 8.3 s.

| 설정 | p50 ms | p95 ms | 처리량 예제/s | 모델 파일 MB | 프로세스 peak RSS GB | fp32 bs=1과 출력 문자열 일치 % |
|---|---:|---:|---:|---:|---:|---:|
| fp32, bs=1, kv-cache on | 995.7 | 1484.1 | 0.985 | 1200.8 | 3.38 | 100.0 |
| fp32, bs=8, kv-cache on | 446.9 | 555.2 | 2.196 | 1200.8 | 3.38 | 100.0 |
| fp32, bs=1, kv-cache OFF | 2736.9 | 3674.2 | 0.356 | 1200.8 | 3.38 | 100.0 |
| int8, bs=1, kv-cache on | 594.1 | 729.0 | 1.676 | 684.6 | 3.73 | 35.4 |
| int8, bs=8, kv-cache on | 273.4 | 333.1 | 3.66 | 684.6 | 3.73 | 22.9 |

<!-- results:bench:end -->

읽는 법과 주의:

1. **KV 캐시는 필수다**: 끄면 p50이 <!-- num:experiments/bench/inference.json:results.0.p50_ms -->995.7<!-- /num --> ms → <!-- num:experiments/bench/inference.json:results.2.p50_ms -->2,736.9<!-- /num --> ms(약 2.7배 느림)로 늘어난다.
2. **배치 처리는 처리량을 약 2.2배 올린다**(fp32 bs=1 <!-- num:experiments/bench/inference.json:results.0.throughput_ex_per_s -->0.985<!-- /num --> → bs=8 <!-- num:experiments/bench/inference.json:results.1.throughput_ex_per_s -->2.2<!-- /num --> 예제/s).
3. **int8 동적 양자화는 빠르고 파일이 작지만 정확도를 크게 해친다.** 파일 <!-- num:experiments/bench/inference.json:results.0.state_dict_mb -->1,200.8<!-- /num --> MB → <!-- num:experiments/bench/inference.json:results.3.state_dict_mb -->684.6<!-- /num --> MB(250k×512 임베딩과 lm_head는 fp32로 남아 절반에 못 미침). 처리량은 bs=8에서 <!-- num:experiments/bench/inference.json:results.1.throughput_ex_per_s -->2.2<!-- /num --> → <!-- num:experiments/bench/inference.json:results.4.throughput_ex_per_s -->3.7<!-- /num --> 예제/s. **그러나 출력 문자열이 fp32와 일치하는 비율은 bs=1에서 <!-- num:experiments/bench/inference.json:results.3.agreement_with_fp32_bs1:pct -->35.4<!-- /num -->%뿐이고, 평가셋 점수도 한국어 독립 test verified EM <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->% → <!-- num:experiments/eval/sft_chem_int8_ko_test/metrics.json:metrics.verified_em:pct -->17.7<!-- /num -->%, lookup EM <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.lookup_em:pct -->37.1<!-- /num -->% → <!-- num:experiments/eval/sft_chem_int8_ko_test/metrics.json:metrics.lookup_em:pct -->18.6<!-- /num -->%로 떨어지고 오보류율이 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.false_abstain_rate:pct -->19.4<!-- /num -->% → <!-- num:experiments/eval/sft_chem_int8_ko_test/metrics.json:metrics.false_abstain_rate:pct -->55.3<!-- /num -->%로 뛴다.** 작은 수작업 평가셋(30·32문항)에서는 오히려 올라가지만(보류가 늘어 보류 문항이 맞는 효과) 표본이 작고 같은 방향의 개선으로 읽으면 안 된다. 따라서 이 모델에서 int8 동적 양자화는 **공짜 최적화가 아니다.** mT5는 활성값 이상치에 민감한 것으로 알려져 있어 선택적 양자화(민감한 층 제외)나 정적 양자화를 시도해 볼 만하지만 **시도하지 않았다.**
4. **메모리**: 프로세스 최대 RSS는 fp32 <!-- num:experiments/bench/inference.json:results.0.peak_rss_gb -->3.4<!-- /num --> GB, int8 <!-- num:experiments/bench/inference.json:results.3.peak_rss_gb -->3.7<!-- /num --> GB로 **int8이 오히려 크다.** `quantize_dynamic`이 fp32 모델을 먼저 올린 뒤 변환하기 때문에 최대치에 두 모델이 겹친다. 서빙 시 상주 메모리를 줄이려면 양자화된 가중치를 파일에서 직접 로드해야 하며 구현하지 않았다.
5. **변동성**: 공유 VM이라 같은 설정의 p50이 실행마다 20% 이상 달라질 수 있다(앞선 오염된 실행에서 fp32 bs=1 p50이 이번보다 약 25% 낮게 관측되었다). 단일 실행의 절대값이 아니라 설정 간 비율을 보라. 반복은 측정 2라운드(워밍업 1)뿐이라 신뢰구간은 구하지 않았다.
6. **실행하지 않은 것**: vLLM/SGLang 서빙, GPU 지연·메모리, 그 외 양자화(GPTQ/AWQ), 컴파일(torch.compile), ONNX. 이것들은 성능을 주장하지 않는다.

## 9. 멀티 GPU Model Parallelism — 방식·환경·결과

**수행한 것은 CPU 2프로세스 기능 검증이며 GPU 병렬 실험은 하지 못했다.** 이 컨테이너에는 GPU가 없다(`nvidia-smi` 없음, `torch.cuda.is_available()`=False).

- **방식**: 2-스테이지 **파이프라인 모델 병렬**(`bench/pipeline_parallel.py`). rank 0이 인코더(공유 임베딩 포함), rank 1이 디코더+lm_head를 들고, rank 0이 인코딩한 hidden state를 `torch.distributed` `send/recv`로 rank 1에 보내면 rank 1이 greedy 디코딩 후 토큰 id를 돌려준다. 한 모델을 두 프로세스에 나눈 것이며, GPU마다 모델을 복제하는 DDP가 아니다.
- **환경**: CPU 4코어, 백엔드 `gloo`, 프로세스당 2 스레드. 모델은 mT5-small 화학 SFT 모델.

<!-- results:pp:start -->
조건: CPU(gloo), n=16, bs=8, 단일 프로세스 300,176,768 파라미터

| 구성 | 장치 | 스테이지 파라미터 | 처리량 예제/s | 메모리 MB | 평균 배치 지연 s |
|---|---|---:|---:|---:|---:|
| 단일 프로세스 | cpu | 300,176,768 | 1.472 | 1747 | 5.44 |
| 파이프라인 rank0 (encoder) | cpu | 146,940,608 | 1.46 | 1159 | 5.47 |
| 파이프라인 rank1 (decoder+lm_head) | cpu | 281,293,504 |  | 1618 | 5.47 |

단일 프로세스와 2-스테이지의 생성 출력 일치: **예** (16개 입력)

<!-- results:pp:end -->

- **분할 확인**: rank 0은 파라미터 <!-- num:experiments/bench/pp_2stage.json:stages.0.stage_params:int -->146,940,608<!-- /num -->개(인코더+임베딩), rank 1은 <!-- num:experiments/bench/pp_2stage.json:stages.1.stage_params:int -->281,293,504<!-- /num -->개(디코더+임베딩+lm_head)를 가졌다. 합이 전체 300,176,768보다 큰 것은 공유 임베딩(약 1.28억)이 인코더 입력과 디코더 입력에 모두 필요해 **양쪽에 복제**되었기 때문이다. 나머지 레이어는 분할되었다.
- **정확성**: 같은 16개 입력에서 단일 프로세스와 2-스테이지의 생성 출력이 **모두 일치**했다.
- **성능**: 처리량 이득 **없음**(단일 <!-- num:experiments/bench/pp_single.json:throughput_ex_per_s -->1.5<!-- /num --> vs 2-스테이지 <!-- num:experiments/bench/pp_2stage.json:throughput_ex_per_s -->1.5<!-- /num --> 예제/s). 두 프로세스가 같은 4코어를 나눠 쓰고 마이크로배치 파이프라이닝이 없어 스테이지가 순차 실행되므로 예상된 결과이며, 이 실험은 속도를 보이려는 것이 아니다.
- **GPU별 메모리·지연·처리량은 측정하지 못했다.** 실행 명령, 필요 자원(GPU 2장, 각 ≥8 GB), 예상 시간(분 단위)과 비용(시간당 $1–3 기준 $1 미만)은 docs/experiments/parallel.md. vLLM 텐서 병렬(`--tensor-parallel-size 2`) 서빙 스크립트도 준비만 했다.

## 10. 테스트와 반복 검증

| 검증 | 방법 | 실행 횟수·결과 |
|---|---|---|
| 데이터 출처·라이선스 | 저장소 LICENSE·README를 직접 확인, docs/research/datasets.md | 1회 기록 |
| 데이터 분할·누수 | `scripts/check_data.py`: 표·문서 공유 0, 수작업·합성 정답의 자동 검수 | 데이터를 만들 때마다 실행, 마지막 실행 오류 0 |
| 평가 재현성 | 모든 평가가 `tabletrace.eval.run`으로 metrics.json + predictions.jsonl 생성. 평가 코드 수정 후 **모든 모델을 같은 코드로 다시 평가**(`scripts/train/finalize.sh`) | 플래너·모델 8종(기준선·미튜닝·SFT 3·RL 2·int8)을 한국어 test·한국어 수작업·화학 수작업 평가셋에서 재평가 |
| 단위·API 테스트 | `pytest -q tests`: 숫자·계산기·문법·검증기·휴리스틱·검색·API·엔진·학습 데이터·RL 보상·모델 | 최종 <!-- num:experiments/tests/summary.json:passed -->82<!-- /num -->개 통과, <!-- num:experiments/tests/summary.json:skipped -->0<!-- /num -->개 skip, <!-- num:experiments/tests/summary.json:failed -->0<!-- /num -->개 실패(모델 가중치가 없으면 모델 테스트는 skip) |
| 콘솔 E2E | Playwright, 데스크톱 1440×900·모바일 390×844 × 실시간/정적 모드 | 실시간 <!-- num:docs/images/e2e-summary.json:live.passed -->16<!-- /num -->/<!-- num:docs/images/e2e-summary.json:live.total -->16<!-- /num -->, 정적 <!-- num:docs/images/e2e-summary.json:static.passed -->13<!-- /num -->/<!-- num:docs/images/e2e-summary.json:static.total -->13<!-- /num --> 검사 통과 (`docs/images/e2e-*.json`). 이전 실행에서 실패 2회→수정→재실행 |
| Docker | 이미지 빌드 + 컨테이너 smoke(health, release, corpora, ask, 콘솔) | 빌드가 여러 번 실패(데몬 미실행, Docker Hub·ECR 429, 프록시 CA TLS 오류)한 뒤 성공, smoke 통과 |
| 학습 전후 비교 | 동일 test·custom 세트에서 미튜닝/SFT1/SFT2/RL v1/RL v2/화학 SFT/int8 평가 | §5–§8 |
| 추론 최적화 | 정밀도별 별도 프로세스, 워밍업 1 + 측정 2라운드, 양자화 모델의 정확도 평가 | §8. 첫 실행은 메모리 비교가 무효이고 측정 중 테스트를 돌려 오염되어 **폐기하고 재실행** |
| 병렬 | 2-스테이지 파이프라인의 출력이 단일 프로세스와 일치하는지 | §9 (smoke 1회 + 본 실행) |
| 검색 | 전체 표 대상 BM25 hit@1/5 | §3 표와 `experiments/eval/retrieval/metrics.json` |
| 문서 수치 | 본문 수치는 표식으로 산출물에 묶고, 표는 `render_results.py --check`로 대조. 값을 바꿔 넣으면 실패함을 시연 | `scripts/check_numbers.py --strict` |
| 반복 수정 | docs/dev/issues-log.md 32건: 발견 → 수정 → 재검증 | 아래 §13 |

실제 반복의 예: RL은 NaN 종료 → 수정 후 v1 완주 → 보상 편법 발견 → v2 재학습(실행 3회), 추론 벤치는 2회(첫 실행 폐기), E2E는 실패 후 수정·재실행을 반복, 평가 코드는 채점 방식 수정 후 모든 모델을 같은 코드로 재평가.

## 11. UI 조사와 디자인 반영

조사한 화면(docs/design/ui-research.md): Microsoft Document Intelligence 샘플 라벨링 도구(OCR Form Tools 스크린샷 4장 직접 확인), Google Document AI Workbench 제품 페이지, Label Studio, doccano, MLflow 트레이스 뷰·게이트웨이 대시보드, promptfoo 평가 표, Marker 벤치마크 차트, Tabula, PaddleOCR. 제품 문서 사이트 대부분이 차단되어 GitHub 공개 스크린샷·README와 Google Cloud 페이지를 썼다(확인하지 못한 화면은 문서에 "미확인"으로 표시).

**데모 배경 조사**: "AI가 흔히 만드는 데모 배경은 금지"라는 요구를 데모 화면의 바탕(캔버스)에 대한 것으로 해석하고, OCR Form Tools·MLflow(트레이스·평가)·promptfoo·doccano·Marker의 화면 7장을 새로 받아 바탕 색을 측정하고 그중 4장은 직접 열어 눈으로 확인했다(docs/design/ui-research.md "데모 배경 조사", 표본이 작다). 눈으로 본 4장은 모두 그라데이션·질감·블러 없이 단색 중립면 위에 실제 콘텐츠를 올렸고, 색은 상태·근거에만 썼다. Label Studio·Streamlit·Gradio는 이미지를 받지 못해 조사했다고 쓰지 않았다. TableTrace는 단색 `#f5f6f8` 바탕·흰 패널·1px 선에 실제 위키·교과서 표를 올리고, `tests/test_console_style.py`(5개)가 장식 배경의 재유입을 막는다. 다른 해석(데모 장면 구성)이 의도였는지는 확인하지 못했다.

| 관찰 | TableTrace 반영 (docs/design/screens.md, console/) |
|---|---|
| 3단(목록 / 문서 / 속성) 레이아웃이 공통 | 문서 목록 / 본문·표 / 질문·결과 3열, 모바일은 탭 |
| 문서 위 하이라이트와 오른쪽 필드가 색·번호로 짝지어짐 | 근거 셀에 노란 테두리+번호 배지, 오른쪽 근거 배지를 누르면 셀로 이동·강조, 본문 근거는 문장 하이라이트 |
| 예측값 옆 신뢰도·페이지 배지 | 모델 확률 대신 **검증기 판정**(통과 검사 수, 보류 사유)과 r/c 좌표 배지 |
| 긴 작업의 상태 바, PASS/FAIL 배지 | 대기→실행 중(경과 ms)→완료/보류/오류/시간 초과 상태 띠, 작업 ID, 429/422 메시지와 재시도 |
| 트레이스 트리 + 상세 탭 | 실행 추적 카드: LangGraph 노드·도구 호출·소요 ms, 입력/출력 펼치기, 플래너 원문 출력 |
| 평가 표 + 조건 요약 | 연구 결과 화면: 각 표 위에 실행 조건, 상태 필(완료/미실행/실패) |
| 튜토리얼식 첫 화면 | 4단계 안내 띠(닫기 가능) + 문서별 대표 질문 칩(범주 표시) |
| 실시간 vs 저장 결과 | 상단 배지와 결과 카드 배지로 구분, 저장 결과에는 기록 시각·모델·커밋. 저장 결과 모드는 모델/휴리스틱 두 결과를 플래너 선택으로 비교 |

피한 것: 큰 입력창만 있는 챗봇 화면, 그라데이션·장식, 의미 없는 카드 나열. 시스템 글꼴, 차분한 2색(남색·앰버).

## 12. README 참고 사례와 반영

SKN24-FINAL-3Team(ALPLED), SKN20-FINAL-6TEAM(bizi), SKN27-FINAL-1Team(밥벌이)을 clone해 README 구성을 비교했고 KorWikiTableQuestions, KLUE, ragas README도 읽었다(docs/research/readme-research.md). 반영: (1) 한 줄 정의·상태 요약·CI 배지를 맨 위(SKN27, ragas), (2) 실제 화면 이미지와 체험 순서를 바로 아래(SKN27의 영상 자리), (3) 핵심 기능을 기능·설명·구현 3열 표(SKN27), (4) 데이터 출처·라이선스·분할·누수 검사를 표와 수치로(KLUE·KorWikiTQ), (5) 결과 표마다 산출물 경로를 적고 미달 결과도 그대로 — SKN20의 단계별 성능 추적을 정직한 버전으로(후퇴·편법 포함), (6) 실패·한계·수행/미수행 표를 마지막에. 팀 소개·시장 규모·기술 스택 배지 나열은 넣지 않았다. 문구·디자인·코드는 복사하지 않았다.

## 13. 발견한 문제와 수정

전체 목록은 docs/dev/issues-log.md(번호 1–32). 큰 것을 모으면:

- **모델 변환(1–4)**: transformers 5에서 mT5 토크나이저 생성과 `tie_word_embeddings`가 달라 변환이 두 번 틀렸다(센티널 id·lm_head 분리로 해결, 디노이징 손실 50→5–7 nats로 검증).
- **데이터(5–8)**: 공개 분할의 표 누수 발견 → 표 단위 재분할, OpenStax 표 파싱 누락(18→56 문서), 단위 파서 오검출, 숫자 파서 오버플로.
- **휴리스틱·검증기(9–12, 26)**: 모호 판정 과다, 연산 의도 우선순위, 구절 일치 보너스, 숫자 부분 문자열 허점, 같은 셀 두 번 쓰는 퇴화 계산.
- **Agent(20)**: LangGraph가 상태 스키마에 없는 키를 버려 API 응답의 플래너 표시가 항상 휴리스틱이었고 보완 분기가 한 번도 실행되지 않았다.
- **RL(23–24)**: dropout 불일치로 KL이 폭발해 NaN 종료, 그리고 **보상 편법**(쓰레기 프로그램이 의도적 보류와 같은 점수)을 로그에서 발견해 v2로 수정·재학습.
- **평가(22, 25)**: 정답 행이 잘린 입력 위에서 채점하던 오류 수정, 전 모델 재평가. 모델이 열 좌표를 못 맞히는 약점은 검증기의 근거 복구와 별도 지표로 분리해 드러냈다.
- **지표·검증기 허점(30–32)**: README 사례를 예측 파일과 대조해 잘못 옮긴 좌표를 바로잡았고, 보류 재현율에 우연한 보류가 섞여 있음을 경로별 분석(`abstain_breakdown`)과 퇴화 계산 집계로 드러냈다. 표에 없는 대상에 엉뚱한 셀을 인용해 답해도 통과하는 검증기 허점은 **고치지 못하고** 한계로 남겼다.
- **벤치(27)**: 메모리 비교 무효·측정 오염을 발견해 폐기하고 재측정.
- **E2E·운영(13–19, 21, 28–29)**: CSS `hidden` 우선순위, 모바일 탭 전환, 스크립트 크래시가 통과처럼 보이는 문제, `pkill -f` 자기 종료, 세션 워커 재시작으로 파이프라인 중단(→ 재시작 가능 파이프라인), Docker 레지스트리 429, README의 존재하지 않는 데모 주소 정정.

## 14. 실행하지 못한 작업과 이유

| 작업 | 이유 | 준비된 것 |
|---|---|---|
| tabletrace / chartwire 원격 푸시 | 두 저장소 모두 git 푸시와 GitHub API 푸시가 `403`. Claude GitHub App 미설치. 사용자 요청으로 재시도했으나 동일 | 로컬 커밋 이력, 번들, chartwire 안의 복사본과 로컬 커밋(§1) |
| GitHub Actions 실행·결과 확인 | 푸시 불가 | `ci.yml`, `pages.yml` — 같은 명령(린트·pytest·데이터 검사·수치 검사·Docker smoke)을 로컬에서 실행해 통과 |
| GitHub Pages 공개 배포 | 푸시 불가, 외부 배포 플랫폼 접근도 차단 | 정적 빌드 스크립트 + 로컬 Playwright 검증 |
| EXAONE 다운로드·튜닝·서빙 | `huggingface.co` 차단, GPU 없음 | 라이선스·버전 확인(docs/experiments/exaone.md), LoRA SFT 스크립트, 예상 자원·비용 |
| 멀티 GPU 병렬 실측 | GPU 없음 | 파이프라인 병렬 코드(CPU 2프로세스로 정확성 검증), GPU 명령·예상 자원 |
| vLLM / SGLang 실행 | GPU 없음 | OpenAI 호환 클라이언트·서빙 스크립트·벤치 스크립트, 모의 서버 테스트 |
| 채용 공고·LG 논문 페이지 원문 확인 | `www.lgresearch.ai` 차단 | 사용자 제공 역량 목록 기준으로 진행 |
| 논문·특허 기반 화학 데이터 | PMC·ChemRxiv·Google Patents 등 차단 | OpenStax 교과서 데이터 표 사용 |
| 외부 유료 API | `api.openai.com` 차단, 키 없음 | 사용 안 함 — 비용 0, 승인 필요한 실행 없음 |
| 본문 답변(`op: text`) 재학습 | 시간·범위 | 원인 규명(§5.4의 8번)과 수정 방향 |
| 선택적·정적 양자화 시도 | 시간·범위 | int8 동적 양자화의 정확도 하락 측정 |

## 15. 남은 한계

1. **성능**: 어휘 겹침 기준선을 전체 평가에서 이기지 못했다. 원본 lookup에서는 이기지만 계산·보류·본문 답변·단위/기간은 약하다(§5.4).
2. **좌표 생성**: 모델이 인용한 셀의 열은 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:lookup_citation.col_correct:pct -->27.8<!-- /num -->%만 맞다. 검증기의 근거 복구가 점수를 지탱하며, 복구는 답 텍스트가 표에서 유일할 때만 된다.
3. **`op: text` 지름길**: 학습 데이터 설계 결함으로 실제 표가 있는 질문에서 본문 답변을 하지 못한다.
4. **보류**: 답이 없는 문항에서도 값을 만들어 답하는 경우가 많다(보류 재현율 모델 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.abstain_recall:pct -->16.0<!-- /num -->% 대 기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.abstain_recall:pct -->94.0<!-- /num -->%) 그마저 모델이 직접 보류한 것이 아니라 해석 불가·검증 실패로 우연히 보류된 경우다(§5.4의 7번). 검증기는 질문 대상과 인용 셀의 일치를 확인하지 않는다.
5. **계산**: 두 셀 간 차·합·평균·비율·증감률만, 단위 환산·집계·argmax 없음.
6. **입력 예산 512 토큰**: test의 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.truncated_gold_rate:pct -->8.9<!-- /num -->%는 정답 행이 잘려 원리적으로 맞힐 수 없다. 다중 표·긴 표 질문 미지원.
7. **데이터**: 합성 계산·보류는 템플릿이라 표현이 단조롭고 기준선에 유리한 편향이 있다. 화학은 논문이 아니라 교과서 표다. 수작업 평가는 한국어 30·화학 32문항으로 1 표준오차가 6–9%p다.
8. **검색**: BM25만. 문서를 지정하지 않으면 한국어 질문의 약 <!-- num:experiments/eval/retrieval/metrics.json:ko_test_lookup.hit_at_1:pct -->80.0<!-- /num -->%만 첫 번째 표가 맞다(hit@1). 문서 지정 없는 엔드투엔드 정확도는 측정하지 않았다.
9. **int8 양자화**는 정확도를 해친다. 메모리도 줄지 않았다(§8).
10. **하드웨어**: CPU 4코어 단일 환경의 수치다. 지연 시간은 공유 VM이라 실행마다 20% 이상 변동한다. GPU·멀티 GPU·vLLM·EXAONE 실측 없음.
11. **RL**: 60 step 예비 실험, 보상은 검증기가 정의하므로 검증기의 허점이 곧 보상 허점이다(실제로 한 번 발생). v2에서도 개선이 없었고(§7.5) 보류를 직접 학습시키는 데 실패했다. 샘플 960개의 예비 규모이고 원인은 검증하지 않았다.
12. **배포**: 공개 URL 없음, CI는 원격 미실행.

## 16. 사용자가 데모를 직접 확인하는 순서

**A. 저장소를 tabletrace로 옮기기** (이 세션은 어느 원격에도 푸시하지 못했다)

```bash
# 컨테이너 안: /home/user/tabletrace 가 원본 git 저장소, /home/user/chartwire/tabletrace-history.bundle 이 전체 이력 번들
git clone /home/user/chartwire/tabletrace-history.bundle tabletrace && cd tabletrace
git remote add origin https://github.com/sokldjs554/tabletrace && git push -u origin main
```
먼저 https://claude.ai/connect-github 에서 GitHub를 다시 연결하고 Claude GitHub App을 tabletrace에 설치해야 푸시된다(또는 본인 환경에서 위 명령 실행).

**B. 공개 데모(GitHub Pages)**: main 푸시 → Actions `pages` 워크플로가 `console/` + 저장된 실행 결과를 배포한다. 저장소 Settings → Pages → Source가 "GitHub Actions"인지 확인한다.

**C. 로컬 실시간 실행**:
```bash
pip install -e ".[model,dev]" && pytest -q       # 테스트
tabletrace serve                                  # models/mt5-small-tabletrace 가 있으면 모델 플래너(없으면 휴리스틱)
# 또는: docker compose up --build   (휴리스틱)   /   WITH_MODEL=1 docker compose up --build   (모델)
```
모델 가중치(`models/`, `experiments/*/model`)는 git에 없다. 재학습 명령은 scripts/train/README.md.

**D. 화면에서 볼 것**: ① 한국어 표 → 「2018년 한국영화 박스 오피스」 → 대표 질문 7개 ② 근거 배지 클릭 → 셀 강조 ③ 계산 카드의 입력 값·단위 ④ 보류 질문의 사유 ⑤ 영어 화학 문서 → 「Phase Diagrams」「Non-Ideal Gas Behavior」「Rate Laws」 ⑥ **플래너 선택을 "모델"과 "휴리스틱"으로 바꿔 같은 질문의 결과를 비교** — 모델은 답이 없는 질문에도 답하는 사례와 근거 복구(검사 목록에 ✗로 표시) 사례가 보이고, 휴리스틱은 보류하는 사례가 보인다 ⑦ 연구 결과 탭 ⑧ 작동 방식 탭의 그래프와 신뢰 경계.

**E. 수치 확인**: `experiments/eval/*/metrics.json`(지표), `predictions.jsonl`(문항별 모델 원문 출력·예측 셀·검사), `analysis.json`(오류 분석), `experiments/*/train_log.jsonl`(학습 곡선), `experiments/bench/*.json`, `docs/images/e2e-*.json`, `python scripts/check_numbers.py --strict && python scripts/render_results.py --check`.

## 17. 자소서·포트폴리오 작성 시 확인 가능한 사실과 수치

모든 수치는 위 표식으로 산출물에 묶여 있다. **한 줄 요약**: 한국어 표·영어 화학 문서에서 답과 근거·계산을 검증하는 파이프라인(검색→모델 제안→도구 실행→검증→보류)을 직접 설계·구현하고, 300M 모델을 CPU에서 튜닝·강화학습해 **그 결과가 기준선을 못 넘는다는 것까지 정직하게 측정·분석**했다.

### 확인 가능한 사실

| 영역 | 사실 | 근거 |
|---|---|---|
| 데이터 | KorWikiTQ 공개 분할이 표 <!-- num:data/ko/official_split_profile.json:shared_tables_by_url:int -->1,755<!-- /num -->개를 공유함을 측정하고 표 단위로 재분할(공유 0). 영어 화학 교과서 <!-- num:data/chem/build_report.json:documents_with_tables:int -->56<!-- /num -->문서·<!-- num:data/chem/build_report.json:tables:int -->113<!-- /num -->표를 CNXML에서 직접 파싱 | `data/ko/official_split_profile.json`, `data/*/build_report.json` |
| 평가셋 | 한국어 test <!-- num:data/ko/build_report.json:test_examples:int -->539<!-- /num -->(원본)+160(합성), 수작업 한국어 30·화학 32(5범주, 자동 검수) | `data/`, `scripts/check_data.py` |
| 모델 | mT5-small 300,176,768 파라미터를 Mesh-TF 체크포인트에서 PyTorch로 직접 변환·검증, 토크나이저 재구성 | `scripts/model/`, 이슈 1–4 |
| 학습 | CPU 4스레드: SFT 1단계 <!-- num:experiments/sft_ko/summary.json:steps:int -->858<!-- /num --> step·<!-- num:experiments/sft_ko/summary.json:wall_s:int -->7,219<!-- /num -->초, 2단계 <!-- num:experiments/sft_ko2/summary.json:steps:int -->193<!-- /num --> step·<!-- num:experiments/sft_ko2/summary.json:wall_s:int -->1,813<!-- /num -->초, 화학 <!-- num:experiments/sft_chem/summary.json:steps:int -->236<!-- /num --> step·<!-- num:experiments/sft_chem/summary.json:wall_s:int -->1,927<!-- /num -->초 | `experiments/*/summary.json` |
| 성능 | 한국어 독립 test verified EM: 미튜닝 <!-- num:experiments/eval/base_ko_test/metrics.json:metrics.verified_em:pct -->7.1<!-- /num -->% → 튜닝 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->%, 기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->%. 원본 539문항만: 튜닝 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->37.1<!-- /num -->% vs 기준선 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->26.2<!-- /num -->% | `experiments/eval/` |
| 분석 | 모델 인용 셀의 열 정확도 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:lookup_citation.col_correct:pct -->27.8<!-- /num -->%가 병목, 본문 답변이 실패한 원인(빈 표 지름길) 규명 | `analysis.json`, §5.4 |
| 강화학습 | GRPO 방식 정책 경사를 직접 구현, **보상 편법을 로그에서 발견해 보상을 수정하고 재학습**했으나 재학습 후에도 독립 test에서 개선 없음(실패) | `training/rl_grpo.py`, §7, 이슈 23–24 |
| 추론 | KV 캐시·배치·int8을 정밀도별 별도 프로세스로 측정, **int8이 속도 대신 정확도를 잃는다는 것**을 같은 평가셋으로 확인 | §8 |
| 서비스 | FastAPI + LangGraph + 타입 검증 도구 + 비동기 작업 러너(큐·동시성·타임아웃), 임의 코드 실행 없음(계산기는 AST 평가기) | `service/`, `agent/`, `tools/` |
| 검증 | 테스트 <!-- num:experiments/tests/summary.json:passed -->82<!-- /num -->개 통과, E2E 검사 실시간 <!-- num:docs/images/e2e-summary.json:live.passed -->16<!-- /num -->/<!-- num:docs/images/e2e-summary.json:live.total -->16<!-- /num -->·정적 <!-- num:docs/images/e2e-summary.json:static.passed -->13<!-- /num -->/<!-- num:docs/images/e2e-summary.json:static.total -->13<!-- /num -->, Docker 이미지 빌드·smoke | `experiments/tests/`, `docs/images/` |
| 병렬(CPU) | 2-스테이지 파이프라인으로 모델을 두 프로세스에 분할하고 출력이 단일 프로세스와 일치함을 확인(속도 이득 없음) | §9 |

### 주장하면 안 되는 것 (이 프로젝트가 보여 주지 못한 것)

- GPU 학습·튜닝, **멀티 GPU 모델 병렬 실행**, vLLM/SGLang 서빙 실행, EXAONE 사용·튜닝, Hugging Face Hub 사용 경험.
- "기준선보다 좋은 모델", "강화학습으로 성능을 올렸다"(v2도 독립 test에서 개선 없음, §7.5), "int8로 최적화했다"(정확도 하락).
- 공개 배포·GitHub Actions 실행·운영 경험, 실제 사용자 트래픽.
- 논문·특허 화학 문서 처리(교과서 표만 사용), 실사용 질문 분포에서의 일반 성능(수작업 평가는 62문항).
- 공고 원문 대조(공고 페이지를 열지 못함).
