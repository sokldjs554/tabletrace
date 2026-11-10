# EXAONE LoRA + vLLM / SGLang 결과의 출처

저장소 작성자(개발 컨테이너, GPU 없음)는 이 실행을 하지 못했다. 저장소 소유자가 2026-11-07 Kaggle(Tesla T4 ×2 세션)에서 `notebooks/gpu_experiments.ipynb`를 처음부터 세 번 돌리고 보낸 `gpu_results*.tgz`에서 **그대로 꺼낸 파일**이다. `analysis.json`은 작성자가 그 `predictions.jsonl`에 `scripts/analyze_predictions.py`를 돌려 만들었고, `paired_tests.json`의 `exaone_*` 항목도 같은 파일에서 나왔다.

노트북은 이 세션을 처음에 Colab으로 판단했다(Kaggle 이미지에도 `/content`가 있어서, 이슈 38). 실행 플랫폼은 Kaggle이다.

## 다섯 세션, 다섯 번의 LoRA 학습

| | 1차(`*_run1`) | 2차(`*_run2`) | 3차(접미사 없음, 표의 `LoRA 300개` 행) | 4차(`exaone_full_*`, `engine_full_*`, 표의 `전체` 행) |
|---|---|---|---|---|
| LoRA(`experiments/exaone_lora/train_info*.json`) | 300개, 18 step, `--dtype auto` → **bfloat16**(T4 에뮬레이션, 스크립트 결함) | 300개, 18 step, **float16**(스크립트 수정 후) | 300개, 18 step, float16 | **전체 3,587개**(3,654개 중 행 예산 밖 정답 67개 제외), 224 step, float16, 1,862.7초(T4), `experiments/exaone_lora_full/` |
| vLLM 1장 | `exaone_vllm_ko_test_run1`, `_ec_run1`, `bench/engine_vllm_c*_run1.json` (07:24) | `..._run2` (14:08) | `exaone_vllm_ko_test`, `_ec`, `bench/engine_vllm_c*.json` (17:26) | `exaone_full_vllm_ko_test`, `_ec`, `exaone_full_vllm_ko_custom`, `_ec`, `bench/engine_full_vllm_c*.json` (2026-11-08 06:36) |
| vLLM TP=2 | `exaone_vllm_tp2_ko_test_run1`, `bench/engine_vllm_tp2_c*_run1.json` (08:31) | `..._run2` (14:32) | `exaone_vllm_tp2_ko_test`, `bench/engine_vllm_tp2_c*.json` (17:44) | `exaone_full_vllm_tp2_ko_test`, `_ec`, `..._ko_custom`, `_ec`, `bench/engine_full_vllm_tp2_c*.json` (07:31) |
| mT5 파이프라인 | `bench/pp_*_gpu_run1.json` | `bench/pp_*_gpu_run2.json` | `bench/pp_*_gpu.json` | `bench/pp_*_gpu.json`(3차 파일은 `_run3`으로 이동) |
| SGLang | 서버 기동 실패(sm75 커널 없음) | 우회 모듈로 기동, config.json RoPE 키 누락으로 엉뚱한 답 → `experiments/serving/sglang_run3_rope_config/`(표에 넣지 않음) | 우회 모듈 + 설정 복원으로 **성공**: `exaone_sglang_ko_test`, `_ec`, `bench/engine_sglang_c*.json` (17:54) | 우회 모듈로 성공: `exaone_full_sglang_ko_test`, `_ec`, `..._ko_custom`, `_ec`, `bench/engine_full_sglang_c*.json` (07:16) |

- 1차의 `_ec`는 세 번 돌았다. 처음 두 번은 노트북의 재검증 명령이 `--tokenizer`·`--max-in 672`를 빼고 돌아 행 예산이 본 실행과 달랐고(verified EM 50.5%, 50.07%), 세 번째(두 인자 모두)가 `truncated_gold_rate` 3.43%로 본 실행과 같아 그 값을 남겼다. 2·3차의 `_ec`는 고친 노트북으로 바로 맞게 돌았다.
- 평가 클라이언트의 `hardware: x86_64`는 Kaggle CPU를 적은 것이다. 모델은 T4에서 돌았다.
- 서버: vLLM은 `scripts/serving/vllm_tp2.sh`, `DTYPE=half MAX_LEN=2048`(가상환경에 `uv pip install vllm`, 설치 버전은 로그에 남기지 않음). SGLang은 `sglang==0.5.9` + `scripts/serving/sglang_t4_shim.py`(fused 커널 대신 PyTorch 구현) + `--attention-backend triton --sampling-backend pytorch`, 평가는 동시 8요청(vLLM은 16).
- 4차 세션의 `experiments/exaone_lora_full/run_info.json`이 플랫폼(kaggle, T4 ×2)과 설정(LIMIT=0)을 기록한다. 수작업 30문항은 4·5차에서 평가했다.
- **5차 세션(2026-11-08 09:14~09:45, Colab 무료 Tesla T4 1장)**: Ampere GPU 비교를 하려던 세션인데 런타임이 T4였다. 같은 설정의 전체 데이터 학습을 한 번 더 한 것이 되어 `exaone_full_*_run2`, `engine_full_*_run2.json`, `experiments/exaone_lora_full/train_info_run2.json`(1,810초)·`run_info_run2.json`으로 보관했다. TP=2와 파이프라인은 GPU 1장이라 없음.
- 1~3차의 vLLM 결과는 같은 설정의 독립 학습이므로 LoRA 학습 잡음의 크기를 보여 준다(`paired_tests.json: exaone_vllm_run2_vs_run1_*`, `exaone_vllm_run3_vs_run2_ko_test`). 3차의 vLLM 대 SGLang은 같은 모델의 엔진 간 차이다(`exaone_sglang_vs_vllm_*`).
- **6차 세션(2026-11-10 13:4x, Kaggle Tesla T4 ×2)**: 표 입력 형식 실험. 노트북 1번 절에서 `LIMIT = 300`, `TABLE_FORMAT = "colid"`로 두고 0·1·2·5번 절을 실행했다(`experiments/exaone_lora_colid/run_info.json`: limit 300, tag `_colid`). 학습은 같은 300개·18 step, `--max-len 896 --table-format colid`, 182.9초(`experiments/exaone_lora_colid/train_info.json`). 평가는 vLLM 1장, `--max-in 800 --table-format colid`: `exaone_colid_vllm_ko_test`, `_ec`, `exaone_colid_vllm_ko_custom`, `_ec`, `bench/engine_colid_vllm_c*.json`. 올라온 압축 파일(`gpu_results_7.tgz`)에는 저장소를 클론하면서 딸려 온 기존 결과 133개도 들어 있었고, 저장소의 파일과 해시가 모두 같아 `_colid` 파일만 넣었다. SGLang과 TP=2는 이 세션에서 돌리지 않았다.

