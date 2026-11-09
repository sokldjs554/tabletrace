# 3단계 명세 — `tools/cells.py` (셀 읽기·찾기·겹침 점수)

전용 테스트 파일은 없다. 이 모듈은 검증기(`verify/verifier.py`), 휴리스틱 기준선(`agent/heuristic.py`), 지표(`eval/metrics.py`), 도구 등록(`tools/registry.py`)이 쓰므로 `pytest -q` 전체가 간접 테스트다. **끝났는지는 `python scripts/rewrite_parity.py cells`로 판단한다** — 표 6만여 셀과 헤더의 정규화, 모든 표의 가장자리 셀 읽기(범위 밖 포함), 평가 질문 3천여 개에 대한 셀 찾기와 행·열 겹침 점수를 원본과 비교한다(10만여 입력). 차이 0개여야 끝이다.

자료형: `schema.Table`(51행. `table.cell(row, col)`은 범위 밖이면 `IndexError`, 행이 헤더보다 짧으면 빈 문자열), `schema.CellRef`(`.cid`가 `r{row}c{col}`).

## 공개 이름

`normalize_text`, `lookup_cell`, `find_cells`, `row_overlap_scores`, `column_overlap_scores`. 다른 모듈이 이 다섯을 import한다.

## `normalize_text(s: str) -> str`

비교용 정규화. 검증기가 답과 셀을 비교할 때, 기준선이 질문과 셀을 겹쳐 볼 때 이 결과를 쓴다. 순서대로:

1. `None`이면 빈 문자열.
2. 유니코드 **NFKC** 정규화(전각 숫자·영문 → 반각, `㎡` 같은 호환 문자 분해).
3. 유니코드 빼기 기호 `−`(U+2212)와 en dash `–`(U+2013)를 ASCII `-`로. NFKC는 이 둘을 바꾸지 않으므로 따로 해야 한다.
4. 연속된 공백 문자(탭·줄바꿈 포함)를 공백 하나로 줄이고 앞뒤 공백을 지운다.
5. 소문자로.

## `lookup_cell(table, row, col) -> dict`

셀 하나와 화면에 보여 줄 맥락. 반환하는 dict의 키는 정확히 다섯 개:

- `"cell"`: 그 셀의 cid(`"r2c5"`).
- `"text"`: `table.cell(row, col)`의 결과(원문 그대로, 정규화하지 않음).
- `"header"`: 그 열의 헤더 문자열.
- `"row_label"`: 그 행의 **첫 번째 셀** 원문. 행이 빈 리스트면 빈 문자열.
- `"unit"`: `table.units`에 그 열의 단위가 있으면 그 값, 없으면 `None`.

범위 밖이면 `table.cell`이 던지는 `IndexError`를 그대로 내보낸다(잡지 않는다). 음수 행·열도 범위 밖이다.

## `find_cells(table, text, exact=True) -> list[CellRef]`

정규화한 `text`와 같은(`exact=True`) 또는 그것을 포함하는(`exact=False`) 셀을 모두 찾는다.

- 정규화한 질의가 빈 문자열이면 빈 리스트.
- 순서: 행 0부터, 각 행에서 열 0부터. 그 순서대로 리스트에 담는다.
- 열은 **헤더 개수만큼만** 본다. 행이 헤더보다 짧으면 없는 칸은 빈 문자열로 보고, 행이 헤더보다 길면 넘치는 칸은 보지 않는다.
- 셀 쪽도 정규화해서 비교한다.
- 반환 `CellRef`의 `table_id`는 `table.id`.

## `row_overlap_scores(table, tokens, exclude_col=None) -> list[float]`

휴리스틱 기준선이 "질문에 나온 말이 가장 많이 들어 있는 행"을 고를 때 쓰는 점수. 행마다 하나의 float.

- 행의 **모든 칸**을 본다(이 함수는 헤더 개수로 자르지 않는다. `find_cells`와 다른 점).
- `exclude_col`이 주어지면 그 열의 칸은 건너뛴다.
- 칸마다 정규화한 칸 문자열에 대해, `tokens` 중 **빈 문자열이 아니고** 칸 문자열의 부분 문자열인 토큰의 개수를 센다. 행의 점수는 그 개수를 모든 칸에 걸쳐 더한 값을 float으로.
- `tokens`는 호출하는 쪽이 이미 정규화해서 넘긴다. 이 함수는 토큰을 다시 정규화하지 않는다.

## `column_overlap_scores(table, tokens) -> list[float]`

열마다 하나의 float. 정규화한 헤더 문자열에 대해, 빈 문자열이 아닌 토큰 중 부분 문자열인 것의 개수.

## 끝났는지 확인

```bash
python scripts/rewrite_parity.py cells     # 차이 0개
pytest -q                                   # 검증기·기준선·API 테스트가 이 모듈을 거친다
ruff check src tests scripts
git diff --stat origin/main                 # src/tabletrace/tools/cells.py 가 바뀌었는지 먼저 확인
```

브랜치는 `rewrite/03-cells`, 커밋 메시지는 `rewrite: tools/cells.py (owner)`.
