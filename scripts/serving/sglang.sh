#!/usr/bin/env bash
# Same planner behind SGLang (tensor parallel 2). NOT RUN here (no GPU).
set -euo pipefail
MODEL="${MODEL:-LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct}"
PORT="${PORT:-8002}"
exec python -m sglang.launch_server --model-path "$MODEL" --tp 2 --port "$PORT" --dtype bfloat16 --context-length 4096
