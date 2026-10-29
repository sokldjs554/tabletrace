# 추론 서빙: 실제 실행 경로와 준비만 한 경로

## 실제로 실행한 것 (CPU)

| 항목 | 내용 |
|---|---|
| 서빙 방식 | FastAPI 프로세스 안에서 Transformers `MT5ForConditionalGeneration`을 직접 로드(in-process). CPU 바운드 추론은 스레드 풀에서 실행하고, 작업 큐·동시 실행 수·시간 제한을 둔다 (`service/jobs.py`) |
| 최적화 비교 | `bench/inference.py`: fp32 eager vs **int8 동적 양자화(nn.Linear)**, 배치 1 vs 8, KV 캐시 on/off. 결과는 `experiments/bench/inference.json`과 docs/REPORT.md에 기록 |
| 선택 이유 | GPU가 없어 CUDA 전용 엔진(vLLM, SGLang, TensorRT-LLM)을 쓸 수 없다. CPU에서 효과가 확실한 방법은 (1) 동적 int8 양자화(가중치 메모리 1/4, GEMM 가속), (2) 배치 처리(처리량), (3) KV 캐시(디코딩 비용 O(T²)→O(T))다 |

## 준비했지만 실행하지 못한 것 (GPU 필요)

| 항목 | 파일 | 실행 조건 |
|---|---|---|
| vLLM TP=2 서빙 | `scripts/serving/vllm_tp2.sh` | NVIDIA GPU 2장, vllm≥0.6, HF 접근 |
| vLLM PP=2 서빙 | `scripts/serving/vllm_pp2.sh` | 동일 |
| SGLang TP=2 서빙 | `scripts/serving/sglang.sh` | 동일 |
| OpenAI 호환 클라이언트 | `src/tabletrace/service/engines.py` (`EnginePlanner`) | 모의 서버로 테스트 완료 |
| 엔진 벤치 | `src/tabletrace/bench/engine_bench.py` | 서빙 중인 엔진 URL |

**호환성 확인**: EXAONE 3.5 README는 vLLM≥0.6과 SGLang을 공식 지원한다고 적고 있다(docs/experiments/exaone.md). 이 프로젝트의 mT5-small은 encoder-decoder라 vLLM의 주 대상(decoder-only)이 아니므로, 엔진 경로는 EXAONE 같은 causal LM 플래너용이다. PyPI에서 `vllm 0.32.0`, `sglang 0.5.22`가 설치 가능함은 확인했지만 GPU 없이 import·실행 검증은 하지 않았다.

## 측정 지표 정의 (`bench/inference.py`)

- 지연: 요청(예제) 1건당 생성 시간의 p50/p95 (배치일 때는 배치 시간/배치 크기).
- 처리량: 측정 라운드의 예제 수 / 총 시간.
- 메모리: 측정 직후 프로세스 RSS(GB). CPU라 GPU 메모리는 없음.
- 정확성: fp32 bs=1 출력과의 문자열 일치율(양자화가 출력을 바꾸는지).
- 조건: 동일 48개 입력(ko test), max_new_tokens 48, 워밍업 1라운드 + 측정 2라운드, 4 스레드.
