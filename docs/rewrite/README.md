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

## 환경 준비 (맥북, 처음 한 번)

```bash
xcode-select --install                     # git이 없으면 설치 창이 뜬다. 이미 있으면 'already installed'
python3 --version                          # 3.11 이상이어야 한다. 아니면 python.org에서 3.12 설치 파일을 받거나 brew install python@3.12
brew install gh && gh auth login           # GitHub 로그인(GitHub.com → HTTPS → Login with a web browser). Homebrew가 없으면 brew.sh에서 먼저 설치
git config --global user.name "본인 이름"
git config --global user.email "GitHub 계정에 등록된 이메일"   # GitHub → Settings → Emails에 있는 주소(또는 ...@users.noreply.github.com). 그래야 커밋이 본인 계정으로 표시된다

git clone https://github.com/sokldjs554/tabletrace && cd tabletrace
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/test_numbers_calculator.py -q  # 지금은 전부 통과해야 한다
```

GitHub Codespaces(설치 없이 브라우저에서)도 된다: 저장소 페이지 → Code → Codespaces → Create, 터미널에서 `pip install -e ".[dev]"`.

## 한 단계의 흐름

1. `docs/rewrite/NN_*.md` 명세와 해당 테스트 파일을 읽는다.
2. 기존 파일을 `git mv src/tabletrace/tools/numbers.py src/tabletrace/tools/_ref_numbers.py`처럼 옆으로 치운다(참고용, 마지막에 지운다). import 경로는 그대로이므로 새 파일을 같은 이름으로 만든다.
3. 테스트가 통과할 때까지 쓴다. `pytest tests/<파일> -q`.
4. **동작 비교**: `python scripts/rewrite_parity.py <numbers|calculator|program>`. 원본(`origin/main`)과 새 코드를 실제 데이터 전체(표 셀 6만여 개, 데이터셋의 모든 계산, 저장된 모델 출력)에 돌려 차이를 보여 준다. 테스트는 일부 예만 보므로, 테스트를 통과해도 여기서 차이가 나면 저장된 평가 결과가 재현되지 않는다. 차이 0개여야 한다(의도한 개선이라면 먼저 이유를 적고 합의).
5. 전체 테스트 `pytest -q`와 `ruff check src tests scripts`를 돌린다. 다른 모듈이 이 모듈을 쓰기 때문이다.
6. `_ref_*.py`를 지우고 커밋·푸시한다.

```bash
git switch -c rewrite/01-numbers                                   # 단계마다 새 브랜치
git add src/tabletrace/tools/numbers.py src/tabletrace/tools/calculator.py
git commit -m "rewrite: tools/numbers.py, tools/calculator.py (owner)"   # AI 공동 작성 표식(Co-Authored-By)을 넣지 않는다
git push -u origin rewrite/01-numbers
```

7. 푸시했다고 알리면 AI 도구가 GitHub에서 브랜치를 읽고 테스트·동작 비교를 다시 돌려 리뷰한다. 통과하면 소유자가 GitHub에서 Pull request를 만들어 `main`에 합친다(Compare & pull request → Create → Merge).
8. `docs/rewrite/LOG.md`에 한 줄 적는다(날짜, 모듈, 커밋, 메모).
