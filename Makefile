.PHONY: install lint test data check train-all eval-heuristic bench e2e site serve docker
PY=.venv/bin/python
install:
	uv venv --python 3.13 .venv && . .venv/bin/activate && uv pip install -e ".[dev]"
install-model:
	. .venv/bin/activate && uv pip install -e ".[model]"
lint:
	$(PY) -m ruff check src tests scripts
test:
	$(PY) -m pytest -q tests
data:
	$(PY) scripts/data/build_ko.py && $(PY) scripts/data/synth_ko.py && $(PY) scripts/data/build_chem.py && $(PY) scripts/data/synth_chem.py
check:
	$(PY) scripts/check_data.py && $(PY) scripts/check_numbers.py
train-all:
	bash scripts/train/run_pipeline.sh
eval-heuristic:
	$(PY) -m tabletrace.eval.run --planner heuristic --corpus data/ko/documents.jsonl --data data/ko/test.jsonl data/ko/synthetic_test.jsonl --out experiments/eval/heuristic_ko_test
	$(PY) -m tabletrace.eval.run --planner heuristic --corpus data/ko/documents.jsonl --data data/ko/custom_eval.jsonl --out experiments/eval/heuristic_ko_custom
	$(PY) -m tabletrace.eval.run --planner heuristic --corpus data/chem/documents.jsonl --data data/chem/custom_eval.jsonl --out experiments/eval/heuristic_chem_custom
results:
	$(PY) scripts/render_results.py && $(PY) scripts/build_research.py
e2e:
	$(PY) scripts/console_screenshots.py --out docs/images
site:
	$(PY) scripts/build_static_site.py --out _site
serve:
	$(PY) -m uvicorn tabletrace.service.app:app --port 8000
docker:
	docker build -t tabletrace:local .
