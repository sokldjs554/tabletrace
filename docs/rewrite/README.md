# 핵심 모듈 직접 다시 쓰기 — 진행 방식

목적: 저장소 소유자가 핵심 모듈을 **처음부터 직접 구현**해서, 그 부분에 대해 "직접 작성"이 사실이 되게 한다. 기존 구현은 AI 코딩 도구가 쓴 것이고 그대로 남겨 두지 않는다. 소유자가 쓴 코드가 같은 테스트를 통과하면 기존 파일을 대체한다.

## 규칙

1. **코드는 소유자만 쓴다.** AI 도구는 명세(무엇을 받아 무엇을 돌려줘야 하는지, 어떤 입력을 거부해야 하는지)를 설명하고, 소유자가 쓴 코드를 리뷰하고, 테스트 결과를 해석한다. 코드 조각을 대신 써 주지 않는다. 막히면 "어느 테스트가 왜 실패하는지"를 묻는 식으로 진행한다.
2. **커밋은 소유자의 컴퓨터(또는 Codespace)에서 소유자의 git 계정으로** 한다. 이 세션에서 올리는 커밋에는 AI 공동 작성 표식이 붙으므로, 소유자가 쓴 코드는 그 경로로 올리지 않는다.
3. 기존 파일은 참고서다. 먼저 테스트와 명세만 보고 써 보고, 테스트가 통과한 뒤 기존 구현과 비교해 차이를 이해하는 순서를 권한다. 기존 코드를 베껴 붙이면 "직접 작성"이 아니다.
4. 각 모듈이 끝나면 `docs/rewrite/LOG.md`에 날짜·커밋·바뀐 점을 적고, `docs/HANDOFF.md` §0의 역할 구분을 그에 맞게 고친다. 다시 쓰지 않은 모듈은 계속 AI 작성으로 남는다.
5. 테스트는 고치지 않는다. 테스트가 틀렸다고 판단되면 먼저 이유를 적고 합의한 뒤 바꾼다.

## 순서 (작은 것부터, 의존 관계 순)

| 단계 | 모듈 | 줄 수 | 테스트 | 왜 이 순서인가 |
|---|---|---:|---|---|
| 1 | `tools/numbers.py`, `tools/calculator.py` | 94 + 108 | `tests/test_numbers_calculator.py` | 순수 함수. 숫자·단위 파싱과 안전한 계산기. 다른 모든 것이 이 위에 있다 |
| 2 | `agent/program.py` | 85 | `tests/test_program_verifier.py`(파서 부분) | 프로그램 문법 `op ; cells ; answer` 파서 |
| 3 | `tools/cells.py` | 62 | 같은 파일 | 셀 주소 해석·읽기 |
| 4 | `verify/verifier.py` | 289 | `tests/test_program_verifier.py` | 프로젝트의 핵심. 답·근거·계산 검증과 보류 결정, 개체 일치 검사 |
| 5 | `agent/heuristic.py` | 113 | `tests/test_api.py` 일부 | 어휘 겹침 기준선 |
| 6 | `retrieval/tokenize.py`, `bm25.py`, `index.py` | 66 + 50 + 66 | `tests/test_retrieval.py` | 검색 |
| 7 | `eval/metrics.py` | 71 | 평가 재실행으로 확인 | 지표 계산 |
| 8 | `tools/registry.py`, `agent/graph.py` | 94 + 177 | `tests/test_api.py` | 도구 등록과 LangGraph 그래프 |
| 9 | `service/jobs.py`, `service/app.py` | 96 + 220 | `tests/test_api.py` | 비동기 작업 러너와 FastAPI |

1~4단계(약 640줄)가 끝나면 "검증 파이프라인의 핵심을 직접 구현했다"가 사실이 된다. 9단계까지 가면 서비스 계층도 포함된다. 학습·벤치 스크립트(`training/`, `bench/`, `scripts/`)와 문서는 이 계획에 없다.

## 환경 준비

로컬(Python 3.11 이상):

```bash
git clone https://github.com/sokldjs554/tabletrace && cd tabletrace
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest tests/test_numbers_calculator.py -q               # 지금은 전부 통과해야 한다
```

GitHub Codespaces(설치 없이 브라우저에서): 저장소 페이지 → Code → Codespaces → Create. 터미널에서 `pip install -e ".[dev]"` 뒤 위와 같다. 개인 계정은 매달 일정 시간 무료다.

## 한 단계의 흐름

1. `docs/rewrite/NN_*.md` 명세와 해당 테스트 파일을 읽는다.
2. 기존 파일을 `git mv src/tabletrace/tools/numbers.py src/tabletrace/tools/_ref_numbers.py`처럼 옆으로 치운다(참고용, 마지막에 지운다). import 경로는 그대로이므로 새 파일을 같은 이름으로 만든다.
3. 테스트가 통과할 때까지 쓴다. `pytest tests/<파일> -q`.
4. 전체 테스트 `pytest -q`와 `ruff check src tests scripts`를 돌린다. 다른 모듈이 이 모듈을 쓰기 때문이다.
5. `_ref_*.py`를 지우고 커밋한다. 커밋 메시지에 "rewrite: <모듈> (owner)"처럼 적는다.
6. `docs/rewrite/LOG.md`에 한 줄 적는다.
