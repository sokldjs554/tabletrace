# 출처

이 폴더와 `../exaone_vllm_ko_test_ec/`, `../../bench/engine_vllm_c{1,8,32}.json`은 저장소 소유자가 2026-11-07 Colab(Tesla T4 1장)에서 `notebooks/gpu_experiments.ipynb` 2번 절을 실행하고 채팅에 붙여 준 출력을 **그대로 옮겨 적은 것**이다. 저장소 작성자(개발 컨테이너, GPU 없음)는 이 실행을 하지 못했다.

- `metrics.json`은 붙여 준 JSON 그대로다. `predictions.jsonl`·`analysis.json`은 `gpu_results.tgz`를 받기 전까지 없다. 그래서 `scripts/paired_tests.py`(쌍 비교)와 `scripts/analyze_predictions.py`는 이 실행에 대해 아직 돌릴 수 없다.
- 서버: `scripts/serving/vllm_tp2.sh`, `NUM_GPUS=1 DTYPE=half MAX_LEN=2048`, vLLM(가상환경에 `uv pip install vllm`, 버전은 로그 미확인), 모델 `experiments/exaone_lora/merged`(EXAONE-4.0-1.2B + LoRA 병합, fp16).
- LoRA 학습 예제 수·step·손실은 `experiments/exaone_lora/train_info.json`을 받아야 안다. 노트북 기본값은 `LIMIT=300`이고, 11-04의 시험 실행은 32개였다. **어느 쪽인지 확인 전**.
- 평가 클라이언트의 `hardware: x86_64`는 Colab CPU를 적은 것이다. 모델은 T4에서 돌았다.
- `_ec`(검증기 v2 재검증)는 노트북의 재검증 명령이 `--tokenizer`를 빼고 돌아 행 예산을 근사 토크나이저로 다시 계산했다. 그래서 `truncated_gold_rate`가 3.4%에서 9.3%로 달라졌고, v1→v2 차이에는 개체 검사 효과와 행 예산 차이가 섞여 있다. 노트북은 고쳤고(`--tokenizer {MERGED}`), 다시 돌린 값을 받으면 교체한다.
