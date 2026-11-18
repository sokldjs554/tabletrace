# 7단계 명세 — `eval/metrics.py` (평가 지표)

이 프로젝트의 모든 보고 수치(verified EM, 근거 셀 정확도, 보류 재현율 등)는 이 파일의 세 함수가 계산한다. 평가 러너(`eval/run.py`)가 문항마다 기록을 만들고, `summarize`가 그 기록에서 `metrics.json`의 지표를 낸다. `answer_match`는 평가 러너, 본인이 쓴 강화학습 보상(`training/evidence_reward.py`), 근거 오류 분석, 대화 평가, 브라우저 데모가 함께 쓴다.

테스트는 `tests/test_eval_metrics.py`(지금 구현으로 모두 통과한다). **끝났는지는 `python scripts/rewrite_parity.py metrics`로 본다.** 저장된 평가 276건 전체의 `summarize` 결과와, 저장된 답 쌍 1만 5천여 개의 `answer_match`, 셀 쌍 전부의 `cells_match`를 원본과 비교한다. 차이 0개여야 저장된 `metrics.json`이 그대로 재현된다.

의존: `tools.cells.normalize_text`(3단계, 본인 작성), `tools.numbers.parse_number`(1단계, 본인 작성). 이 둘 말고는 import하지 않는다.

## 공개 이름

`answer_match`, `cells_match`, `summarize`. 다른 모듈이 이 셋을 import한다.

## `answer_match(pred: str | None, gold: str | None) -> bool`

모델의 답이 정답과 같은지. 순서대로:

1. 둘 중 하나라도 `None`이면, **둘 다 `None`일 때만** `True`.
2. 둘을 `normalize_text`로 정규화해 같으면 `True`.
3. 둘을 각각 `parse_number`로 읽는다(정규화하지 않은 원래 문자열을 넘긴다). 둘 다 숫자로 읽히고, 단위가 **같거나 둘 중 하나라도 단위가 없으면**(`None`), 값의 차이가 허용 범위 안일 때 `True`.
   - 허용 범위: `|pred 값 - gold 값| <= max(1e-6, 0.005 × |gold 값|)`. 정답 값의 0.5%이고, 정답이 0에 가까우면 최소 `1e-6`이다. 기준은 **정답 쪽 값**이다(대칭이 아니다).
   - 경계는 포함한다(`<=`).
4. 그 밖에는 `False`. 단위가 서로 다르면(둘 다 있고 다르면) 값이 같아도 `False`다.

## `cells_match(pred: list[str], gold: list[str]) -> bool`

모델이 댄 근거 셀이 정답 셀과 같은지. 셀은 `"r2c5"` 같은 cid 문자열이다.

- 순서와 중복을 무시하고 **집합으로 같으면** `True`.
- 단, 정답 셀이 비어 있으면 항상 `False`(둘 다 비어 있어도 `False`).

## `summarize(rows: list[dict]) -> dict`

문항별 기록(평가 러너가 만드는 dict) 목록에서 지표를 낸다. 쓰는 필드: `gold_status`(`"answered"` 또는 `"abstained"`), `gold_op`, `source`, 그리고 참/거짓 필드 `verified_correct`, `raw_correct`, `cells_exact`, `cells_exact_raw`, `evidence_repaired`, `cells_overlap`, `op_correct`, `calc_correct`, `unit_error`, `pred_abstained`, `parse_fail`, `verifier_changed`, `truncated_gold`. 선택 필드: `category`, `ms`. 다른 필드는 무시한다.

### 문항 묶음

- **전체**: 모든 기록.
- **답할 수 있는 문항**: `gold_status == "answered"`.
- **답이 없는 문항**: `gold_status == "abstained"`.
- **조회 문항**: 답할 수 있는 문항 가운데 `gold_op == "lookup"`.
- **계산 문항**: 답할 수 있는 문항 가운데 `gold_op != "lookup"`. 조회가 아닌 것은 모두 여기 든다. 본문에서 답하는 문항(`gold_op == "text"`)도 계산 문항으로 센다.

### 비율

비율은 "묶음 안에서 그 필드가 참인 기록의 수 ÷ 묶음의 크기"를 **소수 넷째 자리에서 반올림**(`round(x, 4)`)한 값이다. 참은 파이썬의 참 거짓 판단(`True`, `1` 등)을 따른다. **묶음이 비어 있으면 `None`**이다(0이 아니다).

### 돌려주는 dict

키는 **정확히 아래 순서**로 넣는다. 순서가 다르면 값이 같아도 새로 만든 `metrics.json`이 저장된 파일과 글자가 달라진다.

| 키 | 값 |
|---|---|
| `n` | 전체 기록 수 |
| `n_answerable` | 답할 수 있는 문항 수 |
| `n_gold_abstain` | 답이 없는 문항 수 |
| `n_calc` | 계산 문항 수 |
| `n_lookup` | 조회 문항 수 |
| `verified_em` | 전체에서 `verified_correct`의 비율 |
| `answer_em_answerable` | 답할 수 있는 문항에서 `verified_correct` |
| `raw_answer_em_answerable` | 답할 수 있는 문항에서 `raw_correct` |
| `evidence_cells_exact` | 답할 수 있는 문항에서 `cells_exact` |
| `evidence_cells_exact_raw` | 답할 수 있는 문항에서 `cells_exact_raw` |
| `evidence_repaired_rate` | 답할 수 있는 문항에서 `evidence_repaired` |
| `evidence_cells_overlap` | 답할 수 있는 문항에서 `cells_overlap` |
| `op_acc` | 전체에서 `op_correct` |
| `lookup_em` | 조회 문항에서 `verified_correct` |
| `calc_em` | 계산 문항에서 `verified_correct` |
| `calc_result_correct` | 계산 문항에서 `calc_correct` |
| `unit_error_rate` | 계산 문항 가운데 `unit_error`가 `None`이 아닌 것에서 `unit_error` |
| `abstain_recall` | 답이 없는 문항에서 `pred_abstained` |
| `false_abstain_rate` | 답할 수 있는 문항에서 `pred_abstained` |
| `abstain_precision` | 아래 참고 |
| `parse_fail_rate` | 전체에서 `parse_fail` |
| `verifier_corrections` | 답할 수 있는 문항에서 `verifier_changed` |
| `truncated_gold_rate` | 전체에서 `truncated_gold` |
| `verified_em_untruncated` | `truncated_gold`가 거짓인 기록에서 `verified_correct` |
| `mean_ms_per_example` | 기록마다 `ms`(없으면 0)를 더해 전체 기록 수로 나누고 **소수 첫째 자리에서 반올림**. 기록이 없으면 `None` |
| `by_source` | 아래 참고 |
| `by_category` | 아래 참고. 조건에 맞을 때만 키를 넣는다 |

- **`abstain_precision`**: `pred_abstained`가 참인 기록이 하나라도 있으면, 그 가운데 `gold_status == "abstained"`인 것의 비율(넷째 자리 반올림). 하나도 없으면 `None`. 값은 `None`이어도 **키는 항상 그 자리에 있다**.
- **`by_source`**: `source` 값마다 `{"n": 그 출처의 기록 수, "verified_em": 그 출처에서 verified_correct의 비율}`. 출처는 **기록에 처음 나온 순서대로** 넣는다. 기록이 없으면 빈 dict.
- **`by_category`**: `category`가 참인 기록(`r.get("category")`가 빈 문자열·`None`이 아닌 것)이 하나라도 있을 때만 넣는다. `category`가 없거나 비어 있는 기록은 빠진다. 키는 **범주 이름의 정렬 순서**, 값은 `by_source`와 같은 꼴.

빈 목록(`[]`)도 받는다: `n`과 개수들은 0, 비율과 `mean_ms_per_example`은 `None`, `by_source`는 빈 dict, `by_category` 키는 없다.

평가 러너는 이 dict에 `gold_subject_fail_rate`, `entity_check` 같은 키를 더 붙인다. 그것은 이 함수의 일이 아니다.

## 생각해 볼 점 (면접에서 물을 만한 것)

- `verified_em`은 전체 문항에서 잰다. 답이 없는 문항에서 보류하면 맞은 것으로 센다. 그래서 보류를 잘하는 모델은 답할 수 있는 문항의 정답률(`answer_em_answerable`)보다 `verified_em`이 높을 수 있다.
- 숫자 허용 범위를 정답 값 기준 0.5%로 둔 까닭과, 그 때문에 `answer_match(a, b)`와 `answer_match(b, a)`가 다를 수 있는 경우.
- 단위가 한쪽에만 있으면 같은 것으로 본다. "1,062,201"과 "1,062,201 명"은 같은 답이다. 반대로 "3 km"와 "3 m"는 다르다.
- 본문 문항이 계산 묶음에 드는 것. 계산 정답률을 읽을 때 무엇이 섞여 있는지.
- 비율이 비면 0이 아니라 `None`인 까닭(문항이 없는 것과 하나도 못 맞힌 것은 다르다).

## 끝났는지 확인

```bash
pytest tests/test_eval_metrics.py -q          # 전부 통과
python scripts/rewrite_parity.py metrics      # 차이 0개
pytest -q                                      # 평가 러너, 보상, 데모 테스트가 이 모듈을 거친다
ruff check src tests scripts
```

## 이 단계의 순서

`docs/rewrite/README.md`의 "한 단계의 흐름"과 같다. 이 단계에 맞춰 적으면:

```bash
git switch main && git pull
git switch -c rewrite/08-metrics
git mv src/tabletrace/eval/metrics.py src/tabletrace/eval/_ref_metrics.py   # 참고용으로 치운다. 먼저 명세와 테스트만 보고 써 본다
# src/tabletrace/eval/metrics.py 를 새로 쓴다
pytest tests/test_eval_metrics.py -q
python scripts/rewrite_parity.py metrics
pytest -q && ruff check src tests scripts
git rm src/tabletrace/eval/_ref_metrics.py
git add src/tabletrace/eval/metrics.py
git commit -m "rewrite: eval/metrics.py (owner)"       # AI 공동 작성 표식(Co-Authored-By)을 넣지 않는다
git push -u origin rewrite/08-metrics
```

푸시했다고 알려 주면 AI 도구가 브랜치를 받아 테스트와 동작 비교를 다시 돌려 리뷰한다. 통과하면 GitHub에서 Pull request를 만들어 `main`에 합친다.

동작 비교 스크립트는 원본을 `origin/main`에서 가져온다. `main`에 합치기 전에는 원본이 그대로 있으니 비교가 된다. 이 스크립트가 잡는지 미리 확인했다. 허용 범위를 0.5%에서 0.4%로 바꾸거나, 본문 문항을 계산 묶음에서 빼거나, 키 순서를 바꾸거나, 정답 셀이 빈 경우를 일치로 보게 고친 판 네 가지를 넣어 보았고, 넷 다 차이로 나왔다(테스트도 넷 다 실패했다).
