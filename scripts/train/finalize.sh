#!/usr/bin/env bash
# After run_pipeline.sh: re-evaluate every model with the final evaluation code (same verifier for all),
# write analyses, render tables into README/REPORT, rebuild research.json and recorded runs.
set -u
cd "$(dirname "$0")/../.."
source .venv/bin/activate
KO="data/ko/documents.jsonl"; CH="data/chem/documents.jsonl"
KO_TEST="data/ko/test.jsonl data/ko/synthetic_test.jsonl"
ev() { # key model corpus data...
  local key=$1 model=$2 corpus=$3; shift 3
  rm -rf "experiments/eval/$key"
  if [ "$model" = "heuristic" ]; then
    python -m tabletrace.eval.run --planner heuristic --corpus $corpus --data "$@" --out "experiments/eval/$key" > "experiments/pipeline/final_$key.log" 2>&1
  else
    python -m tabletrace.eval.run --planner neural --model "$model" --corpus $corpus --data "$@" --out "experiments/eval/$key" --threads 4 > "experiments/pipeline/final_$key.log" 2>&1
  fi
  python scripts/analyze_predictions.py "experiments/eval/$key" > /dev/null 2>&1
  echo "[$(date -u +%H:%M:%S)] eval $key: $(python -c "import json;m=json.load(open('experiments/eval/$key/metrics.json'))['metrics'];print('vEM',m['verified_em'],'untrunc',m['verified_em_untruncated'])" 2>/dev/null)"
}
for pair in "heuristic:heuristic" "base:models/mt5-small-base" "sft_ko:experiments/sft_ko/model" "sft_ko2:experiments/sft_ko2/model" "rl_ko:experiments/rl_ko/model" "sft_chem:experiments/sft_chem/model"; do
  key=${pair%%:*}; model=${pair#*:}
  [ "$model" = "heuristic" ] || [ -f "$model/model.safetensors" ] || { echo "skip $key (no model)"; continue; }
  ev "${key}_ko_test" "$model" "$KO" $KO_TEST
  ev "${key}_ko_custom" "$model" "$KO" data/ko/custom_eval.jsonl
  ev "${key}_chem_custom" "$model" "$CH" data/chem/custom_eval.jsonl
done
for pair in "sft_ko2:experiments/sft_ko2/model" "sft_chem:experiments/sft_chem/model"; do
  key=${pair%%:*}; model=${pair#*:}; [ -f "$model/model.safetensors" ] && ev "${key}_chem_syndev" "$model" "$CH" data/chem/synthetic_dev.jsonl
done
python scripts/render_results.py && python scripts/build_research.py && python scripts/check_numbers.py
echo "[$(date -u +%H:%M:%S)] FINALIZE DONE"
