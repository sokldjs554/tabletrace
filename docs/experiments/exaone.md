# EXAONE 사용 가능성 검토

> **GPU에서 실행하는 방법**은 [gpu-runbook.md](gpu-runbook.md)와 `notebooks/gpu_experiments.ipynb`(Colab·Kaggle)에 있다. 이 문서의 서술은 개발 컨테이너(GPU 없음)에서 실행하지 못한 상태의 기록이다.

## 확인한 사실 (GitHub raw로 LICENSE·README 직접 읽음, 2026-10-29)

| 항목 | EXAONE 3.5 | EXAONE 4.0 |
|---|---|---|
| 모델 크기 | 2.4B / 7.8B / 32B Instruct | 1.2B / 32B (hybrid reasoning) |
| 라이선스 | **EXAONE AI Model License Agreement 1.1 - NC** | **1.2 - NC** |
| 허용 | 연구·교육 목적의 사용·수정·파생물 배포(계약서 동봉, 파생 모델명에 "EXAONE" 접두), 연구 결과 공개 | 동일 |
| 금지 | 상업적 사용 전부(제품·서비스·수익), 경쟁 모델 개발에 사용, 리버스 엔지니어링 | 동일 |
| 환경 요구 | `transformers>=4.43`; vLLM≥0.6 / SGLang / TensorRT-LLM / llama.cpp(GGUF) 지원 | `transformers>=4.54`; llama.cpp b5932+, TensorRT-LLM |
| 배포 | Hugging Face Hub (`LGAI-EXAONE/*`) | 동일 |

이 프로젝트는 비상업 연구 포트폴리오이므로 라이선스상 사용은 가능하다.

## 왜 실제로 쓰지 못했나

1. **다운로드 불가**: 세션 네트워크 정책이 `huggingface.co`(및 미러)를 차단한다. 가중치를 받을 경로가 없었다(docs/research/environment.md).
2. **실행 자원 부족**: GPU가 없고 RAM 15 GB다. 2.4B 모델의 bf16 가중치 4.8 GB는 CPU 추론은 가능하지만(토큰당 수 초), LoRA 튜닝은 CPU에서 비현실적이고 7.8B/32B는 메모리 자체가 부족하다.

## 준비해 둔 것 (EXAONE을 받을 수 있는 환경에서 그대로 실행 가능)

- `scripts/serving/vllm_tp2.sh`, `sglang.sh`, `vllm_pp2.sh` — EXAONE 3.5 2.4B/7.8B를 vLLM/SGLang으로 2-GPU 텐서/파이프라인 병렬 서빙.
- `src/tabletrace/service/engines.py` — OpenAI 호환 API로 플래너를 호출하는 `EnginePlanner`(프로그램 문법 프롬프트 포함). 모의 서버로 왕복 테스트 완료(`tests/test_engines.py`).
- `src/tabletrace/bench/engine_bench.py` — 동시성별 지연·처리량 측정.
- LoRA SFT: `training/sft.py`는 seq2seq(mT5) 전용이다. causal LM용 LoRA 학습은 `scripts/train/exaone_lora_sft.py`(peft, 아래 예상 자원)로 준비했다.

## 예상 자원·비용 (실행하지 않음)

| 작업 | GPU | 시간(추정) | 클라우드 비용(추정, 시간당 A100 80GB ≈ $2–3 기준) |
|---|---|---|---|
| EXAONE 3.5 2.4B LoRA SFT, 3.4k 예제 × 2 epoch, seq 768 | A100 80GB ×1 (또는 L4 24GB) | 약 20–40분 | $1–2 |
| EXAONE 3.5 7.8B LoRA SFT, 동일 데이터 | A100 80GB ×1 | 약 1–1.5시간 | $3–5 |
| vLLM TP=2 서빙 벤치(2.4B) | L4 24GB ×2 또는 A100 ×2 | 30분 | $1–3 |
| GRPO 60 step, 7.8B, G=4 | A100 80GB ×2 | 약 2–3시간 | $10–18 |

추정치는 모델 크기·시퀀스 길이·배치로 계산한 어림값이며 실측이 아니다.
