# TableTrace 최종 보고서

작성 기준: 이 저장소의 커밋과 `experiments/` 산출물. 모든 수치는 산출물 JSON에서 가져오며(`scripts/check_numbers.py`가 README·보고서의 표시 값과 산출물을 대조), 실행하지 않은 것은 "구현 후 미실행"으로 적는다.

## 1. 저장소와 공개 데모

| 항목 | 값 |
|---|---|
| 목표 저장소 | <https://github.com/sokldjs554/tabletrace> — **이 세션은 푸시 권한이 없었다** (Claude GitHub App 미설치: `remote: Claude doesn't have GitHub access to sokldjs554/tabletrace`). |
| 작업 결과가 올라간 곳 | <https://github.com/sokldjs554/chartwire> 브랜치 `claude/bold-carson-ix16u0` (세션에 지정된 브랜치). 트리 전체가 TableTrace 프로젝트다. |
| tabletrace로 옮기는 법 | §16 참고 (`git bundle` 또는 브랜치 push). 옮긴 뒤 main 푸시가 Pages 배포 워크플로를 실행한다. |
| 공개 데모 URL(예정) | <https://sokldjs554.github.io/tabletrace/> — **이 세션에서 배포를 실행·확인하지 못했다.** 정적 데모 빌드는 로컬에서 Playwright로 검증했다(`docs/images/e2e-static.json`). |
| 로컬 실시간 데모 | `docker compose up --build` → http://localhost:8000 |

## 2. 최종 커밋과 배포 버전

(마지막에 채움: 커밋 SHA, `console/data/recorded/index.json`의 commit, 패키지 버전 0.1.0)

## 3. 공고 대조표

공고 원문은 네트워크 차단으로 읽지 못했다(docs/research/job-posting.md). 사용자가 제시한 역량 목록을 기준으로 한다. 상태: **완료 / 실행했으나 실패 / 구현 후 미실행 / 미구현**. 개인의 역량이나 근무 가능 여부는 검증 대상이 아니다.

| 공고 항목 | 프로젝트 적용 방식 | 구현·실행 증거 | 평가 결과 | 상태 |
|---|---|---|---|---|
| 한국어 언어모델 튜닝 | mT5-small을 KorWikiTQ 기반 프로그램 생성 과제로 SFT(2 stage) | `training/sft.py`, `experiments/sft_ko*/summary.json`, `train_log.jsonl` | §5 표 | (채움) |
| 한국어 언어모델 벤치마크 구축 | 표 단위 재분할 test 539 + 합성 160 + 수작업 30(범주 5), 지표 10종, 검수 스크립트 | `data/ko/`, `eval/metrics.py`, `scripts/check_data.py` | §5 | 완료 |
| 표 이해 및 Table MRC | 표 직렬화(r/c 좌표), 셀 근거 프로그램, 검증기 | `model/serialize.py`, `verify/verifier.py` | §5 | 완료 |
| 추론 엔진 최적화 | CPU에서 fp32/int8 동적 양자화/배치/KV 캐시 실측 | `bench/inference.py`, `experiments/bench/inference.json` | §8 | (채움) |
| 영어 화학 도메인 데이터 처리·모델 튜닝 | OpenStax Chemistry 2e CNXML 파싱(113표), 합성 QA, 화학 SFT, 수작업 32문항 | `scripts/data/build_chem.py`, `experiments/sft_chem/` | §6 | (채움) |
| 강화학습 기반 언어모델 개발 | GRPO 방식 정책 경사(검증기 보상, 그룹 정규화, KL) 예비 실험 | `training/rl_grpo.py`, `experiments/rl_ko/` | §7 | (채움) |
| LLM Agent와 외부 도구 연결 | LangGraph 그래프 + 타입 검증 도구 레지스트리(셀 조회·검색·제한 계산) | `agent/graph.py`, `tools/registry.py`, `tests/test_api.py` | 테스트 통과 | 완료 |
| FastAPI 기반 서비스 및 모델 서빙 | REST API, in-process 모델 서빙, 작업 큐 | `service/app.py`, `service/jobs.py` | API 테스트 11건 통과 | 완료 |
| 비동기 처리와 워크플로우 설계 | asyncio 작업 러너(세마포어·큐 제한·타임아웃·상태), LangGraph 분기 | `service/jobs.py` | 동시 5건·타임아웃·429 테스트 통과 | 완료 |
| 프롬프트·컨텍스트 엔지니어링과 검색 결합 | BM25(Kiwi 형태소) 검색 → 문단 스니펫 + 표 직렬화 입력, 행 예산 | `retrieval/`, `model/serialize.py` | §5·§6 | 완료 |
| Linux, Python, Hugging Face, PyTorch | 전부 Python 3.13/PyTorch 2.15/Transformers 5.21, 자체 학습 루프 | 저장소 전체 | — | 완료 |
| 멀티 GPU Model Parallelism | 2-스테이지 파이프라인 병렬(encoder / decoder) torch.distributed | `bench/pipeline_parallel.py`, `experiments/bench/pp_*.json` | CPU gloo 2프로세스 출력 동일성 검증, GPU 미실행 | 구현 후 미실행(GPU) |
| vLLM 또는 SGLang | OpenAI 호환 EnginePlanner + TP/PP 서빙 스크립트 + 벤치 | `service/engines.py`, `scripts/serving/`, `tests/test_engines.py` | 모의 서버 테스트 통과 | 구현 후 미실행(GPU) |
| Docker | API+콘솔 이미지, compose, 헬스체크 | `Dockerfile`, `docker-compose.yml` | (채움: 로컬 빌드 결과) | (채움) |
| LangChain 또는 LangGraph | 위 Agent 항목 | `agent/graph.py` | — | 완료 |
| GitHub Actions | ci.yml(린트·테스트·데이터·수치·Docker smoke), pages.yml | `.github/workflows/` | (채움: chartwire 브랜치에서의 실행 결과) | (채움) |

## 4. 사용한 기술과 실제 역할

| 기술 | 실제 역할 | 실행 여부 |
|---|---|---|
| PyTorch 2.15 / Transformers 5.21 | mT5-small 변환·SFT·RL·추론; 자체 학습 루프(Trainer 미사용) | 실행 |
| SentencePiece / tokenizers | mT5 토크나이저를 spm proto에서 재구성 | 실행 |
| Kiwi (kiwipiepy) | 한국어 형태소 분석으로 BM25 토큰화 | 실행 |
| LangGraph | retrieve→propose→verify→finalize 상태 그래프, 조건부 재시도 | 실행 |
| FastAPI / uvicorn / pydantic | API, 입력 검증, 비동기 작업 | 실행 |
| Playwright | 콘솔 E2E 검사·스크린샷 | 실행 |
| Docker | 이미지·compose | (채움) |
| GitHub Actions | CI·Pages | (채움) |
| torch.distributed (gloo) | 파이프라인 병렬 기능 검증 | 실행(CPU) |
| vLLM / SGLang | 서빙 스크립트·클라이언트 | 미실행(GPU 없음) |
| TensorFlow (별도 venv) | mesh-TF 체크포인트 읽기 전용 | 실행 |

## 5. 한국어 표 QA — 데이터·모델·평가

<!-- results:ko:start -->
**한국어 표 QA — 독립 test (원본 539 + 합성 160)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 % | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 699 | **40.5** | 23.9 | 28.0 | 74.7 | 34.8 | 66.1 | 42.8 | 0.0 | 7 |

**한국어 표 QA — 수작업 30문항**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 % | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 30 | **53.3** | 19.1 | 36.4 | 50.0 | 42.9 | 77.8 | 42.9 | 0.0 | 127 |

**한국어 수작업 — 범주별 verified EM % (n)**

| 범주 | 휴리스틱 기준선 |
|---|---:|
| abstain | 100.0 (5) |
| calc | 83.3 (6) |
| cell | 44.4 (9) |
| text_table | 20.0 (5) |
| unit_period | 20.0 (5) |


<!-- results:ko:end -->

<!-- results:training:start -->
| 실행 | 학습 예제/프롬프트 | 스텝 | 소요 (CPU 4스레드) | best dev verified EM % | dev 추이 % |
|---|---:|---:|---:|---:|---|
| SFT stage1 (ko 표) | 3431 | 858 | (미완료) | – | – |

<!-- results:training:end -->

## 6. 영어 화학 문서 — 데이터·모델·평가

<!-- results:chem:start -->
**영어 화학 문서 — 수작업 32문항 (test 분할 문서)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 % | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 32 | **68.8** | 55.0 | 84.6 | 28.6 | 75.0 | 75.0 | 15.0 | 0.0 | 0 |

_영어 화학 — 합성 dev 80문항(템플릿, 참고용): 산출물 없음_

**화학 수작업 — 범주별 verified EM % (n)**

| 범주 | 휴리스틱 기준선 |
|---|---:|
| abstain | 100.0 (5) |
| calc | 28.6 (7) |
| cell | 80.0 (10) |
| text_table | 66.7 (6) |
| unit_period | 75.0 (4) |


<!-- results:chem:end -->

## 7. 강화학습 — 방법·조건·비교

<!-- results:rl:start -->
_RL 로그 없음_

<!-- results:rl:end -->

## 8. 추론 최적화 — 조건과 측정

<!-- results:bench:start -->
_추론 벤치 산출물 없음_

<!-- results:bench:end -->

## 9. 멀티 GPU Model Parallelism — 방식·환경·결과

<!-- results:pp:start -->
_파이프라인 병렬 산출물 없음_

<!-- results:pp:end -->

## 10. 테스트와 반복 검증

(채움)

## 11. UI 조사와 디자인 반영

조사한 화면(docs/design/ui-research.md): Microsoft Document Intelligence 샘플 라벨링 도구(OCR Form Tools 스크린샷 4장), Google Document AI Workbench 제품 페이지, Label Studio, doccano, MLflow 트레이스 뷰·게이트웨이 대시보드, promptfoo 평가 표, Marker 벤치마크 차트, Tabula, PaddleOCR. 제품 문서 사이트 대부분이 차단되어 GitHub 공개 스크린샷·README와 Google Cloud 페이지를 썼다.

| 관찰 | TableTrace 반영 (docs/design/screens.md, console/) |
|---|---|
| 3단(목록 / 문서 / 속성) 레이아웃이 공통 | 문서 목록 / 본문·표 / 질문·결과 3열, 모바일은 탭 |
| 문서 위 하이라이트와 오른쪽 필드가 색·번호로 짝지어짐 | 근거 셀에 노란 테두리+번호 배지, 오른쪽 근거 배지 클릭 → 셀로 스크롤·강조, 본문 근거는 문장 하이라이트 |
| 예측값 옆 신뢰도·페이지 배지 | 모델 확률 대신 **검증기 판정**(통과 검사 수, 보류 사유)과 r/c 좌표 배지 |
| 긴 작업의 상태 바, PASS/FAIL 배지 | 대기→실행 중(경과 ms)→완료/보류/오류/시간 초과 상태 띠, 작업 ID, 429/422 메시지와 재시도 |
| 트레이스 트리 + 상세 탭 | 실행 추적 카드: LangGraph 노드·도구 호출·소요 ms, 입력/출력 펼치기, 플래너 원문 출력 |
| 평가 표 + 조건 요약 | 연구 결과 화면: 각 표 위에 실행 조건(모델·데이터 크기·반복·하드웨어), 상태 필(완료/미실행/실패) |
| 튜토리얼식 첫 화면 | 4단계 안내 띠(닫기 가능) + 문서별 대표 질문 칩(범주 표시) |
| 실시간 vs 저장 결과 | 상단 배지와 결과 카드 배지로 구분, 저장 결과에는 기록 시각·모델·커밋 |

피한 것: 큰 입력창만 있는 챗봇 화면, 그라데이션·장식, 의미 없는 카드 나열. 시스템 글꼴, 차분한 2색(남색·앰버)만 사용.

## 12. README 참고 사례와 반영

SKN24-FINAL-3Team(ALPLED), SKN20-FINAL-6TEAM(bizi), SKN27-FINAL-1Team(밥벌이)을 clone해 README 구성을 비교했고 KorWikiTableQuestions, KLUE, ragas README도 읽었다(docs/research/readme-research.md). 반영: (1) 한 줄 정의·데모 링크·CI 배지를 맨 위(SKN27, ragas), (2) 실제 화면 이미지와 체험 순서를 바로 아래(SKN27의 영상 자리), (3) 핵심 기능을 기능·설명·구현 3열 표(SKN27), (4) 데이터 출처·라이선스·분할·누수 검사를 표와 수치로(KLUE·KorWikiTQ), (5) 결과 표마다 산출물 경로를 적고 미달 결과도 그대로(SKN20의 단계별 성능 추적을 정직한 버전으로), (6) 실패·한계·수행/미수행 표를 마지막에. 팀 소개·시장 규모·기술 스택 배지 나열은 넣지 않았다. 문구·디자인·코드는 복사하지 않았다.

## 13. 발견한 문제와 수정

전체 목록은 docs/dev/issues-log.md(번호 1–17+). 큰 것만 요약하면: transformers 5에서 mT5 토크나이저·tie 설정이 달라 변환이 두 번 실패했고(센티널 id·lm_head 분리로 해결), KorWikiTQ 공개 분할의 표 누수를 발견해 표 단위로 재분할했으며, 검증기가 짧은 숫자 부분 문자열을 통과시키는 허점을 RL 보상 점검 중 발견해 고쳤다. 콘솔은 `hidden` 속성이 CSS에 눌리는 문제와 모바일 첫 진입 탭 전환 문제를 Playwright 검사에서 잡았다. 운영에서는 평가와 학습을 동시에 돌리자 OpenMP 스레드 초과 구독으로 학습이 약 5배 느려져 순차 파이프라인으로 바꿨다.

## 14. 실행하지 못한 작업과 이유

(채움)

## 15. 남은 한계

(채움)

## 16. 데모를 직접 확인하는 순서

**A. 저장소를 tabletrace로 옮기기** (이 세션은 어느 원격에도 푸시하지 못했다)

```bash
# 컨테이너 안: /home/user/tabletrace 가 원본 git 저장소, /home/user/chartwire/tabletrace-history.bundle 이 전체 이력 번들
git clone tabletrace-history.bundle tabletrace && cd tabletrace
git remote add origin https://github.com/sokldjs554/tabletrace && git push -u origin main
```
Claude GitHub App을 tabletrace(또는 chartwire)에 설치하면 이 세션(또는 재개된 세션)이 직접 푸시할 수 있다.

**B. 공개 데모(GitHub Pages)**: main 푸시 → Actions `pages` 워크플로가 `console/` + 저장된 실행 결과를 배포. 저장소 Settings → Pages → Source가 "GitHub Actions"인지 확인(`configure-pages`의 `enablement: true`가 실패하면 이 설정을 한 번 수동으로).

**C. 로컬 실시간 실행**:
```bash
pip install -e ".[model,dev]" && pytest -q                 # 테스트
tabletrace serve                                           # 모델이 models/mt5-small-tabletrace 에 있으면 신경망 플래너
# 또는 docker compose up --build  (휴리스틱) / WITH_MODEL=1 docker compose up --build
```

**D. 화면에서 볼 것**: ① 한국어 표 → 「2018년 한국영화 박스 오피스」 → 대표 질문 7개(셀·차이·합·본문·단위·기간·보류) ② 근거 배지 클릭 → 셀 강조 ③ 계산 카드의 입력 값·단위 ④ 보류 질문의 사유 ⑤ 영어 화학 문서 → 「Phase Diagrams」「Non-Ideal Gas Behavior」「Rate Laws」의 대표 질문 ⑥ 연구 결과 탭 ⑦ 작동 방식 탭의 그래프와 신뢰 경계.

**E. 수치 확인**: `experiments/eval/*/metrics.json`(지표), `predictions.jsonl`(문항별), `experiments/*/train_log.jsonl`(학습 곡선), `experiments/bench/*.json`(벤치), `docs/images/e2e-*.json`(E2E 검사), `scripts/check_numbers.py`(README·보고서 수치 대조).

## 17. 자소서·포트폴리오 작성 시 확인 가능한 사실과 수치

(채움)
