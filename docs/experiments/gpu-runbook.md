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

공고와 대조했을 때 비어 있던 부분을 채우는 실험을 한 노트북에 모았다. 작성자는 실행해 보지 못했다. **소유자가 2026-11-14에 A~H절을 돌렸다.** 결과 파일은 세션과 함께 사라졌고 수치는 노트북 출력에서 복원했다(`experiments/gpu2_2026-11-14/`, `docs/REPORT.md` §21). **2026-11-15에는 A절, A2절, D절을 다시 돌렸고 결과 묶음을 파일로 받았다**(`docs/REPORT.md` §22). 0번 절(준비)만 필수이고 나머지는 골라서 돌린다.

| 절 | 재는 것 | GPU | 예상 시간 |
|---|---|---|---|
| A | 튜닝하지 않은 EXAONE 1.2B / 7.8B(AWQ) / 32B(AWQ)에 예시 6개를 주고 같은 검증기로 채점 | 32B만 2장 | 40분 + 60분 |
| A2 | 모델이 도구를 스스로 골라 표를 읽는 방식(Tool Calling) | 32B만 2장 | 30분 + 60분 |
| B | 학습 데이터를 풀로 늘림(약 1만, 약 3.4만 문항) | 1장, 2장이면 DDP로 절반 | 1.5시간, 5시간 |
| C | 멀티 GPU 학습(DDP) 속도 | 2장 | 15분 |
| D | EXAONE 강화학습(GRPO). 본인이 쓴 `training/evidence_reward.py`와 `training/grpo.py`를 불러 쓴다(2026-11-12 병합, PR #6). T4 한 장에서는 `--chunk 1`(노트북 기본값). `--chunk 2`는 메모리가 넘쳤다 | 1장 | 1.5~2시간 |
| E | 튜닝 모델을 4비트로 올렸을 때의 정확도·속도·메모리 | 1장 | 20분 |
| F | 열 번호 형식: 시드 둘 더, 전체 데이터 | 1장 | 1시간 |
| G | 영어 화학(교과서 두 세트, 논문 표 62문항) | 1장 | 30분 |
| H | 큰 표(공개 dev의 처음 보는 표 3,072문항): 앞에서 자르기 대 행 선별 | 1장 | 20분 |
| I | 길이 결함을 고친 설정으로 전체 데이터 미세조정. 같은 세션에서 예전 설정도 한 번 | 1장 | 1시간 20분 |
| J | 전체 데이터 모델에서 시작하는 강화학습(2026-11-16에 끝남) | 1장 | 실제로는 시작 모델 학습 29분, 강화학습 45분, 평가 포함 1시간 30분쯤 |
| L | 소유자가 쓴 평가 30문항으로 EXAONE 평가: 전체 데이터 모델(새 세션이면 다시 학습), 튜닝 없는 1.2B와 7.8B(2026-11-16에 끝남) | 1장 | 실제로 전체 데이터 모델 학습 31분, 평가까지 1시간쯤 |
| M | 소유자가 직접 쓴 학습 루프(`training/lm_loop.py`, `--loop owner`)로 전체 데이터 미세조정(2026-11-16에 Colab에서 끝남) | 1장 | 실제로 학습 30분, 평가 포함 50분쯤 |
| N | 화학 문항에서의 EXAONE. 한국어와 화학을 함께 튜닝한 모델과 튜닝 없는 1.2B, 문항별 예측을 남긴다(2026-11-17에 Colab에서 끝남) | 1장 | 실제로 학습 36분, 평가 18건의 기록은 그 뒤 8분 사이에 찍힘 |
| O | 한국어만 튜닝한 EXAONE을 화학 문항으로 평가. N절의 결과에서 화학 문항을 더한 몫을 가른다(2026-11-17에 Colab에서 끝남. 반복 학습은 2026-11-18에 끝남) | 1장 | 실제로 학습 33분, 평가 12건의 기록은 그 뒤 4분 사이에 찍힘. 반복 학습은 실제로 38분 |

알아 둘 것.

- 권하는 순서는 H → A → B(7000) → F → G → E → C → A2 → D다. 앞의 것일수록 실패할 일이 적고 결과의 쓸모가 크다.
- 모든 평가가 `--confidence`로 토큰 로그 확률을 저장한다. 결과가 오면 위험·응답률 곡선을 그린다.
- 노트북이 스크립트에 넘기는 옵션이 실제로 있는지는 `tests/test_notebook_flags.py`가 검사한다. 그 이상(메모리, 서버 기동, 모델 내려받기)은 돌려 봐야 안다.
- 32B AWQ는 T4 두 장에 빠듯하다. 소유자의 첫 시도(2026-11-14)에서 서버는 떴지만 평가 도중 GPU 메모리 부족으로 죽었다(메모리 95% 선점, 동시 8건. GPU 0의 14.56GB 가운데 12.8MB만 남은 상태에서 28MB를 못 잡음). 그래서 32B는 기본으로 끄고(`RUN_32B = False`), 켤 때는 메모리 90% 선점, `--max-num-seqs 2 --max-num-batched-tokens 2048`, 동시 2건, 200문항 표본으로 돌린다. 이 설정이 되는지는 아직 확인되지 않았다. 1.2B와 7.8B AWQ의 참고선은 같은 실행에서 끝까지 돌았다.
- 평가 도중 서버가 죽으면 그 모델의 남은 평가를 그만두고 서버 로그의 끝을 보여 준 뒤 다음으로 넘어간다. 서버 로그의 메모리 관련 줄과 끝부분은 결과 묶음에 함께 담긴다(`experiments/run_logs/`).
- A2의 도구 호출은 CPU에서 EXAONE 1.2B로 한 번 돌려 형식이 맞는 것을 확인했다(`scripts/serving/hf_cpu_server.py`). vLLM의 `--tool-call-parser hermes`는 EXAONE 4.0 모델 카드에 적힌 값이다.
- **2026-11-15 실행에서 끝난 것**: A절의 빠진 두 값(예시만 준 1.2B, 7.8B의 test), A2절의 1.2B, D절의 강화학습 두 번째 실험. 결과는 `docs/REPORT.md` §22에 있다.
- **대조군은 2026-11-15 뒤의 세션에서 돌렸다**(`docs/REPORT.md` §22.7). D절 첫 셀의 `RUN_CONTROL = True`로 돌았고, 새 세션이라 시작 모델을 `exaone_rlstart2b`로 다시 학습해 따로 평가했다. 결과: 배치 구성만 되돌리면 인용 셀 정확도가 오르지 않고 학습 도중 무너진다.
- **본 실험의 반복도 2026-11-15에 돌렸다**(`docs/REPORT.md` §22.8). D절 첫 셀의 `RUN_REPEAT = True`로 돌았다. 대조군을 돌린 세션의 작업 폴더가 Kaggle에 남아 있어서 대조군과 같은 시작 모델(`exaone_rlstart2b`)의 가중치에서 시작했고, 시작 모델은 다시 학습하지 않았다. 결과: 본 실험과 같은 결과가 다시 나왔다.
- **I절은 2026-11-16에 돌렸다**(`docs/REPORT.md` §23). 고친 설정(`exaone_full2`)과 예전 설정(`exaone_full2old`)을 같은 세션에서 학습·평가했다. 결과: 정답률에 검출되는 차이가 없다(86.4% 대 87.0%). 메모리 문제는 없었다.
- **J절은 2026-11-16에 돌렸다**(`docs/REPORT.md` §24). 새 세션이라 시작 모델을 `exaone_full3`으로 다시 학습해 따로 평가한 뒤 거기서 시작했다(학습 29분, 강화학습 45분). 결과: 정답률에 검출되는 차이가 없다(86.0%와 86.1%, 같은 문항에서 8 대 7). 200걸음 가운데 127걸음만 가중치를 바꿨다. 확신도의 변별력은 떨어졌다. 결과 묶음이 결과 가지(`gpu-results-2`)에도 올라와 있었고 대화로 받은 파일과 같았다(결과 가지에서 묶음을 받아 대조한 것은 이번이 처음이다). **L절도 2026-11-16에 돌렸다**(`docs/REPORT.md` §25.6). 새 세션이라 전체 데이터 모델을 `exaone_full4`로 다시 학습했다(31분, test 85.5%). 소유자가 쓴 30문항에서 전체 데이터 EXAONE 80.0%(24/30), 튜닝하지 않은 7.8B 66.7%, 1.2B 43.3%. 평가 10건을 다시 검증해 판정이 모두 같았다. **M절도 2026-11-16에 돌렸다**(`docs/REPORT.md` §27). Kaggle의 주간 할당량이 다 차서 Colab(T4 한 장)에서 돌렸고, 2번 노트북을 Colab에서 돌린 첫 실행이다. 학습 기록의 커밋은 저장소의 `7618400` 그대로다. 결과: 소유자가 쓴 루프로 학습한 전체 데이터 모델이 test 86.0%로, 들어 있는 루프로 한 여섯 번의 범위(84.3%~87.1%) 안이다. 평가 6건을 다시 검증해 판정이 모두 같았다. **지금 돌릴 것은 없다.** 아래는 M절을 실행하기 전에 적어 둔 안내다(2026-11-16 추가). 지금까지의 EXAONE 미세조정은 모두 스크립트에 들어 있는 루프로 돌았고, 소유자가 쓴 루프는 GPU 학습에 쓰인 적이 없다(`docs/REPORT.md` §26). M절은 지난 전체 데이터 학습의 명령에 `--loop owner`만 더해 한 번 학습하고 test, AI 도구가 쓴 30문항, 소유자가 쓴 30문항을 평가한다. 소유자의 루프는 학습률을 선형으로 줄이므로 결과가 지난 여섯 번과 조금 다를 수 있다. GPU에서 이 경로는 처음 돈다. 돌리기 전에 CPU에서 실제 EXAONE 1.2B 가중치로 두 걸음을 돌려 이 경로가 끝까지 도는 것과 학습 기록에 소유자의 루프가 적히는 것을 확인했다(반정밀도와 기울기 스케일러를 쓰는 GPU 쪽은 확인하지 못했다). 아래는 L절을 실행하기 전에 적어 둔 안내다(2026-11-16 추가, 소유자가 쓴 평가 30문항으로 EXAONE 평가). 0번 절의 셀 두 개를 실행한 뒤 L절의 셀을 실행한다. 새 세션이면 전체 데이터 모델을 `exaone_full4`로 다시 학습해(30분) 한국어 test, AI 도구가 쓴 30문항, 소유자가 쓴 30문항을 평가하고, 튜닝하지 않은 1.2B와 7.8B는 소유자 문항만 평가한다. 30문항이라 한두 문항의 차이는 뜻이 없다는 것을 알고 돌린다. 아래는 J절을 실행하기 전에 적어 둔 안내다. 0번 절의 셀 두 개를 실행한 뒤 J절의 셀을 실행한다. 강화학습은 D절의 본 실험과 같고 시작 모델만 다르다. I절을 돌린 세션의 작업 폴더가 남아 있으면 그 모델의 어댑터(`experiments/exaone_lora_full2`)에서 바로 시작한다(1시간 40분쯤). 남아 있지 않으면 같은 설정으로 다시 학습해 `exaone_full3`으로 따로 평가한 뒤 시작한다(40분쯤 더). 미리 적어 두는 예상: 시작 모델이 학습 문항을 이미 잘 맞혀서 표본들의 점수가 같은 걸음이 많고, 갱신이 적게 일어날 것이다. 효과가 없을 가능성이 크다. 어느 쪽이든 "강화학습이 미세조정 위에서도 듣는가"의 답이 된다.
- I절이 말해 줄 수 있는 것과 없는 것. 말해 줄 수 있는 것: 고친 설정의 verified EM, 같은 세션의 예전 설정과의 문항 단위 비교, 표가 긴 문항(정답이 잘리던 길이)에서의 차이, 전체 데이터 모델의 확신도 곡선. 말해 줄 수 없는 것: 한 쌍만으로는 학습 실행 간 흔들림을 다 걷어 내지 못한다. 차이가 작으면 "고쳐도 비슷했다"까지만 쓴다.
- GPU 메모리. 고친 설정의 가장 긴 예제는 882토큰이다. 300문항 시작 모델을 같은 설정으로 세 번 학습했을 때의 가장 긴 예제가 848토큰이었고 T4에서 문제없이 돌았다. 전체 데이터에서 850토큰을 넘는 예제는 4개다. 메모리가 넘치면 그 셀의 출력을 알려 준다.
- **N절은 2026-11-17에 Colab에서 돌렸다**(`docs/REPORT.md` §29). 화학 문항에서의 EXAONE이다. 지난 화학 결과(G절, 2026-11-14)는 세션과 함께 사라져 수치만 되살렸고 문항별 예측이 없었다. N절은 한국어와 화학을 함께 튜닝한 모델을 길이를 고친 설정(입력 672, 전체 960)으로 다시 학습해 화학 세 세트(교과서 수작업 32, 합성 개발 80, 논문 표 62)와 한국어 세 세트로 평가하고, 튜닝하지 않은 1.2B를 화학 세 세트로 평가한다(예시 6개는 화학 합성 학습 문항에서). 결과 이름은 `exaone_kochem2_vllm_*`와 `ref_1p2b_chem_*`이다. 학습 273걸음에 36.2분이 걸렸다. 결과: 논문 표 74.2%(46/62), 교과서 수작업 75.0%, 합성 개발 91.2%, 한국어 test 86.1%. 튜닝하지 않은 모델은 논문 표 24.2%. G절에서 되살린 논문 표 수치(80.7%)보다 4문항 낮다. 받은 묶음은 `python scripts/replay_check.py --session chem`으로 다시 검증했다(18건, 2,214문항, 다른 판정 0개). 결과가 저장소에 있어서 다시 실행해도 아무것도 하지 않는다.
- **O절은 2026-11-17에 Colab에서 돌렸다**(`docs/REPORT.md` §29.7). 한국어만 튜닝한 EXAONE(`exaone_koonly`, 학습 명령은 `exaone_full4`와 같다)을 N절과 같은 여섯 세트로 평가했다. 학습 224걸음에 33.1분이 걸렸다. 결과: 화학 문항을 한 번도 보지 않고 논문 표 67.7%(42/62), 교과서 수작업 59.4%, 합성 개발 82.5%, 한국어 test 86.4%. N절의 모델(화학 문항을 더함)과는 같은 문항에서 논문 표 7 대 3(p 0.344), 교과서 수작업 5 대 0(p 0.062), 합성 개발 9 대 2(p 0.065)로 어디서도 유의하지 않다. 결과를 본 뒤 나눠 보면 답 없는 질문에서 갈린다(13 대 0). 받은 묶음은 `python scripts/replay_check.py --session share`로 다시 검증했다(12건, 1,866문항, 다른 판정 0개). **반복 학습(`RUN_KOCHEM_REPEAT`)은 2026-11-18에 Colab에서 돌렸다**(`exaone_kochem3`, 학습 38.3분, `docs/REPORT.md` §29.8). 볼 것은 실행 전에 §29.7 끝에 적어 두었다. 결과: 논문 표 75.8%(47/62), 답 없는 질문에서 한국어 전용 모델과 10 대 0(p 0.002)로 적어 둔 확인이 성립했다. 답할 수 있는 질문에서는 8 대 3(p 0.227). 받은 묶음은 `python scripts/replay_check.py --session chemrepeat`로 다시 검증했다(12건, 1,866문항, 다른 판정 0개). 결과가 저장소에 있어서 O절은 다시 실행해도 아무것도 하지 않는다.
- **P절의 P1(`P_KOONLY`)은 2026-11-20에 Colab에서 돌렸다**(`docs/REPORT.md` §31.1). 한국어 전용 학습을 O절과 같은 명령으로 한 번 더 했다(`exaone_koonly2`, 학습 32.7분). 볼 것은 실행 전에 §31에 적어 두었다. 답 없는 질문의 비교(1a)는 7 대 1(p 0.070)로 남지 않았고, 논문 표의 비교(1b)는 30 대 3(p <0.001)으로 남았다. 받은 묶음은 `python scripts/replay_check.py --session koonly2`로 다시 검증했다(12건, 1,866문항, 다른 판정 0개). 
- **P절의 P2(`P_RL`)는 2026-11-20에 Colab에서 돌렸다**(`docs/REPORT.md` §31.2). J절의 시작 모델과 강화학습을 같은 명령으로 한 번 더 했다(`exaone_full5` 32.9분, `exaone_grpo4` 46.1분). 미리 적어 둔 확인(강화학습 전후의 정답률에 차이가 없다)이 남았다: 87.3%와 87.3%, 9 대 9(p 1.000). 확신도의 AUROC는 0.806에서 0.758로 처음과 같은 방향이다(미리 적지 않은 비교). 받은 묶음은 `python scripts/replay_check.py --session rl4`로 다시 검증했다(8건, 2,916문항, 다른 판정 0개).
- **P절의 P3(`P_OWNLOOP`)은 2026-11-20에 Colab에서 P2와 같은 세션으로 돌렸다**(`docs/REPORT.md` §31.3). M절의 학습을 직접 쓴 루프로 한 번 더 했다(`exaone_ownloop2`, 학습 32.5분). 미리 적어 둔 두 확인이 남았다: 처음 학습과 20 대 9(p 0.061), 같은 명령의 스크립트 루프 학습과 31 대 17(p 0.059). 새 학습은 한국어 test 87.5%로 그전 여덟 번의 범위보다 높다. 받은 묶음은 `python scripts/replay_check.py --session ownloop2`로 다시 검증했다(6건, 1,518문항, 다른 판정 0개). **이것으로 계획한 GPU 실험은 모두 끝났다.**
- **그 밖에 돌리지 않은 것(선택)**: (1) 강화학습의 시드를 바꾼 실행(학습 스크립트의 `--seed`. 노트북에는 그 선택이 없다). (2) 32B 재실행(`RUN_32B = True`). 급하지 않다. D절의 `RUN_CONTROL`과 `RUN_REPEAT`는 결과가 저장소에 있어서 지금은 켜도 아무것도 하지 않는다. 다시 돌리려면 그 실험의 결과 폴더를 지운다.
- **실행 이름에 점을 쓰지 않는다.** 2026-11-15 묶음의 `ref_1.2b_*`, `ref_7.8b_awq_*`, `tools_1.2b_*`는 저장소에 넣을 때 `ref_1p2b_*`, `ref_7p8b_awq_*`, `tools_1p2b_*`로 바꿨다. 문서의 수치 묶기가 점을 경로 구분자로 쓰기 때문이다. 노트북도 새 이름을 쓴다. 예전 묶음을 되살린 세션에서는 옛 이름의 평가가 끝난 것으로 인식되지 않아 그 세 모델의 평가를 다시 한다.
- **준비 셀은 저장소를 받아 온 main으로 맞춘다**(`git fetch` 뒤 `git reset --hard`). 이전 세션의 작업 폴더가 남아 있으면 그때의 결과 파일이 저장소에 새로 들어간 파일과 겹쳐 `git pull`이 멈추고, 노트북이 예전 코드로 조용히 진행했다(문제 70). 겹치는 파일만 저장소의 것으로 바뀌고 그 밖의 결과와 가중치는 남는다. 준비 셀의 마지막 줄이 찍는 커밋을 확인한다.
- **받은 묶음은 다시 검증한다.** `python scripts/replay_check.py --tokenizer LGAI-EXAONE/EXAONE-4.0-1.2B`가 저장된 모델 출력을 이 저장소의 검증기로 다시 검증해 문항 단위로 견준다. 2026-11-15 묶음은 22회, 8,290문항에서 다른 문항이 없었다. 대조군 묶음은 `--session control`로 확인한다(8회, 2,916문항, 다른 문항 없음). 반복 실행 묶음은 `--session repeat`(4회, 1,458문항, 다른 문항 없음). I절의 묶음은 `--session full2`(8회, 2,916문항, 다른 문항 없음).
- **결과는 GitHub로 바로 올린다.** 소유자의 결과는 두 번 사라졌다. 두 번째(2026-11-15)는 90개 항목을 다 만든 뒤였는데, Kaggle에서 내려받기 링크가 뜨지 않는 결함(문제 59) 때문에 받아 두지 못한 채 세션이 바뀌었다. 그래서 사람 손을 거치지 않게 했다. Kaggle Secrets에 `GH_TOKEN`(이 저장소의 Contents 쓰기 권한만 가진 fine-grained 토큰)을 넣어 두면 `pack()`이 절마다 결과 묶음을 결과 전용 브랜치 `gpu-results-2`에 올린다. 새 세션은 그 브랜치의 묶음을 되살려 끝난 평가를 건너뛴다. 토큰은 git의 헤더 옵션으로만 넘기고 화면에 찍지 않는다. CI는 그 브랜치에서 돌지 않는다. 이 경로는 로컬의 빈 저장소를 원격 삼아 시험했고, 실제 GitHub로 올리는 것은 소유자의 다음 실행에서 처음 돈다.
- **결과를 잃지 않게 한다.** Kaggle은 세션이 끝나거나 새로 시작되면 `/kaggle/working`을 비운다. 소유자의 첫 실행은 끝까지 돌고 결과 묶음까지 만들었지만, 내려받기 전에 세션이 바뀌어 전부 사라졌다(2026-11-13). 그래서 (1) Session options의 Persistence를 Files only로 두고, (2) 절이 끝날 때마다 `pack()`이 `gpu_results_2.tgz`를 다시 묶어 내려받기 링크를 띄우므로 그때그때 받는다.
- **다시 실행하면 끝난 것은 건너뛴다.** 학습은 `train_info.json`, 평가는 `<이름>_<세트>_ec/metrics.json`이 있으면 끝난 것으로 본다. 학습은 끝에서만 저장하므로 도중에 멈춘 학습은 처음부터 다시 한다. 일부러 다시 만들려면 그 폴더를 지운다.
- **디스크.** 병합 모델 하나가 약 2.5GB이고 Kaggle 작업 폴더는 20GB까지다. 평가가 끝난 모델의 병합 가중치는 지운다(어댑터와 기록은 남는다). E, H절이 다시 쓰는 두 모델(B의 풀 모델, D의 시작 모델)만 남긴다. 속도만 재는 C절은 병합 모델을 만들지 않는다.
- 이 동작(건너뛰기, 중단된 부분만 다시 하기, 묶음에 가중치가 없는 것, 남는 모델)은 셸 명령을 기록기로 바꿔 노트북을 GPU 없이 돌려 보는 `tests/test_notebook_dry_run.py`가 검사한다. 명령 자체가 GPU에서 성공하는지는 검사하지 못한다.
- **Colab에서 돌릴 때.** 런타임 유형을 T4 GPU로 하고 보안 비밀에 `HF_TOKEN`을 넣는다. Colab에는 파일 보존 설정이 없어서, 준비 셀이 Google Drive를 연결해 결과 묶음을 `내 드라이브/tabletrace_results/`에도 두고 `pack()`이 브라우저로 바로 내려받게 한다. 런타임이 끊긴 뒤 새로 시작하면 Drive의 묶음을 되살려 끝난 평가를 건너뛴다(묶음에 가중치는 없으므로 강화학습의 시작 모델만 다시 학습한다). GPU가 한 장이라 32B 모델과 C절은 빠진다. Colab 경로는 모의 실행으로만 확인했고 실제 Colab에서는 돌려 보지 못했다.
- 마지막 절도 같은 `gpu_results_2.tgz`를 만든다. 마지막에 받은 것 하나를 대화에 올리면 결과를 문서에 반영한다.

