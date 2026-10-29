#!/usr/bin/env bash
# Serve a causal-LM planner with vLLM across 2 GPUs (tensor parallelism) and expose the OpenAI API.
# NOT RUN in this project: the development container has no GPU (docs/experiments/parallel.md, serving.md).
# Requirements: 2x NVIDIA GPU (>= 16 GB each for the 7.8B bf16 model; 2.4B fits in 1x 8 GB), vllm>=0.6, CUDA 12.
set -euo pipefail
MODEL="${MODEL:-LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct}"   # EXAONE AI Model License 1.1-NC: research use only
PORT="${PORT:-8001}"
exec vllm serve "$MODEL" \
  --tensor-parallel-size 2 \
  --dtype bfloat16 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.90 \
  --port "$PORT" \
  --served-model-name planner
# Then: TABLETRACE_ENGINE_URL=http://127.0.0.1:$PORT TABLETRACE_ENGINE_MODEL=planner uvicorn tabletrace.service.app:app
# Benchmark: python -m tabletrace.bench.engine_bench --url http://127.0.0.1:$PORT --model planner --n 64
