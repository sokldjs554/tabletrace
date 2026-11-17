# EXAONE LoRA + vLLM / SGLang 결과의 출처

저장소 작성자(개발 컨테이너, GPU 없음)는 이 실행을 하지 못했다. 저장소 소유자가 2026-11-07 Kaggle(Tesla T4 ×2 세션)에서 `notebooks/gpu_experiments.ipynb`를 처음부터 세 번 돌리고 보낸 `gpu_results*.tgz`에서 **그대로 꺼낸 파일**이다. `analysis.json`은 작성자가 그 `predictions.jsonl`에 `scripts/analyze_predictions.py`를 돌려 만들었고, `paired_tests.json`의 `exaone_*` 항목도 같은 파일에서 나왔다.

노트북은 이 세션을 처음에 Colab으로 판단했다(Kaggle 이미지에도 `/content`가 있어서, 이슈 38). 실행 플랫폼은 Kaggle이다.

## 다섯 세션, 다섯 번의 LoRA 학습

| | 1차(`*_run1`) | 2차(`*_run2`) | 3차(접미사 없음, 표의 `LoRA 300개` 행) | 4차(`exaone_full_*`, `engine_full_*`, 표의 `전체` 행) |
|---|---|---|---|---|
| LoRA(`experiments/exaone_lora/train_info*.json`) | 300개, 18 step, `--dtype auto` → **bfloat16**(T4 에뮬레이션, 스크립트 결함) | 300개, 18 step, **float16**(스크립트 수정 후) | 300개, 18 step, float16 | **전체 3,587개**(3,654개 중 행 예산 밖 정답 67개 제외), 224 step, float16, 1,862.7초(T4), `experiments/exaone_lora_full/` |
| vLLM 1장 | `exaone_vllm_ko_test_run1`, `_ec_run1`, `bench/engine_vllm_c*_run1.json` (07:24) | `..._run2` (14:08) | `exaone_vllm_ko_test`, `_ec`, `bench/engine_vllm_c*.json` (17:26) | `exaone_full_vllm_ko_test`, `_ec`, `exaone_full_vllm_ko_custom`, `_ec`, `bench/engine_full_vllm_c*.json` (2026-11-08 06:36) |
| vLLM TP=2 | `exaone_vllm_tp2_ko_test_run1`, `bench/engine_vllm_tp2_c*_run1.json` (08:31) | `..._run2` (14:32) | `exaone_vllm_tp2_ko_test`, `bench/engine_vllm_tp2_c*.json` (17:44) | `exaone_full_vllm_tp2_ko_test`, `_ec`, `..._ko_custom`, `_ec`, `bench/engine_full_vllm_tp2_c*.json` (07:31) |
| mT5 파이프라인 | `bench/pp_*_gpu_run1.json` | `bench/pp_*_gpu_run2.json` | `bench/pp_*_gpu.json` | `bench/pp_*_gpu.json`(3차 파일은 `_run3`으로 이동) |
| SGLang | 서버 기동 실패(sm75 커널 없음) | 우회 모듈로 기동, config.json RoPE 키 누락으로 엉뚱한 답 → `experiments/serving/sglang_run3_rope_config/`(표에 넣지 않음) | 우회 모듈 + 설정 복원으로 **성공**: `exaone_sglang_ko_test`, `_ec`, `bench/engine_sglang_c*.json` (17:54) | 우회 모듈로 성공: `exaone_full_sglang_ko_test`, `_ec`, `..._ko_custom`, `_ec`, `bench/engine_full_sglang_c*.json` (07:16) |

- 1차의 `_ec`는 세 번 돌았다. 처음 두 번은 노트북의 재검증 명령이 `--tokenizer`·`--max-in 672`를 빼고 돌아 행 예산이 본 실행과 달랐고(verified EM 50.5%, 50.07%), 세 번째(두 인자 모두)가 `truncated_gold_rate` 3.43%로 본 실행과 같아 그 값을 남겼다. 2·3차의 `_ec`는 고친 노트북으로 바로 맞게 돌았다.
- 평가 클라이언트의 `hardware: x86_64`는 Kaggle CPU를 적은 것이다. 모델은 T4에서 돌았다.
- 서버: vLLM은 `scripts/serving/vllm_tp2.sh`, `DTYPE=half MAX_LEN=2048`(가상환경에 `uv pip install vllm`, 설치 버전은 로그에 남기지 않음). SGLang은 `sglang==0.5.9` + `scripts/serving/sglang_t4_shim.py`(fused 커널 대신 PyTorch 구현) + `--attention-backend triton --sampling-backend pytorch`, 평가는 동시 8요청(vLLM은 16).
- 4차 세션의 `experiments/exaone_lora_full/run_info.json`이 플랫폼(kaggle, T4 ×2)과 설정(LIMIT=0)을 기록한다. 수작업 30문항은 4·5차에서 평가했다.
- **5차 세션(2026-11-08 09:14~09:45, Colab 무료 Tesla T4 1장)**: Ampere GPU 비교를 하려던 세션인데 런타임이 T4였다. 같은 설정의 전체 데이터 학습을 한 번 더 한 것이 되어 `exaone_full_*_run2`, `engine_full_*_run2.json`, `experiments/exaone_lora_full/train_info_run2.json`(1,810초)·`run_info_run2.json`으로 보관했다. TP=2와 파이프라인은 GPU 1장이라 없음.
- 1~3차의 vLLM 결과는 같은 설정의 독립 학습이므로 LoRA 학습 잡음의 크기를 보여 준다(`paired_tests.json: exaone_vllm_run2_vs_run1_*`, `exaone_vllm_run3_vs_run2_ko_test`). 3차의 vLLM 대 SGLang은 같은 모델의 엔진 간 차이다(`exaone_sglang_vs_vllm_*`).
- **6차 세션(2026-11-10 13:4x, Kaggle Tesla T4 ×2)**: 표 입력 형식 실험. 노트북 1번 절에서 `LIMIT = 300`, `TABLE_FORMAT = "colid"`로 두고 0·1·2·5번 절을 실행했다(`experiments/exaone_lora_colid/run_info.json`: limit 300, tag `_colid`). 학습은 같은 300개·18 step, `--max-len 896 --table-format colid`, 182.9초(`experiments/exaone_lora_colid/train_info.json`). 평가는 vLLM 1장, `--max-in 800 --table-format colid`: `exaone_colid_vllm_ko_test`, `_ec`, `exaone_colid_vllm_ko_custom`, `_ec`, `bench/engine_colid_vllm_c*.json`. 올라온 압축 파일(`gpu_results_7.tgz`)에는 저장소를 클론하면서 딸려 온 기존 결과 133개도 들어 있었고, 저장소의 파일과 해시가 모두 같아 `_colid` 파일만 넣었다. SGLang과 TP=2는 이 세션에서 돌리지 않았다.

- **2번 노트북, 2026-11-14 (Kaggle Tesla T4 ×2)**: A~H절. 결과 파일은 세션과 함께 사라졌다. 평가 60건의 지표는 노트북에 남은 출력에서 복원했고 문항별 예측은 없다(`experiments/gpu2_2026-11-14/`, `docs/REPORT.md` §21). 이 폴더(`experiments/eval/`)에는 그 실행의 파일이 없다.
- **2번 노트북, 2026-11-15 (Kaggle Tesla T4 ×2, 커밋 `aaec049`, `experiments/run_info_2.json`)**: A절(튜닝 없는 1.2B, 7.8B AWQ), A2절(1.2B 도구 호출), D절(강화학습 두 번째 실험). 결과 묶음 `gpu_results_2.tgz`를 소유자가 건넸다. 평가 22건: `ref_1p2b_ko_{test,custom}`, `ref_7p8b_awq_ko_{test,custom}`, `tools_1p2b_ko_{test,custom}`, `tools_1p2b_unseen_dev500`, `exaone_rlstart2_vllm_ko_{test,custom}`, `exaone_grpo2_vllm_ko_{test,custom}`와 각각의 `_ec`. 학습 기록은 `experiments/exaone_lora_rlstart2/train_info.json`(300문항, 18걸음, 정답 잘림 0), `experiments/exaone_grpo2/train_info.json`과 `train_log.jsonl`(200걸음, 남긴 모델은 150걸음째). 서버 로그의 끝부분은 `experiments/run_logs/`.
  - 묶음 안의 이름 `ref_1.2b_*`, `ref_7.8b_awq_*`, `tools_1.2b_*`는 넣으면서 `1p2b`, `7p8b`로 바꿨다(문서의 수치 묶기가 점을 경로 구분자로 쓴다). 파일 내용은 손대지 않았다. `_ec`의 `meta.replay_from`에는 원래 이름이 남아 있다.
  - 받은 뒤 `scripts/replay_check.py`로 저장된 모델 출력을 이 저장소의 검증기로 다시 검증했다. 22회, 8,290문항에서 판정(상태, 답, 근거 셀, 정오, 근거 복구)이 다른 문항은 0개다(`replay_check_gpu3.json`). 토크나이저는 EXAONE-4.0-1.2B, 입력 예산 672.
  - 서버: vLLM, 1.2B는 `DTYPE=half`, 7.8B AWQ는 `auto`. 튜닝 없는 모델의 평가는 동시 8건, 도구 호출은 4건. 강화학습 모델과 시작 모델은 병합 가중치를 vLLM으로 올려 동시 16건으로 평가했다(노트북의 기본값).
  - 이 실행에는 대조군(`exaone_grpo2b`)과 32B가 없다. 둘 다 노트북에서 선택 실행이고 꺼져 있었다. 대조군은 아래 세션에서 돌렸다.
- **2번 노트북, 2026-11-15 뒤의 세션 (Kaggle Tesla T4 ×2, 커밋 `f3ce40e`, `experiments/run_info_2_control.json`)**: 강화학습 대조군. D절 첫 셀의 `RUN_CONTROL = True`. 결과 묶음을 소유자가 건넸다. 묶음에는 저장소에서 받아 온 앞 세션의 결과도 그대로 들어 있었다(52개 파일, 저장소의 것과 바이트까지 같음). 새 파일은 평가 8건 `exaone_rlstart2b_vllm_ko_{test,custom}`, `exaone_grpo2b_vllm_ko_{test,custom}`와 각각의 `_ec`, 학습 기록 `experiments/exaone_lora_rlstart2b/train_info.json`(300문항, 18걸음, 정답 잘림 0), `experiments/exaone_grpo2b/train_info.json`과 `train_log.jsonl`(200걸음, 120걸음 갱신, 남긴 모델은 25걸음째)이다.
  - 새 세션에는 앞 세션의 시작 모델 가중치가 없다. 노트북이 시작 모델을 같은 설정으로 다시 학습해 `exaone_rlstart2b`라는 이름으로 따로 평가했고, 대조군은 그 모델에서 시작했다(`train_info.json`의 `args.adapter`). 두 학습 명령에서 다른 것은 `--sampling`과 `--adapter`, `--out`뿐이다.
  - 묶음의 `experiments/run_info_2.json`은 `run_info_2_control.json`으로, `run_logs/vllm_8001.log`는 `vllm_8001_control.log`로 이름을 바꿔 넣었다(앞 세션의 같은 이름 파일을 덮어쓰지 않으려고). 내용은 그대로다.
  - `scripts/replay_check.py --session control`로 다시 검증했다. 8회, 2,916문항에서 판정이 다른 문항은 0개다(`replay_check_control.json`).
  - 같은 시작 모델에서 본 실험을 한 번 더 돌리는 선택(`RUN_REPEAT`, `exaone_grpo2c`)은 꺼져 있었다. 아래 세션에서 돌렸다.
- **2번 노트북, 2026-11-15 그다음 세션 (Kaggle Tesla T4 ×2, 커밋 `401da7e`, `experiments/run_info_2_repeat.json`)**: 본 실험의 반복. D절 첫 셀의 `RUN_REPEAT = True`. 소유자가 묶음 두 개를 건넸다. 첫 묶음(16:38)은 D절 첫 셀 뒤의 것으로 새 파일이 없다. 대조군 세션의 작업 폴더가 Kaggle에 남아 있었고, 노트북이 그 시작 모델(`exaone_rlstart2b`)의 가중치를 찾아 시작 모델 학습과 평가를 건너뛰었다. 둘째 묶음(18:07)의 새 파일은 평가 4건 `exaone_grpo2c_vllm_ko_{test,custom}`와 각각의 `_ec`, 학습 기록 `experiments/exaone_grpo2c/train_info.json`과 `train_log.jsonl`(200걸음, 192걸음 갱신, 남긴 모델은 200걸음째)이다. 나머지 72개 파일은 저장소의 것과 바이트까지 같다.
  - 반복 실행과 대조군은 같은 가중치에서 시작했다. 두 학습 명령에서 다른 것은 `--sampling`과 `--out`뿐이다. 개발셋의 0걸음 점검이 대조군과 숫자까지 같다. 본 실험 1회째와 다른 것은 `--adapter`와 `--out`이다.
  - 묶음의 `run_info_2.json`은 `run_info_2_repeat.json`으로, `run_logs/vllm_8001.log`는 `vllm_8001_repeat.log`로 이름을 바꿔 넣었다. 내용은 그대로다.
  - `scripts/replay_check.py --session repeat`로 다시 검증했다. 4회, 1,458문항에서 판정이 다른 문항은 0개다(`replay_check_repeat.json`).
- **2번 노트북, 2026-11-16 (Kaggle Tesla T4 ×2, 커밋 `30eef7d`, `experiments/run_info_2_full2.json`)**: I절. 길이 결함을 고친 설정의 전체 데이터 미세조정과, 같은 세션에서 예전 설정으로 한 번 더. 새 파일은 평가 8건 `exaone_full2_vllm_ko_{test,custom}`, `exaone_full2old_vllm_ko_{test,custom}`와 각각의 `_ec`, 학습 기록 `experiments/exaone_lora_full2/train_info.json`(`--max-in 672 --max-len 960`, 정답이 잘린 예제 0)과 `experiments/exaone_lora_full2old/train_info.json`(`--max-len 768`, 정답이 통째로 잘린 예제 385, 일부 잘린 예제 153)이다. 둘 다 3,587문항, 224걸음. 나머지 83개 파일은 저장소의 것과 바이트까지 같다.
  - 두 학습 명령에서 다른 것은 `--max-in`, `--max-len`, `--out`뿐이다. 예전 설정은 1번 노트북의 전체 데이터 학습(`exaone_lora_full`, `exaone_full_*`)과 같은 설정이다. 그 결과들은 이름을 그대로 두었다.
  - 묶음의 `run_info_2.json`은 `run_info_2_full2.json`으로, `run_logs/vllm_8001.log`는 `vllm_8001_full2.log`로 이름을 바꿔 넣었다. 내용은 그대로다.
  - `scripts/replay_check.py --session full2`로 다시 검증했다. 8회, 2,916문항에서 판정이 다른 문항은 0개다(`replay_check_full2.json`).
  - 문항 길이별 분석은 `scripts/prompt_lengths.py`(EXAONE 토크나이저로 센 길이를 `ko_test_prompt_lengths.json`에 저장)와 `scripts/length_fix_analysis.py`(`length_fix_analysis.json`)가 한다.
- **2번 노트북, 2026-11-16 (Kaggle Tesla T4 ×2, 커밋 `f2402be`, `experiments/run_info_2_rl3.json`)**: J절. 전체 데이터 모델에서 시작한 강화학습. 새 파일은 평가 8건 `exaone_full3_vllm_ko_{test,custom}`, `exaone_grpo3_vllm_ko_{test,custom}`와 각각의 `_ec`, 시작 모델의 학습 기록 `experiments/exaone_lora_full3/train_info.json`(`--max-in 672 --max-len 960`, 3,587문항, 224걸음, 정답이 잘린 예제 0), 강화학습의 기록 `experiments/exaone_grpo3/train_info.json`과 `train_log.jsonl`(200걸음, 갱신 127회, 75걸음째를 저장)이다. 나머지 102개 파일은 저장소의 것과 같았다.
  - 그 세션에는 `exaone_full2`의 가중치가 없었다. 노트북이 같은 설정으로 다시 학습해 `exaone_full3`으로 따로 평가하고 거기서 강화학습을 시작했다. 강화학습 전후의 비교는 모두 `exaone_full3`과의 비교다.
  - 강화학습의 학습 명령에서 두 번째 실험(`exaone_grpo2`)과 다른 것은 `--adapter`와 `--out`뿐이다.
  - 결과 묶음은 두 길로 왔다. 노트북이 GitHub의 `gpu-results-2` 가지에 올렸고(시작 모델의 평가까지 담은 중간 저장이 먼저 올라왔고, 끝난 뒤 커밋 `cf62543`으로 바뀌었다), 소유자가 같은 파일을 대화에 올렸다. 두 파일의 SHA-256이 같다(`f956e95f…`). 결과 가지에서 묶음을 받아 대조한 것은 이번이 처음이다.
  - 묶음의 `run_info_2.json`은 `run_info_2_rl3.json`으로, `run_logs/vllm_8001.log`는 `vllm_8001_rl3.log`로 이름을 바꿔 넣었다. 내용은 그대로다.
  - `scripts/replay_check.py --session rl3`으로 다시 검증했다. 8회, 2,916문항에서 판정이 다른 문항은 0개다(`replay_check_rl3.json`).
  - 문항 단위 분석과 확신도 비교는 `scripts/rl3_analysis.py`가 한다(`rl3_analysis.json`).
- **2번 노트북, 2026-11-16 (Kaggle Tesla T4 ×2, 커밋 `79a6ce6`, `experiments/run_info_2_owner.json`)**: L절. 소유자가 쓴 평가 30문항(`data/ko/owner_eval.jsonl`)으로 EXAONE을 평가했다. 새 파일은 평가 10건 `exaone_full4_vllm_ko_{test,custom,owner}`, `ref_1p2b_ko_owner`, `ref_7p8b_awq_ko_owner`와 각각의 `_ec`, 학습 기록 `experiments/exaone_lora_full4/train_info.json`(`--max-in 672 --max-len 960`, 3,587문항, 224걸음, 정답이 잘린 예제 0), 서버 로그 두 개(`run_logs/vllm_ref_1p2b_owner.log`, `vllm_ref_7p8b_awq_owner.log`)다. 나머지 122개 파일은 저장소의 것과 같았다.
  - 그 세션에는 전체 데이터 모델의 병합 가중치가 없었다. 노트북이 고친 설정으로 다시 학습해 `exaone_full4`로 평가했다(여섯 번째 전체 데이터 학습).
  - 튜닝하지 않은 두 모델은 A절과 같은 설정이다(`--few-shot data/ko/train.jsonl data/ko/synthetic_train.jsonl --shots-per-kind 2`). 같은 이름의 지난 평가(`ref_1p2b_ko_{test,custom}`, `ref_7p8b_awq_ko_{test,custom}`, 2026-11-15)는 다른 세션의 것이고 그대로 두었다.
  - 묶음은 두 길로 왔다. 소유자가 대화에 올렸고, 노트북이 `gpu-results-2` 가지에도 올렸다(커밋 `d601f63`). 두 파일의 SHA-256이 같다(`ca8356e4…`).
  - 묶음의 `run_info_2.json`은 `run_info_2_owner.json`으로, `run_logs/vllm_8001.log`는 `vllm_8001_owner.log`로 이름을 바꿔 넣었다. 내용은 그대로다.
  - `scripts/replay_check.py --session owner`로 다시 검증했다. 10회, 1,638문항에서 판정이 다른 문항은 0개다(`replay_check_owner.json`).
  - 분석은 `scripts/owner_eval_analysis.py`가 한다(`owner_eval_analysis.json`의 `gpu_planners`).
- **2번 노트북, 2026-11-16 (Colab Tesla T4 ×1, 커밋 `7618400`, `experiments/run_info_2_ownloop.json`)**: M절. 소유자가 직접 쓴 학습 루프(`src/tabletrace/training/lm_loop.py`, `--loop owner`)로 한 전체 데이터 미세조정. 새 파일은 평가 6건 `exaone_ownloop_vllm_ko_{test,custom,owner}`와 각각의 `_ec`, 학습 기록 `experiments/exaone_lora_ownloop/train_info.json`(`"loop": "tabletrace.training.lm_loop (owner-written)"`, 3,587문항, 224걸음, 정답이 잘린 예제 0)이다. 나머지 146개 파일은 저장소의 것과 같았다.
  - 학습 명령에서 `exaone_full4`와 다른 것은 `--loop`와 `--out`뿐이다. 두 루프는 같은 절차가 아니다. 소유자의 루프는 학습률을 선형으로 줄이고(학습 기록에 걸음마다의 학습률이 있다) 들어 있는 루프는 일정하게 둔다.
  - Kaggle의 주간 GPU 할당량이 다 차서 Colab에서 돌렸다. 2번 노트북의 첫 Colab 실행이다. GPU는 한 장이다.
  - 묶음은 두 길로 왔다. 소유자가 대화에 올렸고, 노트북이 `gpu-results-2` 가지에도 올렸다(커밋 `f213fed`). 두 파일의 SHA-256이 같다(`3bbd9c62…`).
  - 묶음의 `run_info_2.json`은 `run_info_2_ownloop.json`으로, `run_logs/vllm_8001.log`는 `vllm_8001_ownloop.log`로 이름을 바꿔 넣었다. 내용은 그대로다.
  - `scripts/replay_check.py --session ownloop`으로 다시 검증했다. 6회, 1,518문항에서 판정이 다른 문항은 0개다(`replay_check_ownloop.json`).
  - 분석은 `scripts/owner_loop_analysis.py`가 한다(`owner_loop_analysis.json`).
- **2번 노트북, 2026-11-17 (Colab Tesla T4 ×1, 커밋 `d7d8ec0`, `experiments/run_info_2_chem.json`)**: N절. 화학 문항에서의 EXAONE, 문항별 예측을 남기는 재실행. 새 파일은 평가 18건(`exaone_kochem2_vllm_{chem_custom,chem_syndev,chem_papers,ko_test,ko_custom,ko_owner}`, `ref_1p2b_{chem_custom,chem_syndev,chem_papers}`와 각각의 `_ec`), 학습 기록 `experiments/exaone_lora_kochem2/train_info.json`(`"loop": "builtin"`, 4,383문항, 273걸음, 정답이 잘린 예제 0), 서버 로그 둘이다. 묶음의 나머지 160개 파일은 저장소의 것과 같았다.
  - 학습 명령에서 `exaone_full4`와 다른 것은 `--train`, `--corpus`, `--out`뿐이다. 화학 합성 학습 문항 820개 가운데 정답 행이 입력 길이에 들어가지 않는 24개는 학습 스크립트가 뺐다.
  - 서버: vLLM. 튜닝한 모델은 병합 가중치를 올려 동시 16건, 튜닝하지 않은 1.2B는 동시 8건으로 평가했다(노트북의 값). 논문 표 평가는 `--row-select overlap`이다. 튜닝하지 않은 모델의 예시 6개는 `data/chem/synthetic_train.jsonl`에서 골랐다(`--shots-per-kind 2`).
  - 묶음은 소유자가 대화에 올렸다(`gpu_results_2_13.tgz`, 3,193,040바이트, SHA-256 `ac26c31f…`). 묶음 안의 코드는 실행하지 않았고, 결과 파일만 꺼내 넣었다.
  - 묶음의 `run_info_2.json`은 `run_info_2_chem.json`으로, `run_logs/vllm_8001.log`는 `vllm_8001_chem.log`로 이름을 바꿔 넣었다. 내용은 그대로다.
  - `scripts/replay_check.py --session chem`으로 다시 검증했다. 18회, 2,214문항에서 판정이 다른 문항은 0개다(`replay_check_chem.json`).
  - 분석은 `scripts/chem_rerun_analysis.py`가 한다(`chem_rerun_analysis.json`). 2026-11-14의 같은 실험(G절)은 수치만 남아 있어 나란히 놓을 수만 있다.
