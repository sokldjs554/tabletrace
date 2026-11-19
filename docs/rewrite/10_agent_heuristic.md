# 5단계 명세 — `agent/heuristic.py` (낱말 겹침 기준선)

**상태: 준비됨(2026-11-19).** 소유자가 이 명세와 테스트만 보고 다시 쓴다.

이 파일은 학습 없이 질문과 표의 낱말 겹침만으로 프로그램(`op ; cells ; answer`)을 고르는 기준선이다. 서류와 문서에 나오는 기준선 수치(한국어 시험 699문항 36.2%, 직접 쓴 30문항 23.3%, "AI 도구가 쓴 계산 문항 5/6, 직접 쓴 계산 문항 0/6")가 모두 이 파일에서 나온다. 모델이 없을 때 서비스가 쓰는 대체 플래너이기도 하다.

테스트는 `tests/test_agent_heuristic.py`(50개, 지금 구현으로 모두 통과한다). **끝났는지는 `python scripts/rewrite_parity.py heuristic`로 본다.** 모든 문항 세트의 모든 질문(평가 때처럼 표를 자른 것과 자르지 않은 것), 질문마다 계산 낱말 판정, 모든 표에 만든 탐색 질문까지 34,686개 입력을 원본과 비교한다. 차이가 0개여야 저장된 기준선 결과가 그대로 재현된다.

의존: `tools.cells`의 `normalize_text`, `column_overlap_scores`, `row_overlap_scores`(3단계, 본인 작성), `tools.numbers.parse_number`(1단계, 본인 작성), `agent.program`의 `make`, `make_abstain`(2단계, 본인 작성), `retrieval.tokenize.tokenize`(AI 작성, 6단계에서 다시 쓸 대상), `schema`의 `CellRef`, `Program`, `Table`.

## 공개 이름

- `plan(question: str, table: Table, lang: str) -> Program`: 평가 러너와 서비스 그래프가 부른다.
- `_calc_intent(question: str) -> str | None`: 이름은 밑줄로 시작하지만 `scripts/owner_eval_analysis.py`가 가져다 쓴다. 이 이름과 동작을 지킨다.

나머지 함수 이름은 자유다.

## 계산 낱말 판정 `_calc_intent`

질문을 소문자로 바꾼 뒤(`question.lower()`), 아래 순서로 정규식을 찾아(`re.search`) **처음 맞는 연산**을 돌려준다. 하나도 맞지 않으면 `None`. 순서가 결과를 바꾼다. "몇 배 차이"는 `ratio`, "합계 차이"는 `diff`다(합계는 열 이름인 경우가 많아서 `diff`를 `sum`보다 먼저 본다).

| 순서 | 연산 | 정규식 (글자 그대로 쓴다) |
|---|---|---|
| 1 | `ratio` | `비율\|몇 배\|배인\|ratio\|times (larger\|greater\|higher\|more)\|fold\|by what factor` |
| 2 | `pct_change` | `몇 ?%\|퍼센트\|percent(age)? change\|증가율\|감소율\|성장률` |
| 3 | `avg` | `평균\|average\|mean` |
| 4 | `diff` | `차이\|차는\|더 많\|더 적\|더 (길\|크\|높\|낮\|짧\|무거\|가벼)\|몇 .{0,6}더\|빼면\|감소\|증가(량\|폭)\|difference\|more than\|fewer\|less than\|increase\|decrease\|change in\|how much (higher\|lower\|larger\|smaller\|greater\|bigger\|longer\|heavier)` |
| 5 | `sum` | `합계\|합은\|합이\|총합\|모두 합\|더하면\|총 \|total\|sum of\|combined\|altogether\|in total` |

(표 안의 `\|`는 정규식의 `|`다. `총 `은 뒤에 공백이 하나 있다.)

## `plan`의 순서

### 1. 질문의 낱말

- `toks` = `tokenize(question, lang)`의 결과 집합에, 질문에서 `[A-Za-z0-9][A-Za-z0-9\.\-]+`에 맞는 조각들을 각각 `normalize_text`한 것을 더한다. 빈 문자열은 뺀다.
- `toks`가 비면 `make_abstain("ambiguous_question")`.
- 행을 맞출 때 쓰는 `row_toks` = `toks` 가운데 두 글자 이상이거나 숫자로만 된 것(한 글자 낱말 "년", "수", "명"은 행 맞추기에 쓰지 않는다).

### 2. 질문이 가리키는 열

- 열 점수 = `column_overlap_scores(table, toks)`.
- 머리글마다 `normalize_text(h)`가 두 글자 이상이고, `toks` 안에 그 머리글을 **포함하면서 같지는 않은** 낱말이 있으면 그 열에 1.0을 더한다("경기수"라는 낱말이 머리글 "경기"를 가리키는 경우).
- `best_col` = 점수가 가장 큰 열. **같으면 앞의 열.** 열이 없으면 없음.
- `has_col` = `best_col`이 있고 그 점수가 0보다 크다.

### 3. 숫자 열

열 `c`의 셀마다 `parse_number(v, table.units.get(c))`로 읽어, 숫자로 읽힌 셀이 `max(2, int(0.6 × 행 수))`개 이상이면 숫자 열이다. 열 번호 순서로 모은다.

### 4. 행 점수 (계산과 조회에서 같이 쓴다)

`row_overlap_scores(table, row_toks, exclude_col=X)`에 **구절 가산점**을 행마다 더한다. 구절 가산점: 질문 전체를 `normalize_text`한 문자열 안에, 그 행의 셀(열 `X`는 빼고)을 `normalize_text`한 값이 두 글자 이상으로 그대로 들어 있으면 셀 하나에 2.0. "carbon dioxide"를 묻는 질문에서 "carbon dioxide" 행이 "nitrogen dioxide" 행을 이기는 까닭이다.

### 5. 계산 (`_calc_intent`가 연산을 돌려줄 때)

- 대상 열: `has_col`이고 `best_col`이 숫자 열이면 `best_col`, 아니면 **마지막 숫자 열**, 숫자 열이 없으면 없음.
- 대상 열이 있으면 4의 행 점수(제외 열 = 대상 열)를 구하고, 점수가 큰 순서로(같으면 행 번호 순서) 점수가 0보다 큰 행을 `sum`이면 3개까지, 나머지는 2개까지 고른다.
- 고른 행이 **2개 이상**이면, 행들을 **질문에서 먼저 나온 순서**로 정렬해 `make(연산, [대상 열의 셀들], None)`을 돌려준다. 답은 비워 둔다(계산기가 채운다).
  - "먼저 나온 위치": 그 행의 셀 가운데 `normalize_text`해서 두 글자 이상인 것이, `normalize_text`한 질문에서 처음 나오는 위치들의 최솟값. 하나도 안 나오면 `10**6`. 위치가 같으면 원래 순서를 지킨다.
- 대상 열이 없거나 고른 행이 2개보다 적으면 계산을 포기하고 아래 조회로 간다("합계" 같은 계산 낱말이 사실은 열 이름이었던 경우).

### 6. 조회

- 제외 열 = `has_col`이면 `best_col`, 아니면 없음. 4의 행 점수를 구한다.
- 행이 없거나 가장 큰 점수가 0이면 `make_abstain("not_in_document")`.
- 가장 큰 점수의 행이 둘 이상이면 `make_abstain("ambiguous_question")`.
- 행 `r`이 정해지면 열은:
  - `has_col`이면 `best_col`.
  - 아니면, 그 행에서 셀 값(`normalize_text`)에 `row_toks`의 어떤 낱말도 들어 있지 않은 열들. 그런 열이 **정확히 하나**면 그 열, 아니면 `make_abstain("ambiguous_question")`.
- `make("lookup", [CellRef(table_id=table.id, row=r, col=c)], table.cell(r, c))`.

표를 바꾸지 않는다.

## 생각해 볼 점 (면접에서 물을 만한 것)

- 이 기준선이 한국어 시험에서 36.2%로, mT5-small(32.8%)보다 높았던 까닭. 질문과 표에 같은 낱말이 많은 데이터에서 낱말 겹침이 얼마나 강한가.
- AI 도구가 쓴 계산 문항에서는 6개 중 5개를 맞히고, 본인이 쓴 계산 문항에서는 0개였던 까닭. 위 정규식과 문항의 낱말을 견주어 설명할 수 있어야 한다(`experiments/eval/owner_eval_analysis.json`).
- 열 점수가 같으면 앞의 열을 고르는 규칙 때문에 생기는 오답("울산 현대 선수의 도움은?"에 선수 이름을 답한다, 테스트에 있다).
- 계산 낱말 순서(`ratio`를 `diff`보다 먼저)가 바뀌면 무엇이 달라지는가.

## 끝났는지 확인

```bash
pytest tests/test_agent_heuristic.py -q          # 전부 통과
python scripts/rewrite_parity.py heuristic       # 차이 0개 (1분쯤)
pytest -q                                         # 서비스, 평가 러너 테스트가 이 모듈을 거친다
ruff check src tests scripts
```

## 이 단계의 순서

```bash
git switch main && git pull
git switch -c rewrite/10-heuristic
git mv src/tabletrace/agent/heuristic.py src/tabletrace/agent/_ref_heuristic.py   # 참고용으로 치운다. 먼저 명세와 테스트만 보고 써 본다
# src/tabletrace/agent/heuristic.py 를 새로 쓴다
pytest tests/test_agent_heuristic.py -q
python scripts/rewrite_parity.py heuristic
pytest -q && ruff check src tests scripts
git rm -f src/tabletrace/agent/_ref_heuristic.py
git add src/tabletrace/agent/heuristic.py
git commit -m "rewrite: agent/heuristic.py (owner)"       # AI 공동 작성 표식(Co-Authored-By)을 넣지 않는다
git push -u origin rewrite/10-heuristic
```

동작 비교 스크립트는 원본을 `origin/main`에서 가져오므로 `main`에 합치기 전에는 비교가 된다. 이 스크립트와 테스트가 잡는지 미리 확인했다. 계산 낱말 순서를 바꾸거나, 구절 가산점을 2.0에서 1.0으로, 합계의 행 수를 3에서 2로, 숫자 열 기준을 60%에서 50%로 바꾼 판 네 가지를 넣어 보았고, 동작 비교와 테스트 모두 넷 다 잡았다.

결함 고치기(`09_numbers_fix.md`)와 순서는 상관없다. 다만 둘을 같은 날 한다면 하나를 `main`에 합친 뒤 다른 브랜치를 시작한다.
