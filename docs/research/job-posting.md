# 채용 공고 확인 기록 — LG AI연구원 NLP Research Engineer Internship

- 공고 URL: <https://www.lgresearch.ai/careers/view?seq=143>
- **원문 확인: 2026-11-10.** 저장소 소유자가 개발 환경의 허용 호스트에 `www.lgresearch.ai`를 추가한 뒤 페이지를 받아 읽었다. 아래 "공고 원문"은 그날 받은 페이지의 문구다. 공고는 연중 상시 모집이고 문구가 바뀔 수 있으므로 지원 전에 다시 확인한다.
- 그전까지(2026-10-29~11-09)는 접근이 막혀 있었다. 세션 프록시가 `www.lgresearch.ai:443`을 403으로 거부했다. 그래서 프로젝트는 소유자가 작업 지시에 적어 준 역량 목록 15개를 기준으로 만들어졌다. 그 목록과 원문의 차이는 아래 "원문과 처음 기준의 차이"에 적었다.

## 공고 원문 (2026-11-10 확인)

**팀 소개.** Language Lab. "자연어 처리 분야의 기술적 난제 해결을 위한 핵심 선행기술을 연구"하고 "Learning-by-Reading AI 확보를 통한 챗봇 등 Language 분야 서비스 혁신"을 비전으로 든다.

**수행 업무.** 다섯 묶음으로 적혀 있다.

| 묶음 | 세부 항목 (원문) |
|---|---|
| 1. 초거대 언어모델 개발 | 한국어 언어 모델 Tuning / 한국어 언어 모델 벤치마크 구축 / 한국어 언어 모델 Inference 엔진 최적화 |
| 2. 심층문서이해 기술 개발 | 영어 Chemical 도메인의 언어 모델을 위한 데이터 처리 및 모델 튜닝 |
| 3. 강화학습 기반 언어모델 개발 | 강화학습기반 언어모델 개발 관련 데이터 처리 및 모델 튜닝 |
| 4. 테이블이해 기술(Table MRC) 개발 | 데이터 구조 이해를 위한 언어모델(Pre-trained Language Model) 구현 / 한국어 모델 Tuning 및 Inference 엔진 최적화 |
| 5. LLM기반 AI서비스 및 Agent 시스템 개발 | LLM 기반 챗봇/에이전트 서비스 개발 / LLM과 외부 Tool을 연결하는 Agent Orchestration 시스템 개발 / FastAPI / gRPC 기반 AI서비스 API 개발 / LLM 추론 엔진 연동 및 모델 서빙 시스템 개발 / AI 서비스의 비동기 처리, 워크플로우 설계, 성능 최적화 / 프롬프팅, 컨텍스트 엔지니어링, 메모리/검색 결합을 통한 LLM 서비스 품질 개선 |

**지원자격.** 학사/석사/박사 무관. 6개월 이상 근무 가능.

**필요역량.** Linux, Python, HuggingFace 언어 모델 활용 능력 / HuggingFace Transformers 등 Deep NLP 학습 경험(pytorch or jax) / Linux 활용 능숙, python 코딩 중급 이상, github 등 Coding Tool 활용 능력 / Python 기반 AI서비스 또는 백엔드 개발 경험 / REST API 또는 gRPC 기반 서비스 개발 경험 / 네트워크 및 서버 구조에 대한 기본적인 이해 / LLM 동작 원리에 대한 기본적인 이해 / 최신 딥러닝 논문 독해. 끝에 "Tech Cell별 연구 주제/수행 업무에 따라 요구되는 세부 역량은 일부 상이할 수 있습니다"라는 단서가 붙어 있다.

**우대사항.** 한국어 언어 모델 튜닝 숙련자 / 한국어 벤치마크 구축 경험자 / Multi-GPU Model-Parallelism 경험자 / LLM 기반 서비스 또는 챗봇 개발 경험 / vLLM, SGLang 등 LLM 서빙 프레임워크 사용 경험 / Agent 아키텍처, Tool Calling, Personal Agent 개발 경험 / Docker 등 컨테이너 기반 개발 경험 / LangChain 등 LLM 프레임워크 사용 경험.

**전형절차.** 서류심사 → LG Way Fit Test & 코딩테스트 → 기술 인터뷰(온라인) → 최종 합격. "본 포지션은 연중 상시 모집으로 진행되며, Tech Cell별 채용 상황에 따라 전형 일정 및 결과 안내 시점이 지원자 별로 상이할 수 있습니다."

## 원문을 읽고 달라진 이해

1. **업무는 다섯 주제로 나뉘어 있고, 채용은 Tech Cell 단위로 진행된다.** 필요역량의 단서와 전형절차의 문구가 둘 다 "Tech Cell별"이라고 적는다. 수행 업무의 다섯 묶음이 각각 하나의 Tech Cell이라고 공고가 직접 말하지는 않는다. 다만 인턴 한 사람이 다섯 묶음을 전부 맡는다고 읽기는 어렵다. 이 해석은 추정이다.
2. **이 프로젝트가 정면으로 맞추는 묶음은 4번(테이블이해, Table MRC)이다.** 한국어 표 질의응답에서 답의 근거 셀을 검증하는 것이 프로젝트의 중심이고, 데이터도 LG AI연구원이 공개한 KorWikiTQ다. 두 번째는 3번(강화학습)이다. 검증기를 보상으로 쓴 예비 실험과 보상 편법을 찾아 고친 기록이 있다. 1번(한국어 튜닝·벤치마크·추론 최적화), 2번(영어 화학), 5번(서비스·에이전트)은 같은 과제 위에서 한 번씩 실행해 본 보조 증거다.
3. 처음 기준이던 15개 목록은 다섯 묶음을 한 줄로 편 것이다. 그래서 프로젝트가 "공고의 모든 줄을 하나씩 채우는" 모양이 되었다. 지원서에서는 4번 묶음에 맞춘 프로젝트로 소개하고 나머지는 근거 표로 돌리는 편이 원문에 맞다.

## 원문 항목별 대응

상태는 `docs/REPORT.md` §3과 같은 기준이다(완료 / 실행했으나 실패 / 구현 후 미실행 / 미구현). "부분"은 한 줄 안에 한 것과 안 한 것이 섞여 있을 때만 쓴다. 수치와 근거는 `docs/REPORT.md` §3 표에 있다.

| 묶음 | 원문 항목 | 프로젝트에서 한 것 | 상태 |
|---|---|---|---|
| 4 | 데이터 구조 이해를 위한 언어모델(PLM) 구현 | 표를 행·열 좌표가 붙은 텍스트로 직렬화해 일반 언어모델(mT5-small, EXAONE-4.0-1.2B)을 튜닝했다. 행·열 임베딩을 갖는 구조 전용 PLM을 새로 구현하거나 사전학습하지는 않았다 | 미구현 (직렬화·튜닝으로 대체) |
| 4 | 한국어 모델 Tuning 및 Inference 엔진 최적화 | KorWikiTQ 표 QA로 mT5 SFT와 EXAONE LoRA. int8 범위별 측정, vLLM·SGLang 서빙 벤치 | 완료 |
| 3 | 강화학습 기반 언어모델 데이터 처리 및 모델 튜닝 | 검증기 보상의 GRPO 방식 정책 경사 3회(v1 보상 편법 발견, v2 수정, v3). 표 정답률은 오르지 않았고 근거 없는 질문의 직접 보류만 학습됨 | 완료 (부분 개선) |
| 1 | 한국어 언어 모델 Tuning | 위 4번과 같은 실행. 모델 크기는 3억, 12억 파라미터로 "초거대"는 아니다 | 완료 |
| 1 | 한국어 언어 모델 벤치마크 구축 | 표 단위 재분할 test 539문항, 합성 160, 수작업 30. 공개 분할의 표 겹침을 세고 제거 | 완료 (규모 작음) |
| 1 | 한국어 언어 모델 Inference 엔진 최적화 | CPU int8 범위별 측정, GPU에서 vLLM 1장·TP=2, SGLang 동시 요청 벤치 | 완료 |
| 2 | 영어 Chemical 도메인 데이터 처리 및 모델 튜닝 | OpenStax Chemistry 2e 교과서의 표 113개를 파싱하고 합성 QA로 튜닝. 논문·특허 문서는 다루지 않았다 | 완료 (교과서 표에 한정) |
| 5 | LLM 기반 챗봇/에이전트 서비스 개발 | 질문 한 건을 받아 검증된 답 또는 보류를 돌려주는 에이전트 서비스. 여러 턴을 잇는 대화형 챗봇은 아니다 | 부분 (에이전트 서비스 완료, 챗봇 미구현) |
| 5 | LLM과 외부 Tool을 연결하는 Agent Orchestration | LangGraph 그래프와 타입 검증 도구 레지스트리(셀 조회·검색·제한 계산) | 완료 |
| 5 | FastAPI / gRPC 기반 AI서비스 API 개발 | FastAPI REST API. gRPC는 쓰지 않았다 | 부분 (FastAPI 완료, gRPC 미구현) |
| 5 | LLM 추론 엔진 연동 및 모델 서빙 | OpenAI 호환 엔진 플래너로 vLLM·SGLang에 연결, 프로세스 내 서빙 | 완료 |
| 5 | 비동기 처리, 워크플로우 설계, 성능 최적화 | asyncio 작업 러너(세마포어·큐 제한·타임아웃), LangGraph 분기, 동시 요청 벤치 | 완료 |
| 5 | 프롬프팅, 컨텍스트 엔지니어링, 메모리/검색 결합 | BM25(Kiwi 형태소) 검색과 컨텍스트 행 예산. 대화 기억(메모리)은 없다 | 부분 (검색·컨텍스트 완료, 메모리 미구현) |
| 우대 | Multi-GPU Model-Parallelism | vLLM TP=2(T4 2장), 2-스테이지 파이프라인 병렬(NCCL). 데이터 병렬(DDP)은 하지 않았다 | 완료 (작은 규모) |
| 우대 | vLLM, SGLang 등 서빙 프레임워크 | 둘 다 실행. SGLang은 T4에서 우회 모듈로 돌렸고 제 성능 비교는 하지 않았다 | 완료 |
| 우대 | Agent 아키텍처, Tool Calling, Personal Agent | 에이전트 그래프와 도구 호출. Personal Agent는 만들지 않았다 | 부분 |
| 우대 | Docker 등 컨테이너 | Dockerfile, compose, CI의 컨테이너 smoke | 완료 |
| 우대 | LangChain 등 LLM 프레임워크 | LangGraph | 완료 |

필요역량 가운데 "네트워크 및 서버 구조에 대한 기본적인 이해", "LLM 동작 원리에 대한 기본적인 이해", "최신 딥러닝 논문 독해", "python 코딩 중급 이상"은 사람의 역량이다. 프로젝트 산출물로 증명되는 항목이 아니므로 이 표에 넣지 않았다. 소유자가 직접 다시 쓴 모듈의 범위는 `docs/rewrite/LOG.md`에 있다.

## 원문과 처음 기준의 차이

처음 기준(소유자가 적어 준 15개): 한국어 언어모델 튜닝 / 한국어 벤치마크 구축 / 표 이해 및 Table MRC / 추론 엔진 최적화 / 영어 화학 도메인 데이터 처리와 모델 튜닝 / 강화학습 기반 언어모델 개발 / LLM Agent와 외부 도구 연결 / FastAPI 기반 서비스 및 모델 서빙 / 비동기 처리와 워크플로우 설계 / 프롬프트·컨텍스트 엔지니어링과 검색 결합 / Linux, Python, Hugging Face, PyTorch / 멀티 GPU Model Parallelism / vLLM 또는 SGLang / Docker / LangChain 또는 LangGraph.

15개 가운데 원문에 없는 항목은 없다. 원문에만 있는 것은 다음과 같다.

| 원문에만 있는 것 | 프로젝트 상태 |
|---|---|
| 업무가 다섯 묶음으로 나뉘고 채용이 Tech Cell별이라는 구조 | 위 "달라진 이해" 참고 |
| 데이터 구조 이해를 위한 PLM **구현** | 구조 전용 PLM은 미구현 |
| gRPC | 미구현 (README §7에 이유) |
| 챗봇 | 미구현 |
| 메모리 결합 | 미구현 |
| Personal Agent | 미구현 |
| 서비스 성능 최적화 | 동시 요청 벤치와 큐 제한까지. 운영 트래픽 최적화는 없음 |
| jax | 사용 안 함 (PyTorch) |
| 6개월 이상 근무, 전형절차(LG Way Fit Test, 코딩테스트, 기술 인터뷰) | 프로젝트와 무관. 지원자가 따로 준비할 일 |

## 추가로 접근한 LG 자료

| 자료 | URL | 결과 |
|---|---|---|
| KorWikiTableQuestions GitHub | https://github.com/LG-NLP/KorWikiTableQuestions | 접근 성공 (clone, README, LICENSE, LFS 데이터) |
| EXAONE 3.5 / 4.0 / Deep GitHub (LICENSE, README) | https://github.com/LG-AI-EXAONE/ | 접근 성공 (raw) |
| Hugging Face 모델 카드 | https://huggingface.co/LGAI-EXAONE | 2026-11-10부터 개발 환경에서 접근 가능. 그전에는 차단되어 소유자가 Kaggle·Colab에서 내려받았다 |
| LG AI연구원 한국어 표 QA 논문 페이지 | https://www.lgresearch.ai/publication/view?seq=37 | 2026-10-29에는 차단. 원논문은 `docs/research/papers.md`에 기록 |
