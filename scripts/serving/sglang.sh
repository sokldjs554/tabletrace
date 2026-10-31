#!/usr/bin/env bash
# The same planner behind SGLang (OpenAI-compatible API). NUM_GPUS=2 for tensor parallelism, 1 on Colab.
# sglang 0.5.23 accepts sm75 and above (T4 is sm75). On a T4 pick the Triton attention backend and fp16:
#   MODEL=experiments/exaone_lora/merged NUM_GPUS=1 DTYPE=half ATTN_BACKEND=triton bash scripts/serving/sglang.sh
# (flag names: --tensor-parallel-size was checked in the sglang 0.5.23 wheel; the others are SGLang's documented names, not run here)
# vLLM and SGLang pin different torch versions: install them in separate virtualenvs (see notebooks/gpu_experiments.ipynb).
set -euo pipefail
MODEL="${MODEL:-LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct}"
PORT="${PORT:-8002}"
NUM_GPUS="${NUM_GPUS:-2}"
DTYPE="${DTYPE:-auto}"
ATTN="${ATTN_BACKEND:-}"
exec python -m sglang.launch_server --model-path "$MODEL" --tensor-parallel-size "$NUM_GPUS" --port "$PORT" --dtype "$DTYPE" --context-length 2048 \
  --served-model-name planner ${ATTN:+--attention-backend "$ATTN"} ${EXTRA_ARGS:-}
