# 과제 C: 화학 평가 문항 검수

> **끝났다(2026-11-19, PR #9).** 문제없음 80, 고쳐야 함 14(논문 표 5, 교과서 표 9), 빼야 함 0. 그 문항을 빼고 세어도 아래에 적어 둔 다섯 비교의 결론이 모두 같다. 결과는 `docs/REPORT.md` §32에 있다. 아래는 과제를 할 때의 안내문 그대로다.

## 왜 하는가

화학 평가 문항 94개는 AI 코딩 도구가 썼고 아무도 확인하지 않았다. 포트폴리오 5쪽과 문서들은 그래서 "화학 문항은 AI로 작성했으며 사람이 따로 검토하지 않았습니다"라고 적는다. 한국어 30문항을 검수했을 때는 4문항에서 문제가 나왔다(그중 하나가 %와 %p를 헷갈린 정답이었다). 화학 문항도 같은 비율로 문제가 있을 수 있다.

검수가 끝나면 두 가지가 사실이 된다.

- 화학 평가 문항 94개를 본인이 한 문항씩 확인했다.
- 문제가 있는 문항을 빼도 화학 결론이 그대로인지(또는 바뀌는지) 쟀다.

**판정은 본인이 한다.** AI 도구에게 문항이 맞는지 묻지 않는다. 그렇게 하면 "사람이 검토했다"가 사실이 아니게 된다. 모르는 화학 용어는 사전이나 교과서로 찾아본다. 도구(`scripts/chem_review_tool.py`)는 문항과 표를 보여 주고 파일을 검사할 뿐 판정하지 않는다.

걸리는 시간은 3~4시간쯤이다. 문항이 영어이고 논문 표는 낯선 기호가 많다. 두 세트를 다른 날 나눠 해도 된다.

| 세트 | 파일 | 문항 | 표 |
|---|---|---:|---|
| 논문 표 (`papers`) | `data/chem_papers/custom_eval.jsonl` | 62 (셀 조회 33, 계산 19, 답 없음 10) | arXiv 화학 논문 12편의 표 20개 |
| 교과서 표 (`textbook`) | `data/chem/custom_eval.jsonl` | 32 (셀 10, 계산 7, 단위·기간 4, 본문 6, 답 없음 5) | OpenStax Chemistry 2e의 표 |

## 순서

```bash
git switch main && git pull
git switch -c review/chem-eval
python scripts/chem_review_tool.py template papers       # 62줄짜리 빈 검수 파일. verdict가 비어 있다
python scripts/chem_review_tool.py review papers | less  # 스페이스로 넘기고 q로 나간다
```

문항마다 논문 제목과 주소, 표 설명(caption), 질문, 정답, 정답 셀(`>>` `<<`로 표시), 표, 필요하면 본문이 나온다. 문항마다 아래 다섯을 본다.

1. 표(또는 본문)를 보고 답이 하나로 정해지는가. 조건(온도, 압력, 물질)을 다 써야 행이 하나로 정해지는데 질문이 일부만 말하지는 않는가.
2. 적힌 정답과 정답 셀이 맞는가. 계산 문항이면 두 셀과 연산(차, 비, 합, 평균, 변화율)이 질문과 맞는가.
3. 단위가 맞는가. 머리글의 단위(`[g/mol]`처럼 표시된다)와 정답의 단위가 어긋나지 않는가. 비율 차이를 %로 적지는 않았는가.
4. 질문이 화학을 아는 사람이 실제로 물을 만한 자연스러운 영어인가.
5. 답 없음 문항(`op abstain`)이면 정말 표와 본문 어디에도 답이 없는가.

판정은 다른 터미널 창에서 검수 파일에 적는다.

```bash
nano data/chem_papers/custom_eval_review.jsonl     # 또는 VS Code. 텍스트 편집기(TextEdit)는 따옴표를 망가뜨리니 쓰지 않는다
```

```json
{"qid": "chem_paper_01", "verdict": "ok", "comment": ""}
{"qid": "chem_paper_02", "verdict": "fix", "comment": "여기에 무엇이 문제인지 적는다"}
```

- `verdict`는 `ok`(문제 없음), `fix`(고쳐야 함), `drop`(빼야 함) 가운데 하나.
- `fix`나 `drop`이면 `comment`에 까닭을 적는다. 한국어로 적어도 된다.
- **문항 파일은 고치지 않는다.** 저장된 평가 결과가 그 문항에 묶여 있다. 판정은 기록으로 남기고, 분석이 문제 문항을 빼고 다시 센다.

교과서 세트도 같다(`template textbook`, `review textbook`, `data/chem/custom_eval_review.jsonl`).

```bash
python scripts/chem_review_tool.py check          # 두 파일이 다 "검수 끝"이 나와야 한다
python scripts/chem_review_analysis.py            # 문제 문항을 빼고 저장된 화학 결과를 다시 센다
pytest tests/test_chem_review.py -q
git add data/chem_papers/custom_eval_review.jsonl data/chem/custom_eval_review.jsonl
git commit -m "review: chemistry evaluation questions (owner)"      # AI 공동 작성 표식을 넣지 않는다
git push -u origin review/chem-eval
```

분석 결과 파일(`experiments/eval/chem_review_analysis.json`)은 커밋하지 않아도 된다. 합친 뒤 AI 도구가 다시 만들어 문서에 넣는다.

## 검수 전에 정해 둔 것

결과를 보고 무엇을 볼지 고르지 않도록, 볼 것을 이 문서와 `scripts/chem_review_analysis.py`에 먼저 적어 두었다(이 파일이 처음 커밋된 때). 문제 문항을 빼고 아래 다섯을 다시 센다.

1. 논문 표 대표 수치: 한국어와 화학으로 튜닝한 모델의 46/62.
2. 논문 표에서 한국어 전용 모델과 화학을 더한 모델: 7 대 3(유의하지 않음).
3. 논문 표에서 한국어 전용 모델과 튜닝하지 않은 모델(30 대 3), 기준선(24 대 9).
4. 교과서 문항에서 화학을 더한 모델과 한국어 전용 모델: 5 대 0(p 0.062).
5. 화학 세 세트의 답 없는 질문에서 반복 학습 모델과 한국어 전용 모델: 10 대 0(p 0.002). 합성 문항 16개는 검수 대상이 아니라 그대로 둔다.

각각 방향(어느 쪽이 더 맞혔나)과 유의성(p < 0.05인가)이 그대로인지 본다. 결론이 바뀌면 바뀐 대로 문서에 적는다. 검수 전에 이 분석을 돌리면 다섯 개 모두 지금 문서의 수치가 그대로 나온다(테스트가 확인한다).

## 끝나면 바뀌는 문장

- 포트폴리오 5쪽 "화학 문항은 AI로 작성했으며 사람이 따로 검토하지 않았습니다"는 "AI로 작성한 화학 문항 94개를 직접 검수했고, 문제가 있는 n개를 빼도 결론은 같았습니다(또는: 이렇게 바뀌었습니다)"가 된다.
- 전달 문서의 "화학 문항의 검수"는 "하지 못한 것" 목록에서 빠진다.
