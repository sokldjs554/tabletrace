#!/usr/bin/env bash
# RL with the corrected reward (v2), then its evaluations. Start only on an idle machine.
set -u
cd "$(dirname "$0")/../.."
source .venv/bin/activate
KO="data/ko/documents.jsonl"; CH="data/chem/documents.jsonl"
rm -rf experiments/rl_ko
python -m tabletrace.training.rl_grpo --model experiments/sft_ko2/model \
  --train data/ko/train.jsonl data/ko/synthetic_train.jsonl --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl \
  --corpus $KO --out experiments/rl_ko/model --steps 60 --prompts-per-step 4 --group 4 --lr 1e-5 --beta 0.02 --threads 4 \
  > experiments/pipeline/rl_ko_v2.log 2>&1
echo "[$(date -u +%H:%M:%S)] rl v2 exit=$?"
for spec in "ko_test:$KO:data/ko/test.jsonl data/ko/synthetic_test.jsonl" "ko_custom:$KO:data/ko/custom_eval.jsonl" "chem_custom:$CH:data/chem/custom_eval.jsonl"; do
  suffix=${spec%%:*}; rest=${spec#*:}; corpus=${rest%%:*}; data=${rest#*:}
  rm -rf experiments/eval/rl_ko_$suffix
  python -m tabletrace.eval.run --planner neural --model experiments/rl_ko/model --corpus $corpus --data $data --out experiments/eval/rl_ko_$suffix --threads 4 > experiments/pipeline/final_rl_ko_$suffix.log 2>&1
  python scripts/analyze_predictions.py experiments/eval/rl_ko_$suffix > /dev/null 2>&1
  echo "[$(date -u +%H:%M:%S)] eval rl_ko_$suffix done"
done
