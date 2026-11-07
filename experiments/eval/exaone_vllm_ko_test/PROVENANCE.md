# 출처

이 폴더와 `../exaone_vllm_ko_test_ec/`, `../../bench/engine_vllm_c{1,8,32}.json`은 저장소 소유자가 2026-11-07 Colab(Tesla T4 1장)에서 `notebooks/gpu_experiments.ipynb` 2번 절을 실행하고 채팅에 붙여 준 출력을 **그대로 옮겨 적은 것**이다. 저장소 작성자(개발 컨테이너, GPU 없음)는 이 실행을 하지 못했다.

- `metrics.json`은 붙여 준 JSON 그대로다. `predictions.jsonl`·`analysis.json`은 `gpu_results.tgz`를 받기 전까지 없다. 그래서 `scripts/paired_tests.py`(쌍 비교)와 `scripts/analyze_predictions.py`는 이 실행에 대해 아직 돌릴 수 없다.
- 서버: `scripts/serving/vllm_tp2.sh`, `NUM_GPUS=1 DTYPE=half MAX_LEN=2048`, vLLM(가상환경에 `uv pip install vllm`, 버전은 로그 미확인), 모델 `experiments/exaone_lora/merged`(EXAONE-4.0-1.2B + LoRA 병합, fp16).
- LoRA 학습 조건(소유자가 붙여 준 `train_info.json` 앞부분, 파일 자체는 아직 없음): 예제 300개(`--limit 300`), 1 epoch, bs 2 × grad-accum 8 = 18 step, lr 2e-4, r 16, max_len 768, `--dtype auto`가 **torch.bfloat16**을 골랐다(T4는 bf16을 에뮬레이션하는데 `torch.cuda.is_bf16_supported()`가 참을 돌려줘서. 스크립트는 이후 compute capability 기준으로 고침). 손실은 step 1 1.236 → step 2 0.245 → step 3 0.200(그 뒤는 파일을 받아야 안다). 서빙은 fp16.
- 평가 클라이언트의 `hardware: x86_64`는 Colab CPU를 적은 것이다. 모델은 T4에서 돌았다.
- `_ec`(검증기 v2 재검증)는 노트북의 재검증 명령이 `--tokenizer`와 `--max-in 672`를 빼고 돌아(기본값 근사 토크나이저, 512) 행 예산이 본 실행과 달랐다. `truncated_gold_rate` 3.4%(본 실행) 대 9.3%(이 파일). 소유자가 `--tokenizer`만 넣어 다시 돌린 두 번째 재검증은 verified EM 50.07%, `truncated_gold_rate` 11.3%로 역시 다르다(`--max-in`이 빠져 있었음). 그래서 v1→v2 차이에는 개체 검사 효과와 행 예산 차이가 섞여 있다. 노트북은 두 인자를 모두 넣도록 고쳤고, 그 값으로 이 파일을 교체할 예정이다.
