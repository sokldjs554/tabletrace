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
| EXAONE LoRA 튜닝 | **된다(실측)** | Kaggle T4 1장에서 300개 18 step은 몇 분, 전체 3,587개 224 step은 **31분**(fp16 + 손실 스케일링, `experiments/exaone_lora_full/train_info.json`). 첫 세션은 `--dtype auto`가 bf16 에뮬레이션을 골라 스크립트를 고침 |
| vLLM 서빙·평가·벤치 | 된다(시도) | vLLM 0.32는 T4에서 float16만 지원하고 FlashInfer를 쓰지 않는다(wheel 확인). 메모리가 모자라면 `MAX_LEN`을 줄이거나 `EXTRA_ARGS=--enforce-eager` |
| SGLang 서빙·평가·벤치 | T4에서 **우회 모듈로 성공**(소유자 실행) | `sgl_kernel`에 sm75 커널이 없어 그대로는 첫 연산에서 `no kernel image is available`. `scripts/serving/sglang_t4_shim.py`가 연산을 PyTorch 구현으로 돌리고, `fix_tokenizer_config.py`가 5.x가 저장한 config.json의 RoPE 키를 복원해야 함(안 하면 엉뚱한 답). 노트북 3번 절이 둘 다 자동으로 함. 점수는 vLLM과 같고 속도는 느림. Ampere 이상이면 우회 없이 실행. 기록: `experiments/serving/sglang_t4_failure.md` |
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

결과 파일(`experiments/eval/exaone_*`, `experiments/bench/engine_*`, `experiments/bench/pp_*_gpu.json`, `experiments/exaone_lora*/train_info.json`)을 저장소에 넣고 `python scripts/render_results.py && python scripts/check_numbers.py --fix --strict`로 README·보고서 표와 숫자를 갱신한다. 2026-11-07~08에 다섯 세션의 결과를 이 절차로 반영했다(`experiments/eval/PROVENANCE_exaone.md`). 실패하거나 mT5보다 낮게 나와도 그대로 적는다.

## 막혔을 때

| 증상 | 원인 | 해결 |
|---|---|---|
| LoRA 단계에서 `ImportError: Found an incompatible version of torchao. Found version 0.10.0, but only versions above 0.16.0 are supported` | Colab에 기본 설치된 `torchao`가 peft 요구 버전보다 낮음 | `pip uninstall -y torchao` 후 튜닝만 다시 실행(노트북 준비 셀에 반영됨) |
| SGLang 가상환경에 `torch`·`sglang`이 없고 서버가 안 뜸(`No module named 'sglang'`) | Colab 기본 파이썬은 3.13. `sglang[all]`의 일부 의존성(`outlines-core`, `pyairports`, `xgrammar`)이 3.13 wheel이 없어 소스 빌드로 넘어가 실패하고, uv는 실패 시 아무것도 설치하지 않음. 최신 `sglang==0.5.23`은 pre-release `flash-attn-4`가 필요해 기본 설정으로는 해석되지 않음 | `uv venv --python 3.12`로 가상환경을 만들고 `sglang==0.5.9`를 설치(3.12에서 wheel만으로 169개 패키지가 해석됨을 확인). 노트북 3번 절에 반영됨 |
| 가상환경 파이썬 실행 때 `Error in sitecustomize ... No module named 'wrapt'` | Colab의 `PYTHONPATH`가 가상환경으로 샌 것 | 무해한 경고. 노트북의 `serve()`는 `PYTHONPATH`를 비워서 실행 |
| vLLM 서버 기동 로그 끝에 `OSError: Repo id must be in the form 'repo_name' or 'namespace/repo_name': 'experiments/exaone_lora/merged'` | 모델 경로가 폴더로 존재하지 않아 허깅페이스 저장소 이름으로 해석됨. 1번 절(LoRA 튜닝)이 끝나지 않았거나 실패해 `experiments/exaone_lora/merged`가 없음 | `!ls -la experiments/exaone_lora experiments/exaone_lora/merged` 로 확인. 튜닝 셀 출력의 마지막 오류를 고친 뒤 다시 실행. 서버만 먼저 시험하려면 `MERGED = "LGAI-EXAONE/EXAONE-4.0-1.2B"` |
| SGLang 로그 끝에 `AttributeError: 'list' object has no attribute 'keys'` (`tokenization_utils_base.py`, `_set_model_specific_special_tokens`) | 학습 환경의 transformers 5.x가 `tokenizer_config.json`에 `extra_special_tokens`를 목록으로, `tokenizer_class`를 `TokenizersBackend`로 저장. SGLang이 고정한 transformers 4.57은 둘 다 읽지 못함 | `python scripts/serving/fix_tokenizer_config.py experiments/exaone_lora/merged` (목록을 `additional_special_tokens`로 옮기고 클래스명을 `PreTrainedTokenizerFast`로). 새로 학습한 모델은 스크립트가 저장할 때 자동 처리 |
| T4에서 SGLang이 샘플링 단계에서 실패 | 기본 샘플링 백엔드 `flashinfer`가 sm75에서 불안정(vLLM 소스에도 같은 경고) | `sglang.sh`가 기본으로 `--sampling-backend pytorch`를 씀(`SAMPLING_BACKEND`로 변경) |
| SGLang이 모델을 올린 뒤 `Capture cuda graph failed: RMSNorm failed with error code no kernel image is available for execution on the device` | T4(sm75)용 커널이 `sgl_kernel` 바이너리에 없음. 설정으로 우회할 수 없음(`--disable-cuda-graph`도 같은 호출이 첫 추론으로 옮겨갈 뿐) | Ampere 이상 GPU에서 실행. T4에서는 vLLM만 사용 |
| `torchrun ... pipeline_parallel --backend nccl`에서 rank 1이 `exitcode 1`로 먼저 죽고 rank 0이 SIGTERM으로 끝남 | NCCL은 CUDA 텐서만 주고받는데, 스크립트의 제어용 작은 텐서(크기, 어텐션 마스크, 토큰 수)가 CPU 텐서였음. gloo(CPU)에서는 되고 nccl에서만 실패 | 프로세스 그룹을 `cpu:gloo,cuda:nccl`로 초기화(CPU 텐서는 gloo, CUDA 텐서는 NCCL). 코드에 반영됨. 그래도 멈추면 `NCCL_P2P_DISABLE=1` |

## 열 번호 형식 실험 (선택, 무료 T4에서 20~30분)

표의 모든 셀 앞에 열 번호를 붙인 입력 형식(`colid`)이 "행은 맞고 열이 틀리는" 근거 오류를 줄이는지 보는 실험이다. 배경과 토큰 비용은 `docs/REPORT.md` §19.7.

1. `notebooks/gpu_experiments.ipynb`의 1번 절 셀에서 `LIMIT = 300`, `TABLE_FORMAT = "colid"`로 바꾼다. `MAX_LEN`은 자동으로 896이 된다.
2. 0번 절(준비), 1번 절(LoRA), 2번 절(vLLM 평가), 5번 절(결과 압축)만 실행한다. 3·4번 절은 건너뛴다.
3. 결과 파일 이름에 `_colid`가 붙는다(`experiments/eval/exaone_colid_vllm_ko_test` 등). 기존 결과를 덮어쓰지 않는다.
4. `gpu_results.tgz`를 올리면 `python scripts/evidence_error.py`가 같은 표(§19.1)에 새 행을 더한다.

같은 명령을 직접 돌리려면:

```bash
python scripts/train/exaone_lora_sft.py --model LGAI-EXAONE/EXAONE-4.0-1.2B --dtype auto --grad-ckpt --merge \
    --train data/ko/train.jsonl data/ko/synthetic_train.jsonl --corpus data/ko/documents.jsonl \
    --epochs 1 --bs 2 --grad-accum 8 --limit 300 --max-len 896 --table-format colid --out experiments/exaone_lora_colid
python -m tabletrace.eval.run --planner engine --engine-url http://127.0.0.1:8001 --engine-model planner \
    --tokenizer experiments/exaone_lora_colid/merged --max-in 800 --table-format colid --no-entity-check \
    --corpus data/ko/documents.jsonl --data data/ko/test.jsonl data/ko/synthetic_test.jsonl --out experiments/eval/exaone_colid_vllm_ko_test
```

서버는 모델을 학습한 형식과 같은 형식으로 띄워야 한다. FastAPI 서비스는 환경 변수 `TABLETRACE_TABLE_FORMAT=colid`로 고른다.

## 보강 실험 노트북 (`notebooks/gpu_experiments_2.ipynb`, 2026-11-11)

공고와 대조했을 때 비어 있던 부분을 채우는 실험을 한 노트북에 모았다. 작성자는 실행해 보지 못했다. 0번 절(준비)만 필수이고 나머지는 골라서 돌린다.

| 절 | 재는 것 | GPU | 예상 시간 |
|---|---|---|---|
| A | 튜닝하지 않은 EXAONE 1.2B / 7.8B(AWQ) / 32B(AWQ)에 예시 6개를 주고 같은 검증기로 채점 | 32B만 2장 | 40분 + 60분 |
| A2 | 모델이 도구를 스스로 골라 표를 읽는 방식(Tool Calling) | 32B만 2장 | 30분 + 60분 |
| B | 학습 데이터를 풀로 늘림(약 1만, 약 3.4만 문항) | 1장, 2장이면 DDP로 절반 | 1.5시간, 5시간 |
| C | 멀티 GPU 학습(DDP) 속도 | 2장 | 15분 |
| D | EXAONE 강화학습(GRPO). 본인이 쓴 `training/evidence_reward.py`와 `training/grpo.py`를 불러 쓴다(2026-11-12 병합, PR #6) | 1장 | 1.5~2시간 |
| E | 튜닝 모델을 4비트로 올렸을 때의 정확도·속도·메모리 | 1장 | 20분 |
| F | 열 번호 형식: 시드 둘 더, 전체 데이터 | 1장 | 1시간 |
| G | 영어 화학(교과서 두 세트, 논문 표 62문항) | 1장 | 30분 |
| H | 큰 표(공개 dev의 처음 보는 표 3,072문항): 앞에서 자르기 대 행 선별 | 1장 | 20분 |

알아 둘 것.

- 권하는 순서는 H → A → B(7000) → F → G → E → C → A2 → D다. 앞의 것일수록 실패할 일이 적고 결과의 쓸모가 크다.
- 모든 평가가 `--confidence`로 토큰 로그 확률을 저장한다. 결과가 오면 위험·응답률 곡선을 그린다.
- 노트북이 스크립트에 넘기는 옵션이 실제로 있는지는 `tests/test_notebook_flags.py`가 검사한다. 그 이상(메모리, 서버 기동, 모델 내려받기)은 돌려 봐야 안다.
- 32B AWQ는 T4 두 장에 빠듯하다. 서버가 뜨지 않으면 그 모델은 건너뛴다.
- A2의 도구 호출은 CPU에서 EXAONE 1.2B로 한 번 돌려 형식이 맞는 것을 확인했다(`scripts/serving/hf_cpu_server.py`). vLLM의 `--tool-call-parser hermes`는 EXAONE 4.0 모델 카드에 적힌 값이다.
- 마지막 절이 `gpu_results_2.tgz`를 만든다. 그 파일을 대화에 올리면 결과를 문서에 반영한다.

