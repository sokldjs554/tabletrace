#!/usr/bin/env bash
# Everything after the evaluations: stored runs for the static demo, research.json, README/REPORT tables, E2E, number checks.
set -u
cd "$(dirname "$0")/../.."
source .venv/bin/activate
CHROMIUM=${TT_CHROMIUM:-/opt/pw-browsers/chromium-1243/chrome-linux64/chrome}
MODEL_FINAL=models/mt5-small-tabletrace
if [ -f "$MODEL_FINAL/model.safetensors" ]; then
  python scripts/make_recorded_runs.py --planners neural heuristic --model "$MODEL_FINAL" > experiments/pipeline/final_recorded.log 2>&1
else
  python scripts/make_recorded_runs.py --planners heuristic > experiments/pipeline/final_recorded.log 2>&1
fi
echo "[$(date -u +%H:%M:%S)] recorded runs: $(tail -1 experiments/pipeline/final_recorded.log)"
python scripts/build_research.py > /dev/null || { echo "[$(date -u +%H:%M:%S)] FAILED: build_research.py"; exit 1; }
python scripts/render_results.py || { echo "[$(date -u +%H:%M:%S)] FAILED: render_results.py"; exit 1; }
python scripts/build_static_site.py --out _site --commit "$(git rev-parse --short HEAD)" > /dev/null
python scripts/console_screenshots.py --out docs/images --chromium "$CHROMIUM" --planner auto > experiments/pipeline/final_e2e_live.log 2>&1
echo "[$(date -u +%H:%M:%S)] e2e live: $(tail -1 experiments/pipeline/final_e2e_live.log)"
python scripts/console_screenshots.py --out docs/images --static _site --chromium "$CHROMIUM" > experiments/pipeline/final_e2e_static.log 2>&1
echo "[$(date -u +%H:%M:%S)] e2e static: $(tail -1 experiments/pipeline/final_e2e_static.log)"
rm -rf _site
python scripts/check_numbers.py
echo "[$(date -u +%H:%M:%S)] FINALIZE DONE"
