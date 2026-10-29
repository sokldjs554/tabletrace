#!/usr/bin/env bash
# Sequential experiment pipeline after stage-1 SFT. Each step logs to experiments/pipeline/*.log and the
# pipeline continues past failures (recorded in experiments/pipeline/status.txt) so partial results survive.
set -u
cd "$(dirname "$0")/../.."
source .venv/bin/activate
mkdir -p experiments/pipeline
STATUS=experiments/pipeline/status.txt
: > "$STATUS"
run() { # name, cmd...
  local name=$1; shift
  echo "[$(date -u +%H:%M:%S)] START $name" | tee -a "$STATUS"
  if "$@" > "experiments/pipeline/$name.log" 2>&1; then echo "[$(date -u +%H:%M:%S)] OK    $name" | tee -a "$STATUS"; else echo "[$(date -u +%H:%M:%S)] FAIL  $name (exit $?)" | tee -a "$STATUS"; fi
}
KO_CORPUS="data/ko/documents.jsonl"
KO_TEST="data/ko/test.jsonl data/ko/synthetic_test.jsonl"
while [ ! -f experiments/sft_ko/summary.json ]; do sleep 60; done
echo "[$(date -u +%H:%M:%S)] stage-1 SFT finished" | tee -a "$STATUS"

run eval_base_ko_test     python -m tabletrace.eval.run --planner neural --model models/mt5-small-base --corpus $KO_CORPUS --data $KO_TEST --out experiments/eval/base_ko_test --threads 4 --label "untuned mT5-small"
run eval_base_ko_custom   python -m tabletrace.eval.run --planner neural --model models/mt5-small-base --corpus $KO_CORPUS --data data/ko/custom_eval.jsonl --out experiments/eval/base_ko_custom --threads 4
run eval_base_chem_custom python -m tabletrace.eval.run --planner neural --model models/mt5-small-base --corpus data/chem/documents.jsonl --data data/chem/custom_eval.jsonl --out experiments/eval/base_chem_custom --threads 4

run eval_sft_ko_ko_test   python -m tabletrace.eval.run --planner neural --model experiments/sft_ko/model --corpus $KO_CORPUS --data $KO_TEST --out experiments/eval/sft_ko_ko_test --threads 4
run eval_sft_ko_ko_custom python -m tabletrace.eval.run --planner neural --model experiments/sft_ko/model --corpus $KO_CORPUS --data data/ko/custom_eval.jsonl --out experiments/eval/sft_ko_ko_custom --threads 4

run sft_ko2 python -m tabletrace.training.sft --model experiments/sft_ko/model --train data/ko/stage2_train.jsonl \
  --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl data/ko/text_dev.jsonl \
  --corpus $KO_CORPUS data/ko/text_documents_train.jsonl data/ko/text_documents_dev.jsonl \
  --out experiments/sft_ko2/model --epochs 1 --bs 8 --lr 1.5e-4 --threads 4
run eval_sft_ko2_ko_test     python -m tabletrace.eval.run --planner neural --model experiments/sft_ko2/model --corpus $KO_CORPUS --data $KO_TEST --out experiments/eval/sft_ko2_ko_test --threads 4
run eval_sft_ko2_ko_custom   python -m tabletrace.eval.run --planner neural --model experiments/sft_ko2/model --corpus $KO_CORPUS --data data/ko/custom_eval.jsonl --out experiments/eval/sft_ko2_ko_custom --threads 4
run eval_sft_ko2_chem_custom python -m tabletrace.eval.run --planner neural --model experiments/sft_ko2/model --corpus data/chem/documents.jsonl --data data/chem/custom_eval.jsonl --out experiments/eval/sft_ko2_chem_custom --threads 4

run sft_chem python -m tabletrace.training.sft --model experiments/sft_ko2/model --train data/chem/stage_train.jsonl --dev data/chem/synthetic_dev.jsonl \
  --corpus data/chem/documents.jsonl $KO_CORPUS --out experiments/sft_chem/model --epochs 2 --bs 8 --lr 1.5e-4 --threads 4
run eval_sft_chem_chem_custom python -m tabletrace.eval.run --planner neural --model experiments/sft_chem/model --corpus data/chem/documents.jsonl --data data/chem/custom_eval.jsonl --out experiments/eval/sft_chem_chem_custom --threads 4
run eval_sft_chem_chem_syndev python -m tabletrace.eval.run --planner neural --model experiments/sft_chem/model --corpus data/chem/documents.jsonl --data data/chem/synthetic_dev.jsonl --out experiments/eval/sft_chem_chem_syndev --threads 4
run eval_sft_ko2_chem_syndev  python -m tabletrace.eval.run --planner neural --model experiments/sft_ko2/model --corpus data/chem/documents.jsonl --data data/chem/synthetic_dev.jsonl --out experiments/eval/sft_ko2_chem_syndev --threads 4
run eval_sft_chem_ko_test     python -m tabletrace.eval.run --planner neural --model experiments/sft_chem/model --corpus $KO_CORPUS --data $KO_TEST --out experiments/eval/sft_chem_ko_test --threads 4
run eval_sft_chem_ko_custom   python -m tabletrace.eval.run --planner neural --model experiments/sft_chem/model --corpus $KO_CORPUS --data data/ko/custom_eval.jsonl --out experiments/eval/sft_chem_ko_custom --threads 4

run rl_ko python -m tabletrace.training.rl_grpo --model experiments/sft_ko2/model --train data/ko/train.jsonl data/ko/synthetic_train.jsonl \
  --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl --corpus $KO_CORPUS --out experiments/rl_ko/model --steps 60 --prompts-per-step 4 --group 4 --lr 1e-5 --beta 0.02 --threads 4
run eval_rl_ko_ko_test   python -m tabletrace.eval.run --planner neural --model experiments/rl_ko/model --corpus $KO_CORPUS --data $KO_TEST --out experiments/eval/rl_ko_ko_test --threads 4
run eval_rl_ko_ko_custom python -m tabletrace.eval.run --planner neural --model experiments/rl_ko/model --corpus $KO_CORPUS --data data/ko/custom_eval.jsonl --out experiments/eval/rl_ko_ko_custom --threads 4

rm -rf models/mt5-small-tabletrace && cp -r experiments/sft_chem/model models/mt5-small-tabletrace && echo "final model = sft_chem" | tee -a "$STATUS"
run bench_inference python -m tabletrace.bench.inference --model models/mt5-small-tabletrace --n 48 --out experiments/bench/inference.json --threads 4
run pp_single python -m tabletrace.bench.pipeline_parallel --model models/mt5-small-tabletrace --single --n 16 --bs 8 --threads 2 --out experiments/bench/pp_single.json
run pp_2stage torchrun --nproc_per_node=2 -m tabletrace.bench.pipeline_parallel --model models/mt5-small-tabletrace --backend gloo --n 16 --bs 8 --threads 2 --out experiments/bench/pp_2stage.json
run recorded_runs python scripts/make_recorded_runs.py --planner neural --model models/mt5-small-tabletrace
run research_json python scripts/build_research.py
run model_tests python -m pytest -q tests/test_model.py
run e2e_live python scripts/console_screenshots.py --out docs/images --chromium /opt/pw-browsers/chromium-1243/chrome-linux64/chrome --planner auto
run static_build python scripts/build_static_site.py --out _site --commit local
run e2e_static python scripts/console_screenshots.py --out docs/images --static _site --chromium /opt/pw-browsers/chromium-1243/chrome-linux64/chrome
echo "[$(date -u +%H:%M:%S)] PIPELINE DONE" | tee -a "$STATUS"
