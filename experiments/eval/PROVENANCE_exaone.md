# EXAONE LoRA + vLLM / SGLang 결과의 출처

저장소 작성자(개발 컨테이너, GPU 없음)는 이 실행을 하지 못했다. 저장소 소유자가 2026-11-07 Kaggle(Tesla T4 ×2 세션)에서 `notebooks/gpu_experiments.ipynb`를 돌리고 보낸 `gpu_results*.tgz`에서 **그대로 꺼낸 파일**이다. `analysis.json`은 작성자가 그 `predictions.jsonl`에 `scripts/analyze_predictions.py`를 돌려 만들었고, `paired_tests.json`의 `exaone_*` 항목도 같은 파일에서 나왔다.

노트북은 이 세션을 처음에 Colab으로 판단했다(Kaggle 이미지에도 `/content`가 있어서, 이슈 38). 실행 플랫폼은 Kaggle이다.

## 두 세션, 두 번의 LoRA 학습

| | 첫 세션(`*_run1`) | 두 번째 세션(접미사 없음, README·REPORT의 표) |
|---|---|---|
| LoRA(`experiments/exaone_lora/train_info*.json`) | 300개, 18 step, `--dtype auto` → **torch.bfloat16**(T4 에뮬레이션, 스크립트 결함) | 300개, 18 step, **torch.float16**(스크립트 수정 후) |
| vLLM 1장 | `exaone_vllm_ko_test_run1`, `_ec_run1`, `bench/engine_vllm_c*_run1.json` (07:24) | `exaone_vllm_ko_test`, `_ec`, `bench/engine_vllm_c*.json` (14:08) |
| vLLM TP=2 | `exaone_vllm_tp2_ko_test_run1`, `bench/engine_vllm_tp2_c*_run1.json` (08:31) | `exaone_vllm_tp2_ko_test`, `bench/engine_vllm_tp2_c*.json` (14:32) |
| mT5 파이프라인 | `bench/pp_*_gpu_run1.json` | `bench/pp_*_gpu.json` |
| SGLang | 서버 기동 실패(sm75 커널 없음) | 우회 모듈로 서버 기동, 출력이 프로그램 문법이 아님 → `experiments/serving/sglang_run3_rope_config/`(표에 넣지 않음) |

- 첫 세션의 `_ec`는 세 번 돌았다. 처음 두 번은 노트북의 재검증 명령이 `--tokenizer`·`--max-in 672`를 빼고 돌아 행 예산이 본 실행과 달랐고(verified EM 50.5%, 50.07%), 세 번째(두 인자 모두)가 `truncated_gold_rate` 3.43%로 본 실행과 같아 그 값을 남겼다. 두 번째 세션의 `_ec`는 고친 노트북으로 바로 맞게 돌았다.
- 평가 클라이언트의 `hardware: x86_64`는 Kaggle CPU를 적은 것이다. 모델은 T4에서 돌았다.
- 서버: `scripts/serving/vllm_tp2.sh`, `DTYPE=half MAX_LEN=2048`, vLLM(가상환경에 `uv pip install vllm`, 설치 버전은 로그에 남기지 않음). SGLang은 `sglang==0.5.9` + `scripts/serving/sglang_t4_shim.py`.
- 두 세션의 vLLM 결과는 같은 설정의 독립 학습이므로 LoRA 학습 잡음의 크기를 보여 준다(`paired_tests.json: exaone_vllm_run2_vs_run1_*`).
