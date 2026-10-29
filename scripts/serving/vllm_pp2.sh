#!/usr/bin/env bash
# Pipeline parallelism variant (2 stages on 2 GPUs). NOT RUN here (no GPU).
set -euo pipefail
MODEL="${MODEL:-LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct}"
exec vllm serve "$MODEL" --pipeline-parallel-size 2 --dtype bfloat16 --max-model-len 4096 --port "${PORT:-8001}" --served-model-name planner
