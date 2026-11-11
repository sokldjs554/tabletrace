# 4b단계 명세 — 검증기에 "근거 복구 끄기" 옵션 추가 (`verify/verifier.py`)

> **상태: 완료.** 소유자가 구현해 2026-11-11 PR #5로 병합했다(커밋 `9bd0f54`). 리뷰와 재검증 결과는 `docs/rewrite/LOG.md`와 `docs/REPORT.md` §19.8.

4단계에서 직접 쓴 검증기에 옵션 하나를 더한다. 새로 쓰는 것이 아니라 **본인 코드를 고치는 작업**이고, 10~20줄이면 된다.

## 왜 필요한가

검증기는 조회 답에서 "모델이 인용한 셀에 답이 없으면, 답과 같은 셀이 표에 하나뿐일 때 근거를 그 셀로 고쳐서 답한다"(근거 복구, 4단계 명세 7번의 `evidence_repaired`). 저장된 예측을 다시 분석해 보니 이 복구가 하는 일은 다음과 같았다(`docs/REPORT.md` §19.1, §19.2).

- 약한 모델의 점수는 복구가 지탱한다. 복구를 끄고 보류로 채점하면 verified EM이 mT5 최종 32.8% → 20.2%, EXAONE 300개 53.1% → 23.5%로 내려간다. 전체 데이터 EXAONE은 84.3% → 83.8%로 거의 그대로다.
- 복구는 오답도 함께 내보낸다. "답 텍스트가 표의 한 셀과 같다"는 것만 확인하기 때문이다. mT5 최종 모델의 오답 유출은 42.2%이고 복구가 없으면 16.7%다.

지금 이 "복구 없이" 값은 **계산값**이다. 검증기 코드에서 복구 분기 다음이 보류라는 점에 근거해 저장된 출력에서 셌다(`scripts/evidence_error.py`). 검증기에 끄는 옵션이 있으면 같은 모델 출력을 실제로 다시 검증해 측정값으로 바꿀 수 있고, 서비스에서도 "근거가 틀리면 답하지 않는" 운영을 고를 수 있다.

## 무엇을 바꾸나

`resolve`에 키워드 인자 하나를 더한다.

```python
def resolve(question, table, program, retrieval_ok=True, context=None, passage_id="context",
            entity_check=True, column_check=False, repair=True):
```

- **`repair=True`(기본값)**: 지금과 완전히 같다. 답, 근거, 검사 목록, 실행 추적이 하나도 달라지면 안 된다.
- **`repair=False`**: 조회(`lookup`)에서 제안 답이 인용 셀과 같지도 않고 부분 일치도 아니며 비어 있지도 않을 때(4단계 명세 7번에서 `cell_find`를 부르던 바로 그 조건), 다른 셀을 찾지 않고 곧바로 **보류 `"verification_failed"`** 한다.
  - `cell_find` 도구를 부르지 않는다. 실행 추적(`trace`)에 `cell_find`가 없어야 한다.
  - 검사 `evidence_repaired`를 붙이지 않는다. 그 앞의 검사 `answer_matches_cell`(실패)은 지금처럼 붙는다.
- **바뀌지 않는 것**
  - 답이 인용 셀과 같거나 부분 일치인 조회, 계산 op, `text`, `abstain`, 범위·기간 검사.
  - `column_check`의 열 보정(`column_repaired`). 이것은 따로 켜고 끄는 스위치이고 `repair`와 무관하다.
  - 개체 일치 검사(`entity_check`). 순서도 그대로다.
- 인자는 맨 뒤에 둔다. 기존 호출부(`eval/run.py`, `agent/graph.py`, `training/*.py`)는 고치지 않아도 된다.

## 테스트

`tests/test_verifier_repair_option.py`. 지금은 `resolve`에 `repair` 인자가 없어서 **건너뛴다(skipped)**. 인자를 넣으면 자동으로 실행된다. 테스트는 고치지 않는다.

1. 기본값에서는 지금처럼 근거를 고쳐 답한다.
2. `repair=False`면 같은 입력에서 보류하고(`verification_failed`), 근거 셀이 없고, `evidence_repaired` 검사와 `cell_find` 호출이 없다.
3. `repair=False`가 다른 경로(맞는 조회, 부분 일치, 계산, 보류 프로그램)를 건드리지 않는다.
4. 저장된 모델 출력(EXAONE·mT5의 수작업 30문항)에서, 복구가 있었던 문항은 보류로 바뀌고 나머지는 그대로다.

## 끝났는지 확인

```bash
pytest tests/test_verifier_repair_option.py -q     # "skipped"가 아니라 "passed"여야 한다
python scripts/rewrite_parity.py verifier          # 기본 동작이 그대로인지: 차이 0개
pytest -q && ruff check src tests scripts
git diff --stat origin/main                        # src/tabletrace/verify/verifier.py 가 바뀌었는지 확인
```

브랜치는 `rewrite/05-repair-option`, 커밋 메시지는 `verifier: option to withhold instead of repairing evidence (owner)`. 푸시한 뒤 알려 주면 리뷰하고, 병합 뒤 아래 측정을 이 세션에서 돌린다.

## 병합 뒤 측정 (AI 도구가 실행)

저장된 모델 출력을 `--no-repair`로 다시 검증해 계산값과 문항 단위로 대조한다. 평가 스크립트에는 이 옵션이 이미 연결되어 있다(검증기에 인자가 없으면 안내 문구와 함께 멈춘다).

```bash
python -m tabletrace.eval.run --planner engine --replay-from experiments/eval/exaone_full_vllm_ko_test --no-entity-check --no-repair \
    --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B --max-in 672 --corpus data/ko/documents.jsonl \
    --data data/ko/test.jsonl data/ko/synthetic_test.jsonl --out experiments/eval/exaone_full_vllm_ko_test_norepair
python scripts/evidence_error.py --compare-no-repair experiments/eval/exaone_full_vllm_ko_test experiments/eval/exaone_full_vllm_ko_test_norepair
```

재검증은 원래 실행과 같은 토크나이저와 입력 예산을 줘야 표의 행이 같은 곳에서 잘린다. EXAONE 토크나이저는 Hugging Face에서 받을 수 있어 위 명령은 맥에서도 된다. mT5 결과는 토크나이저 파일이 저장소에 없어서 이 세션에서 돌린다.
