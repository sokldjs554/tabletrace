# 4단계 명세 — `verify/verifier.py` (검증기, 이 프로젝트의 중심)

모델(또는 기준선)이 제안한 프로그램이 표와 본문으로 뒷받침되는지 확인하고, **답할지(answered) 보류할지(abstained)와 그 이유**를 정한다. 판단 하나하나를 `Check` 기록으로 남겨 화면과 지표가 "왜"를 보여 줄 수 있게 한다. 원본 289줄.

테스트: `tests/test_program_verifier.py`(20여 개 중 검증기 부분). **끝났는지는 `python scripts/rewrite_parity.py verifier`로 판단한다** — 저장된 모델 출력 8,600여 개를 세 가지 설정(검증기 v1, v2, v2+열 보정)으로, 정답 프로그램 1,000여 개를 v2로, 검색 실패·표 없음 경로까지 원본과 비교한다(2만 8천여 입력). 비교 항목은 상태, 답, 근거 셀, 보류 이유, **검사(`Check`) 이름과 통과 여부의 순서**, 계산의 식과 표기, 본문 근거 구간, 도구 호출 기록(어떤 도구를 어떤 인자로 불렀는지)이다. 검사의 `detail` 문장은 비교하지 않는다(화면에 보이는 설명이므로 뜻만 같으면 된다). 차이 0개여야 끝이다.

일부러 규칙을 조금씩 바꿔 이 검사가 잡는지 확인했다: 개체 일치 기준 0.5→0.6이면 65곳, 반올림 허용 1%→0.5%면 6곳, 부분 일치 최소 길이 2→3이면 11곳, 근거 복구를 "하나일 때"→"하나 이상"으로 바꾸면 538곳이 달라진다.

크기가 커서 **두 부분으로 나눠 쓰기**를 권한다. 앞부분(보조 함수)을 쓰고 `find_span` 테스트를 통과시킨 뒤 뒷부분(`resolve`)을 쓴다. 커밋을 둘로 나눠도 되고 하나로 해도 된다.

## 의존하는 것 (이 단계에서 고치지 않음)

- `schema`: `Program`, `Table`, `CellRef`, `Calculation`, `Check(name, passed, detail)`, `Verdict(status, reason, checks)`, `EvidenceSpan(passage_id, start, end, text)`, `TraceStep`, `AbstainReason`.
- `tools.cells.normalize_text`(3단계), `tools.numbers.parse_number`(1단계).
- `retrieval.tokenize`: `tokenize(text, lang) -> list[str]`(질문·헤더의 내용어), `entity_tokens(text, lang) -> list[str]`(질문의 고유명사 비슷한 말: 한국어는 Kiwi 고유명사·외국어·한자, 영어는 화학식).
- `tools.registry`: `REGISTRY.call(name, table, args, trace)`가 도구를 실행하고 그 호출을 `trace` 리스트에 `TraceStep`으로 덧붙인다. 실패하면 `ToolError`(메시지는 도구의 오류 메시지). 쓰는 도구는 셋:
  - `"cell_lookup"`, 인자 `{"row": r, "col": c}` → `lookup_cell` 결과 dict(`"text"` 키에 셀 원문).
  - `"cell_find"`, 인자 `{"text": 문자열, "exact": True}` → `CellRef` 리스트.
  - `"calculate"`, 인자 `{"op": op, "cells": ["r1c5", "r2c5"]}` → `Calculation`. 단위 불일치면 메시지에 `"unit mismatch"`가 든 `ToolError`.
  
  **도구는 반드시 `REGISTRY.call`로 부른다**(셀을 직접 읽으면 화면의 도구 호출 기록이 비고, 동작 비교에서 차이로 잡힌다). 단, 아래에 "직접 읽는다"고 적힌 곳은 `table.cell`을 직접 쓴다.

## 공개 이름

`Resolution`, `resolve`, `find_span`은 다른 모듈과 테스트가 import한다. `subject_check`, `header_column`은 이 모듈 안에서 쓰지만 이름을 유지한다(문서와 스크립트가 가리킨다). 나머지 보조 함수의 이름은 자유.

`Resolution`은 dataclass: `status`(`"answered"`|`"abstained"`), `answer`(str|None), `cells`(list[CellRef]), `calculation`(Calculation|None), `verdict`(Verdict), `trace`(list[TraceStep], 기본 빈 리스트), `spans`(list[EvidenceSpan], 기본 빈 리스트). 필드 순서도 이대로(위치 인자로 만드는 곳이 있다).

---

## 앞부분: 보조 함수

### 연도 추출
질문과 행에서 연도를 뽑는다: 앞뒤가 숫자가 아닌 곳의 `19xx` 또는 `20xx` 네 자리. 결과는 문자열 집합.

### 숫자 근사 비교 (계산 답 확인용)
두 float이 (가) 상대 오차 1e-6 또는 절대 오차 1e-9 안이면 같다. 아니면 (나) 상대 오차 1%(0.01) 또는 절대 오차 0.051 안이면 같다(모델이 반올림한 답을 내는 경우). 파이썬 `math.isclose`의 `rel_tol`, `abs_tol` 의미 그대로다(둘 중 하나만 만족해도 참).

### `find_span(answer, context, passage_id="context") -> EvidenceSpan | None`
본문에서 답 문자열의 위치를 찾아 **원문 그대로의** 부분 문자열을 돌려준다.

1. 비교용으로 두 문자열을 NFKC 정규화하고 소문자로 바꾼다. 답은 앞뒤 공백도 지운다.
2. 답이 비었거나 200자를 넘으면 `None`.
3. 정규화한 본문에서 정규화한 답을 처음 나오는 곳에서 찾으면, 그 시작 위치와 `시작 + 답 길이`로 `EvidenceSpan(passage_id, start, end, text=원래 본문[start:end])`.
4. 없으면 공백 차이를 허용한다. 둘 다에서 모든 공백 문자를 지운 문자열로 다시 찾고, 찾은 위치를 **원래(정규화한) 본문의 위치로 되돌린다**: 시작은 "공백이 아닌 글자를 그 위치만큼 센 지점", 끝은 거기서부터 "공백이 아닌 글자를 답(공백 뺀) 길이만큼 센 지점". 그 사이를 원래 본문에서 잘라 돌려준다. 그래도 없으면 `None`.

주의: 위치 계산은 정규화한 본문 기준인데 자르는 것은 원래 본문이다. NFKC가 글자 수를 바꾸는 경우(호환 문자) 원본과 같은 결과를 내려면 이 순서를 그대로 지킨다.

### 압축 문자열
NFKC 정규화 → 모든 공백 문자 제거 → 소문자. 개체 일치 검사와 열 이름 일치에 쓴다.

### 언급 판정 `mentions(text, e)` (둘 다 이미 압축된 문자열)
`e`가 `text`의 부분 문자열이면 참. 아니면 `e`의 **글자 2-gram 집합**(겹치는 두 글자씩)을 만들고, 그 집합이 2개 미만이면 거짓, 아니면 그중 `text`에 들어 있는 2-gram의 비율이 0.5 이상이면 참. (음역 차이 "자오웨"/"자오위에"를 허용하기 위한 규칙.)

### `subject_check(question, table, cells, context=None) -> (Check | None, reason | None)`
"질문이 묻는 대상이 인용한 근거에 나오는가".

1. `entity_tokens(question, table.lang)`이 비었거나 `cells`가 비었으면 `(None, None)`(검사 안 함).
2. 표의 제목·캡션·모든 헤더를 공백으로 이어 압축한 문자열을 만든다. 개체 토큰 중 **압축했을 때 이 문자열의 부분 문자열인 것은 대상에서 뺀다**(표나 열의 이름은 질문의 대상이 아니다). 남은 게 없으면 `(None, None)`.
3. 인용한 셀들의 **행 번호 집합**(정렬)의 행들을 각각 공백으로 잇고, 다시 공백으로 이은 뒤 본문(`context`, 없으면 빈 문자열)을 공백 하나 사이에 두고 붙여 압축한다. 행 번호가 표 범위 밖이면 그 행은 건너뛴다.
4. 대상 중 하나라도 이 근거 문자열에 언급(위의 판정)되면 `Check(name="subject_in_evidence", passed=True, ...)`와 `None`.
5. 아니면 표 전체 행을 같은 방식으로 이어 압축한 문자열에 언급되는 대상이 있는지 본다. 있으면 이유 `"verification_failed"`(대상은 표에 있는데 다른 행을 인용함), 없으면 `"not_in_document"`. `Check(name="subject_in_evidence", passed=False, ...)`와 그 이유.

### `header_column(question, table, cited) -> int | None`
"질문이 이름을 부르는 열"(열 보정용, 기본 꺼짐).

1. 질문을 압축하고, `tokenize(question, table.lang)`의 집합을 만든다.
2. 각 헤더 j에 대해(앞에서부터): 헤더를 압축한 것이 비면 건너뛴다. 압축 헤더가 2글자 이상이고 압축 질문의 부분 문자열이면 점수 1.0. 아니면 헤더의 `tokenize` 집합이 비어 있지 않고 그중 질문 토큰 집합과 겹치는 비율이 0.5 이상이면 그 비율이 점수.
3. 점수가 하나도 없거나 `cited` 열에 점수가 있으면 `None`.
4. 최고 점수의 열이 하나뿐이면 그 열 번호, 동점이 여럿이면 `None`.

---

## 뒷부분: `resolve`

### `resolve(question, table, program, retrieval_ok=True, context=None, passage_id="context", entity_check=True, column_check=False) -> Resolution`

1. 아래 "기본 판정"을 실행한다.
2. `entity_check`가 참이고, 결과가 answered이고, 근거 셀이 있고, `table`이 있으면 `subject_check(question, table, 결과의 셀들, context)`를 부른다.
   - 검사가 `None`이면 결과 그대로.
   - 이유가 있으면(실패): 검사 목록 = 기존 검사들 + 개체 검사 + `Check(name="abstain", passed=True, ...)`. `Resolution("abstained", None, [], None, Verdict(status="abstained", reason=이유, checks=목록), 기존 trace)`. spans는 비운다.
   - 이유가 없으면(통과): 기존 검사들 뒤에 개체 검사를 붙인 answered 결과(답·셀·계산·trace·spans 유지).

### 기본 판정

진행하며 `checks`와 `trace` 두 리스트를 쌓는다. **보류**는 언제나 같은 방식이다: `Check(name="abstain", passed=True, detail=설명)`을 `checks`에 붙이고 `Resolution("abstained", None, [], None, Verdict(status="abstained", reason=이유, checks=checks), trace)`를 돌려준다.

순서대로:

1. `table`이 없거나 `retrieval_ok`가 거짓 → 보류 `"retrieval_low"`.
2. `program`이 없음(파싱 실패) → 보류 `"invalid_program"`.
3. `op == "abstain"` → 보류(이유는 프로그램의 `reason`, 없으면 `"not_in_document"`).
4. `op == "text"`:
   - `context`가 없거나 비었으면 → 보류 `"not_in_document"`.
   - `find_span(답 또는 "", context, passage_id)`. 검사 `answer_in_passage`(찾았으면 통과)를 붙인다.
   - 못 찾으면 → 보류 `"verification_failed"`.
   - 찾으면 → `Resolution("answered", 구간의 원문, [], None, Verdict(answered, checks), trace, [구간])`.
5. **셀 범위**: 행 번호가 표 행 수 이상이거나 열 번호가 헤더 수 이상인 셀들. 검사 `cells_in_range`(그런 셀이 없으면 통과)를 붙이고, 있으면 → 보류 `"invalid_program"`.
6. **기간(연도) 일치** — 보류하지 않는 기록용 검사: 질문에 연도가 있으면, 인용한 각 셀의 **행 전체**(셀들을 공백으로 이은 것)의 연도와 표 제목의 연도를 모은다. 검사 `period_consistent`: 둘이 겹치거나 근거 쪽에 연도가 하나도 없으면 통과. 질문에 연도가 없으면 이 검사를 붙이지 않는다.
7. **`op == "lookup"`**:
   - 셀이 정확히 1개가 아니면 → 보류 `"ambiguous_question"`.
   - `REGISTRY.call("cell_lookup", table, {"row", "col"}, trace)`로 셀 원문을 얻는다. 공백뿐이면 → 보류 `"not_in_document"`.
   - `column_check`가 참이면: `header_column(question, table, 인용 열)`이 열 j2를 주고 같은 행의 j2 칸(직접 읽는다)이 공백뿐이 아니면, 검사 `column_repaired`(**실패로** 기록)를 붙이고 `Resolution("answered", 그 칸 원문, [그 칸], None, Verdict(answered, checks), trace)`.
   - `same` = 정규화한 제안 답 == 정규화한 셀 원문(제안 답이 없으면 빈 문자열로).
   - `contained` = 제안 답이 비어 있지 않고, 정규화한 길이가 2 이상이고, 정규화한 셀 원문에 들어 있고, **그리고** 제안 답과 셀이 둘 다 숫자로 읽히면서 값 차이가 1e-9를 넘는 경우가 아니다("5,436,789"의 "9"나 다른 숫자는 부분 일치로 인정하지 않는다).
   - 검사 `answer_matches_cell`(통과 = `same`)을 붙인다.
   - `same`도 `contained`도 아니고 제안 답이 비어 있지 않으면: `REGISTRY.call("cell_find", table, {"text": 제안 답, "exact": True}, trace)`. 결과가 **정확히 하나**이고 정규화한 제안 답이 2글자 이상이면, 검사 `evidence_repaired`(**실패로** 기록)를 붙이고 `Resolution("answered", 그 셀 원문(직접 읽는다), [그 셀], None, Verdict(answered, checks), trace)`. 아니면 → 보류 `"verification_failed"`.
   - 그 외(같거나 부분 일치거나 제안 답이 비었음) → `Resolution("answered", 셀 원문, [인용 셀], None, Verdict(answered, checks), trace)`. 답은 언제나 **셀의 원문**이다(제안 답이 셀의 일부여도).
8. **계산 op**(`diff, sum, avg, ratio, count, pct_change`):
   - 같은 셀(cid)이 두 번 이상 나오면 검사 `distinct_cells`(실패)를 붙이고 → 보류 `"invalid_program"`.
   - `REGISTRY.call("calculate", table, {"op": op, "cells": [cid들]}, trace)`. `ToolError`면: 메시지에 `"unit mismatch"`가 있으면 이유 `"unit_mismatch"`, 아니면 `"invalid_program"`. 검사 `calculation`(실패)을 붙이고 → 그 이유로 보류.
   - 성공하면 검사 `calculation`(통과), 검사 `units_consistent`(입력 단위 집합의 크기가 1이거나 op가 `ratio`·`count`면 통과)를 붙인다.
   - 제안 답이 있으면: 숫자로 읽히지 않으면 검사 `answer_matches_calc`(실패), 읽히면 위의 근사 비교로 검사 `answer_matches_calc`(통과/실패). **어느 경우든 보류하지 않는다** — 계산 결과가 답이 된다.
   - `Resolution("answered", 계산 결과의 표기(formatted), 인용 셀들, 계산, Verdict(answered, checks), trace)`.

## 끝났는지 확인

```bash
pytest tests/test_program_verifier.py -q
python scripts/rewrite_parity.py verifier     # 차이 0개 (30초 정도 걸린다)
pytest -q && ruff check src tests scripts
git diff --stat origin/main                   # src/tabletrace/verify/verifier.py 가 바뀌었는지 먼저 확인
```

브랜치는 `rewrite/04-verifier`, 커밋 메시지는 `rewrite: verify/verifier.py (owner)`(둘로 나누면 `... helpers (owner)`, `... resolve (owner)`).
