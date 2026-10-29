# 멀티 GPU Model Parallelism — 설계, CPU 기능 검증, GPU 실행 계획

## 데이터 병렬과 모델 병렬의 구분

- **DDP(데이터 병렬)**: GPU마다 모델 전체를 복제하고 배치를 나눈다. 이 프로젝트에서는 수행하지 않았고, 수행했다고 주장하지 않는다.
- **모델 병렬**: 한 모델을 여러 장치에 나눈다. 텐서 병렬(TP, 한 레이어의 행렬을 분할)과 파이프라인 병렬(PP, 레이어 묶음을 장치별로 배치)이 있다.

## 선택: 2-스테이지 파이프라인 병렬 (`src/tabletrace/bench/pipeline_parallel.py`)

mT5는 encoder-decoder라 **rank 0 = 인코더(+공유 임베딩), rank 1 = 디코더 + lm_head**로 자르는 경계가 자연스럽다. rank 0이 배치를 인코딩해 hidden state(B×L×512)를 rank 1에 보내고, rank 1이 greedy 디코딩 후 토큰 id를 돌려준다. `torch.distributed`의 `send/recv`를 사용하며 백엔드는 `gloo`(CPU) 또는 `nccl`(GPU).

TP가 아닌 PP를 고른 이유: (1) 300M 모델은 단일 GPU에 들어가므로 TP의 통신 비용이 이득보다 크고, (2) 인코더/디코더 경계가 뚜렷해 분할 정확성을 출력 동일성으로 검증하기 쉽다. 큰 causal LM(EXAONE 7.8B+)에는 vLLM의 TP(`--tensor-parallel-size 2`)를 쓰도록 `scripts/serving/vllm_tp2.sh`를 준비했다.

## 이 환경에서 실제로 한 것

GPU가 없으므로 **CPU 2프로세스(gloo)**로 같은 코드를 실행해 (a) 모델이 두 프로세스에 분할되어 각 프로세스가 일부 파라미터만 갖는지, (b) 통신이 동작하는지, (c) 단일 프로세스 결과와 생성 출력이 동일한지를 검증했다. 결과는 `experiments/bench/pp_single.json`, `pp_2stage.json`, docs/REPORT.md에 기록. **GPU 지연·처리량·메모리는 측정하지 못했다.**

## GPU 실행 명령 (미실행)

```bash
# 2 GPU, NCCL
torchrun --nproc_per_node=2 -m tabletrace.bench.pipeline_parallel --model experiments/sft_chem/model --backend nccl --n 256 --bs 16 --out experiments/bench/pp_2gpu.json
python -m tabletrace.bench.pipeline_parallel --model experiments/sft_chem/model --backend nccl --single --n 256 --bs 16 --out experiments/bench/pp_1gpu.json
# vLLM 텐서 병렬 (causal LM)
bash scripts/serving/vllm_tp2.sh
```

필요 자원·예상: GPU 2장(각 ≥8 GB면 mT5-small/EXAONE 2.4B 충분), 실행 수 분, 클라우드 비용 $1 미만(시간당 $1–3 GPU 2장 기준 10–20분). GPU별 메모리는 스크립트가 `torch.cuda.max_memory_allocated`로 기록한다.
