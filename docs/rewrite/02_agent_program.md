# 2단계 명세 — `agent/program.py` (프로그램 문법)

테스트: `tests/test_program_verifier.py`의 `test_parse_roundtrip`, `test_parse_rejects`(나머지 테스트도 이 파서를 거쳐 검증기를 부르므로 모두 통과해야 한다). 동작 비교: `python scripts/rewrite_parity.py program` — 저장된 모델 출력 6,600여 개를 원본과 새 파서로 파싱해 결과를 비교한다. **차이 0개여야 끝**이다.

자료형은 `src/tabletrace/schema.py`의 `Program`(124행: `op`, `cells`, `answer`, `reason`), `CellRef`(34행, `CellRef.parse(table_id, "r2c5")`와 `.cid`), `Op`(20행), `AbstainReason`(21행)을 쓴다.

## 왜 중요한가

이 문법은 프로젝트 전체의 접점이다. 학습 데이터의 정답 문자열은 `serialize`가 만들고(`training/data.py`), mT5·EXAONE이 낸 문자열은 `parse`가 읽고(`model/planner.py`, `service/engines.py`, `eval/run.py`, `training/rl_grpo.py`), 휴리스틱 기준선은 `make`·`make_abstain`으로 같은 객체를 만든다. 그래서 **`serialize`의 출력은 글자 하나까지 원본과 같아야** 하고(바뀌면 학습 데이터와 저장된 모델 출력이 맞지 않는다), `parse`는 실제 모델 출력에 대해 원본과 같은 판정을 내려야 한다.

문법:

```
op: <op> ; cells: <r{i}c{j}, r{i}c{j}, ... 또는 -> ; answer: <텍스트 또는 -> [; reason: <보류 이유>]
```

예: `op: lookup ; cells: r2c5 ; answer: 60`, `op: diff ; cells: r1c5, r2c5 ; answer: 52`, `op: text ; cells: - ; answer: 2018년 1월 1일`, `op: abstain ; cells: - ; answer: - ; reason: not_in_document`.

## 공개 이름

`OPS`, `REASONS`, `ProgramParseError`, `serialize`, `parse`, `make_abstain`, `make`. 다른 모듈이 이 이름들을 import한다.

- `OPS`: 튜플, 순서 그대로 `("lookup", "text", "diff", "ratio", "sum", "avg", "count", "pct_change", "abstain")`. `schema.Op`와 같은 집합.
- `REASONS`: 튜플, `("not_in_document", "ambiguous_question", "unit_mismatch", "verification_failed", "retrieval_low", "invalid_program", "timeout")`. `schema.AbstainReason`과 같은 집합.
- `ProgramParseError(ValueError)`.

## `serialize(p: Program) -> str`

세 가지 모양만 있다. 구분자는 정확히 `" ; "`(공백-세미콜론-공백), 필드 이름 뒤는 `": "`.

1. `op == "abstain"`: `op: abstain ; cells: - ; answer: - ; reason: <reason>`. `reason`이 없으면 `not_in_document`.
2. `op == "text"`: `op: text ; cells: - ; answer: <answer>`. 셀은 항상 `-`. 답이 비었으면 `-`.
3. 그 밖: `op: <op> ; cells: <cid들> ; answer: <answer>`. cid들은 `", "`로 잇고, 셀이 없으면 `-`. `answer`가 `None`이면 `-`(빈 문자열은 그대로 빈 문자열).

`reason` 필드는 abstain일 때만 쓴다.

## `parse(text: str, table_id: str) -> Program`

엄격한 파서다. 추측해서 고쳐 주지 않고, 이상하면 `ProgramParseError`를 던진다. 처리 순서:

1. **정리**: `None`은 빈 문자열로 본다. mT5가 붙이는 `<pad>`와 `</s>`를 모두 지우고 앞뒤 공백을 지운다.
2. **크기**: 정리한 결과가 비었거나 400자를 넘으면 오류.
3. **필드 나누기**: 필드 이름은 `op`, `cells`, `answer`, `reason` 넷이고, 이름 뒤에 공백이 있을 수 있고 콜론, 다시 공백이 올 수 있다(`op:`, `op :`, `op:  `). 문자열의 **맨 앞이 필드여야** 한다(`hello op: ...`는 오류). 각 필드의 값은 그 필드 이름 다음부터 다음 필드 이름 직전까지이며, 값의 앞뒤 공백과 끝의 `;`를 지운다. 같은 필드가 두 번 나오면 오류(`op: lookup ; cells: r1c1 ; op: diff`).
   - 주의할 원본의 동작: 필드 이름은 **단어 경계 없이** 찾는다. 그래서 답 텍스트 안에 `cop:`이나 `reason:` 같은 글자가 있으면 그 자리에서 새 필드로 잘린다. 원본의 한계지만, 저장된 결과를 재현하려면 같은 동작이어야 한다. 바꾸고 싶다면 따로 제안해서 합의한 뒤 바꾼다(이 단계에서는 원본과 같게).
4. **op**: `op` 필드가 없거나 `OPS`에 없으면 오류(`op: fly`, `answer: 3`만 있는 경우).
5. **abstain**: `op`가 `abstain`이면 다른 필드는 보지 않고 바로 `Program(op="abstain", cells=[], answer=None, reason=...)`을 돌려준다. `reason`이 없거나 `REASONS`에 없으면 오류가 아니라 `not_in_document`로 둔다(모델이 낸 이유가 이상해도 보류 자체는 유효).
6. **cells**: 없거나 `-`거나 빈 값이면 셀 없음. 아니면 쉼표로 나누고, 각 조각의 공백을 지우고, 빈 조각은 건너뛰고, `CellRef.parse(table_id, 조각)`으로 읽는다. 읽지 못하면(`x1`) `ProgramParseError`. 이때 `CellRef.parse`가 던지는 `ValueError`를 그대로 내보내지 말고 `ProgramParseError`로 바꾼다.
7. **answer**: 없거나 빈 값이거나 `-`이면 `None`.
8. **text**: `op`가 `text`이면 답이 있어야 하고(없으면 오류, `op: text ; cells: - ; answer: -`), 셀은 무시해서 `Program(op="text", cells=[], answer=답)`.
9. **그 밖의 op**: 셀이 하나도 없으면 오류(`op: lookup ; cells: - ; answer: 1`), 12개를 넘으면 오류(20개 셀 예). 아니면 `Program(op, cells, answer)`.

검증(셀이 표 범위 안인지, 답이 셀과 맞는지)은 이 파서가 하지 않는다. 그건 4단계 검증기의 일이다. 이 파서는 문법만 본다.

## `make_abstain(reason) -> Program`, `make(op, cells, answer) -> Program`

휴리스틱 기준선이 쓰는 작은 생성 함수. 각각 `Program(op="abstain", cells=[], answer=None, reason=reason)`, `Program(op=op, cells=cells, answer=answer)`.

## 테스트가 보는 것

- 왕복: 위 예 네 개를 `parse` → `serialize`하면 원래 문자열이 그대로 나와야 한다.
- 거부: `""`, `"hello"`, 모르는 op, 셀 없는 lookup, 잘못된 셀 id, 중복 필드, op 없음, 답 없는 text, 셀 20개.

## 끝났는지 확인

```bash
pytest tests/test_program_verifier.py -q
python scripts/rewrite_parity.py program       # 원본과 차이 0개
pytest -q && ruff check src tests scripts
```

1단계와 같은 흐름으로 `rewrite/02-program` 브랜치에서 작업하고 푸시한다.
