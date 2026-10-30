#!/usr/bin/env bash
# Stage 2 again from the stage-1 model, with real-table text examples and natural not-in-document negatives
# (fixes the empty-table shortcut, REPORT 5.4 item 8). Then the chemistry stage on top of it.
set -u
cd "$(dirname "$0")/../.."
source .venv/bin/activate
KO="data/ko/documents.jsonl"
mkdir -p experiments/pipeline
if [ ! -f experiments/sft_ko3/summary.json ]; then
  python -m tabletrace.training.sft --model experiments/sft_ko/model --train data/ko/stage3_train.jsonl \
    --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl data/ko/text2_dev.jsonl \
    --corpus $KO data/ko/text2_documents_train.jsonl data/ko/text2_documents_dev.jsonl \
    --out experiments/sft_ko3/model --epochs 1 --bs 8 --lr 1.5e-4 --threads 4 > experiments/pipeline/sft_ko3.log 2>&1
  echo "[$(date -u +%H:%M:%S)] sft_ko3 exit=$?"
fi
