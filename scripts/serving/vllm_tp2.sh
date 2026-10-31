#!/usr/bin/env bash
# Serve a causal-LM planner with vLLM (OpenAI-compatible API). NUM_GPUS=2 gives tensor parallelism (Kaggle 2xT4, 2xL4, 2xA100).
# Colab has ONE GPU: NUM_GPUS=1. Needs a GPU box with CUDA; not runnable in the CPU container.
# T4 (compute capability 7.5) has no bfloat16: vLLM 0.32 lists only float16/float32 there, so use DTYPE=half (or auto with an fp16 checkpoint).
#   MODEL=experiments/exaone_lora/merged NUM_GPUS=1 DTYPE=half bash scripts/serving/vllm_tp2.sh
set -euo pipefail
MODEL="${MODEL:-LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct}"   # EXAONE AI Model License 1.1-NC: research use only
PORT="${PORT:-8001}"
NUM_GPUS="${NUM_GPUS:-2}"
DTYPE="${DTYPE:-auto}"
MAX_LEN="${MAX_LEN:-2048}"
GPU_UTIL="${GPU_UTIL:-0.88}"
exec vllm serve "$MODEL" \
  --tensor-parallel-size "$NUM_GPUS" \
  --dtype "$DTYPE" \
  --max-model-len "$MAX_LEN" \
  --gpu-memory-utilization "$GPU_UTIL" \
  --port "$PORT" \
  --served-model-name planner ${EXTRA_ARGS:-}
# Then: TABLETRACE_ENGINE_URL=http://127.0.0.1:$PORT TABLETRACE_ENGINE_MODEL=planner tabletrace serve
# Evaluate with the same verifier as every other planner:
#   python -m tabletrace.eval.run --planner engine --engine-url http://127.0.0.1:$PORT --tokenizer approx --corpus data/ko/documents.jsonl --data data/ko/test.jsonl data/ko/synthetic_test.jsonl --out experiments/eval/exaone_vllm_ko_test
# Benchmark: python -m tabletrace.bench.engine_bench --url http://127.0.0.1:$PORT --model planner --n 64
