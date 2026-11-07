# 추론 서빙: 실제 실행 경로와 준비만 한 경로

> **GPU에서 실행하는 방법**은 [gpu-runbook.md](gpu-runbook.md)와 `notebooks/gpu_experiments.ipynb`(Colab·Kaggle)에 있다. 이 문서의 서술은 개발 컨테이너(GPU 없음)에서 실행하지 못한 상태의 기록이다.

## 실제로 실행한 것 (CPU)

| 항목 | 내용 |
|---|---|
| 서빙 방식 | FastAPI 프로세스 안에서 Transformers `MT5ForConditionalGeneration`을 직접 로드(in-process). CPU 바운드 추론은 스레드 풀에서 실행하고, 작업 큐·동시 실행 수·시간 제한을 둔다 (`service/jobs.py`) |
| 최적화 비교 | `bench/inference.py`: fp32 eager vs **int8 동적 양자화(nn.Linear)**, 배치 1 vs 8, KV 캐시 on/off. 결과는 `experiments/bench/inference.json`과 docs/REPORT.md에 기록 |
| 선택 이유 | GPU가 없어 CUDA 전용 엔진(vLLM, SGLang, TensorRT-LLM)을 쓸 수 없다. CPU에서 효과가 확실한 방법은 (1) 동적 int8 양자화(가중치 메모리 1/4, GEMM 가속), (2) 배치 처리(처리량), (3) KV 캐시(디코딩 비용 O(T²)→O(T))다 |

## 준비했지만 실행하지 못한 것 (GPU 필요)

| 항목 | 파일 | 실행 조건 |
|---|---|---|
| vLLM 서빙 | `scripts/serving/vllm_tp2.sh` | GPU 1장은 **실행됨**(아래). TP=2는 GPU 2장, 수치 대기 |
| vLLM PP=2 서빙 | `scripts/serving/vllm_pp2.sh` | 동일 |
| SGLang TP=2 서빙 | `scripts/serving/sglang.sh` | 동일 |
| OpenAI 호환 클라이언트 | `src/tabletrace/service/engines.py` (`EnginePlanner`) | 모의 서버로 테스트 완료 |
| 엔진 벤치 | `src/tabletrace/bench/engine_bench.py` | 서빙 중인 엔진 URL |

**호환성 확인 (실측)**: `scripts/serving/check_engine_support.py`가 두 엔진의 공개 wheel을 내려받아(설치하지 않음) 모델 등록부를 읽는다. 결과는 `experiments/serving/engine_support.json`.

| 엔진 (wheel) | T5/mT5 | BART 계열 | EXAONE |
|---|---|---|---|
| vLLM 0.32.0 | **없음** | 외부 플러그인으로만 | `ExaoneForCausalLM`, `Exaone4ForCausalLM` 등 지원 |
| SGLang 0.5.23 | **없음** | 없음 | `exaone.py`, `exaone4.py` 지원 |

따라서 **이 프로젝트의 mT5-small(encoder-decoder)은 vLLM/SGLang으로 서빙할 수 없다.** 서빙 스크립트가 의미를 가지려면 EXAONE 같은 decoder-only 모델을 LoRA SFT해야 하고(`scripts/train/exaone_lora_sft.py`), 가중치가 필요하다. 이 환경은 가중치 호스트(`huggingface.co`, 미러, ModelScope)가 정책으로 막혀 있고 GPU도 없어 여기서는 실행하지 못했다. 이전 문서의 "EXAONE이 vLLM≥0.6을 지원한다"는 EXAONE 3.5 README의 문구이고, 위 표는 현재 wheel에서 직접 확인한 값이다.

## 측정 지표 정의 (`bench/inference.py`)

- 지연: 요청(예제) 1건당 생성 시간의 p50/p95 (배치일 때는 배치 시간/배치 크기).
- 처리량: 측정 라운드의 예제 수 / 총 시간.
- 메모리: 측정 직후 프로세스 RSS(GB). CPU라 GPU 메모리는 없음.
- 정확성: fp32 bs=1 출력과의 문자열 일치율(양자화가 출력을 바꾸는지).
- 조건: 동일 48개 입력(ko test), max_new_tokens 48, 워밍업 1라운드 + 측정 2라운드, 4 스레드.

## 실행 결과 (사용자 Colab T4, 2026-11-04)

- **SGLang 0.5.9**: T4에서 **실패**. 서버가 모델을 올린 뒤 첫 연산에서 `no kernel image is available for execution on the device`. `sgl_kernel`에 sm75 커널이 없다. 설정으로 우회할 수 없다. 로그와 해석은 `experiments/serving/sglang_t4_failure.md`. Ampere 이상(L4·A100·H100)에서는 시도하지 않았다.
- **vLLM**(가상환경에 `uv pip install vllm`, 2026-11-07): EXAONE-4.0-1.2B LoRA 병합 모델을 fp16·GPU 1장으로 띄워 ko test 699문항을 같은 검증기로 평가하고 동시 요청 1/8/32 벤치를 받았다. 값은 `experiments/eval/exaone_vllm_ko_test*/metrics.json`, `experiments/bench/engine_vllm_c*.json`, 표와 해석은 README §10.3·REPORT §18.3, 출처는 `experiments/eval/exaone_vllm_ko_test/PROVENANCE.md`. 처음에는 상대 경로 모델 폴더를 서버가 못 찾아 `OSError`가 났고(이슈 37), 절대 경로로 고친 뒤 떴다.
- **vLLM TP=2·NCCL 파이프라인**(Kaggle T4 2장): 소유자가 성공을 보고했으나 결과 파일을 받지 못해 수치가 없다.

