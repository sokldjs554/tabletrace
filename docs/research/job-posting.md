# 채용 공고 확인 기록 — LG AI연구원 NLP Research Engineer Internship

- 공고 URL: <https://www.lgresearch.ai/careers/view?seq=143>
- 확인 시각: 2026-10-29 07:31 UTC (세션 시작 직후)
- **결과: 접근 불가.** 세션 이그레스 프록시가 `www.lgresearch.ai:443` CONNECT를 403으로 거부했고(`curl`), 보조 페이지 도구는 `getaddrinfo ENOTFOUND www.lgresearch.ai`로 실패했다. 재시도 2회 동일. `https://www.lgresearch.ai`(루트)도 동일하게 차단됐다. 따라서 **공고의 현재 문구(수행 업무·필요 역량·우대사항)를 이 세션에서 직접 읽지 못했다.**

## 이 프로젝트가 기준으로 삼은 역량 목록

공고 원문을 읽을 수 없었으므로, 사용자가 작업 지시에 적어 준 역량 목록을 그대로 기준으로 삼았다. 공고가 변경되었거나 아래 목록과 다를 수 있다.

| # | 항목 (사용자 제공) | 프로젝트에서 대응하는 위치 |
|---|---|---|
| 1 | 한국어 언어모델 튜닝 | `src/tabletrace/training/sft.py`, `docs/experiments/ko-table-qa.md` |
| 2 | 한국어 언어모델 벤치마크 구축 | `data/ko/`, `data/ko/custom_eval.jsonl`, `src/tabletrace/eval/` |
| 3 | 표 이해 및 Table MRC | 전체 — 표 직렬화, 셀 근거, 프로그램 검증 |
| 4 | 추론 엔진 최적화 | `src/tabletrace/bench/inference.py`, `docs/experiments/inference.md` |
| 5 | 영어 화학 도메인 데이터 처리와 모델 튜닝 | `scripts/data/build_chem.py`, `docs/experiments/chem-docs.md` |
| 6 | 강화학습 기반 언어모델 개발 | `src/tabletrace/training/rl_grpo.py`, `docs/experiments/rl.md` |
| 7 | LLM Agent와 외부 도구 연결 | `src/tabletrace/agent/graph.py`, `src/tabletrace/tools/registry.py` |
| 8 | FastAPI 기반 서비스 및 모델 서빙 | `src/tabletrace/service/` |
| 9 | 비동기 처리와 워크플로우 설계 | `src/tabletrace/service/jobs.py`, LangGraph 그래프 |
| 10 | 프롬프트·컨텍스트 엔지니어링과 검색 결합 | `src/tabletrace/model/serialize.py`, `src/tabletrace/retrieval/` |
| 11 | Linux, Python, Hugging Face, PyTorch | 전체 |
| 12 | 멀티 GPU Model Parallelism | `src/tabletrace/bench/pipeline_parallel.py`, `docs/experiments/parallel.md` |
| 13 | vLLM 또는 SGLang | `src/tabletrace/service/engines.py`, `docs/experiments/serving.md` |
| 14 | Docker | `Dockerfile`, `docker-compose.yml` |
| 15 | LangChain 또는 LangGraph | `src/tabletrace/agent/graph.py` |

공고 대조표(적용 방식·증거·평가 결과·상태)는 `docs/REPORT.md` §3에 있다.

## 추가로 접근을 시도한 LG 자료

| 자료 | URL | 결과 |
|---|---|---|
| LG AI연구원 한국어 표 QA 논문 페이지 | https://www.lgresearch.ai/publication/view?seq=37 | 동일 차단 |
| KorWikiTableQuestions GitHub | https://github.com/LG-NLP/KorWikiTableQuestions | **접근 성공** (clone + README + LICENSE + LFS 데이터) |
| EXAONE 3.5 / 4.0 / Deep GitHub (LICENSE, README) | https://github.com/LG-AI-EXAONE/ | **접근 성공** (raw) |
| Hugging Face 모델 카드 | https://huggingface.co/LGAI-EXAONE | 차단 |
