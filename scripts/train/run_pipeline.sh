#!/usr/bin/env bash
# Sequential experiment pipeline after stage-1 SFT. Each step logs to experiments/pipeline/*.log and the
# pipeline continues past failures (recorded in experiments/pipeline/status.txt) so partial results survive.
set -u
cd "$(dirname "$0")/../.."
source .venv/bin/activate
mkdir -p experiments/pipeline
STATUS=experiments/pipeline/status.txt
echo "[$(date -u +%H:%M:%S)] pipeline (re)started" >> "$STATUS"
run() { # name, done-marker-path, cmd...   (skips the step when the marker already exists -> restartable)
  local name=$1; shift
  local marker=$1; shift
  if [ -e "$marker" ]; then echo "[$(date -u +%H:%M:%S)] SKIP  $name (exists: $marker)" | tee -a "$STATUS"; return; fi
  echo "[$(date -u +%H:%M:%S)] START $name" | tee -a "$STATUS"
  if "$@" > "experiments/pipeline/$name.log" 2>&1; then echo "[$(date -u +%H:%M:%S)] OK    $name" | tee -a "$STATUS"; else echo "[$(date -u +%H:%M:%S)] FAIL  $name (exit $?)" | tee -a "$STATUS"; fi
}
KO_CORPUS="data/ko/documents.jsonl"
KO_TEST="data/ko/test.jsonl data/ko/synthetic_test.jsonl"
while [ ! -f experiments/sft_ko/summary.json ]; do sleep 60; done
echo "[$(date -u +%H:%M:%S)] stage-1 SFT finished" | tee -a "$STATUS"

run eval_base_ko_test experiments/eval/base_ko_test/metrics.json     python -m tabletrace.eval.run --planner neural --model models/mt5-small-base --corpus $KO_CORPUS --data $KO_TEST --out experiments/eval/base_ko_test --threads 4 --label "untuned mT5-small"
run eval_base_ko_custom experiments/eval/base_ko_custom/metrics.json   python -m tabletrace.eval.run --planner neural --model models/mt5-small-base --corpus $KO_CORPUS --data data/ko/custom_eval.jsonl --out experiments/eval/base_ko_custom --threads 4
run eval_base_chem_custom experiments/eval/base_chem_custom/metrics.json python -m tabletrace.eval.run --planner neural --model models/mt5-small-base --corpus data/chem/documents.jsonl --data data/chem/custom_eval.jsonl --out experiments/eval/base_chem_custom --threads 4

run eval_sft_ko_ko_test experiments/eval/sft_ko_ko_test/metrics.json   python -m tabletrace.eval.run --planner neural --model experiments/sft_ko/model --corpus $KO_CORPUS --data $KO_TEST --out experiments/eval/sft_ko_ko_test --threads 4
run eval_sft_ko_ko_custom experiments/eval/sft_ko_ko_custom/metrics.json python -m tabletrace.eval.run --planner neural --model experiments/sft_ko/model --corpus $KO_CORPUS --data data/ko/custom_eval.jsonl --out experiments/eval/sft_ko_ko_custom --threads 4

run sft_ko2 experiments/sft_ko2/summary.json python -m tabletrace.training.sft --model experiments/sft_ko/model --train data/ko/stage2_train.jsonl \
  --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl data/ko/text_dev.jsonl \
  --corpus $KO_CORPUS data/ko/text_documents_train.jsonl data/ko/text_documents_dev.jsonl \
  --out experiments/sft_ko2/model --epochs 1 --bs 8 --lr 1.5e-4 --threads 4
run eval_sft_ko2_ko_test experiments/eval/sft_ko2_ko_test/metrics.json     python -m tabletrace.eval.run --planner neural --model experiments/sft_ko2/model --corpus $KO_CORPUS --data $KO_TEST --out experiments/eval/sft_ko2_ko_test --threads 4
run eval_sft_ko2_ko_custom experiments/eval/sft_ko2_ko_custom/metrics.json   python -m tabletrace.eval.run --planner neural --model experiments/sft_ko2/model --corpus $KO_CORPUS --data data/ko/custom_eval.jsonl --out experiments/eval/sft_ko2_ko_custom --threads 4
run eval_sft_ko2_chem_custom experiments/eval/sft_ko2_chem_custom/metrics.json python -m tabletrace.eval.run --planner neural --model experiments/sft_ko2/model --corpus data/chem/documents.jsonl --data data/chem/custom_eval.jsonl --out experiments/eval/sft_ko2_chem_custom --threads 4

run sft_chem experiments/sft_chem/summary.json python -m tabletrace.training.sft --model experiments/sft_ko2/model --train data/chem/stage_train.jsonl --dev data/chem/synthetic_dev.jsonl \
  --corpus data/chem/documents.jsonl $KO_CORPUS --out experiments/sft_chem/model --epochs 2 --bs 8 --lr 1.5e-4 --threads 4
run eval_sft_chem_chem_custom experiments/eval/sft_chem_chem_custom/metrics.json python -m tabletrace.eval.run --planner neural --model experiments/sft_chem/model --corpus data/chem/documents.jsonl --data data/chem/custom_eval.jsonl --out experiments/eval/sft_chem_chem_custom --threads 4
run eval_sft_chem_chem_syndev experiments/eval/sft_chem_chem_syndev/metrics.json python -m tabletrace.eval.run --planner neural --model experiments/sft_chem/model --corpus data/chem/documents.jsonl --data data/chem/synthetic_dev.jsonl --out experiments/eval/sft_chem_chem_syndev --threads 4
run eval_sft_ko2_chem_syndev experiments/eval/sft_ko2_chem_syndev/metrics.json  python -m tabletrace.eval.run --planner neural --model experiments/sft_ko2/model --corpus data/chem/documents.jsonl --data data/chem/synthetic_dev.jsonl --out experiments/eval/sft_ko2_chem_syndev --threads 4
run eval_sft_chem_ko_test experiments/eval/sft_chem_ko_test/metrics.json     python -m tabletrace.eval.run --planner neural --model experiments/sft_chem/model --corpus $KO_CORPUS --data $KO_TEST --out experiments/eval/sft_chem_ko_test --threads 4
run eval_sft_chem_ko_custom experiments/eval/sft_chem_ko_custom/metrics.json   python -m tabletrace.eval.run --planner neural --model experiments/sft_chem/model --corpus $KO_CORPUS --data data/ko/custom_eval.jsonl --out experiments/eval/sft_chem_ko_custom --threads 4

run rl_ko experiments/rl_ko/summary.json python -m tabletrace.training.rl_grpo --model experiments/sft_ko2/model --train data/ko/train.jsonl data/ko/synthetic_train.jsonl \
  --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl --corpus $KO_CORPUS --out experiments/rl_ko/model --steps 60 --prompts-per-step 4 --group 4 --lr 1e-5 --beta 0.02 --threads 4
run eval_rl_ko_ko_test experiments/eval/rl_ko_ko_test/metrics.json   python -m tabletrace.eval.run --planner neural --model experiments/rl_ko/model --corpus $KO_CORPUS --data $KO_TEST --out experiments/eval/rl_ko_ko_test --threads 4
run eval_rl_ko_ko_custom experiments/eval/rl_ko_ko_custom/metrics.json python -m tabletrace.eval.run --planner neural --model experiments/rl_ko/model --corpus $KO_CORPUS --data data/ko/custom_eval.jsonl --out experiments/eval/rl_ko_ko_custom --threads 4

if [ ! -f models/mt5-small-tabletrace/model.safetensors ] && [ -f experiments/sft_chem/model/model.safetensors ]; then cp -r experiments/sft_chem/model models/mt5-small-tabletrace && echo "final model = sft_chem" | tee -a "$STATUS"; fi
run bench_inference experiments/bench/inference.json python -m tabletrace.bench.inference --model models/mt5-small-tabletrace --n 48 --out experiments/bench/inference.json --threads 4
run pp_single experiments/bench/pp_single.json python -m tabletrace.bench.pipeline_parallel --model models/mt5-small-tabletrace --single --n 16 --bs 8 --threads 2 --out experiments/bench/pp_single.json
run pp_2stage experiments/bench/pp_2stage.json torchrun --nproc_per_node=2 -m tabletrace.bench.pipeline_parallel --model models/mt5-small-tabletrace --backend gloo --n 16 --bs 8 --threads 2 --out experiments/bench/pp_2stage.json
run recorded_runs console/data/recorded/.neural_done bash -c 'python scripts/make_recorded_runs.py --planner neural --model models/mt5-small-tabletrace && touch console/data/recorded/.neural_done'
run research_json console/data/.research_done bash -c 'python scripts/build_research.py && touch console/data/.research_done'
run model_tests experiments/pipeline/.model_tests_done bash -c 'python -m pytest -q tests/test_model.py && touch experiments/pipeline/.model_tests_done'
run e2e_live docs/images/e2e-live-neural.json bash -c 'python scripts/console_screenshots.py --out docs/images --chromium /opt/pw-browsers/chromium-1243/chrome-linux64/chrome --planner auto && cp docs/images/e2e-live.json docs/images/e2e-live-neural.json'
run static_build experiments/pipeline/.static_build_done bash -c 'python scripts/build_static_site.py --out _site --commit local && touch experiments/pipeline/.static_build_done'
run e2e_static docs/images/e2e-static-neural.json bash -c 'python scripts/console_screenshots.py --out docs/images --static _site --chromium /opt/pw-browsers/chromium-1243/chrome-linux64/chrome && cp docs/images/e2e-static.json docs/images/e2e-static-neural.json'
echo "[$(date -u +%H:%M:%S)] PIPELINE DONE" | tee -a "$STATUS"
