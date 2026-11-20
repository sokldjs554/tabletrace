# 맥북에서 테스트와 평가 돌리기

pytest, 한국어 형태소 분석기(Kiwi), 전체 평가를 본인 컴퓨터에서 돌리는 방법이다. 여기 적은 명령과 결과는 2026-11-19에 AI 도구가 이 저장소(`2bb0f95` 이후)에서 실제로 돌려 확인한 것이다. GPU가 필요한 것(모델 학습과 생성)은 여기서 하지 않는다. 그것은 Kaggle·Colab 노트북의 일이다.

## 0. 준비 (처음 한 번)

```bash
cd tabletrace
git switch main && git pull
python3 -m venv .venv && source .venv/bin/activate      # 이미 있으면 source만
pip install -e ".[dev]"                                  # 테스트, 서비스, 형태소 분석기까지
pip install -e ".[model]"                                # 선택. PyTorch·Transformers. 아래 3절의 "저장된 값과 똑같이"에 필요하다
```

새 터미널을 열 때마다 `source .venv/bin/activate`를 먼저 한다.

## 1. pytest

```bash
pytest -q                                   # 전체. 2~4분
pytest -q -x                                # 처음 실패에서 멈춘다
pytest -q tests/test_numbers_fix.py         # 파일 하나만
pytest -q -k heuristic                      # 이름에 heuristic이 든 테스트만
```

이렇게 나오면 정상이다.

| 설치 | 결과 | 어디서 확인했나 |
|---|---|---|
| `[dev]`만 | 552 passed, 22 skipped (2분 안쪽) | GitHub Actions CI와 같은 설치 |
| `[dev]` + `[model]` (맥북처럼 모델 파일 없음) | 582 passed, 7 skipped (3~4분) | AI 작업 환경에서 모델 폴더 없이 잰 값 |
| 모델 파일까지 있는 AI 작업 환경 | 599 passed, 1 skipped | `experiments/tests/summary.json` |

테스트는 계속 늘어나므로 통과 수는 이보다 많을 수 있다. 볼 것은 failed가 없는지다. 건너뛰는(skipped) 테스트는 실패가 아니다. 까닭은 셋이다. (결함 40·41의 테스트 19개는 2026-11-20의 수정 뒤로 건너뛰지 않는다.)

- 저장소에 없는 파일이 필요한 테스트 6개: 변환한 mT5 토크나이저(`models/mt5-small-base`), 튜닝한 mT5 모델, EXAONE 토크나이저 폴더. `[model]`을 설치해도 건너뛴다.
- PyTorch·Transformers가 필요한 테스트: `[dev]`만 설치하면 15개를 더 건너뛴다.
- 1개는 본인이 쓴 학습 루프(`training/lm_loop.py`)가 없을 때만 도는 테스트다. 지금은 있으므로 늘 건너뛴다.

다시 쓰기 작업 중에는 그 작업의 테스트 파일만 먼저 돌리고, 끝에 전체를 돌린다. 안내 문서마다 "끝났는지 확인"에 적혀 있다.

## 2. 한국어 형태소 분석기 (Kiwi)

**무엇인가.** `kiwipiepy`(Kiwi)는 한국어 문장을 형태소로 나누고 품사를 붙인다. `pip install -e ".[dev]"`가 함께 설치한다(기본 의존성이다). 이 저장소에서 확인한 판은 0.24.1이다.

**어디에 쓰나.** `src/tabletrace/retrieval/tokenize.py` 한 곳에서 부르고, 세 군데가 그 결과를 쓴다.

| 쓰는 곳 | 하는 일 |
|---|---|
| 낱말 겹침 기준선(`agent/heuristic.py`) | 질문의 낱말과 표의 행·열을 맞춘다 |
| 표 검색(`retrieval/`, BM25) | 질문에 맞는 표를 찾는다 |
| 검증기의 대상 확인(`verify/verifier.py`) | 질문에 나온 고유명사(`NNP`)가 근거 셀의 행에 있는지 본다 |

조사와 어미는 버리고 내용 형태소만 남긴다. 그래서 "러시아가"가 표의 "러시아"와 맞는다.

**잘 깔렸는지 보기.**

```bash
python -c "
from tabletrace.retrieval.tokenize import tokenize, entity_tokens
q = '2002년 K리그 도움 순위표에서 이천수의 도움은 메도보다 몇 개 많습니까?'
print(tokenize(q, 'ko'))
print(entity_tokens(q, 'ko'))
print(tokenize('러시아가 획득한 메달은', 'ko'))
"
```

이렇게 나와야 한다.

```
['2002', '년', 'k', '리그', '도움', '순위', '표', '이천수', '도움', '메도', '개', '많']
['이천수', '메도']
['러시아', '획득', '메달']
```

처음 부를 때 사전을 읽느라 2초쯤 걸린다. 그다음부터는 빠르다. 저장된 평가에서 첫 문항의 시간이 유난히 긴 것도 이 때문이다.

설치가 실패하면(오래된 macOS에서 내려받을 판이 없어 직접 빌드하려다 실패하는 경우 등) 오류 메시지 전체를 알려 준다.

## 3. 전체 평가

### 3.1 기준선 평가 다섯 개 (CPU, 몇 분)

저장된 기준선 결과를 본인 컴퓨터에서 다시 만든다. **결과는 `experiments/` 밖에 쓴다.** `experiments/eval/` 안에 쓰면 저장된 결과를 덮어쓴다.

```bash
mkdir -p ~/tt_eval
T="--tokenizer google/mt5-small"     # [model] 설치와 인터넷이 필요하다. 처음 한 번 토크나이저를 내려받는다
python -m tabletrace.eval.run --planner heuristic $T --no-entity-check --corpus data/ko/documents.jsonl --data data/ko/test.jsonl data/ko/synthetic_test.jsonl --out ~/tt_eval/ko_test
python -m tabletrace.eval.run --planner heuristic $T                   --corpus data/ko/documents.jsonl --data data/ko/test.jsonl data/ko/synthetic_test.jsonl --out ~/tt_eval/ko_test_ec
python -m tabletrace.eval.run --planner heuristic $T --no-entity-check --corpus data/ko/documents.jsonl --data data/ko/custom_eval.jsonl --out ~/tt_eval/ko_custom
python -m tabletrace.eval.run --planner heuristic $T --no-entity-check --corpus data/ko/documents.jsonl --data data/ko/owner_eval.jsonl --out ~/tt_eval/ko_owner
python -m tabletrace.eval.run --planner heuristic $T --no-entity-check --corpus data/chem/documents.jsonl --data data/chem/custom_eval.jsonl --out ~/tt_eval/chem_custom
python -m tabletrace.eval.run --planner heuristic $T --no-entity-check --max-in 4096 --corpus data/chem_papers/documents.jsonl --data data/chem_papers/custom_eval.jsonl --out ~/tt_eval/chem_papers
python -c "import json,glob; [print(p.split('/')[-2], json.load(open(p))['metrics']['verified_em']) for p in sorted(glob.glob('$HOME/tt_eval/*/metrics.json'))]"
```

| 평가 | 저장된 값 | 위 명령으로 | `[model]` 없이(`$T`를 비우면) |
|---|---:|---:|---:|
| 한국어 시험 699문항, 대상 확인 없음 | 36.2% | 36.2% | 36.5% |
| 같은 문항, 대상 확인 켬(`_ec`) | 35.9% | 35.9% | 36.2% |
| AI 도구가 쓴 30문항 | 50.0% | 50.0% | 50.0% |
| 직접 쓴 30문항 | 23.3% | 23.3% | 23.3% |
| 화학 교과서 32문항 | 56.2% | 56.2% | 56.2% |
| 화학 논문 62문항 | 43.5% | 43.5% | 43.5% |

- 평가 하나에 토크나이저가 있으면 1분쯤, 없으면 몇 초다.
- **토크나이저가 왜 필요한가.** 표가 길면 입력 길이(기본 512토큰)에 맞춰 행을 자른다. 저장된 실행은 mT5 토크나이저로 길이를 셌다. 그 파일(`models/mt5-small-base`)은 저장소에 없지만, 공개된 `google/mt5-small`의 토크나이저가 같은 값을 낸다(위 표에서 확인). 토크나이저 없이 돌리면 길이를 어림해서 세기 때문에, 표가 잘리는 문항에서 결과가 조금 달라진다.
- **화학 논문의 `--max-in 4096`.** 저장된 실행은 표를 자르지 않고 전부 보여 줬다. 그런데 그 결과 파일에는 입력 길이가 기록되지 않았다. `--max-in 4096`이면 62문항의 출력이 모두 저장된 것과 같다. 표를 자르면 달라진다. 기본값(512)으로 돌리면 토크나이저가 있을 때 41.9%, 없을 때 40.3%다. 표 전체를 보여 주므로 이 평가에는 토크나이저가 필요 없다. 이 사실은 `docs/dev/issues-log.md` 87번에 적었다.
- `metrics.json`의 다른 지표(근거 셀 정확도, 보류 재현율 등)와 문항별 결과(`predictions.jsonl`)도 같은 폴더에 생긴다.

### 3.2 저장된 모델 출력을 다시 검증하기 (GPU 없이, 1분쯤)

EXAONE 같은 모델은 맥북에서 돌리지 않는다. 대신 GPU 세션에서 저장한 모델의 원래 출력을, 지금 저장소의 검증기로 다시 검증해 저장된 판정과 같은지 볼 수 있다. `[model]` 설치와 인터넷(EXAONE 토크나이저를 내려받는다)이 필요하다.

```bash
python scripts/replay_check.py --session ownloop --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B
```

직접 쓴 학습 루프로 학습한 모델의 평가 6건(1,518문항)을 다시 검증한다. 이렇게 끝나야 한다(37초쯤).

```
-> experiments/eval/replay_check_ownloop.json | replays 6 | questions 1518 | differ 0
```

다른 세션 이름은 `scripts/replay_check.py` 맨 위에 있다(`gpu3`, `control`, `repeat`, `full2`, `rl3`, `owner`, `chem`, `share`, `chemrepeat`, `koonly2`, `rl4`). 결과 파일이 저장된 것과 같으면 `git status`에 아무것도 나오지 않는다.

### 3.3 문서의 수치가 결과 파일과 맞는지

```bash
python scripts/check_data.py               # 정답과 표, 분할이 서로 맞는가. 마지막 줄에 "errors": 0
python scripts/check_numbers.py --strict   # README·보고서·한 장 요약의 수치 4,600여 개가 결과 파일과 같은가. "0 mismatches"
python scripts/render_results.py --check   # 결과 표가 최신인가. "0 stale"
```

CI가 푸시할 때마다 이 셋과 pytest를 돌린다. 본인 컴퓨터에서 돌려도 같은 결과가 나와야 한다.

## 4. 여기서 할 수 없는 것

- 모델 학습, EXAONE이나 mT5로 답을 새로 만드는 평가: GPU와 가중치가 필요하다. 노트북(`notebooks/gpu_experiments_2.ipynb`)으로 한다.
- `make eval-heuristic`: 결과를 `experiments/eval/` 안에 써서 저장된 결과를 덮어쓴다. 위 3.1의 명령을 쓴다.
