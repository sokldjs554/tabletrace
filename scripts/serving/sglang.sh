#!/usr/bin/env bash
# The same planner behind SGLang (OpenAI-compatible API). NUM_GPUS=2 for tensor parallelism, 1 on Colab.
# On a T4 (sm75) sglang 0.5.9 fails in the first forward pass: sgl_kernel has no sm75 kernels (experiments/serving/
# sglang_t4_failure.md). Workaround: install scripts/serving/sglang_t4_shim.py into the venv and set SGLANG_T4_SHIM=1,
# which routes every MultiPlatformOp to its PyTorch forward_native (slower than the fused kernels; untested by the author).
#   <venv>/bin/python scripts/serving/sglang_t4_shim.py --install
#   SGLANG_T4_SHIM=1 ATTN_BACKEND=triton MODEL=experiments/exaone_lora/merged NUM_GPUS=1 DTYPE=half bash scripts/serving/sglang.sh
# On Ampere or newer (L4, A100, H100) run it without the shim.
# (flag names: --tensor-parallel-size was checked in the sglang 0.5.23 wheel; the others are SGLang's documented names, not run here)
# Python: use a 3.12 virtualenv and `sglang==0.5.9` on Colab (3.13 lacks wheels for some dependencies of sglang[all], see docs/experiments/gpu-runbook.md).
# vLLM and SGLang pin different torch versions: install them in separate virtualenvs (see notebooks/gpu_experiments.ipynb).
set -euo pipefail
MODEL="${MODEL:-LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct}"
PORT="${PORT:-8002}"
NUM_GPUS="${NUM_GPUS:-2}"
DTYPE="${DTYPE:-auto}"
ATTN="${ATTN_BACKEND:-}"
SAMPLING="${SAMPLING_BACKEND:-pytorch}"      # the default (flashinfer) is unreliable on T4 (sm75)
exec python -m sglang.launch_server --model-path "$MODEL" --tensor-parallel-size "$NUM_GPUS" --port "$PORT" --dtype "$DTYPE" --context-length 2048 \
  --served-model-name planner ${ATTN:+--attention-backend "$ATTN"} --sampling-backend "$SAMPLING" ${EXTRA_ARGS:-}
