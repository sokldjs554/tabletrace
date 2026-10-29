# 학습·평가 재현 명령

모든 명령은 저장소 루트에서, `.venv`(`pip install -e ".[model,dev]"`)를 활성화한 뒤 실행한다. 기본 모델은 `models/mt5-small-base`(GCS mT5-small을 변환, `scripts/model/`).

```bash
# 0) 데이터
python scripts/data/build_ko.py && python scripts/data/synth_ko.py && python scripts/data/build_korquad_text.py
python scripts/data/build_chem.py && python scripts/data/synth_chem.py && python scripts/check_data.py

# 1) 한국어 표 QA SFT (stage 1: lookup + 합성 계산/보류)
python -m tabletrace.training.sft --model models/mt5-small-base \
  --train data/ko/train.jsonl data/ko/synthetic_train.jsonl --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl \
  --corpus data/ko/documents.jsonl --out experiments/sft_ko/model --epochs 2 --bs 8 --lr 3e-4 --threads 4

# 2) stage 2: 본문 답변(op: text) 추가, 표 데이터 일부 재생
python scripts/data/mix.py data/ko/stage2_train.jsonl data/ko/train.jsonl:600 data/ko/synthetic_train.jsonl:300 data/ko/text_train.jsonl:700
python -m tabletrace.training.sft --model experiments/sft_ko/model \
  --train data/ko/stage2_train.jsonl --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl data/ko/text_dev.jsonl \
  --corpus data/ko/documents.jsonl data/ko/text_documents_train.jsonl data/ko/text_documents_dev.jsonl \
  --out experiments/sft_ko2/model --epochs 1 --bs 8 --lr 1.5e-4

# 3) 영어 화학 문서 SFT (stage 2 모델에서 계속)
python scripts/data/mix.py data/chem/stage_train.jsonl data/chem/synthetic_train.jsonl:820 data/ko/train.jsonl:150
python -m tabletrace.training.sft --model experiments/sft_ko2/model \
  --train data/chem/stage_train.jsonl --dev data/chem/synthetic_dev.jsonl \
  --corpus data/chem/documents.jsonl data/ko/documents.jsonl --out experiments/sft_chem/model --epochs 2 --bs 8 --lr 1.5e-4

# 4) 강화학습(GRPO 방식) — 한국어, stage 2 모델에서
python -m tabletrace.training.rl_grpo --model experiments/sft_ko2/model \
  --train data/ko/train.jsonl data/ko/synthetic_train.jsonl --dev data/ko/dev.jsonl data/ko/synthetic_dev.jsonl \
  --corpus data/ko/documents.jsonl --out experiments/rl_ko/model --steps 60 --prompts-per-step 4 --group 4 --lr 1e-5 --beta 0.02

# 5) 평가 (동일 독립 평가셋)
for M in models/mt5-small-base experiments/sft_ko/model experiments/sft_ko2/model experiments/rl_ko/model; do
  python -m tabletrace.eval.run --planner neural --model $M --corpus data/ko/documents.jsonl \
     --data data/ko/test.jsonl data/ko/synthetic_test.jsonl --out experiments/eval/$(basename $(dirname $M))_ko_test
  python -m tabletrace.eval.run --planner neural --model $M --corpus data/ko/documents.jsonl \
     --data data/ko/custom_eval.jsonl --out experiments/eval/$(basename $(dirname $M))_ko_custom
done
python -m tabletrace.eval.run --planner heuristic --corpus data/ko/documents.jsonl --data data/ko/test.jsonl data/ko/synthetic_test.jsonl --out experiments/eval/heuristic_ko_test

# 6) 추론 최적화 측정, 파이프라인 병렬(CPU 2프로세스 기능 검증)
python -m tabletrace.bench.inference --model experiments/sft_chem/model --n 48 --out experiments/bench/inference.json
python -m tabletrace.bench.pipeline_parallel --model experiments/sft_chem/model --single --n 16 --out experiments/bench/pp_single.json
torchrun --nproc_per_node=2 -m tabletrace.bench.pipeline_parallel --model experiments/sft_chem/model --backend gloo --n 16 --out experiments/bench/pp_2stage.json
```
