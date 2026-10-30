#!/usr/bin/env bash
# Round two, part B (usage: resolve_pipeline_b.sh <pid of resolve_pipeline.sh>): takes over once the chemistry-stage
# evaluations are done, runs RL v3 with fewer, cheaper dev evaluations, evaluates it, picks the final model by a rule
# fixed in advance (RL checkpoint only if its dev score beat step 0, otherwise the SFT model), measures selective int8
# on that model and refreshes the stored demo runs.
set -u
cd "$(dirname "$0")/../.."
source .venv/bin/activate
A_PID=${1:?pid of resolve_pipeline.sh}
STATUS=experiments/pipeline/r2_status.txt
KO=data/ko/documents.jsonl; CH=data/chem/documents.jsonl
KOT="data/ko/test.jsonl data/ko/synthetic_test.jsonl"
TXT="$KO data/ko/text2_documents_train.jsonl data/ko/text2_documents_dev.jsonl data/ko/text2_documents_test.jsonl"
step() { local name=$1 marker=$2; shift 2
  if [ -e "$marker" ]; then echo "[$(date -u +%H:%M:%S)] SKIP  $name" | tee -a $STATUS; return; fi
  echo "[$(date -u +%H:%M:%S)] START $name" | tee -a $STATUS
  if "$@" > "experiments/pipeline/r2_$name.log" 2>&1; then echo "[$(date -u +%H:%M:%S)] OK    $name" | tee -a $STATUS; else echo "[$(date -u +%H:%M:%S)] FAIL  $name" | tee -a $STATUS; fi; }
evalone() { local n=$1 m=$2 c=$3; shift 3; local extra=${EVAL_EXTRA:-}
  rm -rf experiments/eval/$n experiments/eval/${n}_ec
  python -m tabletrace.eval.run --planner neural --model $m --corpus $c --data "$@" --out experiments/eval/$n --threads 4 --no-entity-check $extra || return 1
  python -m tabletrace.eval.run --planner neural --replay-from experiments/eval/$n --corpus $c --data "$@" --out experiments/eval/${n}_ec --label "entity check (replay of $n)" || return 1
  python scripts/analyze_predictions.py experiments/eval/$n > /dev/null && python scripts/analyze_predictions.py experiments/eval/${n}_ec > /dev/null; }
evalsets() { local n=$1 m=$2
  step eval_${n}_ko_test experiments/eval/${n}_ko_test_ec/metrics.json evalone ${n}_ko_test $m $KO $KOT
  step eval_${n}_ko_custom experiments/eval/${n}_ko_custom_ec/metrics.json evalone ${n}_ko_custom $m $KO data/ko/custom_eval.jsonl
  step eval_${n}_chem_custom experiments/eval/${n}_chem_custom_ec/metrics.json evalone ${n}_chem_custom $m $CH data/chem/custom_eval.jsonl
  step eval_${n}_text2_test experiments/eval/${n}_text2_test_ec/metrics.json evalone ${n}_text2_test $m "$TXT" data/ko/text2_test.jsonl
  step eval_${n}_chem_syndev experiments/eval/${n}_chem_syndev_ec/metrics.json evalone ${n}_chem_syndev $m $CH data/chem/synthetic_dev.jsonl; }

# wait for part A to finish the chemistry-stage evaluations, then take over from it
until grep -q "OK    eval_sft_chem2_chem_syndev" $STATUS 2>/dev/null; do sleep 20; done
kill "$A_PID" 2>/dev/null; sleep 2
pkill -f "training.rl_grpo --model experiments/sft_chem2" 2>/dev/null; sleep 3
[ -f experiments/rl_v3/summary.json ] || rm -rf experiments/rl_v3
echo "[$(date -u +%H:%M:%S)] part B took over" | tee -a $STATUS

step rl_v3 experiments/rl_v3/summary.json python -m tabletrace.training.rl_grpo --model experiments/sft_chem2/model \
  --train data/ko/train.jsonl data/ko/synthetic_train.jsonl data/chem/synthetic_train.jsonl data/ko/text2_train.jsonl \
  --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl data/chem/synthetic_dev.jsonl data/ko/text2_dev.jsonl \
  --corpus $KO $CH data/ko/text2_documents_train.jsonl data/ko/text2_documents_dev.jsonl \
  --out experiments/rl_v3/model --steps 120 --prompts-per-step 4 --group 4 --lr 2e-5 --beta 0.02 --eval-every 40 --threads 4
evalsets rl_v3 experiments/rl_v3/model

# final model, chosen by a rule fixed in advance: the RL checkpoint only if its dev score beat step 0
FINAL=$(python - <<'PY'
import json
s = json.load(open("experiments/rl_v3/summary.json"))
print("experiments/rl_v3/model" if s["best_step"] > 0 else "experiments/sft_chem2/model")
PY
)
echo "[$(date -u +%H:%M:%S)] final model = $FINAL" | tee -a $STATUS
echo "$FINAL" > experiments/final_model.txt

# selective int8 on the final model (accuracy), then the speed/memory benchmark
for scope in all no_lm_head ffn attn; do
  export EVAL_EXTRA="--quantize --quantize-scope $scope"
  step eval_final_int8_${scope}_ko_test experiments/eval/final_int8_${scope}_ko_test_ec/metrics.json evalone final_int8_${scope}_ko_test $FINAL $KO $KOT
done
export EVAL_EXTRA=""
step bench_inference experiments/bench/inference_r2.json python -m tabletrace.bench.inference --model $FINAL --n 48 --out experiments/bench/inference_r2.json --threads 4 \
  --precisions fp32 int8 int8-no_lm_head int8-ffn int8-attn
echo "[$(date -u +%H:%M:%S)] ROUND2 B DONE" | tee -a $STATUS
