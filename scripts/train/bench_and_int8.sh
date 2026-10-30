#!/usr/bin/env bash
# Inference benchmark (fp32 vs int8, one process per precision) + accuracy of the int8 model on the same eval sets.
# Run on an otherwise idle machine: latency numbers are only meaningful without competing CPU load.
set -u
cd "$(dirname "$0")/../.." && source .venv/bin/activate
rm -f experiments/bench/inference.json
python -m tabletrace.bench.inference --model models/mt5-small-tabletrace --n 48 --out experiments/bench/inference.json > experiments/pipeline/bench2.log 2>&1
echo "bench done $(date -u +%H:%M:%S) exit-file=$(ls experiments/bench/inference.json 2>&1)" > experiments/pipeline/post_bench.status
KO="data/ko/documents.jsonl"
python -m tabletrace.eval.run --planner neural --quantize --model experiments/sft_chem/model --corpus $KO --data data/ko/test.jsonl data/ko/synthetic_test.jsonl --out experiments/eval/sft_chem_int8_ko_test --threads 4 > experiments/pipeline/int8_ko_test.log 2>&1
python -m tabletrace.eval.run --planner neural --quantize --model experiments/sft_chem/model --corpus $KO --data data/ko/custom_eval.jsonl --out experiments/eval/sft_chem_int8_ko_custom --threads 4 > experiments/pipeline/int8_ko_custom.log 2>&1
python -m tabletrace.eval.run --planner neural --quantize --model experiments/sft_chem/model --corpus data/chem/documents.jsonl --data data/chem/custom_eval.jsonl --out experiments/eval/sft_chem_int8_chem_custom --threads 4 > experiments/pipeline/int8_chem_custom.log 2>&1
for k in sft_chem_int8_ko_test sft_chem_int8_ko_custom sft_chem_int8_chem_custom; do python scripts/analyze_predictions.py experiments/eval/$k > /dev/null 2>&1; done
echo "int8 evals done $(date -u +%H:%M:%S)" >> experiments/pipeline/post_bench.status
