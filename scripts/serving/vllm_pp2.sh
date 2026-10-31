#!/usr/bin/env bash
# Pipeline parallelism (2 stages on 2 GPUs) with vLLM. Needs 2 GPUs (Kaggle 2xT4 / 2xL4): Colab's single GPU cannot run it.
# On T4 use DTYPE=half. vllm_tp2.sh is the tensor-parallel variant of the same server.
set -euo pipefail
MODEL="${MODEL:-LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct}"
exec vllm serve "$MODEL" --pipeline-parallel-size "${NUM_GPUS:-2}" --dtype "${DTYPE:-auto}" --max-model-len "${MAX_LEN:-2048}" \
  --port "${PORT:-8001}" --served-model-name planner ${EXTRA_ARGS:-}
