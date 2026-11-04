# GPU 실험 실행 안내: Colab / Kaggle로 vLLM·SGLang·멀티 GPU 하기

개발 컨테이너에는 GPU가 없고 Hugging Face가 막혀 있어 아래를 실행하지 못했다. 준비물은 모두 저장소에 있다. **아래 절차 전체는 실제 GPU에서 실행해 본 적이 없다.** 학습 루프(작은 무작위 모델, CPU)와 엔진 연결(모의 서버)만 시험했다.

## 먼저 이해할 것: 왜 지금 모델로는 안 되나

TableTrace의 학습된 모델은 **mT5-small(encoder-decoder)** 이다. vLLM 0.32.0과 SGLang 0.5.23은 모델 등록부에 T5/mT5가 없어 이 모델을 서빙할 수 없다(`experiments/serving/engine_support.json`, `scripts/serving/check_engine_support.py`로 재확인). 그래서 vLLM·SGLang 실험은 **EXAONE 같은 decoder-only 모델을 같은 데이터·같은 프로그램 문법으로 LoRA 튜닝한 뒤** 서빙하는 별도 경로다. 두 엔진 모두 EXAONE 계열(`exaone`, `exaone4`)을 지원한다.

```
학습 데이터(data/ko/*.jsonl) ─▶ scripts/train/exaone_lora_sft.py ─▶ LoRA 어댑터 + 병합 모델
병합 모델 ─▶ vLLM 또는 SGLang 서버(OpenAI 호환 API)
서버 ─▶ python -m tabletrace.eval.run --planner engine   (같은 검증기·같은 지표로 평가)
서버 ─▶ python -m tabletrace.bench.engine_bench           (지연·처리량)
서버 ─▶ TABLETRACE_ENGINE_URL=... tabletrace serve        (콘솔·API가 엔진을 플래너로 사용)
```

## Colab으로 되나?

| 항목 | Colab 무료(T4 1장) | 비고 |
|---|---|---|
| EXAONE LoRA 튜닝 | 된다(어림) | T4는 bf16이 없어 fp16 + 손실 스케일링. 스크립트가 자동 선택 |
| vLLM 서빙·평가·벤치 | 된다(시도) | vLLM 0.32는 T4에서 float16만 지원하고 FlashInfer를 쓰지 않는다(wheel 확인). 메모리가 모자라면 `MAX_LEN`을 줄이거나 `EXTRA_ARGS=--enforce-eager` |
| SGLang 서빙·평가·벤치 | 된다(시도) | wheel이 "sm75 이상"을 요구한다(T4는 sm75). T4에서는 `ATTN_BACKEND=triton`을 지정 |
| 텐서 병렬 TP=2, 멀티 GPU 모델 병렬 | **안 된다** | Colab은 GPU 1장. **Kaggle 노트북(T4 ×2, 무료 주 30시간)** 이나 GPU 2장 이상 환경이 필요 |

vLLM과 SGLang은 torch 버전을 다르게 고정한다(vLLM 0.32.0은 torch 2.13.0, SGLang 0.5.23은 2.14.1). 같은 환경에 같이 설치하지 말고 노트북처럼 가상환경을 따로 만든다.

## 실행 순서

`notebooks/gpu_experiments.ipynb`를 Colab(런타임 GPU) 또는 Kaggle(Accelerator GPU T4 x2, Internet on)에 올려 위에서 아래로 실행한다. 순서: 준비 → EXAONE LoRA(`LIMIT=300`으로 먼저 시험) → vLLM 평가·벤치 → SGLang 평가·벤치 → (Kaggle) TP=2와 mT5 2단계 파이프라인 → 결과 압축.

노트북 없이 터미널에서 할 때:

```bash
pip install -e ".[dev]" peft accelerate sentencepiece
# 1. 튜닝 (T4: 자동으로 fp16)
python scripts/train/exaone_lora_sft.py --model LGAI-EXAONE/EXAONE-4.0-1.2B --dtype auto --grad-ckpt --merge \
  --train data/ko/train.jsonl data/ko/synthetic_train.jsonl --corpus data/ko/documents.jsonl --epochs 1 --out experiments/exaone_lora
# 2. vLLM (가상환경 안에서 pip install vllm)
MODEL=experiments/exaone_lora/merged NUM_GPUS=1 DTYPE=half bash scripts/serving/vllm_tp2.sh &
python -m tabletrace.eval.run --planner engine --engine-url http://127.0.0.1:8001 --tokenizer experiments/exaone_lora/merged --max-in 672 \
  --corpus data/ko/documents.jsonl --data data/ko/test.jsonl data/ko/synthetic_test.jsonl --out experiments/eval/exaone_vllm_ko_test
python -m tabletrace.bench.engine_bench --url http://127.0.0.1:8001 --model planner --n 64 --concurrency 8 --tokenizer experiments/exaone_lora/merged
# 3. SGLang (다른 가상환경, 다른 포트)
MODEL=experiments/exaone_lora/merged NUM_GPUS=1 DTYPE=half ATTN_BACKEND=triton bash scripts/serving/sglang.sh &
# 4. 멀티 GPU (GPU 2장)
NUM_GPUS=2 DTYPE=half MODEL=experiments/exaone_lora/merged bash scripts/serving/vllm_tp2.sh
python -m tabletrace.bench.pipeline_parallel --model google/mt5-small --single --backend nccl --n 64 --out experiments/bench/pp_single_gpu.json
torchrun --nproc_per_node=2 -m tabletrace.bench.pipeline_parallel --model google/mt5-small --backend nccl --n 64 --out experiments/bench/pp_2stage_gpu.json
```

## 각 실험이 말해 주는 것과 말해 주지 않는 것

- **EXAONE 평가표**: 같은 평가셋·같은 검증기에서 mT5(1차·2차)와 같은 표에 놓인다. EXAONE은 한국어 표에 대한 사전학습이 훨씬 커서 mT5-small보다 높게 나올 가능성이 크지만, **실측 전에는 어느 쪽도 주장하지 않는다.**
- **vLLM과 SGLang 비교**: 같은 모델·같은 GPU·같은 요청 수에서 지연(p50/p95)과 처리량을 비교한다. 동시성(1, 8, 32)을 바꿔 가며 본다. T4 한 장의 결과는 A100/H100과 일반화되지 않는다.
- **mT5 2단계 파이프라인**: 튜닝한 가중치는 git에 없어 `google/mt5-small` 원본으로 돌린다. 분할·전송·메모리와 "1장과 2장의 출력 일치"를 보며 답변 품질은 보지 않는다. 마이크로배치 파이프라이닝이 없어 속도 이득이 없을 수 있다(CPU 검증에서도 없었다).
- **TP=2**: 2.4B 이하 모델은 한 장에 들어가므로 TP=2는 처리량·지연의 변화를 보는 실험이지 필수는 아니다.

## 라이선스와 토큰

EXAONE은 비상업 연구용 라이선스(EXAONE AI Model License 1.2-NC)이고 Hugging Face에서 동의가 필요할 수 있다. 토큰은 Colab Secrets / Kaggle Secrets의 `HF_TOKEN`에 넣고 노트북·로그·저장소에 쓰지 않는다.

## 결과를 저장소에 반영하는 법

결과 파일(`experiments/eval/exaone_*`, `experiments/bench/engine_*`, `experiments/bench/pp_*_gpu.json`, `experiments/exaone_lora/train_info.json`)을 저장소에 넣고 `python scripts/render_results.py && python scripts/check_numbers.py --expand` 후 README·보고서의 "구현 후 미실행"을 해당 수치로 바꾼다. 실패하거나 mT5보다 낮게 나와도 그대로 적는다.

## 막혔을 때

| 증상 | 원인 | 해결 |
|---|---|---|
| LoRA 단계에서 `ImportError: Found an incompatible version of torchao. Found version 0.10.0, but only versions above 0.16.0 are supported` | Colab에 기본 설치된 `torchao`가 peft 요구 버전보다 낮음 | `pip uninstall -y torchao` 후 튜닝만 다시 실행(노트북 준비 셀에 반영됨) |
| SGLang 가상환경에 `torch`·`sglang`이 없고 서버가 안 뜸(`No module named 'sglang'`) | Colab 기본 파이썬은 3.13. `sglang[all]`의 일부 의존성(`outlines-core`, `pyairports`, `xgrammar`)이 3.13 wheel이 없어 소스 빌드로 넘어가 실패하고, uv는 실패 시 아무것도 설치하지 않음. 최신 `sglang==0.5.23`은 pre-release `flash-attn-4`가 필요해 기본 설정으로는 해석되지 않음 | `uv venv --python 3.12`로 가상환경을 만들고 `sglang==0.5.9`를 설치(3.12에서 wheel만으로 169개 패키지가 해석됨을 확인). 노트북 3번 절에 반영됨 |
| 가상환경 파이썬 실행 때 `Error in sitecustomize ... No module named 'wrapt'` | Colab의 `PYTHONPATH`가 가상환경으로 샌 것 | 무해한 경고. 노트북의 `serve()`는 `PYTHONPATH`를 비워서 실행 |
| vLLM 서버 기동 로그 끝에 `OSError: Repo id must be in the form 'repo_name' or 'namespace/repo_name': 'experiments/exaone_lora/merged'` | 모델 경로가 폴더로 존재하지 않아 허깅페이스 저장소 이름으로 해석됨. 1번 절(LoRA 튜닝)이 끝나지 않았거나 실패해 `experiments/exaone_lora/merged`가 없음 | `!ls -la experiments/exaone_lora experiments/exaone_lora/merged` 로 확인. 튜닝 셀 출력의 마지막 오류를 고친 뒤 다시 실행. 서버만 먼저 시험하려면 `MERGED = "LGAI-EXAONE/EXAONE-4.0-1.2B"` |

