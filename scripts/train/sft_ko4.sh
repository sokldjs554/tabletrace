#!/usr/bin/env bash
# One more lookup-heavy epoch on top of sft_ko3: ko3 learned `op: text` but then sent 15% of table lookups to
# `text`; extra lookup exposure rebalances without throwing the text behaviour away.
set -u
cd "$(dirname "$0")/../.."
source .venv/bin/activate
KO="data/ko/documents.jsonl"
python -m tabletrace.training.sft --model experiments/sft_ko3/model --train data/ko/stage4_train.jsonl \
  --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl data/ko/text2_dev.jsonl \
  --corpus $KO data/ko/text2_documents_train.jsonl data/ko/text2_documents_dev.jsonl \
  --out experiments/sft_ko4/model --epochs 1 --bs 8 --lr 1e-4 --threads 4 > experiments/pipeline/sft_ko4.log 2>&1
echo "[$(date -u +%H:%M:%S)] sft_ko4 exit=$?"
