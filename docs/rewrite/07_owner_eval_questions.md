# 과제 E: 평가 문항을 직접 검수하고 직접 쓰기

> **끝났다(2026-11-16, PR #7).** 검수 결과는 문제없음 26, 고쳐야 함 4이고 새 문항은 30개다. 결과와 한계는 `docs/REPORT.md` §25에 있다. 아래는 과제를 할 때의 안내문 그대로다.

## 왜 하는가

한국어 수작업 평가 30문항(`data/ko/custom_eval.jsonl`)은 AI 코딩 도구가 썼다. 문서의 한계에도 그렇게 적혀 있다. 공고의 우대사항에는 "한국어 벤치마크 구축 경험"이 있다. 이 과제를 끝내면 두 가지가 사실이 된다.

- 기존 30문항을 본인이 한 문항씩 확인했다.
- 본인이 직접 쓴 평가 문항이 저장소에 있고, 모델들을 그 문항으로 평가했다.

**문항은 본인이 쓴다.** AI 도구에게 질문을 만들어 달라고 하지 않는다. 그렇게 하면 이 과제의 뜻이 없어진다. 도구(`scripts/owner_eval_tool.py`)는 표를 보여 주고, 계산 답의 표기를 맞춰 주고, 파일을 검사할 뿐이다. 질문은 한 줄도 쓰지 않는다.

걸리는 시간은 검수 40분쯤, 문항 쓰기 2~3시간쯤이다.

## 준비

```bash
cd tabletrace
git checkout main && git pull
git checkout -b rewrite/07-owner-eval
source .venv/bin/activate            # 전에 만든 가상환경. 없으면 docs/rewrite/README.md의 "환경 준비"
python scripts/owner_eval_tool.py check      # 두 파일이 "아직 없습니다"라고 나오면 정상
```

## 과제 A: 기존 30문항 검수

```bash
python scripts/owner_eval_tool.py review | less      # 스페이스로 넘기고 q로 나간다
```

문항마다 질문, 정답, 정답 셀(`>>` `<<`로 표시), 표, 필요한 경우 본문이 나온다. 문항마다 아래 넷을 본다.

1. 표(또는 본문)를 보고 답이 하나로 정해지는가. 두 행이 다 맞는 질문은 아닌가.
2. 적힌 정답이 맞는가. 정답 셀이 맞는가.
3. 질문이 자연스러운 한국어인가. 사람이 실제로 물을 만한가.
4. 보류 문항(`abstain`)이라면, 정말 표와 본문에 답이 없는가.

`less`는 읽기만 하는 화면이다. 여기에 판정을 입력하지 않는다. 스페이스로 다음 쪽, `b`로 앞쪽, `g`로 맨 처음, `/ko_custom_12`와 엔터로 그 문항 찾기, `q`로 나가기다. 판정은 따로 파일에 적는다. 터미널 창을 하나 더 열어(⌘N) 한쪽에서 읽고 다른 쪽에서 적으면 편하다.

판정을 `data/ko/custom_eval_review.jsonl`에 한 줄에 하나씩 적는다. 30줄이어야 한다. 문항 번호 30개를 손으로 치지 않아도 되게, 판정 칸을 비운 파일을 만들어 주는 명령이 있다.

```bash
python scripts/owner_eval_tool.py template             # 30줄짜리 빈 검수 파일을 만든다. verdict는 비어 있다
nano data/ko/custom_eval_review.jsonl                  # 또는 VS Code: code data/ko/custom_eval_review.jsonl
```

`nano`에서는 화살표로 움직여 따옴표 사이에 적고, Ctrl+O와 엔터로 저장하고, Ctrl+X로 나간다. 텍스트 편집기(TextEdit)는 따옴표를 둥근 따옴표로 바꿔서 파일을 망가뜨리니 쓰지 않는다. 판정을 비워 둔 줄은 검사를 통과하지 못한다.

```json
{"qid": "ko_custom_01", "verdict": "ok", "comment": ""}
{"qid": "ko_custom_02", "verdict": "fix", "comment": "여기에 무엇이 문제인지 적는다"}
```

- `verdict`는 셋 가운데 하나다. `ok`(문제 없음), `fix`(고쳐야 함), `drop`(빼야 함).
- `fix`나 `drop`이면 `comment`에 까닭을 적는다. `ok`여도 적고 싶은 것이 있으면 적는다.
- **기존 문항 파일은 고치지 않는다.** 저장된 평가 결과가 그 문항에 묶여 있다. 검수 결과는 기록으로 남기고, 문서에 "30문항 가운데 몇 문항에 문제가 있었다"로 적는다.

## 과제 B: 새 문항 쓰기

`data/ko/owner_eval.jsonl`에 한 줄에 한 문항씩 쓴다.

### 얼마나, 어떤 문항을

**30문항을 권한다(적어도 20문항).** 표는 10개 이상에서 고른다. 범주는 아래처럼 섞는다.

| 범주 (`category`) | 연산 (`op`) | 무엇을 묻는가 | 권하는 수 |
|---|---|---|---:|
| `cell` | `lookup` | 표의 셀 하나가 답인 질문 | 12 |
| `calc` | `diff` `sum` `avg` `ratio` `pct_change` | 두 셀로 계산해야 하는 질문 | 6 |
| `unit_period` | `lookup` (또는 `text`) | 기간이나 단위 조건으로 행을 가려야 하는 질문 | 4 |
| `text_table` | `text` | 답이 표가 아니라 본문에 있는 질문 | 4 |
| `abstain` | `abstain` | 표와 본문 어디에도 답이 없는 질문 | 4 |

### 표 고르기

```bash
python scripts/owner_eval_tool.py tables --unused          # 기존 문항이 쓰지 않은 시험 표
python scripts/owner_eval_tool.py tables --with-passage    # 본문이 있는 표 (text_table 문항에 필요)
python scripts/owner_eval_tool.py show ko_29fbd6328d       # 표 하나를 셀 번호와 함께 본다
```

- **시험 분할의 표만 쓴다.** 학습에 쓰인 표로 문항을 만들면 검사가 거부한다.
- 기존 문항이 쓰지 않은 표를 먼저 고른다.
- 행은 `r0`부터, 열은 `c0`부터 센다. 머리글 줄은 행으로 세지 않는다.
- 계산 문항은 숫자가 든 열이 있는 표에서 쓴다. 머리글 옆에 `[명]`처럼 단위가 보이는 열이 계산하기 좋다.

### 한 줄의 모양

아래 다섯 줄은 **기존 문항**이다. 형식만 본다. 내용을 가져다 쓰지 않는다.

```json
{"qid": "ko_custom_01", "category": "cell", "question": "2018년 박스오피스에서 안시성의 관객수는 몇 명입니까?", "answer": "5,436,789", "doc_id": "doc_ko_29fbd6328d", "table_id": "ko_29fbd6328d", "op": "lookup", "gold_cells": [[6, 4]], "source": "custom", "needs_text": false, "unit": "명"}
{"qid": "ko_custom_03", "category": "calc", "question": "신과함께: 인과 연과 어벤져스: 인피니티 워의 관객수 차이는 몇 명입니까?", "answer": "1,062,201 명", "doc_id": "doc_ko_29fbd6328d", "table_id": "ko_29fbd6328d", "op": "diff", "gold_cells": [[0, 4], [1, 4]], "source": "custom", "needs_text": false, "unit": "명"}
{"qid": "ko_custom_06", "category": "unit_period", "question": "2017년 12월에 개봉한 영화 중 2018년 박스오피스 순위가 더 높은 영화는 무엇입니까?", "answer": "신과함께: 죄와 벌", "doc_id": "doc_ko_29fbd6328d", "table_id": "ko_29fbd6328d", "op": "lookup", "gold_cells": [[3, 1]], "source": "custom", "needs_text": false}
{"qid": "ko_custom_07", "category": "text_table", "question": "이 2018년 박스오피스 순위는 언제부터의 통계를 집계합니까?", "answer": "2018년 1월 1일", "doc_id": "doc_ko_29fbd6328d", "table_id": "ko_29fbd6328d", "op": "text", "gold_cells": [], "source": "custom", "needs_text": true}
{"qid": "ko_custom_08", "category": "abstain", "question": "2018년 박스오피스에서 보헤미안 랩소디의 관객수는 몇 명입니까?", "answer": null, "doc_id": "doc_ko_29fbd6328d", "table_id": "ko_29fbd6328d", "op": "abstain", "reason": "not_in_document", "gold_cells": [], "source": "custom", "needs_text": false}
```

본인이 쓰는 줄에서 달라지는 것은 이렇다.

| 항목 | 쓰는 법 |
|---|---|
| `qid` | `ko_owner_01`, `ko_owner_02`, … 겹치지 않게 |
| `source` | `"owner"` |
| `doc_id`, `table_id` | `show`의 첫 줄에 나온다 |
| `gold_cells` | `[[행, 열]]`. 계산 문항은 셀 둘(합과 평균은 셋 이상도 된다). `text`와 `abstain`은 `[]` |
| `answer` | 아래 규칙대로 |
| `needs_text` | `op`가 `text`일 때만 `true` |
| `unit`, `note`, `alt_answers` | 없어도 된다. `note`에 문항의 의도를 적어 두면 나중에 설명하기 좋다 |

### 정답(`answer`)의 규칙

- **조회(`lookup`)**: 정답 셀의 글자를 **그대로** 적는다. 쉼표, 띄어쓰기, 괄호까지 같아야 한다. `show`가 보여 주는 대로 옮긴다.
- **계산**: 직접 적지 않는다. 도구가 내는 문자열을 그대로 넣는다. 셀의 순서도 그대로 쓴다.

  ```bash
  python scripts/owner_eval_tool.py calc ko_29fbd6328d diff 0,4 1,4
  # 정답 문자열(answer에 그대로 넣는다): 1,062,201 명
  # gold_cells: [[0, 4], [1, 4]]
  ```

  `diff`는 첫 셀에서 둘째 셀을 뺀다. `pct_change`는 (첫째 − 둘째) ÷ 둘째 × 100이다.
- **본문(`text`)**: 본문에 **글자 그대로 들어 있는** 구절을 적는다.
- **보류(`abstain`)**: `"answer": null`, `"reason": "not_in_document"`.

### 좋은 문항

- 표를 보고 답이 **하나로** 정해진다.
- 표의 글자를 이어 붙인 질문이 아니라 **자기 말로** 묻는다. "A의 B는 무엇입니까?"만 30개 쓰지 않는다. 순위, 처음과 마지막, 두 조건을 함께 만족하는 행처럼 표를 읽어야 답할 수 있는 질문을 섞는다.
- 쉬운 문항과 어려운 문항을 섞는다. 무엇이 어려운 문항인지 `note`에 한 줄 적는다.
- 보류 문항은 그럴듯해야 한다. 표에 있을 법한데 없는 것을 묻는다(표에 없는 연도, 표에 없는 열).
- 이름이 비슷한 행이 여럿인 표에서는 어느 행인지 질문에서 분명히 한다. 일부러 헷갈리게 쓴 문항이라면 `note`에 적는다.

## 확인

```bash
python scripts/owner_eval_tool.py check       # 두 파일 모두 "통과"가 나와야 한다
python scripts/check_data.py                  # 끝에 "errors": 0
python -m pytest -q tests/test_owner_eval.py  # 건너뛴 테스트 없이 통과
```

`check`는 틀린 곳을 문항 번호와 함께 알려 준다. 가장 흔한 것은 조회 답이 셀의 글자와 다른 경우다(쉼표나 띄어쓰기).

## 올리기

**본인 컴퓨터에서 본인 계정으로** 커밋한다(`docs/rewrite/README.md`의 규칙 2).

```bash
git add data/ko/owner_eval.jsonl data/ko/custom_eval_review.jsonl
git commit -m "Owner-written evaluation questions and review of the 30 hand-made ones"
git push -u origin rewrite/07-owner-eval
```

GitHub에서 Pull Request를 열고, 검사(CI)가 초록색이 되면 병합한다. 병합한 뒤 대화에 알려 주면 AI 도구가 이어서 한다.

- 휴리스틱 기준선과 mT5-small로 새 문항을 평가한다(CPU에서 된다).
- EXAONE으로 평가할 노트북 절을 준비한다(GPU가 필요하다).
- 검수 결과와 새 문항의 수, 평가 결과를 문서에 적는다. 문항의 작성자는 본인으로 적는다.

## 물어봐도 되는 것과 안 되는 것

- 되는 것: 형식이 헷갈릴 때, `check`가 낸 메시지의 뜻, 어떤 표가 계산 문항에 맞는지 고르는 법.
- 안 되는 것: 질문 문장을 대신 써 달라는 것, 쓴 질문을 고쳐 달라는 것. 검토 의견("이 질문은 두 행에 다 맞는다")까지는 줄 수 있다.
