# 출처

이 폴더와 `../exaone_vllm_ko_test_ec/`, `../../bench/engine_vllm_c{1,8,32}.json`, `../../exaone_lora/train_info.json`은 저장소 소유자가 2026-11-07 Kaggle(T4 ×2 세션, GPU 1장 사용)에서 `notebooks/gpu_experiments.ipynb` 1~2번 절을 실행하고 보낸 `gpu_results.tgz`(162 KB)에서 **그대로 꺼낸 파일**이다. 저장소 작성자(개발 컨테이너, GPU 없음)는 이 실행을 하지 못했다. `analysis.json`은 작성자가 그 `predictions.jsonl`에 `scripts/analyze_predictions.py`를 돌려 만들었고, `../paired_tests.json`의 `exaone_*` 항목도 같은 파일에서 나왔다.

- 노트북은 이 세션을 Colab으로 판단했다(Kaggle 이미지에도 `/content`가 있어서, 이슈 38). 그래서 저장소가 `/content/tabletrace`에 있었고 처음 두 번의 "Colab" 표기는 이 때문이다. 실행 플랫폼은 Kaggle이다.
- 서버: `scripts/serving/vllm_tp2.sh`, `NUM_GPUS=1 DTYPE=half MAX_LEN=2048`, vLLM(가상환경에 `uv pip install vllm`, 설치된 버전은 로그에 남기지 않음), 모델 `experiments/exaone_lora/merged`(EXAONE-4.0-1.2B + LoRA 병합).
- LoRA(`train_info.json`): 예제 300개(`--limit 300`), 1 epoch, bs 2 × grad-accum 8 = 18 step, lr 2e-4, r 16, max_len 768. `--dtype auto`가 **torch.bfloat16**을 골랐다(T4는 bf16을 에뮬레이션하는데 `torch.cuda.is_bf16_supported()`가 참을 돌려줘서. 스크립트는 이후 compute capability 기준으로 고침). 서빙은 fp16. 학습 시간은 기록하지 않았다.
- 평가 클라이언트의 `hardware: x86_64`는 Kaggle CPU를 적은 것이다. 모델은 T4에서 돌았다.
- `_ec`(검증기 v2 재검증)는 세 번 돌았다. 처음 두 번은 노트북의 재검증 명령이 `--tokenizer`·`--max-in 672`를 빼고 돌아 행 예산이 본 실행과 달랐다(verified EM 50.5%, 50.07%, `truncated_gold_rate` 9.3%·11.3%). 세 번째(07:59, 두 인자 모두)가 `truncated_gold_rate` 3.43%로 본 실행과 같고, 그 파일이 지금의 `../exaone_vllm_ko_test_ec/`다. 앞의 두 값은 폐기.
- 같은 세션의 `experiments/eval/exaone_sglang_ko_test/`는 빈 폴더였다(SGLang 서버가 뜨지 않아 평가가 시작되지 않음). 저장소에 넣지 않았다.
- 두 번째 보관 파일(`gpu_results_1.tgz`, 같은 Kaggle 세션, 4번 절 실행 뒤): `../exaone_vllm_tp2_ko_test/`(vLLM `--tensor-parallel-size 2`, 검증기 v1만), `../../bench/engine_vllm_tp2_c{1,8,32}.json`, `../../bench/pp_single_gpu.json`·`pp_2stage_gpu.json`(mT5-small 2-스테이지 파이프라인, NCCL). 첫 파일과 겹치는 항목은 내용이 같았다.

