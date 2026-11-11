# 학습 과제(T) 명세 — 학습 코드 직접 쓰기 (`training/evidence_reward.py`, `training/grpo.py`, `training/lm_loop.py`)

> **상태: 시작 전.** 세 파일 모두 아직 없다. 테스트 `tests/test_owner_training_code.py`는 파일이 생기기 전에는 건너뛴다(skipped).

1~4단계는 검증 파이프라인이었다. 이 과제는 **학습 코드**다. `README.md`의 5~9단계와 순서가 무관하므로 먼저 해도 된다. 지금 저장소의 학습 스크립트(`training/sft.py`, `training/rl_grpo.py`, `scripts/train/exaone_lora_sft.py`)는 AI 코딩 도구가 썼다. 그래서 "학습 코드를 직접 짰다"고 말할 수 없다. 이 과제에서 학습의 핵심 세 조각을 새 파일로 직접 쓴다. 이번에는 참고할 기존 파일이 없다. 명세와 테스트만 보고 쓴다.

세 파일은 서로 독립이다. A → B → C 순서를 권하지만 어느 것부터 해도 된다. 합쳐서 150줄 안팎이다.

| 파일 | 내용 | 쓰이는 곳 |
|---|---|---|
| A. `training/evidence_reward.py` | 모델 출력 하나에 보상을 매기는 함수 | EXAONE 강화학습 (`scripts/train/exaone_grpo.py`) |
| B. `training/grpo.py` | 그룹 이점, 생성 토큰의 로그 확률, 정책 경사 손실, KL 항 | 같은 스크립트 |
| C. `training/lm_loop.py` | 라벨 가리기, 학습률 일정, 학습 루프 | `scripts/train/exaone_lora_sft.py --loop owner` |

`scripts/train/exaone_grpo.py`와 `--loop owner`는 이미 연결해 두었다. 모델 불러오기, 데이터 읽기, 샘플 생성, 기록은 그 스크립트가 하고, **보상·이점·손실·루프는 여기서 쓴 함수를 불러 쓴다.** 세 파일이 없으면 그 경로는 안내 문구와 함께 멈춘다.

## A. `evidence_reward.py`

```python
def evidence_reward(raw: str, question: str, table: Table, gold_answer: str | None,
                    context: str | None = None, entity_check: bool = False) -> tuple[float, dict]:
```

모델이 쓴 글 `raw`를 검증기에 넣었을 때 **서비스가 실제로 내보낼 결과**에 점수를 매긴다. `gold_answer`가 `None`이면 "문서에 답이 없는 질문"이라는 뜻이다.

| 단계(level) | 점수 | 뜻 |
|---|---:|---|
| `correct` | +1.0 | 근거 복구 없이 검증을 통과했고 답이 정답과 같다. 답 없는 질문에서는 모델이 스스로 `op: abstain`을 냈다 |
| `repaired` | +0.3 | 답 글자는 맞는데 인용 셀이 틀려서, 근거 복구를 켜야만 정답이 나간다 |
| `withheld` | 0.0 | 아무 답도 나가지 않는다(검증기가 거부했거나, 답이 있는 질문에서 모델이 보류했다) |
| `wrong` | −0.5 | 틀린 답이 나간다(검증을 통과한 오답, 또는 답 없는 질문에 답함) |
| `unparsable` | −1.0 | 프로그램 문법이 아니다 |

판정 순서는 다음과 같다. 이 순서대로 쓰면 된다.

1. `agent.program.parse(raw, table.id)`가 `ProgramParseError`를 내면 `unparsable`.
2. 검증기를 두 번 쓴다. **엄격**은 `resolve(question, table, program, context=context, entity_check=entity_check, repair=False)`, **느슨**은 같은 호출에서 `repair=True`.
3. `gold_answer`가 `None`일 때: 프로그램의 op가 `abstain`이면 `correct`. 아니고 엄격 또는 느슨 결과가 `answered`면 `wrong`. 둘 다 아니면 `withheld`.
4. `gold_answer`가 있을 때: 엄격 결과가 `answered`면, `eval.metrics.answer_match(답, gold_answer)`가 참일 때 `correct`, 거짓일 때 `wrong`. 엄격이 `answered`가 아니고 느슨이 `answered`면, 답이 맞을 때 `repaired`, 틀릴 때 `wrong`. 둘 다 `answered`가 아니면 `withheld`.

돌려주는 `dict`에는 적어도 `level`(위 다섯 이름 중 하나), `parse_ok`(bool), `op`(파싱된 op, 실패하면 `None`)가 있어야 한다.

지켜야 할 것.

- 어떤 입력에도 예외를 내지 않는다(빈 문자열, 범위 밖 셀, 아주 긴 답).
- 같은 입력에는 같은 결과를 낸다. 표를 바꾸지 않는다.
- 계산 op에서 모델이 쓴 `answer`가 계산값과 달라도 서비스는 계산값을 내보낸다. 보상은 **내보내는 답**을 기준으로 한다(테스트의 `diff ... answer: 15` 사례).

이 보상이 예전 것(`rl_grpo.reward`)과 다른 점을 알고 쓰면 좋다. 예전 보상은 정답 셀 라벨로 부분 점수를 줬다. 이 보상은 **정답 글자만** 쓴다. 근거가 맞는지는 "복구 없이 통과했는가"로 검증기가 판단한다. 그리고 부분 점수가 한 곳(`repaired`)뿐이고 정답일 때만 붙는다. 답 없는 질문에서 검증기가 거부한 쓰레기 출력은 0점이다. RL v1에서 이것에 +1.0을 줬다가 퇴화 출력이 늘었던 일(`docs/REPORT.md` §8)을 반복하지 않기 위해서다.

## B. `grpo.py`

토치 텐서만 다루는 순수 함수 네 개다. 모델도 토크나이저도 모른다.

```python
def group_advantages(rewards: Tensor, eps: float = 1e-4) -> Tensor:                      # (프롬프트 P, 그룹 G) -> (P, G)
def completion_logprobs(logits: Tensor, input_ids: Tensor, completion_mask: Tensor):     # -> (token_logp, mask), 둘 다 (N, L-1)
def policy_gradient_loss(token_logp: Tensor, mask: Tensor, advantages: Tensor) -> Tensor  # 스칼라
def kl_k3(token_logp: Tensor, ref_logp: Tensor, mask: Tensor, clamp: float = 10.0) -> Tensor   # 스칼라
```

- **`group_advantages`**: 같은 프롬프트에서 뽑은 G개 샘플의 보상을 그 그룹 안에서 정규화한다. `(r − 그룹 평균) / (그룹 표준편차 + eps)`. 표준편차는 토치 기본값(표본 표준편차, n−1로 나눔)이다. 보상이 모두 같은 그룹은 전부 0이 된다.
- **`completion_logprobs`**: 인과 언어모델에서 위치 t의 토큰은 위치 t−1의 logits가 예측한다. `logits`는 `(N, L, V)`, `input_ids`는 `(N, L)`, `completion_mask`는 `(N, L)`이고 모델이 생성한 토큰 자리만 1이다(프롬프트와 패딩은 0). 돌려주는 `token_logp[n, t]`는 `input_ids[n, t+1]`의 로그 확률(`log_softmax`)이고, `mask[n, t]`는 `completion_mask[n, t+1]`을 실수로 바꾼 것이다.
- **`policy_gradient_loss`**: `−Σ_n Σ_t advantages[n] · token_logp[n, t] · mask[n, t] / Σ mask`. `mask`의 합이 0이면 0을 돌려준다(NaN이 아니다).
- **`kl_k3`**: 학습 전 모델(기준)에서 너무 멀어지지 않게 하는 항. `d = clamp(ref_logp − token_logp, −clamp, +clamp)`로 두고 `Σ (exp(d) − d − 1) · mask / Σ mask`. 두 로그 확률이 같으면 0이고 다르면 양수다.

테스트는 손으로 계산한 값과 비교한다. 그리고 두 단어짜리 장난감 정책에서 한 걸음 갱신했을 때 보상이 높았던 단어의 확률이 오르는지 본다.

## C. `lm_loop.py`

```python
def mask_labels(input_ids: Tensor, prompt_lengths: Sequence[int], attention_mask: Tensor) -> Tensor:
def lr_at(step: int, total_steps: int, base_lr: float, warmup_steps: int = 0) -> float:
def train(model, batches, optimizer, *, total_steps: int, base_lr: float, warmup_steps: int = 0,
          grad_accum: int = 1, max_grad_norm: float = 1.0, scaler=None, on_step=None) -> list[float]:
```

- **`mask_labels`**: `input_ids`를 복사해서, 각 행의 앞 `prompt_lengths[i]`개와 `attention_mask`가 0인 자리를 `-100`으로 바꾼다. 원본 텐서는 바꾸지 않는다. 모델이 프롬프트를 외우는 데 손실을 쓰지 않게 하려는 것이다.
- **`lr_at`**: `step`은 0부터 센다. `step < warmup_steps`이면 `base_lr · (step + 1) / warmup_steps`. 그 뒤는 `base_lr · (total_steps − step) / (total_steps − warmup_steps)`로 곧게 내려간다. `step ≥ total_steps`이면 0.
- **`train`**: `batches`는 `input_ids`, `attention_mask`, `labels`가 든 dict를 차례로 주는 것이다. 한 배치의 손실은 `model(**batch).loss`.
  1. 배치 `grad_accum`개마다 한 번 갱신한다. 각 배치의 손실을 `grad_accum`으로 나눠서 `backward` 한다. 그래야 작은 배치 여러 개가 큰 배치 하나와 같은 갱신이 된다.
  2. 갱신 직전에 `lr_at(지금까지 갱신 횟수, ...)`로 계산한 학습률을 옵티마이저의 모든 `param_groups`에 넣는다. 옵티마이저에 원래 들어 있던 학습률은 쓰지 않는다.
  3. 기울기 크기를 `max_grad_norm`으로 자른 뒤(`torch.nn.utils.clip_grad_norm_`) 갱신하고, 기울기를 비운다.
  4. 갱신 `total_steps`번을 채우면 배치가 남아도 멈춘다. 배치가 끝났는데 `grad_accum`개를 못 채운 나머지는 버린다.
  5. `scaler`가 주어지면(GPU의 fp16 학습용 `torch.amp.GradScaler`) 순서는 이렇다. 배치마다 `scaler.scale(loss).backward()`. 갱신 때 `scaler.unscale_(optimizer)` → 기울기 자르기 → `scaler.step(optimizer)` → `scaler.update()`.
  6. 갱신할 때마다 그 걸음의 손실(나눈 손실들의 합, 곧 배치 평균)을 리스트에 넣는다. `on_step`이 주어지면 `on_step(step, loss, lr)`을 부른다(`step`은 0부터).
  7. 손실 리스트를 돌려준다. 길이는 실제 갱신 횟수다.

테스트는 12단어짜리 장난감 모델로 한다. 손실이 절반 아래로 내려가는지, 학습률이 일정대로 들어가는지, 배치 둘을 모은 갱신이 큰 배치 하나와 소수점 여섯 자리까지 같은지, 기울기가 잘렸는지, `scaler` 호출 순서가 맞는지를 본다.

## 끝났는지 확인

```bash
pip install -e ".[dev,model]"                       # 토치가 있어야 B, C 테스트가 돈다 (CPU면 충분)
pytest tests/test_owner_training_code.py -q -rs     # 35개. 파일을 쓴 만큼 skipped가 passed로 바뀐다
pytest tests/test_exaone_grpo_smoke.py -q           # A, B가 있으면: 작은 무작위 모델로 강화학습 스크립트 한 바퀴
pytest tests/test_lora_sft_smoke.py -q              # C가 있으면: --loop owner 경로도 함께 돈다
pytest -q && ruff check src tests scripts
```

브랜치는 `rewrite/06-training-code`, 커밋은 파일마다 따로 해도 된다. 메시지 예: `training: verifier-outcome reward for RL (owner)`. 푸시한 뒤 알려 주면 리뷰한다.

## 이 코드로 하는 실험 (소유자가 Kaggle에서 실행)

`notebooks/gpu_experiments.ipynb` 6번 절. EXAONE 4.0 1.2B를 300문항으로 튜닝한 모델(정답 중 근거 셀 오류가 절반을 넘는 모델)에서 시작해, 이 보상으로 GRPO를 돌린다. 볼 것은 verified EM이 아니라 **근거 복구를 끈 정답률과 근거 셀 오류율**이 움직이는가다. 결과가 좋든 나쁘든 그대로 적는다.
