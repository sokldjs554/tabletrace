#!/usr/bin/env bash
# Second experiment round: fix what failed in round one (text answers next to a real table, missing-subject
# hallucinations, RL without gain). Restartable: every step has a done-marker. Logs: experiments/pipeline/r2_*.log
#   1. sft_ko3   stage 2 again from stage 1 with real-table text examples + natural not-in-document negatives
#   1b. sft_ko4  one lookup-heavy epoch on top (ko3 sent 15% of table lookups to `op: text`; see scripts/train/sft_ko4.sh)
#   2. sft_chem2 chemistry stage on top of sft_ko4 (+ rehearsal of text/abstain examples)
#   3. rl_v3     GRPO from sft_chem2 on ko + chem + text prompts, 150 steps, dev checkpoint selection
#   4. int8 variants of the final model (selective quantisation)
# Every model is run once WITHOUT the subject check (--no-entity-check, identical planner outputs) and its stored raw
# outputs are replayed WITH the check (*_ec), so before/after rows come from the same model run.
set -u
cd "$(dirname "$0")/../.."
source .venv/bin/activate
STATUS=experiments/pipeline/r2_status.txt
KO=data/ko/documents.jsonl; CH=data/chem/documents.jsonl
KOT="data/ko/test.jsonl data/ko/synthetic_test.jsonl"
TXT="$KO data/ko/text2_documents_train.jsonl data/ko/text2_documents_dev.jsonl data/ko/text2_documents_test.jsonl"
step() { # name marker cmd...
  local name=$1 marker=$2; shift 2
  if [ -e "$marker" ]; then echo "[$(date -u +%H:%M:%S)] SKIP  $name" | tee -a $STATUS; return; fi
  echo "[$(date -u +%H:%M:%S)] START $name" | tee -a $STATUS
  if "$@" > "experiments/pipeline/r2_$name.log" 2>&1; then echo "[$(date -u +%H:%M:%S)] OK    $name" | tee -a $STATUS; else echo "[$(date -u +%H:%M:%S)] FAIL  $name" | tee -a $STATUS; fi
}
evalone() { # run-name model corpus data... (replay with the check afterwards)
  local n=$1 m=$2 c=$3; shift 3
  rm -rf experiments/eval/$n experiments/eval/${n}_ec
  python -m tabletrace.eval.run --planner neural --model $m --corpus $c --data "$@" --out experiments/eval/$n --threads 4 --no-entity-check || return 1
  python -m tabletrace.eval.run --planner neural --replay-from experiments/eval/$n --corpus $c --data "$@" --out experiments/eval/${n}_ec --label "entity check (replay of $n)" || return 1
  python scripts/analyze_predictions.py experiments/eval/$n > /dev/null && python scripts/analyze_predictions.py experiments/eval/${n}_ec > /dev/null
}
evalsets() { # name model [chem]  -> ko_test, ko_custom, chem_custom, text2_test (+ chem_syndev for chem models)
  local n=$1 m=$2
  step eval_${n}_ko_test experiments/eval/${n}_ko_test_ec/metrics.json evalone ${n}_ko_test $m $KO $KOT
  step eval_${n}_ko_custom experiments/eval/${n}_ko_custom_ec/metrics.json evalone ${n}_ko_custom $m $KO data/ko/custom_eval.jsonl
  step eval_${n}_chem_custom experiments/eval/${n}_chem_custom_ec/metrics.json evalone ${n}_chem_custom $m $CH data/chem/custom_eval.jsonl
  step eval_${n}_text2_test experiments/eval/${n}_text2_test_ec/metrics.json evalone ${n}_text2_test $m "$TXT" data/ko/text2_test.jsonl
  if [ "${3:-}" = chem ]; then step eval_${n}_chem_syndev experiments/eval/${n}_chem_syndev_ec/metrics.json evalone ${n}_chem_syndev $m $CH data/chem/synthetic_dev.jsonl; fi
}
export -f evalone 2>/dev/null || true

# 1. stage 2 with real-table text examples
while [ ! -f experiments/sft_ko3/summary.json ]; do sleep 30; done
# baseline for the new text test: the round-one models (empty-table text training) on the same items
step eval_sft_ko2_text2_test experiments/eval/sft_ko2_text2_test_ec/metrics.json evalone sft_ko2_text2_test experiments/sft_ko2/model "$TXT" data/ko/text2_test.jsonl
step eval_sft_chem_text2_test experiments/eval/sft_chem_text2_test_ec/metrics.json evalone sft_chem_text2_test experiments/sft_chem/model "$TXT" data/ko/text2_test.jsonl

evalsets sft_ko3 experiments/sft_ko3/model

# 1b. lookup-heavy epoch on top of ko3 (started separately by scripts/train/sft_ko4.sh)
while [ ! -f experiments/sft_ko4/summary.json ]; do sleep 30; done
evalsets sft_ko4 experiments/sft_ko4/model

# 2. chemistry stage on top (rehearsal: text + not-in-document examples keep their behaviour)
python - <<'PY'
import json, random
rnd = random.Random(5)
rows = [json.loads(l) for l in open("data/chem/stage_train.jsonl", encoding="utf-8")]
t2 = [json.loads(l) for l in open("data/ko/text2_train.jsonl", encoding="utf-8")]
rnd.shuffle(t2)
rows += [r for r in t2 if r["op"] == "text"][:100] + [r for r in t2 if r["op"] == "abstain"][:60]
rnd.shuffle(rows)
open("data/chem/stage2_train.jsonl", "w", encoding="utf-8").write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
print(len(rows), "chem stage-2 examples")
PY
step sft_chem2 experiments/sft_chem2/summary.json python -m tabletrace.training.sft --model experiments/sft_ko4/model --train data/chem/stage2_train.jsonl \
  --dev data/chem/synthetic_dev.jsonl --corpus $CH $KO data/ko/text2_documents_train.jsonl --out experiments/sft_chem2/model --epochs 2 --bs 8 --lr 1.5e-4 --threads 4
evalsets sft_chem2 experiments/sft_chem2/model chem

# 3. RL v3
step rl_v3 experiments/rl_v3/summary.json python -m tabletrace.training.rl_grpo --model experiments/sft_chem2/model \
  --train data/ko/train.jsonl data/ko/synthetic_train.jsonl data/chem/synthetic_train.jsonl data/ko/text2_train.jsonl \
  --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl data/chem/synthetic_dev.jsonl data/ko/text2_dev.jsonl \
  --corpus $KO $CH data/ko/text2_documents_train.jsonl data/ko/text2_documents_dev.jsonl \
  --out experiments/rl_v3/model --steps 150 --prompts-per-step 4 --group 4 --lr 2e-5 --beta 0.02 --eval-every 25 --threads 4
evalsets rl_v3 experiments/rl_v3/model chem
echo "[$(date -u +%H:%M:%S)] ROUND2 DONE" | tee -a $STATUS
