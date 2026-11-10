# TableTrace 최종 보고서

작성 기준: 이 저장소의 커밋과 `experiments/` 산출물. 본문의 수치는 산출물 JSON을 가리키는 `<!-- num:… -->` 표식으로 묶여 있고 `scripts/check_numbers.py --strict`가 값을 대조한다. 결과 표는 `scripts/render_results.py`가 산출물에서 생성하며 `--check`가 낡은 표를 잡는다. 실행하지 않은 것은 "구현 후 미실행"으로 적는다.

## 0. 요약 — 무엇을 쟀고 무엇이 나왔나

대상 공고는 LG AI연구원 NLP Research Engineer Internship이고, 이 프로젝트가 맞춘 업무 묶음은 **테이블이해 기술(Table MRC)** 이다(§3). 한국어 표 질의응답에서 모델이 답과 근거 셀을 함께 내고, 고정 규칙 검증기가 인용 셀로 답을 다시 확인해 실패하면 보류한다. 아래 수치는 모두 한국어 독립 test(표 단위 재분할)에서 나왔다.

1. **답이 맞아도 근거 셀은 절반 넘게 틀린다. 전체 데이터로 학습하거나, 표 입력에 열 번호를 붙이면 1~3%대가 된다.** 답 텍스트가 맞은 조회 답 가운데 모델이 인용한 셀에 그 답이 없는 비율은 mT5-small 최종 모델 <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.strict.rate:pct -->52.6<!-- /num -->%, EXAONE-4.0-1.2B LoRA 300개 <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.strict.rate:pct -->65.2<!-- /num -->%, 같은 모델 전체 데이터 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.strict.rate:pct -->1.3<!-- /num -->%다(§19.1, 95% 구간 포함). 같은 300개 학습에서 표의 셀마다 열 번호를 붙여 주기만 해도 <!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.strict.rate:pct -->3.2<!-- /num -->%가 된다. 답 정확도는 그대로였고 검증기를 통과하는 오답은 오히려 늘었다(§19.7).
2. **검증기는 오답 유출을 줄인다.** 전체 데이터 EXAONE의 출력을 그대로 내보내면 전체 문항의 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.raw.wrong_answer_rate.rate:pct -->21.6<!-- /num -->%가 오답이고, 검증기를 거치면 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier.wrong_answer_rate.rate:pct -->13.9<!-- /num -->%(v1), <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_subject_check.wrong_answer_rate.rate:pct -->12.0<!-- /num -->%(v2)다. 대가는 답하는 비율 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.raw.coverage:pct -->95.3<!-- /num -->% → <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_subject_check.coverage:pct -->88.7<!-- /num -->%다(§19.2).
3. **공개 분할은 표가 겹친다.** KorWikiTQ 공개 dev 질문의 <!-- num:data/ko/official_split_profile.json:dev_on_train_table.rate:pct -->42.9<!-- /num -->%가 train에도 있는 표를 묻는다. 표 단위로 다시 나눴다. 겹침이 점수에 주는 영향도 쟀는데, mT5-small에서는 학습 때 본 표라고 점수가 오르지 않았다(차이 <!-- num:experiments/eval/leak_effect.json:planners.rl_v3.verified_em.diff:pct -->-2.3<!-- /num -->%p, 95% 구간 <!-- num:experiments/eval/leak_effect.json:planners.rl_v3.verified_em.diff_lo:pct -->-6.0<!-- /num --> ~ <!-- num:experiments/eval/leak_effect.json:planners.rl_v3.verified_em.diff_hi:pct -->1.4<!-- /num -->%p, §19.3).
4. **강화학습은 점수를 올리지 못했고, 보상 허점을 하나 찾아 고쳤다.** 검증기가 거부해 보류된 쓰레기 출력이 의도한 보류와 같은 보상을 받고 있었다. 같은 셀을 두 번 쓰는 퇴화 출력은 SFT <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:degenerate_calc_outputs:int -->101<!-- /num -->건에서 RL v1 <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:degenerate_calc_outputs:int -->160<!-- /num -->건으로 늘었고, 보상만 고친 v2에서도 <!-- num:experiments/eval/rl_ko_ko_test/analysis.json:degenerate_calc_outputs:int -->146<!-- /num -->건이 남았다. 학습 데이터까지 고친 최종 모델에서 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:degenerate_calc_outputs:int -->0<!-- /num -->건이 됐다(§7, §18).
5. **정답률.** 검증을 통과한 정답률(verified EM)은 어휘 겹침 기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->%, mT5-small 최종 <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->%(기준선 미달), EXAONE-4.0-1.2B 전체 데이터 LoRA <!-- num:experiments/eval/exaone_full_vllm_ko_test/metrics.json:metrics.verified_em:pct -->84.3<!-- /num -->%(1번째 학습), <!-- num:experiments/eval/exaone_full_vllm_ko_test_run2/metrics.json:metrics.verified_em:pct -->87.1<!-- /num -->%(2번째 학습)다(§5, §18.3).

가까운 논문 12편을 원문으로 읽고 무엇이 이미 있는지 확인했다(§19.4). 문제 제기와 개별 기법은 이미 있다. 이 프로젝트가 보태는 것은 한국어 표에서의 위 측정이다. 서비스(FastAPI, LangGraph), 서빙(vLLM, SGLang), 컨테이너, CI는 공고의 다른 업무 묶음에 대한 보조 근거로 §3 표에 있다. 코드와 실험의 역할 구분(소유자, AI 코딩 도구)은 `docs/HANDOFF.md` §0에 있다.

## 1. 저장소와 공개 데모

| 항목 | 값 |
|---|---|
| 목표 저장소 | <https://github.com/sokldjs554/tabletrace> (공개). 사용자가 GitHub를 다시 연결한 뒤 `main`에 푸시했다(`0f38f8d`). 이전에는 `403`으로 막혀 있었다 |
| 지금 코드가 있는 곳 | GitHub `sokldjs554/tabletrace` `main`과 컨테이너의 `/home/user/tabletrace` |
| 공개 데모 | **GitHub Pages**: <https://sokldjs554.github.io/tabletrace/> — Actions `pages` 실행 [성공](https://github.com/sokldjs554/tabletrace/actions/runs/41213002281)(build·deploy). 소유자가 2026-11-08 브라우저에서 열리는 것을 확인했다(개발 컨테이너에서는 `github.io`가 차단되어 작성자는 접속하지 못함). 백엔드가 없어 저장된 실행 결과 모드로만 동작한다. 같은 데이터의 단일 HTML 사본을 claude.ai Artifact로도 올렸다(비공개 링크, 소유자만 열 수 있음): <https://claude.ai/artifact/KvdrLkxC8PbSLWmpLvBPDM> |
| 로컬 실시간 데모 | `docker compose up --build` → http://localhost:8000 (Docker 빌드·컨테이너 smoke는 이 세션에서 실행해 통과) |
| 정적 데모 | 로컬에서 `scripts/build_static_site.py`(GitHub Pages용 폴더)와 `scripts/build_artifact_page.py`(단일 HTML, Artifact용)로 빌드하고 Playwright로 검증(§10). 단일 HTML은 file:// 로 열어 데스크톱·모바일에서 오류 0, 가로 넘침 없음을 확인 |



## 2. 최종 커밋과 배포 버전

| 항목 | 값 |
|---|---|
| 최종 커밋 | GitHub `sokldjs554/tabletrace` `main`의 최신 커밋(2026-11-08). 코드와 실험 산출물은 `4f873c5`까지이고 그 뒤는 문서 마무리 커밋뿐이다. 1차 결과의 기준 커밋은 `e6f9d71`, 2차(재학습·RL v3·int8 범위)와 GPU 실측(EXAONE LoRA, vLLM·SGLang, 멀티 GPU)은 11-04~11-08 커밋에 있다 |
| 패키지 버전 | 0.1.0 (`src/tabletrace/__init__.py`) |
| 정적 데모에 기록된 커밋 | `ae298b7`, 2026-11-10 생성(`console/data/recorded/index.json`). EXAONE 저장 출력 플래너가 추가됐다(§19.6). claude.ai Artifact 사본은 그 전 판(`e6f9d71`, mT5·휴리스틱만)에 머물러 있다 |
| 배포된 버전 | GitHub Pages <https://sokldjs554.github.io/tabletrace/>: `main`에 푸시할 때마다 `pages.yml`이 다시 배포한다(최신 실행 성공, 소유자가 브라우저에서 확인). claude.ai Artifact(저장된 결과, 비공개): 버전 1, 기록 커밋 `e6f9d71` — <https://claude.ai/artifact/KvdrLkxC8PbSLWmpLvBPDM> |

## 3. 공고 대조표

공고 원문은 2026-11-10에 읽었다(`docs/research/job-posting.md`에 문구 기록). 그전까지는 접근이 막혀 있어 프로젝트는 소유자가 적어 준 역량 목록 15개를 기준으로 만들어졌고, 아래 표의 행도 그 목록을 따른다. 15개 가운데 원문에 없는 항목은 없다. 원문에만 있는 항목은 표 아래에 따로 적었다.

원문은 수행 업무를 다섯 묶음으로 나눈다: (1) 초거대 언어모델 개발, (2) 심층문서이해 기술 개발, (3) 강화학습 기반 언어모델 개발, (4) 테이블이해 기술(Table MRC) 개발, (5) LLM기반 AI서비스 및 Agent 시스템 개발. 필요역량과 전형절차는 둘 다 "Tech Cell별"로 다를 수 있다고 적는다. **이 프로젝트가 정면으로 맞추는 묶음은 (4) 테이블이해이고, 두 번째가 (3) 강화학습이다.** (1)·(2)·(5)에 해당하는 행은 같은 표 QA 과제 위에서 한 번씩 실행해 본 보조 증거로 읽어야 한다.

상태는 **완료 / 실행했으나 실패 / 구현 후 미실행 / 미구현** 넷 중 하나이며, 상태 판단의 단서는 "평가 결과" 열에 적었다. 이 표는 프로젝트 결과만을 대상으로 하며 개인의 역량이나 근무 가능 여부를 검증했다고 주장하지 않는다.

| 공고 항목 | 프로젝트 적용 방식 | 구현·실행 증거 | 평가 결과 | 상태 |
|---|---|---|---|---|
| 한국어 언어모델 튜닝 | mT5-small(300M)을 KorWikiTQ 표 QA 프로그램 생성 과제로 SFT. 1차 2단계 → 2차에서 본문 학습 결함을 고쳐 재학습, 화학 단계, RL | `training/sft.py`, `experiments/sft_ko*/`, `experiments/sft_chem*/`, `experiments/rl_v3/` | 독립 test verified EM 미튜닝 <!-- num:experiments/eval/base_ko_test/metrics.json:metrics.verified_em:pct -->7.1<!-- /num -->% → 1차 최종 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->% → 2차 최종(RL v3) <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->%. 1차 최종 대 2차 화학 SFT v2는 쌍 비교 p=<!-- num:experiments/eval/paired_tests.json:chem2_vs_chem1_ko_test.p_display -->0.041<!-- /num -->. 어휘 겹침 기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->%에는 여전히 미달(§5, §18) | 완료 |
| 한국어 언어모델 벤치마크 구축 | 표 단위 재분할 test <!-- num:data/ko/build_report.json:test_examples -->539<!-- /num -->문항 + 합성 160 + 수작업 30(5범주), verified EM·근거 셀 일치·보류 재현율 등 지표, 자동 검수 | `data/ko/`, `eval/metrics.py`, `scripts/check_data.py` | 공개 분할의 표 누수를 측정하고 제거(공유 표 0). 수작업 30·합성 160은 표본이 작거나 편향이 있음(§5) | 완료 |
| 표 이해 및 Table MRC | 표 직렬화(r/c 좌표) → 셀·연산 프로그램 생성 → 검증기 | `model/serialize.py`, `verify/verifier.py` | 원본 KorWikiTQ 539문항에서 튜닝 모델 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->37.1<!-- /num -->% vs 기준선 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->26.2<!-- /num -->% | 완료 |
| 추론 엔진 최적화 | CPU에서 fp32 / int8 동적 양자화(범위별) / 배치 / KV 캐시를 정밀도별 별도 프로세스로 실측, 양자화 모델의 정확도도 평가 | `bench/inference.py`, `model/quant.py`, `experiments/bench/inference*.json`, `experiments/eval/final_int8_*` | 1차: fp32 <!-- num:experiments/bench/inference.json:results.0.throughput_ex_per_s -->0.985<!-- /num --> → int8(전부) bs=8 <!-- num:experiments/bench/inference.json:results.4.throughput_ex_per_s -->3.66<!-- /num --> 예제/s이지만 정확도 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->% → <!-- num:experiments/eval/sft_chem_int8_ko_test/metrics.json:metrics.verified_em:pct -->17.7<!-- /num -->%. **2차**: `lm_head`만 int8이면 ko test <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->% → <!-- num:experiments/eval/final_int8_lm_head_ko_test/metrics.json:metrics.verified_em:pct -->32.2<!-- /num -->%(쌍 비교 p=<!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_ko_test.p_display -->0.636<!-- /num -->)로 손실이 검출되지 않고 같은 측정에서 처리량 <!-- num:experiments/bench/inference_r2b.json:results.0.throughput_ex_per_s -->0.93<!-- /num --> → <!-- num:experiments/bench/inference_r2b.json:results.3.throughput_ex_per_s -->1.48<!-- /num --> 예제/s(bs=1). 모든 층 int8은 <!-- num:experiments/eval/final_int8_all_ko_test/metrics.json:metrics.verified_em:pct -->21.2<!-- /num -->%로 하락(§8, §18) | 완료 |
| 영어 화학 도메인 데이터 처리·모델 튜닝 | OpenStax Chemistry 2e CNXML 파싱(문서 <!-- num:data/chem/build_report.json:documents_with_tables:int -->56<!-- /num -->, 표 <!-- num:data/chem/build_report.json:tables:int -->113<!-- /num -->), 합성 QA, 화학 SFT(1차·2차), RL v3, 수작업 32문항 | `scripts/data/build_chem.py`, `experiments/sft_chem*/`, `experiments/rl_v3/` | 합성 dev 80: <!-- num:experiments/eval/sft_ko2_chem_syndev/metrics.json:metrics.verified_em:pct -->22.5<!-- /num -->% → 1차 화학 SFT <!-- num:experiments/eval/sft_chem_chem_syndev/metrics.json:metrics.verified_em:pct -->41.2<!-- /num -->% → 2차 <!-- num:experiments/eval/sft_chem2_chem_syndev/metrics.json:metrics.verified_em:pct -->38.8<!-- /num -->% → RL v3 <!-- num:experiments/eval/rl_v3_chem_syndev/metrics.json:metrics.verified_em:pct -->45.0<!-- /num -->%. 수작업 32문항: <!-- num:experiments/eval/sft_ko2_chem_custom/metrics.json:metrics.verified_em:pct -->9.4<!-- /num -->% → 1차 최종 <!-- num:experiments/eval/sft_chem_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num -->% → RL v3 <!-- num:experiments/eval/rl_v3_chem_custom/metrics.json:metrics.verified_em:pct -->21.9<!-- /num -->%(1–2문항 차이, 쌍 비교 p=<!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_chem_custom.p_display -->1.000<!-- /num -->). 전부 보류하는 미튜닝 모델이 <!-- num:experiments/eval/base_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num -->%, 기준선 <!-- num:experiments/eval/heuristic_chem_custom/metrics.json:metrics.verified_em:pct -->56.2<!-- /num -->%(§6, §18) | 완료 |
| 강화학습 기반 언어모델 개발 | GRPO 방식 정책 경사(검증기 보상, 그룹 정규화, KL). 정책 갱신 3회: v1(보상 편법), v2(수정 보상), v3(한국어+화학+본문 프롬프트 5,130개, 120 step) | `training/rl_grpo.py`, `experiments/rl_ko_v1/`, `experiments/rl_ko/`, `experiments/rl_v3/` | v1은 보상 편법 발견(§7.2), v2는 개선 없음(실패, §7.5). **v3**: 본문 근거 없음 50문항에서 모델의 직접 보류 <!-- num:experiments/eval/sft_chem2_text2_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->0.0<!-- /num -->% → <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->90.0<!-- /num -->%(쌍 비교 <!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_text2_test.candidate_better:int -->26<!-- /num -->문항 대 <!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_text2_test.reference_better:int -->11<!-- /num -->문항, p=<!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_text2_test.p_display -->0.020<!-- /num -->), 그러나 ko test 전체 verified EM은 <!-- num:experiments/eval/sft_chem2_ko_test/metrics.json:metrics.verified_em:pct -->32.9<!-- /num -->% → <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->%로 그대로(p=<!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_ko_test.p_display -->1.000<!-- /num -->). 시드 1개의 예비 실험(§18) | 완료 |
| LLM Agent와 외부 도구 연결 | LangGraph 그래프 + 타입 검증 도구 레지스트리(셀 조회·검색·제한 계산) | `agent/graph.py`, `tools/registry.py`, `tests/test_api.py` | API·도구·신뢰 경계 테스트 통과(§10) | 완료 |
| FastAPI 기반 서비스 및 모델 서빙 | REST API, 프로세스 내 모델 서빙, 작업 큐, 정적 콘솔 | `service/app.py`, `service/jobs.py` | API 테스트 통과, 컨테이너 smoke 통과, 모델 플래너 E2E 통과 | 완료 |
| 비동기 처리와 워크플로우 설계 | asyncio 작업 러너(세마포어·큐 제한·타임아웃·상태), LangGraph 분기 | `service/jobs.py`, `agent/graph.py` | 동시 5건·타임아웃·큐 초과(429)·실패 상태 테스트 통과 | 완료 |
| 프롬프트·컨텍스트 엔지니어링과 검색 결합 | BM25(Kiwi 형태소) 검색, 본문 스니펫+표 직렬화, 컨텍스트→행 예산 | `retrieval/`, `model/serialize.py` | 표 검색 hit@1 <!-- num:experiments/eval/retrieval/metrics.json:ko_test_lookup.hit_at_1:pct -->80.0<!-- /num -->% / hit@5 <!-- num:experiments/eval/retrieval/metrics.json:ko_test_lookup.hit_at_5:pct -->95.7<!-- /num -->%(한국어 <!-- num:experiments/eval/retrieval/metrics.json:ko_test_lookup.n_tables_searched -->1,140<!-- /num -->표), 화학 hit@1 <!-- num:experiments/eval/retrieval/metrics.json:chem_custom.hit_at_1:pct -->65.6<!-- /num -->%. 컨텍스트 유무의 모델 정확도 효과는 분리 측정하지 않음 | 완료 |
| Linux, Python, Hugging Face, PyTorch | Python 3.13 / PyTorch 2.15 / **Hugging Face Transformers·tokenizers 라이브러리**(Hub는 차단되어 사용하지 못함), 자체 학습 루프 | 저장소 전체 | — | 완료 |
| 멀티 GPU Model Parallelism | 2-스테이지 파이프라인 병렬(인코더 / 디코더+lm_head), torch.distributed | `bench/pipeline_parallel.py`, `experiments/bench/pp_*.json` | CPU 2프로세스(gloo)로 분할·통신·출력 일치 검증 뒤, 소유자가 Kaggle T4 2장에서 네 세션 NCCL로 실측: 출력 일치, 2-스테이지 14~15 예제/s로 안정적이나 단일 GPU 측정이 세션마다 달라 처리량 이득은 주장하지 않음, 장치당 메모리 분할(§9). vLLM TP=2는 §18.3 | 완료 |
| vLLM 또는 SGLang | OpenAI 호환 EnginePlanner + TP/PP 서빙 스크립트 + 엔진 벤치. mT5는 두 엔진이 지원하지 않아(`experiments/serving/engine_support.json`) EXAONE을 같은 데이터로 LoRA 튜닝해 서빙하는 경로 | `service/engines.py`, `scripts/serving/`, `scripts/train/exaone_lora_sft.py`, `notebooks/gpu_experiments.ipynb`, `experiments/serving/sglang_t4_failure.md` | EXAONE-4.0-1.2B LoRA 병합 모델을 소유자가 Kaggle T4에서 vLLM(1장·TP=2)과 SGLang(T4 우회 모듈)으로 띄워 같은 ko test·수작업 30문항을 같은 검증기로 평가하고 동시 요청 1/8/32 벤치를 받음. 전체 데이터 LoRA(3,587개, T4 31분): verified EM <!-- num:experiments/eval/exaone_full_vllm_ko_test/metrics.json:metrics.verified_em:pct -->84.3<!-- /num -->%(기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->%), 세 엔진 구성이 같은 답. 300개 LoRA: <!-- num:experiments/eval/exaone_vllm_ko_test/metrics.json:metrics.verified_em:pct -->53.1<!-- /num -->%. SGLang은 T4에서 두 번 커널 오류·한 번 설정 오류 뒤 우회 모듈로 성공(§18.3) | 완료(vLLM·SGLang) |
| Docker | API+콘솔 이미지, compose, 헬스체크 | `Dockerfile`, `docker-compose.yml`, `experiments/docker/smoke.json` | 이 세션에서 이미지 빌드(786 MB) + 컨테이너 smoke 통과(Docker Hub 429로 MCR 베이스 이미지 사용) | 완료 |
| LangChain 또는 LangGraph | 위 Agent 항목(LangGraph) | `agent/graph.py` | `GET /v1/graph` 가 Mermaid 반환, 조건부 재시도 분기 | 완료 |
| GitHub Actions | `ci.yml`(린트·테스트·데이터·수치·Docker smoke), `pages.yml` | `.github/workflows/` | GitHub Actions에서 실행해 **통과**: [ci](https://github.com/sokldjs554/tabletrace/actions/runs/41213002277)의 `test`·`docker` 작업과 [pages](https://github.com/sokldjs554/tabletrace/actions/runs/41213002281)의 build·deploy 작업이 모두 success(커밋 `0f38f8d`) | 완료 |
| 공개 데모 배포 | GitHub Pages 정적 데모 | `pages.yml`, `scripts/build_static_site.py` | 배포 작업 success. 소유자가 브라우저에서 열리는 것을 확인(2026-11-08). 개발 컨테이너에서는 `github.io` 차단 | 완료 |
| 저장된 결과 데모 호스팅(대체) | 단일 HTML 페이지를 claude.ai Artifact로 호스팅 | `scripts/build_artifact_page.py`, <https://claude.ai/artifact/KvdrLkxC8PbSLWmpLvBPDM> | 데스크톱·모바일 오류 0 확인. 링크는 비공개, 소유자가 공유해야 공개됨 | 완료 |

**원문에만 있는 항목** (처음 기준이던 15개 목록에 없던 것. 2026-11-10 원문 확인 뒤 추가)

| 원문 항목 | 프로젝트에서 한 것 | 상태 |
|---|---|---|
| (4) 데이터 구조 이해를 위한 언어모델(Pre-trained Language Model) 구현 | 표를 행·열 좌표가 붙은 텍스트로 직렬화해 일반 언어모델을 튜닝했다. 행·열 임베딩을 갖는 구조 전용 PLM을 구현하거나 사전학습하지 않았다 | 미구현 (직렬화·튜닝으로 대체) |
| (5) gRPC 기반 API | REST만 구현 | 미구현 |
| (5) 챗봇 | 질문 한 건에 답하는 에이전트 서비스만 있다. 여러 턴 대화는 없다 | 미구현 |
| (5) 메모리 결합 | 검색 결합만 있다. 대화 기억은 없다 | 미구현 |
| 우대: Personal Agent | 없음 | 미구현 |

## 4. 사용한 기술과 실제 역할

| 기술 | 실제 역할 | 실행 여부 |
|---|---|---|
| PyTorch 2.15 / Transformers 5.21 | mT5-small 변환·SFT·RL·추론; 자체 학습 루프(Trainer 미사용) | 실행 |
| tokenizers / SentencePiece | mT5 토크나이저를 spm proto에서 재구성(transformers 5가 spm 직접 로드를 지원하지 않음) | 실행 |
| Kiwi (kiwipiepy) | 한국어 형태소 분석으로 BM25 토큰화 | 실행 |
| LangGraph | retrieve→propose→verify→finalize 상태 그래프, 조건부 재시도 | 실행 |
| FastAPI / uvicorn / pydantic | API, 입력 검증, 비동기 작업 | 실행 |
| Playwright | 콘솔 E2E 검사·스크린샷 | 실행 |
| Docker | 이미지 빌드·컨테이너 smoke | 실행 |
| torch.distributed (gloo) | 파이프라인 병렬 기능 검증(CPU) | 실행(CPU) |
| TensorFlow (별도 venv) | mesh-TF 체크포인트 읽기 전용(변환 시 1회) | 실행 |
| GitHub Actions | CI·Pages 워크플로 | 작성만, 원격 실행 없음 |
| vLLM / SGLang | 서빙 스크립트·클라이언트·엔진 벤치·T4 우회 모듈 | 둘 다 소유자가 Kaggle T4에서 실행(§18.3) |
| Hugging Face Hub / EXAONE | EXAONE-4.0-1.2B LoRA SFT 스크립트 | 개발 컨테이너는 `huggingface.co` 차단. 소유자가 Kaggle에서 내려받아 튜닝·서빙(§18.3) |

## 5. 한국어 표 QA — 데이터·모델·평가

### 5.1 데이터

- **출처·라이선스**: KorWikiTQ(LG AI연구원, CC BY-SA 4.0). 공개 분할은 train <!-- num:data/ko/official_split_profile.json:train.examples:int -->58,221<!-- /num --> / dev <!-- num:data/ko/official_split_profile.json:dev.examples:int -->11,771<!-- /num -->문항이며 **셀까지 똑같은 표 <!-- num:data/ko/official_split_profile.json:shared_tables_by_url_and_content:int -->1,578<!-- /num -->개가 두 파일에 다 들어 있다**(같은 위키 페이지 기준 <!-- num:data/ko/official_split_profile.json:shared_tables_by_url:int -->1,755<!-- /num -->개. 이전 판은 이 페이지 수를 "표"라고 적었다, 이슈 42). 공개 dev 질문의 <!-- num:data/ko/official_split_profile.json:dev_on_train_table.rate:pct -->42.9<!-- /num -->%(<!-- num:data/ko/official_split_profile.json:dev_on_train_table.examples:int -->5,046<!-- /num -->개)가 train에도 있는 표를 묻는다. 같은 표에서 같은 답을 묻는 질문이 train에도 있는 경우는 <!-- num:data/ko/official_split_profile.json:dev_same_table_same_answer_in_train.examples:int -->51<!-- /num -->개뿐이고 같은 질문은 없다. 원논문과 README는 분할 방식을 밝히지 않는다(§19.4). 정답이 표의 어떤 셀과 정확히 일치하는 비율은 train <!-- num:data/ko/official_split_profile.json:train.answer_is_cell_pct -->99.6<!-- /num -->%라 "셀 선택" 과제이며 산술·보류 사례는 없다.
- **재분할**: URL+표 내용 해시로 표를 식별해 표 단위로 나눴다. 필터(16행·7열·900자 이하 등)를 통과한 표 <!-- num:data/ko/build_report.json:tables_after_filter:int -->7,294<!-- /num -->개 중 <!-- num:data/ko/build_report.json:tables_used.train:int -->900<!-- /num -->/<!-- num:data/ko/build_report.json:tables_used.dev:int -->60<!-- /num -->/<!-- num:data/ko/build_report.json:tables_used.test:int -->180<!-- /num -->개를 train/dev/test에 배정했고 **분할 간 공유 표는 0**이다(`leak_check_shared_tables`, `scripts/check_data.py`가 CI에서 재검사).
- **문항 수**: train <!-- num:data/ko/build_report.json:train_examples:int -->2,694<!-- /num --> / dev <!-- num:data/ko/build_report.json:dev_examples:int -->180<!-- /num --> / test <!-- num:data/ko/build_report.json:test_examples:int -->539<!-- /num -->(원본 lookup). 합성(템플릿) 계산·보류: train 960 / dev 65 / test 160. 본문 답변 학습용 KorQuAD 700/100. 수작업 평가 30(표 6개 위에 직접 작성, 5범주, 정답은 스크립트가 셀 텍스트·계산기·본문 포함 여부로 자동 검수).
- **학습 입력 예산**: 512 토큰. 본문을 300→150→0자로 줄여서라도 표 전체를 넣고, 그래도 넘으면 뒤 행을 자른다. 학습에서는 정답 행이 잘린 <!-- num:experiments/sft_ko/summary.json:n_train_dropped_truncated:int -->223<!-- /num -->건을 제외했고, 평가에서는 제외하지 않고 `truncated_gold_rate`(<!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.truncated_gold_rate:pct -->8.9<!-- /num -->%)를 따로 보고한다. 즉 test의 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.truncated_gold_rate:pct -->8.9<!-- /num -->%는 입력 예산 때문에 모델이 원리적으로 맞힐 수 없다.

### 5.2 모델·학습 조건

mT5-small 300,176,768 파라미터(GCS 체크포인트를 PyTorch로 직접 변환). 하드웨어: 4 vCPU CPU만 사용. stage 1: <!-- num:experiments/sft_ko/summary.json:n_train:int -->3,431<!-- /num -->예제, <!-- num:experiments/sft_ko/summary.json:steps:int -->858<!-- /num --> step, 약 <!-- num:experiments/sft_ko/summary.json:wall_s:int -->7,219<!-- /num -->초. stage 2(본문 답변 추가): <!-- num:experiments/sft_ko2/summary.json:n_train:int -->1,542<!-- /num -->예제, <!-- num:experiments/sft_ko2/summary.json:steps:int -->193<!-- /num --> step, <!-- num:experiments/sft_ko2/summary.json:wall_s:int -->1,813<!-- /num -->초. 학습 중 dev 지표는 이후 수정한 채점 코드(§13의 25번) 이전 값이라 아래 test 표와 직접 비교하지 않는다.

### 5.3 결과 (동일한 독립 평가셋, 같은 검증기)

<!-- results:ko:start -->
**한국어 표 QA — 독립 test (원본 539 + 합성 160), 검증기 v1: 개체 일치 검사 없음 (1차 평가와 같은 조건)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 699 | **36.2** | 21.7 | 26.2 | 59.1 | 31.6 | 31.6 | 94.0 | 42.4 | 0.0 | 21 |
| mT5-small 기본(미튜닝) | 699 | **7.1** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 399 |
| SFT stage1 | 699 | **25.0** | 26.7 | 29.9 | 1.8 | 25.4 | 18.5 | 24.0 | 28.8 | 0.0 | 591 |
| SFT stage2(+본문) | 699 | **27.5** | 28.0 | 32.3 | 4.5 | 28.0 | 21.4 | 26.0 | 31.0 | 0.0 | 422 |
| GRPO RL v1 (보상 허점) | 699 | **26.8** | 27.4 | 30.6 | 4.5 | 26.7 | 20.6 | 34.0 | 37.9 | 0.0 | 460 |
| GRPO RL v2 (보상 수정) | 699 | **27.0** | 27.6 | 31.0 | 4.5 | 27.0 | 20.3 | 34.0 | 35.9 | 0.0 | 504 |
| 화학 SFT | 699 | **29.8** | 33.4 | 37.1 | 0.0 | 30.8 | 17.1 | 16.0 | 19.4 | 0.0 | 615 |
| 화학 SFT + int8 동적 양자화 | 699 | **17.7** | 16.0 | 18.6 | 0.0 | 15.4 | 13.6 | 48.0 | 55.3 | 15.0 | 383 |
| [2차] SFT stage2 재학습(실제 표 옆 본문 예제) | 699 | **24.9** | 25.3 | 25.4 | 6.4 | 23.0 | 17.1 | 60.0 | 45.3 | 1.0 | 519 |
| [2차] + 표 조회 보강 epoch | 699 | **30.6** | 32.2 | 36.9 | 3.6 | 31.7 | 22.5 | 22.0 | 24.0 | 0.0 | 530 |
| [2차] 화학 SFT v2 | 699 | **32.9** | 34.2 | 38.4 | 0.0 | 31.9 | 17.9 | 46.0 | 29.0 | 1.4 | 538 |
| [2차] GRPO RL v3 | 699 | **32.8** | 32.2 | 38.2 | 0.0 | 31.7 | 18.9 | 46.0 | 27.0 | 0.0 | 500 |

**한국어 표 QA — 독립 test, 검증기 v2: 개체 일치 검사 있음 (같은 모델 출력을 다시 검증)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 699 | **35.9** | 21.7 | 25.6 | 59.1 | 31.1 | 31.6 | 96.0 | 45.8 | 0.0 | 21 |
| mT5-small 기본(미튜닝) | 699 | **7.1** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 399 |
| SFT stage1 | 699 | **25.3** | 26.7 | 28.0 | 1.8 | 23.9 | 18.5 | 48.0 | 40.1 | 0.0 | 591 |
| SFT stage2(+본문) | 699 | **28.2** | 28.0 | 30.6 | 4.5 | 26.7 | 21.4 | 54.0 | 39.0 | 0.0 | 422 |
| GRPO RL v1 (보상 허점) | 699 | **27.5** | 27.4 | 29.3 | 4.5 | 25.6 | 20.6 | 58.0 | 45.9 | 0.0 | 460 |
| GRPO RL v2 (보상 수정) | 699 | **27.8** | 27.6 | 29.7 | 4.5 | 25.9 | 20.3 | 58.0 | 43.9 | 0.0 | 504 |
| 화학 SFT | 699 | **30.2** | 33.4 | 35.1 | 0.0 | 29.1 | 17.1 | 44.0 | 26.5 | 0.0 | 615 |
| 화학 SFT + int8 동적 양자화 | 699 | **17.9** | 16.0 | 17.2 | 0.0 | 14.3 | 13.6 | 64.0 | 60.7 | 15.0 | 383 |
| [2차] SFT stage2 재학습(실제 표 옆 본문 예제) | 699 | **24.2** | 25.3 | 24.3 | 6.4 | 22.0 | 17.1 | 62.0 | 51.9 | 1.0 | 519 |
| [2차] + 표 조회 보강 epoch | 699 | **30.9** | 32.2 | 35.1 | 3.6 | 30.2 | 22.5 | 46.0 | 31.7 | 0.0 | 530 |
| [2차] 화학 SFT v2 | 699 | **31.8** | 34.2 | 36.7 | 0.0 | 30.5 | 17.9 | 48.0 | 33.9 | 1.4 | 538 |
| [2차] GRPO RL v3 | 699 | **31.6** | 32.2 | 36.5 | 0.0 | 30.3 | 18.9 | 48.0 | 31.6 | 0.0 | 500 |

**한국어 표 QA — 수작업 30문항, 검증기 v1: 개체 일치 검사 없음 (1차 평가와 같은 조건)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 30 | **50.0** | 20.0 | 38.5 | 41.7 | 44.0 | 44.0 | 100.0 | 40.0 | 0.0 | 133 |
| mT5-small 기본(미튜닝) | 30 | **16.7** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 242 |
| SFT stage1 | 30 | **16.7** | 12.0 | 7.7 | 0.0 | 4.0 | 8.0 | 80.0 | 80.0 | 0.0 | 447 |
| SFT stage2(+본문) | 30 | **23.3** | 8.0 | 7.7 | 8.3 | 8.0 | 12.0 | 100.0 | 80.0 | 0.0 | 480 |
| GRPO RL v1 (보상 허점) | 30 | **20.0** | 8.0 | 7.7 | 0.0 | 4.0 | 12.0 | 100.0 | 84.0 | 0.0 | 437 |
| GRPO RL v2 (보상 수정) | 30 | **20.0** | 8.0 | 7.7 | 0.0 | 4.0 | 12.0 | 100.0 | 76.0 | 0.0 | 525 |
| 화학 SFT | 30 | **3.3** | 8.0 | 7.7 | 0.0 | 4.0 | 4.0 | 0.0 | 48.0 | 0.0 | 536 |
| 화학 SFT + int8 동적 양자화 | 30 | **13.3** | 8.0 | 15.4 | 0.0 | 8.0 | 4.0 | 40.0 | 52.0 | 16.7 | 393 |
| [2차] SFT stage2 재학습(실제 표 옆 본문 예제) | 30 | **16.7** | 12.0 | 7.7 | 0.0 | 16.0 | 24.0 | 80.0 | 72.0 | 0.0 | 488 |
| [2차] + 표 조회 보강 epoch | 30 | **16.7** | 12.0 | 7.7 | 16.7 | 16.0 | 16.0 | 40.0 | 60.0 | 0.0 | 538 |
| [2차] 화학 SFT v2 | 30 | **6.7** | 4.0 | 7.7 | 0.0 | 16.0 | 12.0 | 20.0 | 36.0 | 6.7 | 623 |
| [2차] GRPO RL v3 | 30 | **13.3** | 4.0 | 7.7 | 0.0 | 12.0 | 20.0 | 60.0 | 32.0 | 0.0 | 507 |

**한국어 표 QA — 수작업 30문항, 검증기 v2: 개체 일치 검사 있음 (같은 모델 출력을 다시 검증)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 30 | **50.0** | 20.0 | 38.5 | 41.7 | 44.0 | 44.0 | 100.0 | 40.0 | 0.0 | 133 |
| mT5-small 기본(미튜닝) | 30 | **16.7** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 242 |
| SFT stage1 | 30 | **16.7** | 12.0 | 7.7 | 0.0 | 4.0 | 8.0 | 80.0 | 80.0 | 0.0 | 447 |
| SFT stage2(+본문) | 30 | **23.3** | 8.0 | 7.7 | 8.3 | 8.0 | 12.0 | 100.0 | 80.0 | 0.0 | 480 |
| GRPO RL v1 (보상 허점) | 30 | **20.0** | 8.0 | 7.7 | 0.0 | 4.0 | 12.0 | 100.0 | 84.0 | 0.0 | 437 |
| GRPO RL v2 (보상 수정) | 30 | **20.0** | 8.0 | 7.7 | 0.0 | 4.0 | 12.0 | 100.0 | 76.0 | 0.0 | 525 |
| 화학 SFT | 30 | **6.7** | 8.0 | 7.7 | 0.0 | 4.0 | 4.0 | 20.0 | 56.0 | 0.0 | 536 |
| 화학 SFT + int8 동적 양자화 | 30 | **13.3** | 8.0 | 15.4 | 0.0 | 8.0 | 4.0 | 40.0 | 52.0 | 16.7 | 393 |
| [2차] SFT stage2 재학습(실제 표 옆 본문 예제) | 30 | **16.7** | 12.0 | 7.7 | 0.0 | 16.0 | 24.0 | 80.0 | 72.0 | 0.0 | 488 |
| [2차] + 표 조회 보강 epoch | 30 | **20.0** | 12.0 | 7.7 | 16.7 | 16.0 | 16.0 | 60.0 | 60.0 | 0.0 | 538 |
| [2차] 화학 SFT v2 | 30 | **6.7** | 4.0 | 7.7 | 0.0 | 16.0 | 12.0 | 20.0 | 40.0 | 6.7 | 623 |
| [2차] GRPO RL v3 | 30 | **13.3** | 4.0 | 7.7 | 0.0 | 12.0 | 20.0 | 60.0 | 32.0 | 0.0 | 507 |

**한국어 수작업 (검증기 v2) — 범주별 verified EM % (n)**

| 범주 | 휴리스틱 기준선 | mT5-small 기본(미튜닝) | SFT stage1 | SFT stage2(+본문) | GRPO RL v1 (보상 허점) | GRPO RL v2 (보상 수정) | 화학 SFT | 화학 SFT + int8 동적 양자화 | [2차] SFT stage2 재학습(실제 표 옆 본문 예제) | [2차] + 표 조회 보강 epoch | [2차] 화학 SFT v2 | [2차] GRPO RL v3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| abstain | 100.0 (5) | 100.0 (5) | 80.0 (5) | 100.0 (5) | 100.0 (5) | 100.0 (5) | 20.0 (5) | 40.0 (5) | 80.0 (5) | 60.0 (5) | 20.0 (5) | 60.0 (5) |
| calc | 83.3 (6) | 0.0 (6) | 0.0 (6) | 16.7 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 16.7 (6) | 0.0 (6) | 0.0 (6) |
| cell | 44.4 (9) | 0.0 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) | 11.1 (9) |
| text_table | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 20.0 (5) | 0.0 (5) | 0.0 (5) |
| unit_period | 20.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 20.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) | 0.0 (5) |


<!-- results:ko:end -->

<!-- results:training:start -->
| 실행 | 학습 예제/프롬프트 | 스텝 | 소요 (CPU 4스레드) | best dev verified EM % | dev 추이 % |
|---|---:|---:|---:|---:|---|
| SFT stage1 (ko 표) | 3431 | 858 | 120 min | 20.8 | 15.1, 20.8 |
| SFT stage2 (ko 표+본문) | 1542 | 193 | 30 min | 29.3 | 29.3 |
| SFT chem | 937 | 236 | 32 min | 42.5 | 38.8, 42.5 |
| GRPO RL v1 (ko) | 3485 | 60 | 29 min | 30.2 | 28.2, 30.2, 26.5, 24.1 |
| GRPO RL v2 (ko) | 3485 | 60 | 32 min | 30.6 | 28.2, 30.2, 30.6, 30.6 |
| [2차] SFT stage2 재학습 | 2136 | 267 | 52 min | 27.1 | 27.1 |
| [2차] 표 조회 보강 epoch | 2379 | 298 | 52 min | 29.9 | 29.9 |
| [2차] SFT chem v2 | 1590 | 398 | 62 min | 41.2 | 40.0, 41.2 |
| [2차] GRPO RL v3 (ko+chem+text) | 5130 | 120 | 57 min | 43.2 | 36.2, 40.6, 43.2, 41.1 |

<!-- results:training:end -->

### 5.4 해석 — 무엇이 되고 무엇이 안 되었나

> **2차 시도 이후의 읽는 법**: 이 절의 해석은 **1차 모델**(화학 SFT가 최종)의 결과를 설명한다. 2차에서 고친 것과 2차 최종 모델(RL v3)의 수치는 §18에 있고, 위 표는 두 차수의 모델을 한 표에 함께 보여 준다(`[2차]` 접두어).


1. **튜닝은 실제로 효과가 있었다.** 미튜닝 mT5-small은 프로그램 문법을 몰라 출력이 전부 해석 불가(파싱 실패 <!-- num:experiments/eval/base_ko_test/metrics.json:metrics.parse_fail_rate:pct -->100.0<!-- /num -->%)이고, 시스템이 전부 보류한다. 점수 <!-- num:experiments/eval/base_ko_test/metrics.json:metrics.verified_em:pct -->7.1<!-- /num -->%는 정답이 "보류"인 <!-- num:experiments/eval/base_ko_test/metrics.json:metrics.n_gold_abstain:int -->50<!-- /num -->문항을 보류로 맞힌 값뿐이다. SFT stage 1 <!-- num:experiments/eval/sft_ko_ko_test/metrics.json:metrics.verified_em:pct -->25.0<!-- /num -->% → stage 2 <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.verified_em:pct -->27.5<!-- /num -->% → 화학 SFT 후 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->%(n=699, 1 표준오차 약 1.7%p).
2. **그러나 단순한 어휘 겹침 기준선을 전체 점수로는 넘지 못했다.** 기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->% > 최고 모델 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->%. 수작업 30문항에서도 기준선 <!-- num:experiments/eval/heuristic_ko_custom/metrics.json:metrics.verified_em:pct -->50.0<!-- /num -->% > SFT stage 2 <!-- num:experiments/eval/sft_ko2_ko_custom/metrics.json:metrics.verified_em:pct -->23.3<!-- /num -->%(표본 30: 1 표준오차 약 7–9%p).
3. **원본 데이터와 합성 데이터로 쪼개면 그림이 갈린다.** 원본 KorWikiTQ 539문항만 보면 화학 SFT 모델 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->37.1<!-- /num -->%가 기준선 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->26.2<!-- /num -->%를 앞선다. 합성 160문항(계산·보류)에서는 기준선 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:by_source_verified.synthetic.verified_em:pct -->70.0<!-- /num -->% 대 모델 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:by_source_verified.synthetic.verified_em:pct -->5.0<!-- /num -->%다. **이 합성 점수는 독립적인 비교가 아니다**: 합성 질문 템플릿과 기준선의 의도 정규식("차이", "합하면", "평균")을 같은 사람이 썼기 때문에 기준선에 유리하다. 전체 점수의 격차는 이 160문항이 만든 것이다.
4. **약한 고리는 셀 열 좌표다.** 모델이 인용한 셀 중 lookup 문항에서 행이 맞은 비율은 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:lookup_citation.row_correct:pct -->77.7<!-- /num -->%인데 열이 맞은 비율은 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:lookup_citation.col_correct:pct -->27.8<!-- /num -->%에 그친다(기준선은 열 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:lookup_citation.col_correct:pct -->56.7<!-- /num -->%). 질문의 속성어를 헤더와 맞추는 일을 작은 모델이 2 epoch 안에 배우지 못했다.
5. **검증기의 "근거 복구"가 많이 개입한다.** 모델의 답 텍스트는 표 어딘가에 있는 값을 정확히 베껴 쓰는 경우가 많지만 좌표는 틀린다. 답 텍스트가 표에서 유일한 셀이면 그 셀을 근거로 삼고 `evidence_repaired` 검사를 실패로 기록한다. 화학 SFT 모델은 답한 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:pred_status_answerable.answered:int -->523<!-- /num -->문항 중 <!-- num:experiments/eval/sft_chem_ko_test/analysis.json:evidence_repaired:int -->386<!-- /num -->건이 복구였다. 그래서 표의 "근거 셀 일치(모델 인용)" 열(<!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.evidence_cells_exact_raw:pct -->17.1<!-- /num -->%)이 "최종" 열(<!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.evidence_cells_exact:pct -->30.8<!-- /num -->%)보다 낮다. **모델 자체가 올바른 근거를 댄 비율은 후자가 아니라 전자**다.
6. **계산은 거의 못 한다.** 모델은 연산 종류(diff/sum/avg)는 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.op_acc:pct -->78.1<!-- /num -->% 맞히지만 서로 다른 두 행의 같은 열 셀을 모두 맞혀야 해서 계산 정답률이 <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.calc_em:pct -->4.5<!-- /num -->%(stage 2) 수준이다. 화학 SFT 후에는 계산 문항을 대부분 lookup으로 처리해 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.calc_em:pct -->0.0<!-- /num -->%가 되었다(치명적 망각 의심: 화학 학습 데이터가 lookup 중심).
7. **보류는 모델의 판단이 아니다.** 답이 없는 문항에서 최종 상태가 보류인 비율(보류 재현율)은 화학 SFT <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.abstain_recall:pct -->16.0<!-- /num -->%, RL v1 <!-- num:experiments/eval/rl_ko_v1_ko_test/metrics.json:metrics.abstain_recall:pct -->34.0<!-- /num -->%로 기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.abstain_recall:pct -->94.0<!-- /num -->%보다 훨씬 낮다. 더 중요한 점은 이 숫자 자체가 우연한 보류를 포함한다는 것이다. 모델이 **직접** `op: abstain`을 낸 비율은 SFT stage 2 <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->0.0<!-- /num -->%, RL v1 <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->0.0<!-- /num -->%이고 기준선은 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->94.0<!-- /num -->%다. 모델의 보류는 해석 불가·퇴화 프로그램(SFT stage 2 <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:abstain_breakdown.abstained_via_invalid_program_recall:pct -->12.0<!-- /num -->%)이나 검증 실패(<!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:abstain_breakdown.abstained_via_verifier_recall:pct -->14.0<!-- /num -->%)로 우연히 일어난 것이다. 같은 셀을 두 번 쓰는 퇴화 계산 출력은 test <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:n:int -->699<!-- /num -->문항 중 SFT stage 2에서 <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:degenerate_calc_outputs:int -->101<!-- /num -->건이었고 RL v1에서 <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:degenerate_calc_outputs:int -->160<!-- /num -->건으로 늘었다. 또한 검증기는 인용한 셀이 질문의 대상에 대한 것인지는 확인하지 않아, 표에 없는 대상에 엉뚱한 셀을 인용해 답해도 통과했다(수작업 `ko_custom_08`, README §11). 2차의 검증기 v2가 이를 막는다(§18). 따라서 "모델이 근거 부족을 판단해 보류한다"는 주장은 **1차 모델들**에 대해서는 뒷받침되지 않는다(2차 RL v3는 직접 보류를 학습했다, §18).
8. **본문+표 범주는 실패했고, 원인은 학습 데이터 설계 결함이다.** 어떤 모델도 평가 문항 62개(한국어 수작업 30 + 화학 수작업 32)에서 `op: text`를 **한 번도 내지 않았다**(본문 답변이 정답인 문항은 한국어 6, 화학 7). 그러나 학습과 같은 형식(KorQuAD 본문 + **행이 없는 빈 표**)의 dev 100문항에서는 stage 2 모델이 `op: text`를 <!-- num:experiments/eval/sft_ko2_text_dev/analysis.json:op_confusion_top.0.1:int -->99<!-- /num -->번 내고 <!-- num:experiments/eval/sft_ko2_text_dev/metrics.json:metrics.verified_em:pct -->29.0<!-- /num -->%를 맞힌다. 즉 모델은 "본문에서 답을 베끼는 법"이 아니라 **"표에 행이 없으면 text"라는 형식 지름길**을 배웠다. 학습의 text 예제를 실제 표와 함께 만들고(답이 표가 아닌 본문에 있는 경우) 표 질문과 섞어야 한다. 이 수정은 2차에서 **했다**(§18): 실제 표 옆에 본문을 두는 예제로 재학습해 `op: text` 선택을 고쳤지만 본문 답 구간의 정확도는 아직 낮다.
9. **단위·기간 범주도 0에 가깝다.** 연도·기간 조건으로 행을 고르거나 표기 단위가 다른 셀을 구별해야 하는 5문항을 모든 모델이 풀지 못했다(기준선도 <!-- num:experiments/eval/heuristic_ko_custom/metrics.json:metrics.by_category.unit_period.verified_em:pct -->20.0<!-- /num -->%, 5문항 중 1문항).

## 6. 영어 화학 문서 — 데이터·모델·평가

### 6.1 데이터

OpenStax *Chemistry 2e*(Rice University, CC BY-NC-SA 4.0, 비상업 연구 용도) CNXML 원본에서 표가 있는 문서 <!-- num:data/chem/build_report.json:documents_with_tables:int -->56<!-- /num -->개, 표 <!-- num:data/chem/build_report.json:tables:int -->113<!-- /num -->개, 본문 문단 <!-- num:data/chem/build_report.json:passages:int -->3,780<!-- /num -->개를 구축했다. MathML은 평문(`H2O`, `10^−6`)으로 풀었고 헤더에서 단위(`kPa`, `K`, `°C`, `mol/L`)를 파싱한다. 문서(모듈) 단위로 train 40 / dev 5 / test 11로 나눴고(`data/chem/split.json`), 수작업 평가 32문항은 모두 test 문서 8개 위에 작성했다(`check_data.py`가 test 분할 밖의 문서를 거부). 학습에는 train 문서의 표에서 만든 합성 QA(lookup 420, diff 120, ratio 60, sum 60, abstain 160)를 썼다.

논문·특허 사이트(PMC, ChemRxiv, Google Patents 등)가 차단되어 **논문 속 실험 데이터가 아니라 교과서의 데이터 표**를 쓴 것이 한계다. 교과서는 문장이 설명적이고 표가 깨끗해 실제 논문보다 쉽다.

### 6.2 결과 (튜닝 전후 비교)

"튜닝 전"은 영어 화학 데이터를 보지 않은 stage 2 모델, "튜닝 후"는 화학 SFT 모델이며 같은 32문항·같은 검증기·같은 CPU에서 평가했다.

<!-- results:chem:start -->
**영어 화학 문서 — 수작업 32문항 (test 분할 문서), 검증기 v1: 개체 일치 검사 없음 (1차 평가와 같은 조건)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 32 | **56.2** | 40.7 | 84.6 | 14.3 | 55.6 | 55.6 | 100.0 | 25.9 | 0.0 | 0 |
| mT5-small 기본(미튜닝) | 32 | **15.6** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 138 |
| SFT stage1 | 32 | **12.5** | 18.5 | 7.7 | 0.0 | 3.7 | 7.4 | 60.0 | 70.4 | 0.0 | 399 |
| SFT stage2(+본문) | 32 | **9.4** | 7.4 | 0.0 | 0.0 | 0.0 | 0.0 | 60.0 | 81.5 | 0.0 | 352 |
| GRPO RL v1 (보상 허점) | 32 | **15.6** | 7.4 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 81.5 | 3.1 | 424 |
| GRPO RL v2 (보상 수정) | 32 | **12.5** | 7.4 | 0.0 | 0.0 | 0.0 | 7.4 | 80.0 | 85.2 | 0.0 | 426 |
| 화학 SFT | 32 | **15.6** | 22.2 | 7.7 | 7.1 | 7.4 | 22.2 | 60.0 | 66.7 | 3.1 | 459 |
| 화학 SFT + int8 동적 양자화 | 32 | **25.0** | 14.8 | 30.8 | 0.0 | 14.8 | 11.1 | 80.0 | 59.3 | 21.9 | 328 |
| [2차] SFT stage2 재학습(실제 표 옆 본문 예제) | 32 | **18.8** | 14.8 | 0.0 | 14.3 | 7.4 | 11.1 | 80.0 | 85.2 | 25.0 | 403 |
| [2차] + 표 조회 보강 epoch | 32 | **18.8** | 22.2 | 15.4 | 7.1 | 11.1 | 14.8 | 60.0 | 59.3 | 6.2 | 479 |
| [2차] 화학 SFT v2 | 32 | **18.8** | 18.5 | 23.1 | 0.0 | 11.1 | 7.4 | 60.0 | 55.6 | 0.0 | 447 |
| [2차] GRPO RL v3 | 32 | **21.9** | 18.5 | 23.1 | 7.1 | 14.8 | 14.8 | 60.0 | 51.8 | 0.0 | 391 |

**영어 화학 — 수작업 32문항, 검증기 v2: 개체 일치 검사 있음 (같은 모델 출력을 다시 검증)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 32 | **56.2** | 40.7 | 84.6 | 14.3 | 55.6 | 55.6 | 100.0 | 25.9 | 0.0 | 0 |
| mT5-small 기본(미튜닝) | 32 | **15.6** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 | 138 |
| SFT stage1 | 32 | **12.5** | 18.5 | 7.7 | 0.0 | 3.7 | 7.4 | 60.0 | 70.4 | 0.0 | 399 |
| SFT stage2(+본문) | 32 | **9.4** | 7.4 | 0.0 | 0.0 | 0.0 | 0.0 | 60.0 | 81.5 | 0.0 | 352 |
| GRPO RL v1 (보상 허점) | 32 | **15.6** | 7.4 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 81.5 | 3.1 | 424 |
| GRPO RL v2 (보상 수정) | 32 | **12.5** | 7.4 | 0.0 | 0.0 | 0.0 | 7.4 | 80.0 | 85.2 | 0.0 | 426 |
| 화학 SFT | 32 | **15.6** | 22.2 | 7.7 | 7.1 | 7.4 | 22.2 | 60.0 | 66.7 | 3.1 | 459 |
| 화학 SFT + int8 동적 양자화 | 32 | **25.0** | 14.8 | 30.8 | 0.0 | 14.8 | 11.1 | 80.0 | 63.0 | 21.9 | 328 |
| [2차] SFT stage2 재학습(실제 표 옆 본문 예제) | 32 | **18.8** | 14.8 | 0.0 | 14.3 | 7.4 | 11.1 | 80.0 | 85.2 | 25.0 | 403 |
| [2차] + 표 조회 보강 epoch | 32 | **18.8** | 22.2 | 15.4 | 7.1 | 11.1 | 14.8 | 60.0 | 59.3 | 6.2 | 479 |
| [2차] 화학 SFT v2 | 32 | **18.8** | 18.5 | 23.1 | 0.0 | 11.1 | 7.4 | 60.0 | 55.6 | 0.0 | 447 |
| [2차] GRPO RL v3 | 32 | **21.9** | 18.5 | 23.1 | 7.1 | 14.8 | 14.8 | 60.0 | 51.8 | 0.0 | 391 |

**영어 화학 — 합성 dev 80문항(템플릿, 참고용), 검증기 v1: 개체 일치 검사 없음 (1차 평가와 같은 조건)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SFT stage2(+본문) | 80 | **22.5** | 26.6 | 22.5 | 0.0 | 14.1 | 23.4 | 56.2 | 57.8 | 0.0 | 442 |
| 화학 SFT | 80 | **41.2** | 39.1 | 57.5 | 8.3 | 26.6 | 29.7 | 50.0 | 35.9 | 2.5 | 521 |
| [2차] 화학 SFT v2 | 80 | **38.8** | 34.4 | 50.0 | 4.2 | 23.4 | 32.8 | 62.5 | 45.3 | 0.0 | 656 |
| [2차] GRPO RL v3 | 80 | **45.0** | 42.2 | 57.5 | 0.0 | 34.4 | 37.5 | 81.2 | 43.8 | 5.0 | 537 |

**영어 화학 — 합성 dev 80문항, 검증기 v2: 개체 일치 검사 있음 (같은 모델 출력을 다시 검증)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SFT stage2(+본문) | 80 | **26.2** | 26.6 | 22.5 | 0.0 | 14.1 | 23.4 | 75.0 | 62.5 | 0.0 | 442 |
| 화학 SFT | 80 | **45.0** | 39.1 | 57.5 | 8.3 | 26.6 | 29.7 | 68.8 | 35.9 | 2.5 | 521 |
| [2차] 화학 SFT v2 | 80 | **41.2** | 34.4 | 50.0 | 4.2 | 23.4 | 32.8 | 75.0 | 45.3 | 0.0 | 656 |
| [2차] GRPO RL v3 | 80 | **46.2** | 42.2 | 57.5 | 0.0 | 34.4 | 37.5 | 87.5 | 43.8 | 5.0 | 537 |

**화학 수작업 (검증기 v2) — 범주별 verified EM % (n)**

| 범주 | 휴리스틱 기준선 | mT5-small 기본(미튜닝) | SFT stage1 | SFT stage2(+본문) | GRPO RL v1 (보상 허점) | GRPO RL v2 (보상 수정) | 화학 SFT | 화학 SFT + int8 동적 양자화 | [2차] SFT stage2 재학습(실제 표 옆 본문 예제) | [2차] + 표 조회 보강 epoch | [2차] 화학 SFT v2 | [2차] GRPO RL v3 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| abstain | 100.0 (5) | 100.0 (5) | 60.0 (5) | 60.0 (5) | 100.0 (5) | 80.0 (5) | 60.0 (5) | 80.0 (5) | 80.0 (5) | 60.0 (5) | 60.0 (5) | 60.0 (5) |
| calc | 28.6 (7) | 0.0 (7) | 0.0 (7) | 0.0 (7) | 0.0 (7) | 0.0 (7) | 14.3 (7) | 0.0 (7) | 0.0 (7) | 0.0 (7) | 0.0 (7) | 14.3 (7) |
| cell | 80.0 (10) | 0.0 (10) | 10.0 (10) | 0.0 (10) | 0.0 (10) | 0.0 (10) | 10.0 (10) | 20.0 (10) | 0.0 (10) | 10.0 (10) | 20.0 (10) | 10.0 (10) |
| text_table | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 0.0 (6) | 16.7 (6) | 16.7 (6) | 0.0 (6) | 0.0 (6) |
| unit_period | 75.0 (4) | 0.0 (4) | 0.0 (4) | 0.0 (4) | 0.0 (4) | 0.0 (4) | 0.0 (4) | 50.0 (4) | 25.0 (4) | 25.0 (4) | 25.0 (4) | 50.0 (4) |


<!-- results:chem:end -->

### 6.3 해석

> **2차 시도 이후의 읽는 법**: 이 절의 해석은 **1차 모델**(화학 SFT가 최종)의 결과를 설명한다. 2차에서 고친 것과 2차 최종 모델(RL v3)의 수치는 §18에 있고, 위 표는 두 차수의 모델을 한 표에 함께 보여 준다(`[2차]` 접두어).


1. **분포 안(합성 dev 80)에서는 확실히 올랐다**: <!-- num:experiments/eval/sft_ko2_chem_syndev/metrics.json:metrics.verified_em:pct -->22.5<!-- /num -->% → <!-- num:experiments/eval/sft_chem_chem_syndev/metrics.json:metrics.verified_em:pct -->41.2<!-- /num -->%. 그러나 합성 dev는 학습 데이터와 같은 템플릿이라 일반화 증거가 아니다.
2. **손으로 쓴 32문항에서는 유의한 개선이 아니다**: <!-- num:experiments/eval/sft_ko2_chem_custom/metrics.json:metrics.verified_em:pct -->9.4<!-- /num -->% → <!-- num:experiments/eval/sft_chem_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num -->%(32문항 중 2문항 차이, 1 표준오차 약 6%p). 기준선 <!-- num:experiments/eval/heuristic_chem_custom/metrics.json:metrics.verified_em:pct -->56.2<!-- /num -->%가 모든 모델보다 높다. **참고로 모든 입력을 보류하는 미튜닝 모델도 <!-- num:experiments/eval/base_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num -->%(보류가 정답인 5문항)라, 화학 SFT는 이 자명한 점수와 같은 값이다.** 즉 이 평가셋에서는 화학 SFT가 "아무것도 하지 않는 시스템"보다 낫다는 증거가 없다.
3. **모델이 인용한 근거 셀의 정확도**는 화학 SFT 후 <!-- num:experiments/eval/sft_chem_chem_custom/metrics.json:metrics.evidence_cells_exact_raw:pct -->22.2<!-- /num -->%(32문항 중 답이 있는 문항 기준)로 낮고, 보류 재현율은 <!-- num:experiments/eval/sft_chem_chem_custom/metrics.json:metrics.abstain_recall:pct -->60.0<!-- /num -->%(5문항 중)다.
4. **수치·단위 오류**: 계산 문항에서 단위가 틀린 비율은 정의상 계산 결과가 나온 문항에서만 계산된다(`unit_error_rate` = <!-- num:experiments/eval/sft_chem_chem_custom/metrics.json:metrics.unit_error_rate:pct -->0.0<!-- /num -->%). 계산이 거의 성립하지 않아 이 값은 표본이 너무 작아 의미가 없다. lookup 답은 셀 텍스트와 단위를 그대로 가져오므로 단위 오류는 곧 셀 오류로 나타난다. 단위 환산(원↔억원, kPa↔atm)은 지원하지 않는다.
5. **한국어에 대한 부작용 가능성**: 화학 SFT 후 한국어 수작업 30문항의 점수가 <!-- num:experiments/eval/sft_ko2_ko_custom/metrics.json:metrics.verified_em:pct -->23.3<!-- /num -->% → <!-- num:experiments/eval/sft_chem_ko_custom/metrics.json:metrics.verified_em:pct -->3.3<!-- /num -->%로 떨어지고 보류 재현율이 <!-- num:experiments/eval/sft_chem_ko_custom/metrics.json:metrics.abstain_recall:pct -->0.0<!-- /num -->%가 되었다(표본 30이라 확정은 못 한다). 한국어 독립 test(539+160)는 오히려 올랐다. 보류 행동은 학습 데이터 구성에 민감한 것으로 보인다.
6. **본문 근거(문장)**: `text_table` 범주는 모든 모델이 0%다. 한국어와 마찬가지로 모델은 화학 문서에서 `op: text`를 한 번도 내지 않았다(원인은 §5.4의 8번).

## 7. 강화학습 — 방법·조건·비교

### 7.1 방법

> **2차 시도 이후의 읽는 법**: 이 절의 해석은 **1차 모델**(화학 SFT가 최종)의 결과를 설명한다. 2차에서 고친 것과 2차 최종 모델(RL v3)의 수치는 §18에 있고, 위 표는 두 차수의 모델을 한 표에 함께 보여 준다(`[2차]` 접두어).


GRPO 방식 정책 경사를 PyTorch로 직접 구현했다(TRL은 쓰지 않았다. GRPOTrainer는 causal LM 기준으로 알려져 있어 mT5에 시험하지 않고 같은 수식을 직접 구현했다). 프롬프트 4개 × 샘플 G=4, 샘플링 temperature 1.0, 보상은 검증기 기반(정답, 근거 셀 일치, 연산 일치, 보류의 적절성). 이점은 그룹 내 평균·표준편차 정규화, 손실은 −A·log π + β·KL(k3 추정, 참조=SFT stage 2 모델), β=0.02, lr 1e-5, 60 step, on-policy 1회 업데이트. 이것은 샘플링→보상→정책 업데이트를 실제로 수행한 강화학습이며 DPO 같은 선호 학습이나 SFT가 아니다. 설계 문서: docs/experiments/rl.md.

### 7.2 실행 이력 — 두 번의 수정

1. **첫 시도(NaN)**: step 1의 KL이 770, 이후 3×10⁶으로 폭발하다 NaN으로 종료. 원인은 정책만 dropout이 켜진 학습 모드로 로그확률을 계산한 것(참조는 평가 모드). 평가 모드로 고쳐 KL이 0.0에서 시작함을 확인(§13의 23번).
2. **보상 편법 발견(v1)**: 수정한 첫 정상 실행(v1)에서 보상이 거의 오르지 않는 동안 정책이 이동했다. 아래 v1 표에서 모델의 명시적 abstain은 소폭 늘었지만 최종 보류율이 더 크게 올랐고, 출력이 lookup에서 diff로 옮겨 갔다. 원인은 보상 함수가 "답 없는 문항에서 최종 상태가 보류면 +1.0"으로 채점해서, **검증기가 거부한 쓰레기 프로그램(같은 셀 두 번, 범위 밖 셀)이 의도적 보류와 같은 점수**를 받은 것이다. v1 산출물은 증거로 보존했다(`experiments/rl_ko_v1/`).
3. **v2 보상**: 모델이 직접 `op: abstain`을 낸 경우만 +1.0, 검증기가 잡은 근거 없는 제안 +0.2, 해석 불가·퇴화 프로그램 0.0(답이 있는 문항에서는 −0.5). 회귀 테스트가 이를 고정한다. v2는 SFT stage 2 모델에서 처음부터 다시 학습했다.

### 7.3 v1 (편법 보상) 학습 곡선

<!-- results:rl_v1:start -->
| 구간(step) | 평균 보상 | 샘플 정답률 % | 샘플 최종 보류율 % | 모델이 명시적으로 abstain한 비율 % | lookup 비율 % | diff 비율 % | KL | 그룹 분산 0 비율 % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1–15 | 0.019 | 28.8 | 63.3 | 7.5 | 59.2 | 26.7 | 0.0008 | 18.3 |
| 16–30 | 0.005 | 24.2 | 57.5 | 5.8 | 45.0 | 40.0 | 0.0041 | 18.3 |
| 31–45 | -0.007 | 25.8 | 60.0 | 5.4 | 41.7 | 44.2 | 0.0116 | 20.0 |
| 46–60 | 0.057 | 28.4 | 70.8 | 12.1 | 35.4 | 45.4 | 0.0157 | 25.0 |

dev verified EM(n=245): step 0: 28.2% → step 20: 30.2% → step 40: 26.5% → step 60: 24.1%

**평가에 쓴 체크포인트: step 20** (dev 최고로 선택; 마지막 step이 아님). 60 step wall time 29 min, CPU 4스레드.

<!-- results:rl_v1:end -->

### 7.4 v2 (수정한 보상) 학습 곡선

<!-- results:rl:start -->
| 구간(step) | 평균 보상 | 샘플 정답률 % | 샘플 최종 보류율 % | 모델이 명시적으로 abstain한 비율 % | lookup 비율 % | diff 비율 % | KL | 그룹 분산 0 비율 % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1–15 | -0.165 | 13.7 | 63.3 | 7.5 | 60.0 | 25.4 | 0.0007 | 13.3 |
| 16–30 | -0.209 | 9.2 | 59.6 | 8.8 | 45.4 | 38.8 | 0.0039 | 13.3 |
| 31–45 | -0.121 | 15.8 | 59.6 | 10.4 | 40.0 | 36.2 | 0.0053 | 10.0 |
| 46–60 | -0.100 | 16.2 | 61.7 | 15.0 | 43.8 | 32.1 | 0.0092 | 8.3 |

dev verified EM(n=245): step 0: 28.2% → step 20: 30.2% → step 40: 30.6% → step 60: 30.6%

**평가에 쓴 체크포인트: step 60** (dev 최고가 마지막 step과 일치). 60 step wall time 32 min, CPU 4스레드.

<!-- results:rl:end -->

### 7.5 비교 — 기본 / SFT / RL (동일 독립 평가셋)

위 §5.3, §6.2 표의 "SFT stage2", "GRPO RL v1", "GRPO RL v2" 행이 같은 평가셋·같은 검증기 결과다. RL의 출발점은 SFT stage 2이므로 비교 대상은 그 행이다.

**v2 결과 요약 — 개선이라고 말할 수 없다.**

| 지표 | SFT stage 2 | RL v1(편법 보상) | RL v2(수정 보상) |
|---|---:|---:|---:|
| 한국어 test 699문항 verified EM % | <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.verified_em:pct -->27.5<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_test/metrics.json:metrics.verified_em:pct -->26.8<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_test/metrics.json:metrics.verified_em:pct -->27.0<!-- /num --> |
| 오보류율 % | <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.false_abstain_rate:pct -->31.0<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_test/metrics.json:metrics.false_abstain_rate:pct -->37.9<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_test/metrics.json:metrics.false_abstain_rate:pct -->35.9<!-- /num --> |
| 퇴화 계산 출력(건) | <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:degenerate_calc_outputs:int -->101<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:degenerate_calc_outputs:int -->160<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_test/analysis.json:degenerate_calc_outputs:int -->146<!-- /num --> |
| 모델이 직접 낸 `op: abstain`(건) | <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->0<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->0<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->6<!-- /num --> |
| └ 그중 답이 있는 문항에서 낸 것(건) | <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:abstain_breakdown.explicit_abstain_on_answerable:int -->0<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:abstain_breakdown.explicit_abstain_on_answerable:int -->0<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_test/analysis.json:abstain_breakdown.explicit_abstain_on_answerable:int -->6<!-- /num --> |
| 한국어 수작업 30문항 verified EM % | <!-- num:experiments/eval/sft_ko2_ko_custom/metrics.json:metrics.verified_em:pct -->23.3<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_ko_custom/metrics.json:metrics.verified_em:pct -->20.0<!-- /num --> | <!-- num:experiments/eval/rl_ko_ko_custom/metrics.json:metrics.verified_em:pct -->20.0<!-- /num --> |
| 화학 수작업 32문항 verified EM % | <!-- num:experiments/eval/sft_ko2_chem_custom/metrics.json:metrics.verified_em:pct -->9.4<!-- /num --> | <!-- num:experiments/eval/rl_ko_v1_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num --> | <!-- num:experiments/eval/rl_ko_chem_custom/metrics.json:metrics.verified_em:pct -->12.5<!-- /num --> |

1. **test 차이는 잡음 범위다.** 699문항에서 verified EM의 1 표준오차는 약 1.7%p이고 SFT stage 2와 v2의 차이는 그보다 작다. 수작업 30·32문항의 차이는 1–3문항이다.
2. **오보류가 늘었다.** 답이 있는 문항을 보류하는 비율이 SFT stage 2보다 높다. 원인은 검증하지 않았다.
3. **dev에서는 올랐으나 test로 전이되지 않았다.** dev 245문항(체크포인트 선택에도 사용)의 verified EM <!-- num:experiments/rl_ko/summary.json:dev_history.0.verified_em:pct -->28.2<!-- /num -->% → <!-- num:experiments/rl_ko/summary.json:dev_history.3.verified_em:pct -->30.6<!-- /num -->%. 이 분할의 1 표준오차는 약 2.9%p이고 선택에 쓰였으므로 낙관적이다.
4. **보상 편법 분석.** v1은 쓰레기 프로그램이 보류 점수를 받았다(§7.2). v2는 이를 막았지만 퇴화 계산 출력이 SFT stage 2보다 많고, §7.4 표의 diff 비율이 보여 주듯 lookup에서 diff로의 정책 이동도 남았다. 보상이 검증기 판정에 의존하므로 검증기가 못 보는 것(질문 대상과 셀의 일치, §5.4)은 보상으로도 학습되지 않는다.
5. **보류 학습은 평가로 전이되지 않았다.** 샘플링 중 명시적 abstain 비율은 올랐지만 탐욕 디코딩 평가에서 답 없는 문항에 직접 낸 `op: abstain`은 0건이고, 낸 것은 모두 답이 있는 문항이었다.
6. **원인은 검증하지 않았다(추정).** 총 샘플 960개(60 step × 4 프롬프트 × 4 샘플), 낮은 샘플 정답률로 인한 희박한 보상, 그룹 내 보상이 같아 신호가 없는 그룹(§7.4 표). 더 긴 학습, β·학습률·보상 크기 조정은 하지 않았다.

**상태 판단(1차 시점)**: 구현·정책 갱신·동일 평가셋 비교까지 수행했으나 목표(검증된 정답률 향상, 올바른 보류)를 달성하지 못해 1차 보고에서는 **실행했으나 실패**로 적었다. 2차의 RL v3(§18)가 본문 근거 없음 문항의 직접 보류를 학습해 공고 대조표는 **완료(부분 개선)**로 바꿨다. 두 결과 모두 "강화학습으로 ko test 점수를 올렸다"는 주장을 뒷받침하지 않는다.


## 8. 추론 최적화 — 조건과 측정

선택 이유: GPU가 없어 CUDA 전용 엔진(vLLM·SGLang·TensorRT-LLM)을 쓸 수 없다. CPU에서 효과를 기대할 수 있는 방법만 적용·측정했다. (a) **KV 캐시**(디코딩 비용 O(T²)→O(T)), (b) **배치 처리**, (c) **int8 동적 양자화**(`nn.Linear` 가중치). 정밀도마다 **별도 프로세스**에서 측정해 메모리를 분리했다. 모든 값은 `experiments/bench/inference.json`에서 가져온다.

<!-- results:bench:start -->
조건: models/mt5-small-tabletrace(1차 최종 모델), 입력 48개(ko test), max_new_tokens 48, 워밍업 1라운드 + 측정 2라운드, 4 스레드, 4 cores x86_64, torch 2.15.0+cu132, CUDA False. 정밀도마다 **별도 프로세스**에서 측정(메모리 비교를 위해). 양자화 준비 시간 int8 8.3s. 모델 실행 조건은 위와 같고 **양자화 범위**는 설정 이름의 `int8`(모든 Linear, lm_head 포함) 또는 `int8-<범위>`(일부)로 구분합니다.

| 설정 | p50 ms | p95 ms | 처리량 예제/s | 모델 파일 MB | 프로세스 peak RSS GB | fp32 bs=1과 출력 문자열 일치 % |
|---|---:|---:|---:|---:|---:|---:|
| fp32, bs=1, kv-cache on | 995.7 | 1484.1 | 0.985 | 1200.8 | 3.38 | 100.0 |
| fp32, bs=8, kv-cache on | 446.9 | 555.2 | 2.196 | 1200.8 | 3.38 | 100.0 |
| fp32, bs=1, kv-cache OFF | 2736.9 | 3674.2 | 0.356 | 1200.8 | 3.38 | 100.0 |
| int8, bs=1, kv-cache on | 594.1 | 729.0 | 1.676 | 684.6 | 3.73 | 35.4 |
| int8, bs=8, kv-cache on | 273.4 | 333.1 | 3.66 | 684.6 | 3.73 | 22.9 |

<!-- results:bench:end -->

읽는 법과 주의:

1. **KV 캐시는 필수다**: 끄면 p50이 <!-- num:experiments/bench/inference.json:results.0.p50_ms -->995.7<!-- /num --> ms → <!-- num:experiments/bench/inference.json:results.2.p50_ms -->2,736.9<!-- /num --> ms(약 2.7배 느림)로 늘어난다.
2. **배치 처리는 처리량을 약 2.2배 올린다**(fp32 bs=1 <!-- num:experiments/bench/inference.json:results.0.throughput_ex_per_s -->0.985<!-- /num --> → bs=8 <!-- num:experiments/bench/inference.json:results.1.throughput_ex_per_s -->2.2<!-- /num --> 예제/s).
3. **int8 동적 양자화는 빠르고 파일이 작지만 정확도를 크게 해친다.** 파일 <!-- num:experiments/bench/inference.json:results.0.state_dict_mb -->1,200.8<!-- /num --> MB → <!-- num:experiments/bench/inference.json:results.3.state_dict_mb -->684.6<!-- /num --> MB(공유 임베딩 250k×512는 fp32로 남아 절반에 못 미침. 1차에는 lm_head도 fp32로 남는다고 적었으나 틀렸고 lm_head는 int8이다, §18.2). 처리량은 bs=8에서 <!-- num:experiments/bench/inference.json:results.1.throughput_ex_per_s -->2.2<!-- /num --> → <!-- num:experiments/bench/inference.json:results.4.throughput_ex_per_s -->3.66<!-- /num --> 예제/s. **그러나 출력 문자열이 fp32와 일치하는 비율은 bs=1에서 <!-- num:experiments/bench/inference.json:results.3.agreement_with_fp32_bs1:pct -->35.4<!-- /num -->%뿐이고, 평가셋 점수도 한국어 독립 test verified EM <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->% → <!-- num:experiments/eval/sft_chem_int8_ko_test/metrics.json:metrics.verified_em:pct -->17.7<!-- /num -->%, lookup EM <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.lookup_em:pct -->37.1<!-- /num -->% → <!-- num:experiments/eval/sft_chem_int8_ko_test/metrics.json:metrics.lookup_em:pct -->18.6<!-- /num -->%로 떨어지고 오보류율이 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.false_abstain_rate:pct -->19.4<!-- /num -->% → <!-- num:experiments/eval/sft_chem_int8_ko_test/metrics.json:metrics.false_abstain_rate:pct -->55.3<!-- /num -->%로 뛴다.** 작은 수작업 평가셋(30·32문항)에서는 오히려 올라가지만(보류가 늘어 보류 문항이 맞는 효과) 표본이 작고 같은 방향의 개선으로 읽으면 안 된다. 따라서 이 모델에서 int8 동적 양자화는 **공짜 최적화가 아니다.** 선택적 양자화는 2차에서 시도했다(§18.2): `lm_head`만 int8이면 정확도 손실이 검출되지 않고 속도 이득의 대부분을 얻는다. 정적 양자화는 시도하지 않았다.
4. **메모리**: 프로세스 최대 RSS는 fp32 <!-- num:experiments/bench/inference.json:results.0.peak_rss_gb -->3.38<!-- /num --> GB, int8 <!-- num:experiments/bench/inference.json:results.3.peak_rss_gb -->3.73<!-- /num --> GB로 **int8이 오히려 크다.** `quantize_dynamic`이 fp32 모델을 먼저 올린 뒤 변환하기 때문에 최대치에 두 모델이 겹친다. 서빙 시 상주 메모리를 줄이려면 양자화된 가중치를 파일에서 직접 로드해야 하며 구현하지 않았다.
5. **변동성**: 공유 VM이라 같은 설정의 p50이 실행마다 20% 이상 달라질 수 있다(앞선 오염된 실행에서 fp32 bs=1 p50이 이번보다 약 25% 낮게 관측되었다). 단일 실행의 절대값이 아니라 설정 간 비율을 보라. 반복은 측정 2라운드(워밍업 1)뿐이라 신뢰구간은 구하지 않았다.
6. **실행하지 않은 것**: GPU 지연·메모리(mT5), 그 외 양자화(GPTQ/AWQ), 컴파일(torch.compile), ONNX. 이것들은 성능을 주장하지 않는다. vLLM 서빙은 EXAONE 모델로 2차에서 실행했고(§18.3), SGLang은 T4에서 실패했다.

## 9. 멀티 GPU Model Parallelism — 방식·환경·결과

**작성자는 CPU 2프로세스 기능 검증까지 했고, GPU 2장 실측은 소유자가 Kaggle에서 같은 코드를 돌려 보낸 파일이다**(아래 GPU 표, `experiments/bench/pp_*_gpu.json`). 이 컨테이너에는 GPU가 없다(`nvidia-smi` 없음, `torch.cuda.is_available()`=False).

- **방식**: 2-스테이지 **파이프라인 모델 병렬**(`bench/pipeline_parallel.py`). rank 0이 인코더(공유 임베딩 포함), rank 1이 디코더+lm_head를 들고, rank 0이 인코딩한 hidden state를 `torch.distributed` `send/recv`로 rank 1에 보내면 rank 1이 greedy 디코딩 후 토큰 id를 돌려준다. 한 모델을 두 프로세스에 나눈 것이며, GPU마다 모델을 복제하는 DDP가 아니다.
- **환경**: CPU 4코어, 백엔드 `gloo`, 프로세스당 2 스레드. 모델은 mT5-small 화학 SFT 모델.

<!-- results:pp:start -->
조건: CPU(gloo), n=16, bs=8, 단일 프로세스 300,176,768 파라미터

| 구성 | 장치 | 스테이지 파라미터 | 처리량 예제/s | 메모리 MB | 평균 배치 지연 s |
|---|---|---:|---:|---:|---:|
| 단일 프로세스 | cpu | 300,176,768 | 1.472 | 1747 | 5.44 |
| 파이프라인 rank0 (encoder) | cpu | 146,940,608 | 1.46 | 1159 | 5.47 |
| 파이프라인 rank1 (decoder+lm_head) | cpu | 281,293,504 |  | 1618 | 5.47 |

단일 프로세스와 2-스테이지의 생성 출력 일치: **예** (16개 입력)

<!-- results:pp:end -->

**GPU 실측(2026-11-07, 소유자가 Kaggle T4 2장에서 실행, 원본 `google/mt5-small`, 입력 64개)**: 같은 코드를 NCCL로 돌린 값이다. 출력은 단일 GPU와 일치했고 처리량 이득은 없다(두 스테이지가 겹치지 않음). 장치당 메모리는 나뉜다.

<!-- results:pp_gpu:start -->
조건: Kaggle Tesla T4 ×2(nccl), 소유자 실행 2026-11-07, 원본 google/mt5-small, n=64, bs=8, 단일 프로세스 300,176,768 파라미터

| 구성 | 장치 | 스테이지 파라미터 | 처리량 예제/s | 메모리 MB | 평균 배치 지연 s |
|---|---|---:|---:|---:|---:|
| 단일 프로세스 | cuda:0 | 300,176,768 | 11.145 | 1376 | 0.72 |
| 파이프라인 rank0 (encoder) | cuda:0 | 146,940,608 | 14.029 | 763 | 0.56 |
| 파이프라인 rank1 (decoder+lm_head) | cuda:1 | 281,293,504 |  | 1265 | 0.56 |

단일 프로세스와 2-스테이지의 생성 출력 일치: **예** (64개 입력)

<!-- results:pp_gpu:end -->

- **분할 확인**: rank 0은 파라미터 <!-- num:experiments/bench/pp_2stage.json:stages.0.stage_params:int -->146,940,608<!-- /num -->개(인코더+임베딩), rank 1은 <!-- num:experiments/bench/pp_2stage.json:stages.1.stage_params:int -->281,293,504<!-- /num -->개(디코더+임베딩+lm_head)를 가졌다. 합이 전체 300,176,768보다 큰 것은 공유 임베딩(약 1.28억)이 인코더 입력과 디코더 입력에 모두 필요해 **양쪽에 복제**되었기 때문이다. 나머지 레이어는 분할되었다.
- **정확성**: 같은 16개 입력에서 단일 프로세스와 2-스테이지의 생성 출력이 **모두 일치**했다.
- **성능**: 처리량 이득 **없음**(단일 <!-- num:experiments/bench/pp_single.json:throughput_ex_per_s -->1.47<!-- /num --> vs 2-스테이지 <!-- num:experiments/bench/pp_2stage.json:throughput_ex_per_s -->1.46<!-- /num --> 예제/s). 두 프로세스가 같은 4코어를 나눠 쓰고 마이크로배치 파이프라이닝이 없어 스테이지가 순차 실행되므로 예상된 결과이며, 이 실험은 속도를 보이려는 것이 아니다.
- **GPU 실측**(T4 ×2, NCCL, 네 세션): 단일 GPU <!-- num:experiments/bench/pp_single_gpu_run1.json:throughput_ex_per_s -->14.61<!-- /num --> / <!-- num:experiments/bench/pp_single_gpu_run2.json:throughput_ex_per_s -->11.46<!-- /num --> / <!-- num:experiments/bench/pp_single_gpu_run3.json:throughput_ex_per_s -->5.94<!-- /num --> / <!-- num:experiments/bench/pp_single_gpu.json:throughput_ex_per_s -->11.14<!-- /num --> 예제/s 대 2-스테이지 <!-- num:experiments/bench/pp_2stage_gpu_run1.json:throughput_ex_per_s -->15.03<!-- /num --> / <!-- num:experiments/bench/pp_2stage_gpu_run2.json:throughput_ex_per_s -->14.88<!-- /num --> / <!-- num:experiments/bench/pp_2stage_gpu_run3.json:throughput_ex_per_s -->14.1<!-- /num --> / <!-- num:experiments/bench/pp_2stage_gpu.json:throughput_ex_per_s -->14.03<!-- /num --> 예제/s(네 세션 순). 단일 GPU <!-- num:experiments/bench/pp_single_gpu.json:mem_mb:int -->1,376<!-- /num --> MB, 2-스테이지 rank0 <!-- num:experiments/bench/pp_2stage_gpu.json:stages.0.mem_mb:int -->763<!-- /num --> MB + rank1 <!-- num:experiments/bench/pp_2stage_gpu.json:stages.1.mem_mb:int -->1,265<!-- /num --> MB, 64개 입력의 출력 일치(네 번 모두). 2-스테이지는 네 번 다 14~15 예제/s인데 단일 GPU 측정이 세션마다 달라(엔진 서버 직후의 잔여 부하 가능성) 처리량 이득은 주장하지 않는다. 설계상 스테이지가 겹치지 않아 이득이 있을 이유도 없다. 300M 모델은 한 장에 들어가므로 이 분할은 필요가 아니라 기능 검증이다. 비용은 Kaggle 무료 GPU. vLLM 텐서 병렬 TP=2(처리량 약 1.6~2.2배)는 §18.3.

## 10. 테스트와 반복 검증

| 검증 | 방법 | 실행 횟수·결과 |
|---|---|---|
| 데이터 출처·라이선스 | 저장소 LICENSE·README를 직접 확인, docs/research/datasets.md | 1회 기록 |
| 데이터 분할·누수 | `scripts/check_data.py`: 표·문서 공유 0, 수작업·합성 정답의 자동 검수 | 데이터를 만들 때마다 실행, 마지막 실행 오류 0 |
| 평가 재현성 | 모든 평가가 `tabletrace.eval.run`으로 metrics.json + predictions.jsonl 생성. 평가 코드 수정 후 **모든 모델을 같은 코드로 다시 평가**(`scripts/train/finalize.sh`) | 플래너·모델 8종(기준선·미튜닝·SFT 3·RL 2·int8)을 한국어 test·한국어 수작업·화학 수작업 평가셋에서 재평가 |
| 단위·API 테스트 | `pytest -q tests`: 숫자·계산기·문법·검증기·휴리스틱·검색·API·엔진·학습 데이터·RL 보상·모델 | 최종 <!-- num:experiments/tests/summary.json:passed -->127<!-- /num -->개 통과, <!-- num:experiments/tests/summary.json:skipped -->8<!-- /num -->개 skip, <!-- num:experiments/tests/summary.json:failed -->0<!-- /num -->개 실패(모델 가중치가 없으면 모델 테스트는 skip) |
| 콘솔 E2E | Playwright, 데스크톱 1440×900·모바일 390×844 × 실시간/정적 모드 | 실시간 <!-- num:docs/images/e2e-summary.json:live.passed -->18<!-- /num -->/<!-- num:docs/images/e2e-summary.json:live.total -->18<!-- /num -->, 정적 <!-- num:docs/images/e2e-summary.json:static.passed -->21<!-- /num -->/<!-- num:docs/images/e2e-summary.json:static.total -->21<!-- /num --> 검사 통과 (`docs/images/e2e-*.json`). 이전 실행에서 실패 2회→수정→재실행 |
| Docker | 이미지 빌드 + 컨테이너 smoke(health, release, corpora, ask, 콘솔) | 빌드가 여러 번 실패(데몬 미실행, Docker Hub·ECR 429, 프록시 CA TLS 오류)한 뒤 성공, smoke 통과 |
| 학습 전후 비교 | 동일 test·custom 세트에서 미튜닝/SFT1/SFT2/RL v1/RL v2/화학 SFT/int8 평가 | §5–§8 |
| 추론 최적화 | 정밀도별 별도 프로세스, 워밍업 1 + 측정 2라운드, 양자화 모델의 정확도 평가 | §8. 첫 실행은 메모리 비교가 무효이고 측정 중 테스트를 돌려 오염되어 **폐기하고 재실행** |
| 병렬 | 2-스테이지 파이프라인의 출력이 단일 프로세스와 일치하는지 | §9 (smoke 1회 + 본 실행) |
| 검색 | 전체 표 대상 BM25 hit@1/5 | §3 표와 `experiments/eval/retrieval/metrics.json` |
| 문서 수치 | 본문 수치는 표식으로 산출물에 묶고, 표는 `render_results.py --check`로 대조. 값을 바꿔 넣으면 실패함을 시연 | `scripts/check_numbers.py --strict` |
| 반복 수정 | docs/dev/issues-log.md 36건: 발견 → 수정 → 재검증 | 아래 §13 |

실제 반복의 예: RL은 NaN 종료 → 수정 후 v1 완주 → 보상 편법 발견 → v2 재학습(실행 3회), 추론 벤치는 2회(첫 실행 폐기), E2E는 실패 후 수정·재실행을 반복, 평가 코드는 채점 방식 수정 후 모든 모델을 같은 코드로 재평가.

## 11. UI 조사와 디자인 반영

조사한 화면(docs/design/ui-research.md): Microsoft Document Intelligence 샘플 라벨링 도구(OCR Form Tools 스크린샷 4장 직접 확인), Google Document AI Workbench 제품 페이지, Label Studio, doccano, MLflow 트레이스 뷰·게이트웨이 대시보드, promptfoo 평가 표, Marker 벤치마크 차트, Tabula, PaddleOCR. 제품 문서 사이트 대부분이 차단되어 GitHub 공개 스크린샷·README와 Google Cloud 페이지를 썼다(확인하지 못한 화면은 문서에 "미확인"으로 표시).

**데모 배경 조사**: "AI가 흔히 만드는 데모 배경은 금지"라는 요구를 데모 화면의 바탕(캔버스)에 대한 것으로 해석하고, OCR Form Tools·MLflow(트레이스·평가)·promptfoo·doccano·Marker의 화면 7장을 새로 받아 바탕 색을 측정하고 그중 4장은 직접 열어 눈으로 확인했다(docs/design/ui-research.md "데모 배경 조사", 표본이 작다). 눈으로 본 4장은 모두 그라데이션·질감·블러 없이 단색 중립면 위에 실제 콘텐츠를 올렸고, 색은 상태·근거에만 썼다. Label Studio·Streamlit·Gradio는 이미지를 받지 못해 조사했다고 쓰지 않았다. TableTrace는 단색 `#f5f6f8` 바탕·흰 패널·1px 선에 실제 위키·교과서 표를 올리고, `tests/test_console_style.py`(5개)가 장식 배경의 재유입을 막는다. 다른 해석(데모 장면 구성)이 의도였는지는 확인하지 못했다.

| 관찰 | TableTrace 반영 (docs/design/screens.md, console/) |
|---|---|
| 3단(목록 / 문서 / 속성) 레이아웃이 공통 | 문서 목록 / 본문·표 / 질문·결과 3열, 모바일은 탭 |
| 문서 위 하이라이트와 오른쪽 필드가 색·번호로 짝지어짐 | 근거 셀에 노란 테두리+번호 배지, 오른쪽 근거 배지를 누르면 셀로 이동·강조, 본문 근거는 문장 하이라이트 |
| 예측값 옆 신뢰도·페이지 배지 | 모델 확률 대신 **검증기 판정**(통과 검사 수, 보류 사유)과 r/c 좌표 배지 |
| 긴 작업의 상태 바, PASS/FAIL 배지 | 대기→실행 중(경과 ms)→완료/보류/오류/시간 초과 상태 띠, 작업 ID, 429/422 메시지와 재시도 |
| 트레이스 트리 + 상세 탭 | 실행 추적 카드: LangGraph 노드·도구 호출·소요 ms, 입력/출력 펼치기, 플래너 원문 출력 |
| 평가 표 + 조건 요약 | 연구 결과 화면: 각 표 위에 실행 조건, 상태 필(완료/미실행/실패) |
| 튜토리얼식 첫 화면 | 4단계 안내 띠(닫기 가능) + 문서별 대표 질문 칩(범주 표시) |
| 실시간 vs 저장 결과 | 상단 배지와 결과 카드 배지로 구분, 저장 결과에는 기록 시각·모델·커밋. 저장 결과 모드는 모델/휴리스틱 두 결과를 플래너 선택으로 비교 |

피한 것: 큰 입력창만 있는 챗봇 화면, 그라데이션·장식, 의미 없는 카드 나열. 시스템 글꼴, 차분한 2색(남색·앰버).

## 12. README 참고 사례와 반영

SKN24-FINAL-3Team(ALPLED), SKN20-FINAL-6TEAM(bizi), SKN27-FINAL-1Team(밥벌이)을 clone해 README 구성을 비교했고 KorWikiTableQuestions, KLUE, ragas README도 읽었다(docs/research/readme-research.md). 반영: (1) 한 줄 정의·상태 요약·CI 배지를 맨 위(SKN27, ragas), (2) 실제 화면 이미지와 체험 순서를 바로 아래(SKN27의 영상 자리), (3) 핵심 기능을 기능·설명·구현 3열 표(SKN27), (4) 데이터 출처·라이선스·분할·누수 검사를 표와 수치로(KLUE·KorWikiTQ), (5) 결과 표마다 산출물 경로를 적고 미달 결과도 그대로 — SKN20의 단계별 성능 추적을 정직한 버전으로(후퇴·편법 포함), (6) 실패·한계·수행/미수행 표를 마지막에. 팀 소개·시장 규모·기술 스택 배지 나열은 넣지 않았다. 문구·디자인·코드는 복사하지 않았다.

## 13. 발견한 문제와 수정

전체 목록은 docs/dev/issues-log.md(번호 1–36). 큰 것을 모으면:

- **모델 변환(1–4)**: transformers 5에서 mT5 토크나이저 생성과 `tie_word_embeddings`가 달라 변환이 두 번 틀렸다(센티널 id·lm_head 분리로 해결, 디노이징 손실 50→5–7 nats로 검증).
- **데이터(5–8)**: 공개 분할의 표 누수 발견 → 표 단위 재분할, OpenStax 표 파싱 누락(18→56 문서), 단위 파서 오검출, 숫자 파서 오버플로.
- **휴리스틱·검증기(9–12, 26)**: 모호 판정 과다, 연산 의도 우선순위, 구절 일치 보너스, 숫자 부분 문자열 허점, 같은 셀 두 번 쓰는 퇴화 계산.
- **Agent(20)**: LangGraph가 상태 스키마에 없는 키를 버려 API 응답의 플래너 표시가 항상 휴리스틱이었고 보완 분기가 한 번도 실행되지 않았다.
- **RL(23–24)**: dropout 불일치로 KL이 폭발해 NaN 종료, 그리고 **보상 편법**(쓰레기 프로그램이 의도적 보류와 같은 점수)을 로그에서 발견해 v2로 수정·재학습.
- **평가(22, 25)**: 정답 행이 잘린 입력 위에서 채점하던 오류 수정, 전 모델 재평가. 모델이 열 좌표를 못 맞히는 약점은 검증기의 근거 복구와 별도 지표로 분리해 드러냈다.
- **지표·검증기 허점(30–32)**: README 사례를 예측 파일과 대조해 잘못 옮긴 좌표를 바로잡았고, 보류 재현율에 우연한 보류가 섞여 있음을 경로별 분석(`abstain_breakdown`)과 퇴화 계산 집계로 드러냈다. 표에 없는 대상에 엉뚱한 셀을 인용해 답해도 통과하는 검증기 허점은 **고치지 못하고** 한계로 남겼다.
- **2차 시도(33–36)**: 1차 문서의 "int8에서 lm_head는 fp32"가 틀렸음을 확인해 정정, 본문 재학습이 반대편 지름길(표 질문을 `op: text`로 보냄)을 만들어 표 조회 보강 epoch 추가, `pkill -f` 자기 종료 재발, 개체 일치 검사의 정답 프로그램 오탐을 매 평가에 기록하도록 지표 추가.
- **벤치(27)**: 메모리 비교 무효·측정 오염을 발견해 폐기하고 재측정.
- **E2E·운영(13–19, 21, 28–29)**: CSS `hidden` 우선순위, 모바일 탭 전환, 스크립트 크래시가 통과처럼 보이는 문제, `pkill -f` 자기 종료, 세션 워커 재시작으로 파이프라인 중단(→ 재시작 가능 파이프라인), Docker 레지스트리 429, README의 존재하지 않는 데모 주소 정정.

## 14. 실행하지 못한 작업과 이유

| 작업 | 이유 | 준비된 것 |
|---|---|---|
| (해결됨) tabletrace 원격 푸시 | 사용자가 GitHub를 다시 연결해 푸시됨 | 이전 `403`은 Claude GitHub App 미설치 때문이었다 |
| (해결됨) GitHub Actions 실행 | 푸시 후 실행·통과 | 위 §3 |
| (해결됨) GitHub Pages 접속 확인 | 소유자가 2026-11-08 브라우저에서 열리는 것을 확인 | 개발 컨테이너의 네트워크에서는 `github.io`가 차단되어 작성자는 Actions 성공 기록만 봄 |
| (해결됨) EXAONE 다운로드·튜닝·서빙 | 소유자가 Kaggle T4에서 노트북으로 실행(§18.3). 개발 컨테이너에서는 `huggingface.co` 차단·GPU 없음 | 결과 파일 수령(`train_info.json`, 예측 파일, 벤치). 전체 데이터 학습은 하지 않음 |
| (해결됨) 멀티 GPU 병렬 실측 | 소유자가 Kaggle T4 ×2에서 노트북 4번 절을 돌려 결과 파일을 보냄(§9, §18.3) | 작성자 쪽에는 GPU가 없어 직접 실행은 못 함. DDP는 하지 않음 |
| (해결됨) SGLang 실행 | T4는 SGLang 미지원(`sgl_kernel`에 sm75 커널 없음)이라 두 번 실패, 세 번째는 config.json 호환 문제. 우회 모듈과 설정 복원으로 네 번째에 성공(§18.3, `experiments/serving/sglang_t4_failure.md`) | Ampere 이상에서의 제 성능 측정은 하지 않음(유료 GPU) |
| (해결됨) 채용 공고 원문 확인 | 2026-11-09까지 `www.lgresearch.ai` 차단. 소유자가 허용 호스트에 추가해 2026-11-10에 읽음 | 원문 문구와 항목별 대응을 `docs/research/job-posting.md`에 기록. 원문에만 있는 항목은 §3 표 아래 |
| 논문·특허 기반 화학 데이터 | PMC·ChemRxiv·Google Patents 등 차단 | OpenStax 교과서 데이터 표 사용 |
| 외부 유료 API | `api.openai.com` 차단, 키 없음 | 사용 안 함 — 비용 0, 승인 필요한 실행 없음 |
| 본문 답변 정확도의 추가 개선 | 학습 예제 1,150개 규모에서 멈춤(시간) | 2차에서 `op: text` 선택은 고쳤고 정확도는 낮음(§18). KorQuAD 6만 개 중 일부만 사용 |
| 정적 양자화·GPTQ/AWQ | 시간·환경(CPU) | 2차에서 동적 int8의 **부분 양자화**(범위별)는 측정함(§8, §18) |

## 15. 남은 한계

1. **성능**: 어휘 겹침 기준선(<!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->%)을 전체 평가에서 이기지 못했다(최종 모델 <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->%). 원본 lookup 539문항에서는 이긴다(<!-- num:experiments/eval/rl_v3_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->38.2<!-- /num -->% 대 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->26.2<!-- /num -->%). 계산·단위/기간은 약하다(§5.4).
2. **좌표 생성**: 최종 모델이 인용한 셀의 열은 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:lookup_citation.col_correct:pct -->30.8<!-- /num -->%만 맞다(행은 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:lookup_citation.row_correct:pct -->91.8<!-- /num -->%). 검증기의 근거 복구가 점수를 지탱하며, 복구는 답 텍스트가 표에서 유일할 때만 된다.
3. **본문 답변**: 1차의 `op: text` 지름길(학습 데이터 결함)은 2차에서 고쳤지만, 실제 표 옆 본문 질문 100개 중 최종 모델이 맞힌 것은 <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:text_answers.verified_correct:int -->26<!-- /num -->개다. 학습 예제 1,150개로는 답 구간 선택이 부족하다.
4. **보류**: RL v3가 직접 보류를 학습했지만(ko test 답 없는 문항의 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->42.0<!-- /num -->%), 정답이 있는 문항에도 직접 보류가 많아(<!-- num:experiments/eval/rl_v3_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->131<!-- /num -->건 중 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:abstain_breakdown.explicit_abstain_on_answerable:int -->110<!-- /num -->건) 전체 점수는 그대로다. 검증기 v2의 개체 일치 검사는 정답 프로그램의 <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.gold_subject_fail_rate:pct -->4.3<!-- /num -->%를 오탐으로 보류하고, 영어는 화학식만 검사한다.
5. **계산**: 두 셀 간 차·합·평균·비율·증감률만, 단위 환산·집계·argmax 없음.
6. **입력 예산 512 토큰**: test의 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.truncated_gold_rate:pct -->8.9<!-- /num -->%는 정답 행이 잘려 원리적으로 맞힐 수 없다. 다중 표·긴 표 질문 미지원.
7. **데이터**: 합성 계산·보류는 템플릿이라 표현이 단조롭고 기준선에 유리한 편향이 있다. 화학은 논문이 아니라 교과서 표다. 수작업 평가는 한국어 30·화학 32문항으로 1 표준오차가 6–9%p다.
8. **검색**: BM25만. 문서를 지정하지 않으면 한국어 질문의 약 <!-- num:experiments/eval/retrieval/metrics.json:ko_test_lookup.hit_at_1:pct -->80.0<!-- /num -->%만 첫 번째 표가 맞다(hit@1). 문서 지정 없는 엔드투엔드 정확도는 측정하지 않았다.
9. **int8 양자화**: 모든 층 int8은 정확도를 해친다(<!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->% → <!-- num:experiments/eval/final_int8_all_ko_test/metrics.json:metrics.verified_em:pct -->21.2<!-- /num -->%). `lm_head`만 int8은 ko test에서 손실이 검출되지 않지만 본문 테스트에서는 fp32가 <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_text2_test.reference_better:int -->6<!-- /num -->문항, int8이 <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_text2_test.candidate_better:int -->1<!-- /num -->문항 더 맞혔다(비유의). 정확도 확인은 CPU에서만 했다(§8, §18.2).
10. **하드웨어**: mT5 수치는 CPU 4코어 단일 환경이다. 지연 시간은 공유 VM이라 실행마다 20% 이상 변동한다. GPU 실측은 소유자가 Kaggle T4에서 돌린 EXAONE+vLLM(1장·TP=2)과 mT5 파이프라인 병렬 각 1회다(§9, §18.3).
11. **RL**: 120 step·시드 1개의 예비 실험이다. 보상은 검증기가 정의하므로 검증기의 허점이 곧 보상 허점이다(1차에서 실제로 발생). v3의 이득은 본문 근거 없음 문항의 직접 보류에 한정되고 ko test 전체 점수는 그대로다(§18). 시드 반복을 하지 않아 이득의 재현성은 모른다.
12. **배포**: Pages는 저장된 결과만 보여 주고 실시간 모드는 호스팅하지 않는다. 배포된 페이지는 이 세션에서 열어 확인하지 못했다.

## 16. 사용자가 데모를 직접 확인하는 순서

**A. 저장소**: <https://github.com/sokldjs554/tabletrace> 를 클론하면 됩니다. 모델 가중치는 git에 없으므로 모델 플래너 실행과 재현은 scripts/train/README.md를 따릅니다.

**B0. 지금 바로 보기(저장된 실행 결과)**: <https://claude.ai/artifact/KvdrLkxC8PbSLWmpLvBPDM> (비공개 링크: 소유자 계정으로 열거나 공유 설정을 켠 뒤 다른 사람에게 보냄). 화면 위쪽 배지가 "저장된 실행 결과"인지 확인하고, 문서를 고른 뒤 대표 질문을 눌러 보고, 오른쪽 패널에서 플래너를 "모델"과 "휴리스틱"으로 바꿔 같은 질문의 결과를 비교한다. 모델 결과에는 틀린 답도 그대로 들어 있다(예: 안시성의 관객수에 날짜 열의 값을 답하면서 검증기가 셀과 답의 일치만 확인해 통과시킨 경우).

**B. 공개 데모(GitHub Pages)**: <https://sokldjs554.github.io/tabletrace/> (main 푸시 → Actions `pages` 워크플로가 `console/` + 저장된 실행 결과를 배포한다. 저장소 Settings → Pages → Source가 "GitHub Actions"인지 확인한다)

**C. 로컬 실시간 실행**:
```bash
pip install -e ".[model,dev]" && pytest -q       # 테스트
tabletrace serve                                  # models/mt5-small-tabletrace 가 있으면 모델 플래너(없으면 휴리스틱)
# 또는: docker compose up --build   (휴리스틱)   /   WITH_MODEL=1 docker compose up --build   (모델)
```
모델 가중치(`models/`, `experiments/*/model`)는 git에 없다. 재학습 명령은 scripts/train/README.md.

**D. 화면에서 볼 것**: ① 한국어 표 → 「2018년 한국영화 박스 오피스」 → 대표 질문 7개 ② 근거 배지 클릭 → 셀 강조 ③ 계산 카드의 입력 값·단위 ④ 보류 질문의 사유 ⑤ 영어 화학 문서 → 「Phase Diagrams」「Non-Ideal Gas Behavior」「Rate Laws」 ⑥ **플래너 선택을 바꿔 같은 질문의 결과를 비교**(공개 데모에는 EXAONE 저장 출력, mT5, 휴리스틱이 있다. 「국도 1호 자동차 전용도로 구간」의 본문 질문을 EXAONE으로 열면 모델이 인용한 셀과 검증기가 고친 근거 셀이 따로 표시된다) — 모델은 답이 없는 질문에도 답하는 사례와 근거 복구(검사 목록에 ✗로 표시) 사례가 보이고, 휴리스틱은 보류하는 사례가 보인다 ⑦ 연구 결과 탭 ⑧ 작동 방식 탭의 그래프와 신뢰 경계.

**E. 수치 확인**: `experiments/eval/*/metrics.json`(지표), `predictions.jsonl`(문항별 모델 원문 출력·예측 셀·검사), `analysis.json`(오류 분석), `experiments/*/train_log.jsonl`(학습 곡선), `experiments/bench/*.json`, `docs/images/e2e-*.json`, `python scripts/check_numbers.py --strict && python scripts/render_results.py --check`.

## 17. 자소서·포트폴리오 작성 시 확인 가능한 사실과 수치

모든 수치는 위 표식으로 산출물에 묶여 있다. **한 줄 요약**: 한국어 표·영어 화학 문서에서 답과 근거·계산을 검증하는 파이프라인(검색→모델 제안→도구 실행→검증→보류)을 직접 설계·구현하고, 300M 모델을 CPU에서 튜닝·강화학습해 **그 결과가 기준선을 못 넘는다는 것까지 정직하게 측정·분석**했고, 같은 데이터로 EXAONE-4.0-1.2B를 LoRA 튜닝해 GPU에서 vLLM·SGLang·텐서 병렬로 서빙한 모델이 같은 test에서 <!-- num:experiments/eval/exaone_full_vllm_ko_test/metrics.json:metrics.verified_em:pct -->84.3<!-- /num -->%로 기준선을 넘는 것을 확인했다(소유자 실행, 1회).

### 확인 가능한 사실

| 영역 | 사실 | 근거 |
|---|---|---|
| 데이터 | KorWikiTQ 공개 train/dev 파일이 같은 표 <!-- num:data/ko/official_split_profile.json:shared_tables_by_url_and_content:int -->1,578<!-- /num -->개를 공유하고 dev 질문의 <!-- num:data/ko/official_split_profile.json:dev_on_train_table.rate:pct -->42.9<!-- /num -->%가 그 표를 묻는다는 것을 측정하고 표 단위로 재분할(공유 0). 영어 화학 교과서 <!-- num:data/chem/build_report.json:documents_with_tables:int -->56<!-- /num -->문서·<!-- num:data/chem/build_report.json:tables:int -->113<!-- /num -->표를 CNXML에서 직접 파싱 | `data/ko/official_split_profile.json`, `data/*/build_report.json` |
| 평가셋 | 한국어 test <!-- num:data/ko/build_report.json:test_examples:int -->539<!-- /num -->(원본)+160(합성), 수작업 한국어 30·화학 32(5범주, 자동 검수) | `data/`, `scripts/check_data.py` |
| 모델 | mT5-small 300,176,768 파라미터를 Mesh-TF 체크포인트에서 PyTorch로 직접 변환·검증, 토크나이저 재구성 | `scripts/model/`, 이슈 1–4 |
| 학습 | CPU 4스레드: SFT 1단계 <!-- num:experiments/sft_ko/summary.json:steps:int -->858<!-- /num --> step·<!-- num:experiments/sft_ko/summary.json:wall_s:int -->7,219<!-- /num -->초, 2단계 <!-- num:experiments/sft_ko2/summary.json:steps:int -->193<!-- /num --> step·<!-- num:experiments/sft_ko2/summary.json:wall_s:int -->1,813<!-- /num -->초, 화학 <!-- num:experiments/sft_chem/summary.json:steps:int -->236<!-- /num --> step·<!-- num:experiments/sft_chem/summary.json:wall_s:int -->1,927<!-- /num -->초 | `experiments/*/summary.json` |
| GPU 서빙·튜닝 | EXAONE-4.0-1.2B를 같은 데이터로 LoRA 튜닝해 vLLM(1장·TP=2)·SGLang(T4 우회)으로 서빙, 같은 ko test·검증기로 평가. 전체 <!-- num:experiments/exaone_lora_full/train_info.json:n_examples:int -->3,587<!-- /num -->개·<!-- num:experiments/exaone_lora_full/train_info.json:steps:int -->224<!-- /num --> step(T4 <!-- num:experiments/exaone_lora_full/train_info.json:wall_s -->1,862.7<!-- /num -->초): **verified EM(두 학습 실행 중 첫 번째; 두 번째는 <!-- num:experiments/eval/exaone_full_vllm_ko_test_run2/metrics.json:metrics.verified_em:pct -->87.1<!-- /num -->%) <!-- num:experiments/eval/exaone_full_vllm_ko_test/metrics.json:metrics.verified_em:pct -->84.3<!-- /num -->%**, 기준선 대비 문항 <!-- num:experiments/eval/paired_tests.json:exaone_full_vs_heuristic_ko_test_ec.candidate_better:int -->344<!-- /num -->/<!-- num:experiments/eval/paired_tests.json:exaone_full_vs_heuristic_ko_test_ec.reference_better:int -->25<!-- /num -->개(p<!-- num:experiments/eval/paired_tests.json:exaone_full_vs_heuristic_ko_test_ec.p_display --><0.001<!-- /num -->), 수작업 30문항 <!-- num:experiments/eval/exaone_full_vllm_ko_custom/metrics.json:metrics.verified_em:pct -->66.7<!-- /num -->%, 직접 보류 <!-- num:experiments/eval/exaone_full_vllm_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->32<!-- /num -->/50건. 300개 LoRA: <!-- num:experiments/eval/exaone_vllm_ko_test/metrics.json:metrics.verified_em:pct -->53.1<!-- /num -->%. 동시 32요청 vLLM <!-- num:experiments/bench/engine_full_vllm_c32.json:throughput_req_per_s -->24.84<!-- /num --> 요청/s, TP=2 <!-- num:experiments/bench/engine_full_vllm_tp2_c32.json:throughput_req_per_s -->38.03<!-- /num -->. 소유자가 Kaggle에서 실행, 작성자는 스크립트·노트북·분석 | `experiments/eval/exaone_*`, `experiments/bench/engine_*`, §18.3 |
| 성능 | 한국어 독립 test verified EM: 미튜닝 <!-- num:experiments/eval/base_ko_test/metrics.json:metrics.verified_em:pct -->7.1<!-- /num -->% → 1차 최종 <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->% → 2차 최종 <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->%, 기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->%. 원본 539문항만: 최종 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->38.2<!-- /num -->% vs 기준선 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->26.2<!-- /num -->%. 1차 최종 대 2차 화학 SFT v2는 짝지어 비교하면 2차가 낫다(p=<!-- num:experiments/eval/paired_tests.json:chem2_vs_chem1_ko_test.p_display -->0.041<!-- /num -->) | `experiments/eval/`, `experiments/eval/paired_tests.json` |
| 분석 | 모델 인용 셀의 열 정확도 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:lookup_citation.col_correct:pct -->30.8<!-- /num -->%가 병목. 1차의 본문 답변 실패 원인(빈 표 지름길)을 규명하고 2차에서 고쳤으나 반대편 지름길(표 질문을 `op: text`로 보냄)이 생겨 한 번 더 고침(이슈 34) | `analysis.json`, §5.4, §18 |
| 강화학습 | GRPO 방식 정책 경사를 직접 구현. 3회 실행: 보상 편법 발견(v1), 수정 후 개선 없음(v2), 본문·보류 프롬프트 추가(v3). v3는 본문 근거 없음 문항에서 모델의 직접 보류를 학습했으나(짝지어 비교 p=<!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_text2_test.p_display -->0.020<!-- /num -->) ko test 전체 점수는 그대로. 시드 1개 | `training/rl_grpo.py`, §7, §18, 이슈 23–24 |
| 추론 | KV 캐시·배치·int8을 정밀도별 별도 프로세스로 측정. 모든 층 int8은 속도를 얻는 대신 정확도를 잃지만(<!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->% → <!-- num:experiments/eval/final_int8_all_ko_test/metrics.json:metrics.verified_em:pct -->21.2<!-- /num -->%), 범위를 나눠 확인하니 `lm_head`만 int8이면 ko test 손실이 검출되지 않고 처리량이 약 1.5배 | §8, §18.2 |
| 서비스 | FastAPI + LangGraph + 타입 검증 도구 + 비동기 작업 러너(큐·동시성·타임아웃), 임의 코드 실행 없음(계산기는 AST 평가기) | `service/`, `agent/`, `tools/` |
| 검증 | 테스트 <!-- num:experiments/tests/summary.json:passed -->127<!-- /num -->개 통과, E2E 검사 실시간 <!-- num:docs/images/e2e-summary.json:live.passed -->18<!-- /num -->/<!-- num:docs/images/e2e-summary.json:live.total -->18<!-- /num -->·정적 <!-- num:docs/images/e2e-summary.json:static.passed -->21<!-- /num -->/<!-- num:docs/images/e2e-summary.json:static.total -->21<!-- /num -->, Docker 이미지 빌드·smoke | `experiments/tests/`, `docs/images/` |
| 병렬(CPU) | 2-스테이지 파이프라인으로 모델을 두 프로세스에 분할하고 출력이 단일 프로세스와 일치함을 확인(속도 이득 없음) | §9 |

### 주장하면 안 되는 것 (이 프로젝트가 보여 주지 못한 것)

- SGLang의 제 성능(T4 우회 모듈 없이, Ampere 이상), 데이터 병렬(DDP), 문서 작성자(AI 코딩 도구)의 GPU 실행 경험(EXAONE LoRA·vLLM·멀티 GPU 실행은 소유자가 Kaggle·Colab에서 했고 작성자는 스크립트·노트북·분석을 맡음). 역할 구분: 문제 정의·핵심 설계(프로그램 제안→도구 실행→검증→보류 구조, 두 영역, 스택, 보고 원칙)와 실험 범위 결정, GPU 실행은 소유자, 세부 실험 설계·구현·문서는 AI 코딩 도구(`docs/HANDOFF.md` §0).
- "mT5로 기준선보다 좋은 모델을 만들었다"(전체 평가에서 <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->% 대 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->%. 기준선을 넘은 것은 EXAONE 1.2B 전체 데이터 LoRA(<!-- num:experiments/eval/exaone_full_vllm_ko_test/metrics.json:metrics.verified_em:pct -->84.3<!-- /num -->%)이며 1회 실행·GPU·4배 모델이다), "EXAONE이 실제 표의 계산을 잘한다"(계산·보류 평가 문항은 학습과 같은 템플릿의 합성), "강화학습으로 ko test 점수를 올렸다"(v3도 그대로), "모든 int8로 최적화했다"(정확도 하락), "mT5를 vLLM/SGLang으로 서빙했다"(두 엔진이 mT5를 지원하지 않음. vLLM 서빙은 EXAONE 모델), "EXAONE이 mT5보다 튜닝이 잘 됐다"(모델 크기·사전학습·하드웨어가 달라 같은 조건 비교가 아님).
- 공개 배포·GitHub Actions 실행·운영 경험, 실제 사용자 트래픽.
- 논문·특허 화학 문서 처리(교과서 표만 사용), 실사용 질문 분포에서의 일반 성능(수작업 평가는 62문항).
- "공고의 모든 항목을 했다". 원문(2026-11-10 확인)에만 있는 gRPC, 챗봇, 메모리 결합, Personal Agent, 구조 전용 PLM 구현은 하지 않았다(§3 표 아래). 프로젝트가 정면으로 맞춘 것은 테이블이해 묶음이다.

## 18. 2차 시도 — 1차에서 실패한 것을 고쳐 다시 돌린 결과

**요약** (최종 모델은 2차의 **RL v3**, 1차의 최종 모델은 "화학 SFT")

- ✅ **튜닝과 2차 재학습이 효과가 있었습니다.** 한국어 독립 test 699문항 verified EM: 미튜닝 <!-- num:experiments/eval/base_ko_test/metrics.json:metrics.verified_em:pct -->7.1<!-- /num -->% → SFT stage2 <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.verified_em:pct -->27.5<!-- /num -->% → 1차 최종(화학 SFT) <!-- num:experiments/eval/sft_chem_ko_test/metrics.json:metrics.verified_em:pct -->29.8<!-- /num -->% → 2차 화학 SFT v2 <!-- num:experiments/eval/sft_chem2_ko_test/metrics.json:metrics.verified_em:pct -->32.9<!-- /num -->% → 2차 최종(RL v3) <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->%. 같은 문항끼리 짝지어 비교하면 1차 최종 대 2차 화학 SFT v2는 2차가 낫습니다(2차만 맞힌 문항 <!-- num:experiments/eval/paired_tests.json:chem2_vs_chem1_ko_test.candidate_better:int -->64<!-- /num -->개, 1차만 맞힌 문항 <!-- num:experiments/eval/paired_tests.json:chem2_vs_chem1_ko_test.reference_better:int -->42<!-- /num -->개, 정확 검정 p=<!-- num:experiments/eval/paired_tests.json:chem2_vs_chem1_ko_test.p_display -->0.041<!-- /num -->).
- ✅ **본문 답변이 동작하기 시작했습니다.** 실제 표 옆의 본문 질문 100개에서 모델이 `op: text`를 고른 비율은 1차 최종 <!-- num:experiments/eval/sft_chem_text2_test/analysis.json:text_answers.chose_text_op_rate:pct -->0.0<!-- /num -->% → 2차 화학 SFT v2 <!-- num:experiments/eval/sft_chem2_text2_test/analysis.json:text_answers.chose_text_op_rate:pct -->92.0<!-- /num -->% → RL v3 <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:text_answers.chose_text_op_rate:pct -->62.0<!-- /num -->%이고, 맞힌 문항은 <!-- num:experiments/eval/sft_chem_text2_test/analysis.json:text_answers.verified_correct:int -->0<!-- /num -->개 → <!-- num:experiments/eval/sft_chem2_text2_test/analysis.json:text_answers.verified_correct:int -->28<!-- /num -->개 → <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:text_answers.verified_correct:int -->26<!-- /num -->개입니다. 아직 낮습니다(아래 18.1).
- ✅ **보류를 모델이 직접 하게 됐습니다(RL v3).** 답이 없는 문항에서 모델이 직접 `op: abstain`을 낸 비율은 ko test 50문항에서 2차 화학 SFT v2 <!-- num:experiments/eval/sft_chem2_ko_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->0.0<!-- /num -->% → RL v3 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->42.0<!-- /num -->%, 본문 근거 없음 50문항에서 <!-- num:experiments/eval/sft_chem2_text2_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->0.0<!-- /num -->% → <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->90.0<!-- /num -->%입니다. 본문 근거 없음 테스트 150문항 전체를 짝지어 비교하면 RL v3가 낫습니다(RL v3만 맞힌 문항 <!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_text2_test.candidate_better:int -->26<!-- /num -->개, 화학 SFT v2만 맞힌 문항 <!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_text2_test.reference_better:int -->11<!-- /num -->개, 정확 검정 p=<!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_text2_test.p_display -->0.020<!-- /num -->). 1차 RL 두 번은 이 값이 0%였습니다.
- ⚠️ **그러나 ko test 전체 verified EM은 RL로 오르지 않았습니다**: <!-- num:experiments/eval/sft_chem2_ko_test/metrics.json:metrics.verified_em:pct -->32.9<!-- /num -->% → <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->%, 짝지어 비교하면 차이가 없습니다(RL v3만 맞힌 문항 <!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_ko_test.candidate_better:int -->34<!-- /num -->개, 화학 SFT v2만 맞힌 문항 <!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_ko_test.reference_better:int -->35<!-- /num -->개, 정확 검정 p=<!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_ko_test.p_display -->1.000<!-- /num -->). 직접 보류가 늘어난 만큼 정답이 있는 문항에 대한 보류도 늘었습니다(직접 보류 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->131<!-- /num -->건 중 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:abstain_breakdown.explicit_abstain_on_answerable:int -->110<!-- /num -->건이 답이 있는 문항).
- ❌ **전체 평가에서는 어휘 겹침 기준선(<!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->%)을 여전히 넘지 못했습니다.** 원본 KorWikiTQ 539문항만 보면 RL v3 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->38.2<!-- /num -->% 대 기준선 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:by_source_verified.korwikitq.verified_em:pct -->26.2<!-- /num -->%로 모델이 앞섭니다. 합성 계산·보류 160문항에서는 모델 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:by_source_verified.synthetic.verified_em:pct -->14.4<!-- /num -->%, 기준선 <!-- num:experiments/eval/heuristic_ko_test/analysis.json:by_source_verified.synthetic.verified_em:pct -->70.0<!-- /num -->%인데, 이 합성 문항은 기준선의 의도 패턴과 같은 사람이 쓴 템플릿이라 **독립적인 비교가 아닙니다**.
- ⚠️ **검증기 v2(개체 일치 검사)는 양날입니다.** 질문의 고유명사가 인용한 행에 없으면 보류해 "표에 없는 대상에 엉뚱한 셀을 인용해 답하는" 사례를 막습니다. 대신 정답 프로그램도 한국어 정답 문항의 <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.gold_subject_fail_rate:pct -->4.3<!-- /num -->%를 오탐으로 보류합니다. 2차 최종 모델에서는 이 대가가 이득보다 커서(짝지어 비교: 검증기 v2만 맞힌 문항 <!-- num:experiments/eval/paired_tests.json:subject_check_on_chem2_ko_test.candidate_better:int -->1<!-- /num -->개, 검증기 v1만 맞힌 문항 <!-- num:experiments/eval/paired_tests.json:subject_check_on_chem2_ko_test.reference_better:int -->9<!-- /num -->개, 정확 검정 p=<!-- num:experiments/eval/paired_tests.json:subject_check_on_chem2_ko_test.p_display -->0.021<!-- /num -->) 서비스 기본값은 켜 두되 `TABLETRACE_ENTITY_CHECK=0`으로 끌 수 있습니다. 표는 두 검증기 결과를 모두 보여 줍니다.
- ⚠️ **약한 고리는 여전히 셀 열 좌표입니다**: RL v3가 인용한 열이 맞는 비율 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:lookup_citation.col_correct:pct -->30.8<!-- /num -->%(행은 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:lookup_citation.row_correct:pct -->91.8<!-- /num -->%). 검증기의 "근거 복구"가 답 텍스트로 올바른 셀을 찾아 점수를 지탱합니다.
- ⚠️ **영어 화학**: 수작업 32문항 verified EM은 1차 최종 <!-- num:experiments/eval/sft_chem_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num -->% → RL v3 <!-- num:experiments/eval/rl_v3_chem_custom/metrics.json:metrics.verified_em:pct -->21.9<!-- /num -->%(1–2문항 차이)이고 전부 보류하는 미튜닝 모델도 <!-- num:experiments/eval/base_chem_custom/metrics.json:metrics.verified_em:pct -->15.6<!-- /num -->%입니다. 합성 dev 80문항은 <!-- num:experiments/eval/sft_chem_chem_syndev/metrics.json:metrics.verified_em:pct -->41.2<!-- /num -->% → <!-- num:experiments/eval/rl_v3_chem_syndev/metrics.json:metrics.verified_em:pct -->45.0<!-- /num -->%입니다. 기준선은 <!-- num:experiments/eval/heuristic_chem_custom/metrics.json:metrics.verified_em:pct -->56.2<!-- /num -->%입니다.
- ⚠️ **int8 정확도 하락은 범위를 나눠 원인을 찾아 대부분 없앴습니다.** 1차의 int8(모든 Linear)은 최종 모델의 ko test verified EM을 <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->% → <!-- num:experiments/eval/final_int8_all_ko_test/metrics.json:metrics.verified_em:pct -->21.2<!-- /num -->%로 떨어뜨렸습니다(쌍 비교 fp32가 <!-- num:experiments/eval/paired_tests.json:int8_all_vs_fp32_ko_test.reference_better:int -->114<!-- /num -->문항, int8이 <!-- num:experiments/eval/paired_tests.json:int8_all_vs_fp32_ko_test.candidate_better:int -->33<!-- /num -->문항 더 맞힘). 출력 층 `lm_head`(512×250,112)만 int8로 하면 <!-- num:experiments/eval/final_int8_lm_head_ko_test/metrics.json:metrics.verified_em:pct -->32.2<!-- /num -->%로 손실이 검출되지 않고(쌍 비교 <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_ko_test.reference_better:int -->22<!-- /num --> 대 <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_ko_test.candidate_better:int -->18<!-- /num -->문항, p=<!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_ko_test.p_display -->0.636<!-- /num -->) 같은 측정에서 처리량이 <!-- num:experiments/bench/inference_r2b.json:results.0.throughput_ex_per_s -->0.93<!-- /num --> → <!-- num:experiments/bench/inference_r2b.json:results.3.throughput_ex_per_s -->1.48<!-- /num --> 예제/s(bs=1)입니다. 나머지 층(FFN·어텐션)의 int8은 속도 이득이 없습니다. 본문 답변 테스트에서는 fp32가 <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_text2_test.reference_better:int -->6<!-- /num -->문항, int8이 <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_text2_test.candidate_better:int -->1<!-- /num -->문항 더 맞혀 약간 나빠졌지만 유의하지는 않습니다(p=<!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_text2_test.p_display -->0.125<!-- /num -->, §10.1). 서비스 설정은 `TABLETRACE_QUANTIZE=1`, `TABLETRACE_QUANTIZE_SCOPE=lm_head`입니다.

### 18.1 무엇을 고쳤고 무엇이 남았나

1차(§5–§8)에서 목표를 이루지 못한 것은 넷이었고, **같은 평가셋·같은 지표**로 다시 시도했습니다. 평가셋을 바꾸거나 문항을 골라내지 않았습니다. 새로 만든 본문 평가셋은 아래 별도 항목에 적었습니다.

| 1차에서 실패한 것 | 원인으로 확인한 것 | 2차에서 한 일 | 결과 |
|---|---|---|---|
| 본문+표 질문에서 `op: text`를 한 번도 내지 않음 | 학습의 본문 예제가 전부 **빈 표**와 함께였음 → "표에 행이 없으면 text" 지름길 | 실제 표 옆에 본문을 두는 학습 예제 600개 + 근거 없음 예제 250개로 2단계를 재학습, 화학 단계에서 본문 550개 추가 재학습 | 독립 text 테스트에서 `op: text` 선택 <!-- num:experiments/eval/sft_chem_text2_test/analysis.json:text_answers.chose_text_op_rate:pct -->0.0<!-- /num -->% → <!-- num:experiments/eval/sft_chem2_text2_test/analysis.json:text_answers.chose_text_op_rate:pct -->92.0<!-- /num -->%, 정답 <!-- num:experiments/eval/sft_chem_text2_test/analysis.json:text_answers.verified_correct:int -->0<!-- /num -->개 → <!-- num:experiments/eval/sft_chem2_text2_test/analysis.json:text_answers.verified_correct:int -->28<!-- /num -->개(100문항) |
| 표에 없는 대상에도 엉뚱한 셀을 인용해 답함(예: `ko_custom_08`) | 검증기가 답과 셀의 일치만 보고 질문의 대상은 보지 않음 | 검증기 v2: 질문의 고유명사(한국어는 Kiwi NNP·SL·SH, 영어는 화학식)가 인용한 행에 없으면 보류 | 1차 모델 보류 재현율 <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.abstain_recall:pct -->26.0<!-- /num -->% → <!-- num:experiments/eval/sft_ko2_ko_test_ec/metrics.json:metrics.abstain_recall:pct -->54.0<!-- /num -->%, 대가로 정답 프로그램 <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.gold_subject_fail_rate:pct -->4.3<!-- /num -->%를 오탐 보류 |
| RL이 개선을 만들지 못함 | 원인은 확인하지 못함(가설: 60 step·샘플 960개로 적고, 프롬프트에 본문·보류 문항이 거의 없었음) | RL v3: 한국어+화학+본문 프롬프트 5,130개, 120 step, 학습률 2e-5, 2차 화학 SFT v2에서 출발 | 본문 근거 없음 50문항 직접 보류 <!-- num:experiments/eval/sft_chem2_text2_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->0.0<!-- /num -->% → <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->90.0<!-- /num -->%(p=<!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_text2_test.p_display -->0.020<!-- /num -->), ko test verified EM은 그대로 |
| int8 정확도 하락 | 확인해 보니 `lm_head`(512×250,112)까지 int8이었음(1차 문서의 "lm_head는 fp32"는 틀린 설명) | 양자화 범위를 고르는 `model/quant.py`, 범위별 정확도·속도 측정 | §8 |

**학습 계보(2차)**: stage1(1차 그대로) → `sft_ko3`(2단계 재학습) → `sft_ko4`(표 조회 1,700개 보강 1 epoch) → `sft_chem2`(화학 + 본문 550개 재학습) → `rl_v3`(최종). `sft_ko3`는 본문은 풀게 됐지만 표 질문 539개 중 82개를 `op: text`로 보내 ko test verified EM이 <!-- num:experiments/eval/sft_ko2_ko_test/metrics.json:metrics.verified_em:pct -->27.5<!-- /num -->%에서 <!-- num:experiments/eval/sft_ko3_ko_test/metrics.json:metrics.verified_em:pct -->24.9<!-- /num -->%로 떨어졌고(반대편 지름길), `sft_ko4`가 이를 <!-- num:experiments/eval/sft_ko4_ko_test/metrics.json:metrics.verified_em:pct -->30.6<!-- /num -->%로 되돌렸습니다. 두 실행 모두 산출물에 남아 있습니다.

**본문 답변·근거 없음 평가셋(`text2_test`)**: KorQuAD v1.0 dev의 질문 150개(본문 100 + 근거 없음 50)를 **실제 표 옆에** 놓았습니다. 표는 한국어 test 분할의 표에서 무작위로 골랐고(학습에는 쓰이지 않음), 본문 창(최대 300자)은 정답을 포함하며, 근거 없음 문항은 다른 문단의 창을 줍니다. 학습용(`text2_train`)·체크포인트 선택용(`text2_dev`)과 질문이 겹치지 않음을 확인했습니다. 라이선스(CC BY-ND)상 파생 파일은 저장소에 올리지 않고 `scripts/data/build_text_v2.py`로 다시 만듭니다.

<!-- results:text:start -->
**본문 답변·근거 없음 — 실제 표 옆 KorQuAD 150문항(본문 100 + 근거 없음 50), 검증기 v1: 개체 일치 검사 없음 (1차 평가와 같은 조건)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SFT stage2(+본문) | 150 | **8.7** | 7.0 | – | 0.0 | 0.0 | 0.0 | 26.0 | 46.0 | 0.0 | 1234 |
| 화학 SFT | 150 | **11.3** | 5.0 | – | 0.0 | 0.0 | 0.0 | 34.0 | 36.0 | 0.0 | 1202 |
| [2차] SFT stage2 재학습(실제 표 옆 본문 예제) | 150 | **27.3** | 12.0 | – | 12.0 | 62.0 | 62.0 | 58.0 | 30.0 | 1.3 | 575 |
| [2차] + 표 조회 보강 epoch | 150 | **15.3** | 11.0 | – | 8.0 | 39.0 | 39.0 | 30.0 | 21.0 | 0.7 | 585 |
| [2차] 화학 SFT v2 | 150 | **37.3** | 28.0 | – | 28.0 | 66.0 | 66.0 | 56.0 | 31.0 | 1.3 | 493 |
| [2차] GRPO RL v3 | 150 | **47.3** | 26.0 | – | 26.0 | 61.0 | 61.0 | 90.0 | 33.0 | 0.7 | 456 |

**본문 답변·근거 없음, 검증기 v2: 개체 일치 검사 있음 (같은 모델 출력을 다시 검증)**

| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SFT stage2(+본문) | 150 | **28.0** | 7.0 | – | 0.0 | 0.0 | 0.0 | 84.0 | 74.0 | 0.0 | 1234 |
| 화학 SFT | 150 | **28.7** | 5.0 | – | 0.0 | 0.0 | 0.0 | 86.0 | 67.0 | 0.0 | 1202 |
| [2차] SFT stage2 재학습(실제 표 옆 본문 예제) | 150 | **29.3** | 12.0 | – | 12.0 | 62.0 | 62.0 | 64.0 | 36.0 | 1.3 | 575 |
| [2차] + 표 조회 보강 epoch | 150 | **26.7** | 11.0 | – | 8.0 | 39.0 | 39.0 | 64.0 | 46.0 | 0.7 | 585 |
| [2차] 화학 SFT v2 | 150 | **38.0** | 28.0 | – | 28.0 | 66.0 | 66.0 | 58.0 | 33.0 | 1.3 | 493 |
| [2차] GRPO RL v3 | 150 | **48.0** | 26.0 | – | 26.0 | 61.0 | 61.0 | 92.0 | 36.0 | 0.7 | 456 |

<!-- results:text:end -->

**RL v3**(5,130 프롬프트: 한국어 lookup 2,993, 계산 867, 보류 670, 본문 600; 120 step, 프롬프트 4 × 샘플 4, 학습률 2e-5, β=0.02):

<!-- results:rl_v3:start -->
| 구간(step) | 평균 보상 | 샘플 정답률 % | 샘플 최종 보류율 % | 모델이 명시적으로 abstain한 비율 % | lookup 비율 % | diff 비율 % | KL | 그룹 분산 0 비율 % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1–30 | 0.193 | 29.2 | 59.8 | 16.2 | 35.8 | 9.0 | 0.0065 | 36.7 |
| 31–60 | 0.147 | 26.5 | 53.1 | 25.4 | 38.3 | 13.1 | 0.0367 | 32.5 |
| 61–90 | 0.183 | 29.4 | 55.6 | 27.9 | 45.2 | 6.0 | 0.0572 | 32.5 |
| 91–120 | 0.253 | 32.9 | 48.1 | 30.4 | 44.8 | 3.3 | 0.0504 | 46.7 |

dev verified EM(n=475): step 0: 36.2% → step 40: 40.6% → step 80: 43.2% → step 120: 41.1%

**평가에 쓴 체크포인트: step 80** (dev 최고로 선택; 마지막 step이 아님). 120 step wall time 57 min, CPU 4스레드.

<!-- results:rl_v3:end -->

**보상 계산에는 검증기 v2(개체 일치 검사)가 쓰였습니다.** 질문 대상이 표에 없는데 답한 출력은 검증기가 보류로 바꾸므로 보상이 −0.8이 아니라 0.0이 됩니다(1차 v2와 보상의 의미가 다릅니다. 고정하는 테스트는 `tests/test_training_data_and_reward.py`).

dev(475문항, 학습과 겹치지 않음)에서 verified EM이 step 0 <!-- num:experiments/rl_v3/summary.json:dev_history.0.verified_em:pct -->36.2<!-- /num -->% → step 40 <!-- num:experiments/rl_v3/summary.json:dev_history.1.verified_em:pct -->40.6<!-- /num -->% → step 80 <!-- num:experiments/rl_v3/summary.json:dev_history.2.verified_em:pct -->43.2<!-- /num -->% → step 120 <!-- num:experiments/rl_v3/summary.json:dev_history.3.verified_em:pct -->41.1<!-- /num -->%였고, **dev 최고인 step 80을 최종 모델로** 정했습니다(평가 전에 정한 규칙: step 0보다 dev가 오르면 RL 체크포인트, 아니면 SFT 모델). dev는 선택에도 쓰였으므로 낙관적이고, 독립 평가는 위 표입니다.

**RL v3 해석**

- **무엇이 늘었나**: 모델이 직접 `op: abstain`을 낸 건수가 0에서 늘었습니다(ko test <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->131<!-- /num -->건, 본문 근거 없음 테스트 <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->75<!-- /num -->건). 근거 없음 문항에서는 <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:abstain_breakdown.planner_chose_abstain_recall:pct -->90.0<!-- /num -->%를 직접 보류했습니다. 검증기가 우연히 막은 것이 아니라 모델의 선택입니다.
- **무엇이 안 늘었나**: ko test verified EM(<!-- num:experiments/eval/sft_chem2_ko_test/metrics.json:metrics.verified_em:pct -->32.9<!-- /num -->% → <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->%), 수작업 30·32문항(쌍 비교 p=<!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_ko_custom.p_display -->0.625<!-- /num -->, <!-- num:experiments/eval/paired_tests.json:rl_v3_vs_chem2_chem_custom.p_display -->1.000<!-- /num -->), 본문 정답 수(<!-- num:experiments/eval/sft_chem2_text2_test/analysis.json:text_answers.verified_correct:int -->28<!-- /num -->개 → <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:text_answers.verified_correct:int -->26<!-- /num -->개).
- **대가와 한계**: ko test에서는 답한 문항 수(<!-- num:experiments/eval/sft_chem2_ko_test/analysis.json:selective.answered:int -->488<!-- /num -->건 → <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:selective.answered:int -->501<!-- /num -->건)와 오답으로 답한 비율(<!-- num:experiments/eval/sft_chem2_ko_test/analysis.json:selective.wrong_answer_rate:pct -->40.2<!-- /num -->% → <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:selective.wrong_answer_rate:pct -->42.2<!-- /num -->%)이 거의 같습니다. RL은 보류를 검증기가 아니라 **모델이 하게 만들었지만** 보류량과 오답 수는 줄이지 못했습니다. 본문 근거 없음 테스트에서는 답한 문항이 <!-- num:experiments/eval/sft_chem2_text2_test/analysis.json:selective.answered:int -->91<!-- /num -->건 → <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:selective.answered:int -->72<!-- /num -->건, 오답으로 답한 비율이 <!-- num:experiments/eval/sft_chem2_text2_test/analysis.json:selective.wrong_answer_rate:pct -->42.0<!-- /num -->% → <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:selective.wrong_answer_rate:pct -->30.7<!-- /num -->%로 줄었습니다. 대신 본문 질문에서 `op: text` 선택이 <!-- num:experiments/eval/sft_chem2_text2_test/analysis.json:text_answers.chose_text_op_rate:pct -->92.0<!-- /num -->% → <!-- num:experiments/eval/rl_v3_text2_test/analysis.json:text_answers.chose_text_op_rate:pct -->62.0<!-- /num -->%로 줄었고, ko test에서 정답이 있는 문항에 직접 보류가 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:abstain_breakdown.explicit_abstain_on_answerable:int -->110<!-- /num -->건 나왔습니다.
- **보상 편법 점검**: 퇴화 계산 출력(같은 셀을 두 번 쓰는 계산)은 ko test에서 SFT stage2 <!-- num:experiments/eval/sft_ko2_ko_test/analysis.json:degenerate_calc_outputs:int -->101<!-- /num -->건, RL v1 <!-- num:experiments/eval/rl_ko_v1_ko_test/analysis.json:degenerate_calc_outputs:int -->160<!-- /num -->건, RL v3 <!-- num:experiments/eval/rl_v3_ko_test/analysis.json:degenerate_calc_outputs:int -->0<!-- /num -->건입니다. 정답이 있는 문항에서 보류는 −0.3으로, 오답(0.0에 부분 점수)보다 비싸게 설계했는데도 위 "대가"처럼 정답 문항에 대한 직접 보류가 많이 나왔습니다. 이 부분의 보상 크기는 조정하지 않았습니다.
- **한계**: 1회 실행(시드 1개), 120 step의 예비 실험입니다. 시드 반복은 하지 않았습니다.

**시도했으나 채택하지 않은 것 — 열 보정**: 가장 약한 고리인 열 좌표를 검증기가 고칠 수 있는지 실험했습니다(질문이 헤더 이름을 직접 언급하는데 모델이 인용한 열이 다르면 같은 행의 그 열로 옮김, `column_check`). 설계와 판단은 dev <!-- num:experiments/eval/column_check_dev.json:n:int -->245<!-- /num -->문항의 예측만으로 했고 test는 보지 않았습니다. dev에서 <!-- num:experiments/eval/column_check_dev.json:fired:int -->91<!-- /num -->건에 작동해 <!-- num:experiments/eval/column_check_dev.json:fixed:int -->14<!-- /num -->건을 고치고 <!-- num:experiments/eval/column_check_dev.json:broke:int -->9<!-- /num -->건을 깨뜨렸습니다(질문 속 헤더 단어가 묻는 열이 아니라 조건인 경우, 예: '감독', '득점', '기록'). verified EM <!-- num:experiments/eval/column_check_dev.json:verified_em_without:pct -->39.2<!-- /num -->% → <!-- num:experiments/eval/column_check_dev.json:verified_em_with:pct -->41.2<!-- /num -->%로 순이득이 작고 사람이 쓴 규칙이 모델의 판단을 덮어쓰는 위험이 커서 **기본값은 꺼 두었습니다**(`tests/test_program_verifier.py`, `experiments/eval/column_check_dev.json`).


### 18.2 int8 범위별 측정(추론 최적화 2차)

**2차: 최종 모델(RL v3)의 int8 범위별 측정.** 1차 문서는 "lm_head는 fp32로 남는다"고 썼지만 확인하니 `lm_head`도 int8이었습니다(모듈 경로 `torch.ao.nn.quantized.dynamic`). 양자화 범위를 고르는 `model/quant.py`를 추가해 범위별로 정확도와 속도를 쟀습니다. 속도는 같은 측정 안의 fp32와만 비교하세요(공유 VM이라 측정 사이에 20% 이상 흔들립니다).

<!-- results:bench_r2:start -->
조건: experiments/rl_v3/model(2차 최종 모델 = RL v3), 입력 48개(ko test), max_new_tokens 48, 워밍업 1라운드 + 측정 2라운드, 4 스레드, 4 cores x86_64, torch 2.15.0+cu132, CUDA False. 정밀도마다 **별도 프로세스**에서 측정(메모리 비교를 위해). 양자화 준비 시간 int8 5.1s, int8-no_lm_head 0.9s, int8-ffn 0.8s, int8-attn 0.6s. 모델 실행 조건은 위와 같고 **양자화 범위**는 설정 이름의 `int8`(모든 Linear, lm_head 포함) 또는 `int8-<범위>`(일부)로 구분합니다.

| 설정 | p50 ms | p95 ms | 처리량 예제/s | 모델 파일 MB | 프로세스 peak RSS GB | fp32 bs=1과 출력 문자열 일치 % |
|---|---:|---:|---:|---:|---:|---:|
| fp32, bs=1, kv-cache on | 996.8 | 1190.2 | 0.997 | 1200.8 | 3.39 | 100.0 |
| fp32, bs=8, kv-cache on | 432.4 | 469.1 | 2.299 | 1200.8 | 3.39 | 100.0 |
| fp32, bs=1, kv-cache OFF | 2990.7 | 3711.6 | 0.335 | 1200.8 | 3.39 | 100.0 |
| int8, bs=1, kv-cache on | 702.7 | 872.1 | 1.411 | 684.6 | 3.72 | 54.2 |
| int8, bs=8, kv-cache on | 317.0 | 362.2 | 3.117 | 684.6 | 3.72 | 31.2 |
| int8-no_lm_head, bs=1, kv-cache on | 1013.7 | 1249.0 | 0.989 | 1068.8 | 3.34 | 58.3 |
| int8-no_lm_head, bs=8, kv-cache on | 478.7 | 601.3 | 2.038 | 1068.8 | 3.34 | 47.9 |
| int8-ffn, bs=1, kv-cache on | 1012.5 | 1259.6 | 0.965 | 1125.3 | 3.36 | 50.0 |
| int8-ffn, bs=8, kv-cache on | 482.7 | 680.1 | 1.967 | 1125.3 | 3.36 | 47.9 |
| int8-attn, bs=1, kv-cache on | 1090.9 | 1263.9 | 0.926 | 1144.2 | 3.32 | 79.2 |
| int8-attn, bs=8, kv-cache on | 470.8 | 557.5 | 2.055 | 1144.2 | 3.32 | 75.0 |

<!-- results:bench_r2:end -->

<!-- results:bench_r2b:start -->
조건: experiments/rl_v3/model(2차 최종 모델 = RL v3, fp32 대 lm_head만 int8), 입력 48개(ko test), max_new_tokens 48, 워밍업 1라운드 + 측정 2라운드, 4 스레드, 4 cores x86_64, torch 2.15.0+cu132, CUDA False. 정밀도마다 **별도 프로세스**에서 측정(메모리 비교를 위해). 양자화 준비 시간 int8-lm_head 4.0s. 모델 실행 조건은 위와 같고 **양자화 범위**는 설정 이름의 `int8`(모든 Linear, lm_head 포함) 또는 `int8-<범위>`(일부)로 구분합니다.

| 설정 | p50 ms | p95 ms | 처리량 예제/s | 모델 파일 MB | 프로세스 peak RSS GB | fp32 bs=1과 출력 문자열 일치 % |
|---|---:|---:|---:|---:|---:|---:|
| fp32, bs=1, kv-cache on | 1071.5 | 1285.2 | 0.93 | 1200.8 | 3.4 | 100.0 |
| fp32, bs=8, kv-cache on | 464.0 | 529.6 | 2.117 | 1200.8 | 3.4 | 100.0 |
| fp32, bs=1, kv-cache OFF | 2832.8 | 3481.1 | 0.351 | 1200.8 | 3.4 | 100.0 |
| int8-lm_head, bs=1, kv-cache on | 665.2 | 845.4 | 1.479 | 816.6 | 3.67 | 68.8 |
| int8-lm_head, bs=8, kv-cache on | 302.3 | 397.1 | 3.209 | 816.6 | 3.67 | 68.8 |

<!-- results:bench_r2b:end -->

| 양자화 범위 | ko test verified EM % | 파싱 실패 % | fp32와 쌍 비교(fp32가 나음 / int8이 나음) | p | 처리량 bs=8 예제/s (같은 측정 안) |
|---|---:|---:|---:|---:|---:|
| 없음(fp32, RL v3) | <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num --> | <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.parse_fail_rate:pct -->0.0<!-- /num --> | – | – | <!-- num:experiments/bench/inference_r2.json:results.1.throughput_ex_per_s -->2.3<!-- /num --> |
| 모든 Linear(lm_head 포함, 1차의 int8) | <!-- num:experiments/eval/final_int8_all_ko_test/metrics.json:metrics.verified_em:pct -->21.2<!-- /num --> | <!-- num:experiments/eval/final_int8_all_ko_test/metrics.json:metrics.parse_fail_rate:pct -->18.2<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_all_vs_fp32_ko_test.reference_better:int -->114<!-- /num --> / <!-- num:experiments/eval/paired_tests.json:int8_all_vs_fp32_ko_test.candidate_better:int -->33<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_all_vs_fp32_ko_test.p_display --><0.001<!-- /num --> | <!-- num:experiments/bench/inference_r2.json:results.4.throughput_ex_per_s -->3.12<!-- /num --> |
| lm_head만 | <!-- num:experiments/eval/final_int8_lm_head_ko_test/metrics.json:metrics.verified_em:pct -->32.2<!-- /num --> | <!-- num:experiments/eval/final_int8_lm_head_ko_test/metrics.json:metrics.parse_fail_rate:pct -->3.6<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_ko_test.reference_better:int -->22<!-- /num --> / <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_ko_test.candidate_better:int -->18<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_ko_test.p_display -->0.636<!-- /num --> | <!-- num:experiments/bench/inference_r2b.json:results.4.throughput_ex_per_s -->3.21<!-- /num --> |
| lm_head 제외 전부 | <!-- num:experiments/eval/final_int8_no_lm_head_ko_test/metrics.json:metrics.verified_em:pct -->28.6<!-- /num --> | <!-- num:experiments/eval/final_int8_no_lm_head_ko_test/metrics.json:metrics.parse_fail_rate:pct -->0.1<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_no_lm_head_vs_fp32_ko_test.reference_better:int -->63<!-- /num --> / <!-- num:experiments/eval/paired_tests.json:int8_no_lm_head_vs_fp32_ko_test.candidate_better:int -->34<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_no_lm_head_vs_fp32_ko_test.p_display -->0.004<!-- /num --> | <!-- num:experiments/bench/inference_r2.json:results.6.throughput_ex_per_s -->2.04<!-- /num --> |
| FFN만 | <!-- num:experiments/eval/final_int8_ffn_ko_test/metrics.json:metrics.verified_em:pct -->28.0<!-- /num --> | <!-- num:experiments/eval/final_int8_ffn_ko_test/metrics.json:metrics.parse_fail_rate:pct -->0.0<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_ffn_vs_fp32_ko_test.reference_better:int -->60<!-- /num --> / <!-- num:experiments/eval/paired_tests.json:int8_ffn_vs_fp32_ko_test.candidate_better:int -->27<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_ffn_vs_fp32_ko_test.p_display --><0.001<!-- /num --> | <!-- num:experiments/bench/inference_r2.json:results.8.throughput_ex_per_s -->1.97<!-- /num --> |
| 어텐션만 | <!-- num:experiments/eval/final_int8_attn_ko_test/metrics.json:metrics.verified_em:pct -->32.9<!-- /num --> | <!-- num:experiments/eval/final_int8_attn_ko_test/metrics.json:metrics.parse_fail_rate:pct -->0.0<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_attn_vs_fp32_ko_test.reference_better:int -->18<!-- /num --> / <!-- num:experiments/eval/paired_tests.json:int8_attn_vs_fp32_ko_test.candidate_better:int -->19<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_attn_vs_fp32_ko_test.p_display -->1.000<!-- /num --> | <!-- num:experiments/bench/inference_r2.json:results.10.throughput_ex_per_s -->2.06<!-- /num --> |

`lm_head`만 int8의 다른 평가셋(verified EM %, fp32 → int8-lm_head):

| 평가셋 | n | fp32 | lm_head만 int8 | 쌍 비교(fp32가 나음 / int8이 나음) | p |
|---|---:|---:|---:|---:|---:|
| 본문 답변·근거 없음 | <!-- num:experiments/eval/rl_v3_text2_test/metrics.json:metrics.n:int -->150<!-- /num --> | <!-- num:experiments/eval/rl_v3_text2_test/metrics.json:metrics.verified_em:pct -->47.3<!-- /num --> | <!-- num:experiments/eval/final_int8_lm_head_text2_test/metrics.json:metrics.verified_em:pct -->44.0<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_text2_test.reference_better:int -->6<!-- /num --> / <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_text2_test.candidate_better:int -->1<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_text2_test.p_display -->0.125<!-- /num --> |
| 한국어 수작업 | <!-- num:experiments/eval/rl_v3_ko_custom/metrics.json:metrics.n:int -->30<!-- /num --> | <!-- num:experiments/eval/rl_v3_ko_custom/metrics.json:metrics.verified_em:pct -->13.3<!-- /num --> | <!-- num:experiments/eval/final_int8_lm_head_ko_custom/metrics.json:metrics.verified_em:pct -->13.3<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_ko_custom.reference_better:int -->1<!-- /num --> / <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_ko_custom.candidate_better:int -->1<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_ko_custom.p_display -->1.000<!-- /num --> |
| 화학 수작업 | <!-- num:experiments/eval/rl_v3_chem_custom/metrics.json:metrics.n:int -->32<!-- /num --> | <!-- num:experiments/eval/rl_v3_chem_custom/metrics.json:metrics.verified_em:pct -->21.9<!-- /num --> | <!-- num:experiments/eval/final_int8_lm_head_chem_custom/metrics.json:metrics.verified_em:pct -->25.0<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_chem_custom.reference_better:int -->1<!-- /num --> / <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_chem_custom.candidate_better:int -->2<!-- /num --> | <!-- num:experiments/eval/paired_tests.json:int8_lm_head_vs_fp32_chem_custom.p_display -->1.000<!-- /num --> |

**읽는 법**: 속도 이득은 거의 전부 `lm_head`(디코딩 토큰마다 25만 어휘로 투영)에서 나오고, FFN·어텐션 int8은 이 CPU에서 속도가 오히려 줄거나 같습니다. 그런데 모든 층을 함께 int8로 하면 정확도가 크게 무너지는 반면 `lm_head`만이면 손실이 검출되지 않습니다(층별 손실의 합보다 훨씬 크게 겹쳐 나타남). 한계: 정확도 확인은 한국어 test 699문항(그리고 위 작은 평가셋)이고, 영어 화학 합성 dev와 GPU에서는 확인하지 않았습니다. 정적 양자화·GPTQ·AWQ·컴파일은 시도하지 않았습니다.

### 18.3 EXAONE LoRA + vLLM 서빙 — GPU 실측 (저장소 소유자가 Kaggle T4 1장에서 실행, 2026-11-07)

§3의 "vLLM 또는 SGLang" 항목이 **완료(vLLM)**가 된 근거다. 작성자는 GPU가 없어 실행하지 못했고, 소유자가 `notebooks/gpu_experiments.ipynb`를 Kaggle(T4 2장 세션)에서 세 번 처음부터 돌려 보낸 결과 파일을 그대로 넣었다(`experiments/eval/PROVENANCE_exaone.md`). 아래는 세 번째 세션이고 앞의 두 세션은 `*_run1`, `*_run2`로 남겼다. 조건: EXAONE-4.0-1.2B를 한국어 학습 데이터(표 조회·계산·보류)로 LoRA 튜닝해 병합, vLLM fp16 GPU 1장, `--max-model-len 2048`, 평가는 ko test 699문항·같은 검증기·동시 16요청.

<!-- results:engine:start -->
| 플래너 / 모델 | n | verified EM % v1 | verified EM % v2 | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % v1 → v2 | 오보류율 % v1 → v2 | 파싱 실패 % | ms/예제 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 (CPU) | 699 | **36.2** | **35.9** | 21.7 | 26.2 | 59.1 | 31.6 | 31.6 | 94.0 → 96.0 | 42.4 → 45.8 | 0.0 | 21 |
| [2차] GRPO RL v3 = mT5-small 300M (CPU 4스레드, bs=1) | 699 | **32.8** | **31.6** | 32.2 | 38.2 | 0.0 | 31.7 | 18.9 | 46.0 → 48.0 | 27.0 → 31.6 | 0.0 | 500 |
| EXAONE-4.0-1.2B + LoRA 300개, vLLM fp16 (Kaggle T4 1장, 동시 16요청) | 699 | **53.1** | **52.5** | 58.1 | 67.2 | 0.0 | 55.6 | 23.1 | 18.0 → 42.0 | 14.3 → 20.3 | 0.1 | 2355 |
| 같은 모델, vLLM 텐서 병렬 TP=2 (Kaggle T4 2장, 동시 16요청) | 699 | **53.1** | **–** | 58.1 | 67.2 | 0.0 | 55.6 | 23.0 | 18.0 → – | 14.3 → – | 0.1 | 1718 |
| 같은 모델, SGLang 0.5.9 + T4 우회 모듈 (Kaggle T4 1장, 동시 8요청) | 699 | **53.2** | **52.6** | 58.1 | 67.3 | 0.0 | 55.8 | 22.7 | 18.0 → 42.0 | 14.0 → 20.0 | 0.1 | 5161 |
| EXAONE-4.0-1.2B + LoRA 300개, **표 입력에 열 번호(`colid`)**, vLLM fp16 (Kaggle T4 1장, 동시 16요청, 입력 예산 800) | 699 | **51.1** | **51.2** | 53.6 | 64.9 | 0.9 | 53.8 | 54.5 | 12.0 → 38.0 | 3.5 → 12.3 | 0.9 | 3173 |
| EXAONE-4.0-1.2B + LoRA **전체 3,587개**(3,654개 중 행 예산 안), vLLM fp16 (Kaggle T4 1장, 동시 16요청) | 699 | **84.3** | **81.5** | 79.3 | 85.0 | 89.1 | 85.5 | 85.5 | 66.0 → 68.0 | 2.0 → 6.9 | 0.1 | 2511 |
| 같은 전체 데이터 모델, vLLM TP=2 (T4 2장) | 699 | **84.3** | **81.5** | 79.3 | 85.0 | 89.1 | 85.5 | 85.5 | 66.0 → 68.0 | 2.0 → 6.9 | 0.1 | 1737 |
| 같은 전체 데이터 모델, SGLang + T4 우회 모듈 | 699 | **84.1** | **81.4** | 79.2 | 84.8 | 89.1 | 85.4 | 85.2 | 66.0 → 68.0 | 2.0 → 6.9 | 0.1 | 5231 |

EXAONE 행의 조건: ko test 699문항 전체를 vLLM 1장·동시 16요청으로 107.1초(끝에서 끝까지 6.5문항/s), ms/예제는 동시 요청 중의 요청당 지연. v1 = 개체 일치 검사 없음, v2 = 같은 출력을 개체 일치 검사로 재검증(본 실행과 같은 토크나이저·행 예산). 300개 모델은 세 번째 세션, 전체 데이터 모델은 네 번째 세션의 학습이다(출처는 `experiments/eval/PROVENANCE_exaone.md`).

**엔진 벤치** (`bench/engine_bench.py`, 같은 병합 모델, ko test 앞 64문항, OpenAI 호환 API 왕복 지연)

| 구성 | 동시 요청 수 | n | 총 시간 s | 처리량 요청/s | p50 ms | p95 ms | 프로그램 파싱 성공 % |
|---|---:|---:|---:|---:|---:|---:|---:|
| vLLM, GPU 1장 | 1 | 64 | 24.05 | 2.661 | 376.4 | 466.3 | 100.0 |
| vLLM, GPU 1장 | 8 | 64 | 4.2 | 15.231 | 471.9 | 616.7 | 100.0 |
| vLLM, GPU 1장 | 32 | 64 | 2.49 | 25.662 | 1073.0 | 1372.2 | 100.0 |
| vLLM TP=2, GPU 2장 | 1 | 64 | 12.65 | 5.06 | 185.0 | 279.1 | 100.0 |
| vLLM TP=2, GPU 2장 | 8 | 64 | 2.93 | 21.867 | 333.6 | 431.3 | 100.0 |
| vLLM TP=2, GPU 2장 | 32 | 64 | 1.56 | 40.966 | 677.7 | 927.4 | 100.0 |
| SGLang + T4 우회 모듈(fused 커널 없음), GPU 1장 | 1 | 64 | 50.58 | 1.265 | 828.9 | 1004.5 | 100.0 |
| SGLang + T4 우회 모듈(fused 커널 없음), GPU 1장 | 8 | 64 | 9.45 | 6.774 | 1104.7 | 1458.6 | 100.0 |
| SGLang + T4 우회 모듈(fused 커널 없음), GPU 1장 | 32 | 64 | 7.68 | 8.331 | 3506.0 | 6017.5 | 100.0 |
| 열 번호 형식 300개 모델, vLLM, GPU 1장 | 1 | 64 | 28.51 | 2.245 | 425.7 | 573.8 | 100.0 |
| 열 번호 형식 300개 모델, vLLM, GPU 1장 | 8 | 64 | 4.57 | 14.006 | 519.8 | 677.2 | 100.0 |
| 열 번호 형식 300개 모델, vLLM, GPU 1장 | 32 | 64 | 2.74 | 23.335 | 1130.9 | 1530.8 | 100.0 |
| 전체 데이터 모델, vLLM, GPU 1장 | 1 | 64 | 26.42 | 2.422 | 410.2 | 504.5 | 100.0 |
| 전체 데이터 모델, vLLM, GPU 1장 | 8 | 64 | 4.45 | 14.391 | 502.7 | 654.0 | 100.0 |
| 전체 데이터 모델, vLLM, GPU 1장 | 32 | 64 | 2.58 | 24.836 | 1064.3 | 1482.8 | 100.0 |
| 전체 데이터 모델, vLLM TP=2 | 1 | 64 | 13.32 | 4.804 | 196.2 | 290.9 | 100.0 |
| 전체 데이터 모델, vLLM TP=2 | 8 | 64 | 3.04 | 21.053 | 345.5 | 443.8 | 100.0 |
| 전체 데이터 모델, vLLM TP=2 | 32 | 64 | 1.68 | 38.027 | 730.4 | 1011.9 | 100.0 |
| 전체 데이터 모델, SGLang + 우회 모듈 | 1 | 64 | 51.95 | 1.232 | 882.3 | 1043.4 | 100.0 |
| 전체 데이터 모델, SGLang + 우회 모듈 | 8 | 64 | 9.67 | 6.622 | 1110.1 | 1659.1 | 100.0 |
| 전체 데이터 모델, SGLang + 우회 모듈 | 32 | 64 | 7.77 | 8.237 | 3503.5 | 6128.1 | 100.0 |

<!-- results:engine:end -->

**수작업 30문항**:

<!-- results:engine_custom:start -->
| 플래너 / 모델 | n | verified EM % v1 | verified EM % v2 | raw EM % (답 있는 문항) | 보류 재현율 % v2 | 오보류율 % v2 | 파싱 실패 % |
|---|---:|---:|---:|---:|---:|---:|---:|
| 휴리스틱 기준선 | 30 | **50.0** | **50.0** | 20.0 | 100.0 | 40.0 | 0.0 |
| [2차] GRPO RL v3 = mT5-small | 30 | **13.3** | **13.3** | 4.0 | 60.0 | 32.0 | 0.0 |
| EXAONE LoRA 300개, 열 번호 형식(`colid`), vLLM | 30 | **43.3** | **46.7** | 56.0 | 20.0 | 12.0 | 0.0 |
| EXAONE LoRA 전체 3,587개, vLLM | 30 | **66.7** | **66.7** | 68.0 | 20.0 | 4.0 | 0.0 |
| EXAONE LoRA 전체, vLLM TP=2 | 30 | **66.7** | **66.7** | 68.0 | 20.0 | 4.0 | 0.0 |
| EXAONE LoRA 전체, SGLang(우회) | 30 | **66.7** | **66.7** | 68.0 | 20.0 | 4.0 | 0.0 |

<!-- results:engine_custom:end -->

해석과 한계는 README §10.3과 같다. 요점만 적으면 (1) verified EM <!-- num:experiments/eval/exaone_vllm_ko_test/metrics.json:metrics.verified_em:pct -->53.1<!-- /num -->%는 mT5 최종 <!-- num:experiments/eval/rl_v3_ko_test/metrics.json:metrics.verified_em:pct -->32.8<!-- /num -->%·기준선 <!-- num:experiments/eval/heuristic_ko_test/metrics.json:metrics.verified_em:pct -->36.2<!-- /num -->%보다 높지만 모델 크기(4배)·사전학습 언어·하드웨어가 모두 달라 튜닝 방법의 비교가 아니다. (2) 계산 문항 <!-- num:experiments/eval/exaone_vllm_ko_test/metrics.json:metrics.calc_em:pct -->0.0<!-- /num -->%로 mT5와 같은 약점이다. (3) 모델이 인용한 셀 그대로는 <!-- num:experiments/eval/exaone_vllm_ko_test/metrics.json:metrics.evidence_cells_exact_raw:pct -->23.1<!-- /num -->%만 맞고 검증기 보정 뒤 <!-- num:experiments/eval/exaone_vllm_ko_test/metrics.json:metrics.evidence_cells_exact:pct -->55.6<!-- /num -->%다. (4) 검증기 v2(같은 토크나이저·행 예산으로 재검증)는 verified EM <!-- num:experiments/eval/exaone_vllm_ko_test_ec/metrics.json:metrics.verified_em:pct -->52.5<!-- /num -->%, 보류 재현율 16% → <!-- num:experiments/eval/exaone_vllm_ko_test_ec/metrics.json:metrics.abstain_recall:pct -->42.0<!-- /num -->%다. 원본 539문항만 보면 <!-- num:experiments/eval/exaone_vllm_ko_test_ec/metrics.json:metrics.by_source.korwikitq.verified_em:pct -->64.2<!-- /num -->%(mT5 최종 <!-- num:experiments/eval/rl_v3_ko_test_ec/metrics.json:metrics.by_source.korwikitq.verified_em:pct -->36.5<!-- /num -->%), 합성 계산 문항은 <!-- num:experiments/eval/exaone_vllm_ko_test_ec/metrics.json:metrics.by_source.synthetic.verified_em:pct -->13.1<!-- /num -->%(mT5 <!-- num:experiments/eval/rl_v3_ko_test_ec/metrics.json:metrics.by_source.synthetic.verified_em:pct -->15.0<!-- /num -->%)로 차이는 조회에서만 난다. (5) 쌍 비교(검증기 v2): mT5 최종보다 나은 문항 <!-- num:experiments/eval/paired_tests.json:exaone_vllm_vs_rl_v3_ko_test_ec.candidate_better:int -->195<!-- /num -->개 대 <!-- num:experiments/eval/paired_tests.json:exaone_vllm_vs_rl_v3_ko_test_ec.reference_better:int -->49<!-- /num -->개(p<!-- num:experiments/eval/paired_tests.json:exaone_vllm_vs_rl_v3_ko_test_ec.p_display --><0.001<!-- /num -->), 휴리스틱보다 <!-- num:experiments/eval/paired_tests.json:exaone_vllm_vs_heuristic_ko_test_ec.candidate_better:int -->242<!-- /num -->개 대 <!-- num:experiments/eval/paired_tests.json:exaone_vllm_vs_heuristic_ko_test_ec.reference_better:int -->126<!-- /num -->개(p<!-- num:experiments/eval/paired_tests.json:exaone_vllm_vs_heuristic_ko_test_ec.p_display --><0.001<!-- /num -->). 직접 보류 출력은 <!-- num:experiments/eval/exaone_vllm_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->0<!-- /num -->건으로 보류는 전부 검증기가 했다. LoRA는 예제 <!-- num:experiments/exaone_lora/train_info.json:n_examples:int -->300<!-- /num -->개·<!-- num:experiments/exaone_lora/train_info.json:steps:int -->18<!-- /num --> step·1 epoch(fp16, 손실 <!-- num:experiments/exaone_lora/train_info.json:loss_log.0.loss -->1.26<!-- /num --> → <!-- num:experiments/exaone_lora/train_info.json:loss_log.17.loss -->0.388<!-- /num -->)이고 전체 데이터 학습은 하지 않았다. (6) SGLang은 T4에서 두 번 커널 오류, 한 번 설정 읽기 오류 뒤 네 번째에 성공했다: 같은 모델로 verified EM <!-- num:experiments/eval/exaone_sglang_ko_test/metrics.json:metrics.verified_em:pct -->53.2<!-- /num -->%(vLLM <!-- num:experiments/eval/exaone_vllm_ko_test/metrics.json:metrics.verified_em:pct -->53.1<!-- /num -->%, 문항 <!-- num:experiments/eval/paired_tests.json:exaone_sglang_vs_vllm_ko_test.candidate_better:int -->1<!-- /num -->/<!-- num:experiments/eval/paired_tests.json:exaone_sglang_vs_vllm_ko_test.reference_better:int -->0<!-- /num -->개 차이), 동시 32요청 <!-- num:experiments/bench/engine_sglang_c32.json:throughput_req_per_s -->8.33<!-- /num --> 요청/s. fused 커널을 PyTorch 구현으로 바꾼 우회 모듈이라 vLLM과의 속도 비교가 아니다(`experiments/serving/sglang_t4_failure.md`). (7) 텐서 병렬 TP=2(T4 2장): 동시 1요청 p50 <!-- num:experiments/bench/engine_vllm_c1.json:p50_ms -->376.4<!-- /num --> → <!-- num:experiments/bench/engine_vllm_tp2_c1.json:p50_ms -->185<!-- /num --> ms, 동시 32요청 처리량 <!-- num:experiments/bench/engine_vllm_c32.json:throughput_req_per_s -->25.66<!-- /num --> → <!-- num:experiments/bench/engine_vllm_tp2_c32.json:throughput_req_per_s -->40.97<!-- /num --> 요청/s, verified EM <!-- num:experiments/eval/exaone_vllm_tp2_ko_test/metrics.json:metrics.verified_em:pct -->53.1<!-- /num -->%(1장과 문항 <!-- num:experiments/eval/paired_tests.json:exaone_vllm_tp2_vs_tp1_ko_test.candidate_better:int -->0<!-- /num -->/<!-- num:experiments/eval/paired_tests.json:exaone_vllm_tp2_vs_tp1_ko_test.reference_better:int -->0<!-- /num -->개 뒤집힘, p=<!-- num:experiments/eval/paired_tests.json:exaone_vllm_tp2_vs_tp1_ko_test.p_display -->1.000<!-- /num -->). mT5 파이프라인 병렬 GPU 실측은 §9. (8) 같은 설정의 LoRA 학습 세션 간 문항별 뒤집힘은 1차 대 2차 <!-- num:experiments/eval/paired_tests.json:exaone_vllm_run2_vs_run1_ko_test.candidate_better:int -->58<!-- /num -->/<!-- num:experiments/eval/paired_tests.json:exaone_vllm_run2_vs_run1_ko_test.reference_better:int -->51<!-- /num -->개(p=<!-- num:experiments/eval/paired_tests.json:exaone_vllm_run2_vs_run1_ko_test.p_display -->0.566<!-- /num -->), 2차 대 3차 <!-- num:experiments/eval/paired_tests.json:exaone_vllm_run3_vs_run2_ko_test.candidate_better:int -->15<!-- /num -->/<!-- num:experiments/eval/paired_tests.json:exaone_vllm_run3_vs_run2_ko_test.reference_better:int -->16<!-- /num -->개: 1점 안의 차이는 학습 잡음이다. (9) SGLang 세 번째 시도는 서버가 떴으나 출력이 프로그램 문법이 아니었다(파싱 실패 99%). 원인은 transformers 5.x가 저장한 config.json의 RoPE 키(`rope_parameters`)를 SGLang의 transformers 4.57이 읽지 못해 `rope_theta` 기본값 10,000과 스케일링 없음으로 모델을 올린 것(`experiments/serving/sglang_run3_rope_config/`, 이슈 39). 키를 복원한 네 번째 시도는 파싱 실패 <!-- num:experiments/eval/exaone_sglang_ko_test/metrics.json:metrics.parse_fail_rate:pct -->0.1<!-- /num -->%였다. 세 300개 LoRA 세션의 verified EM은 <!-- num:experiments/eval/exaone_vllm_ko_test_run1/metrics.json:metrics.verified_em:pct -->52.2<!-- /num --> / <!-- num:experiments/eval/exaone_vllm_ko_test_run2/metrics.json:metrics.verified_em:pct -->53.2<!-- /num --> / <!-- num:experiments/eval/exaone_vllm_ko_test/metrics.json:metrics.verified_em:pct -->53.1<!-- /num -->%다. (10) **전체 데이터 LoRA(4차 세션)**: <!-- num:experiments/exaone_lora_full/train_info.json:n_examples:int -->3,587<!-- /num -->개·<!-- num:experiments/exaone_lora_full/train_info.json:steps:int -->224<!-- /num --> step·T4 <!-- num:experiments/exaone_lora_full/train_info.json:wall_s -->1,862.7<!-- /num -->초로 verified EM <!-- num:experiments/eval/exaone_full_vllm_ko_test/metrics.json:metrics.verified_em:pct -->84.3<!-- /num -->%(v2 <!-- num:experiments/eval/exaone_full_vllm_ko_test_ec/metrics.json:metrics.verified_em:pct -->81.5<!-- /num -->%), 원본 539문항 <!-- num:experiments/eval/exaone_full_vllm_ko_test/metrics.json:metrics.by_source.korwikitq.verified_em:pct -->85.0<!-- /num -->%, 합성 <!-- num:experiments/eval/exaone_full_vllm_ko_test/metrics.json:metrics.by_source.synthetic.verified_em:pct -->81.9<!-- /num -->%(계산 <!-- num:experiments/eval/exaone_full_vllm_ko_test/metrics.json:metrics.calc_em:pct -->89.1<!-- /num -->%, 학습과 같은 템플릿). 기준선 대비 <!-- num:experiments/eval/paired_tests.json:exaone_full_vs_heuristic_ko_test_ec.candidate_better:int -->344<!-- /num -->/<!-- num:experiments/eval/paired_tests.json:exaone_full_vs_heuristic_ko_test_ec.reference_better:int -->25<!-- /num -->개(p<!-- num:experiments/eval/paired_tests.json:exaone_full_vs_heuristic_ko_test_ec.p_display --><0.001<!-- /num -->), 300개 모델 대비 <!-- num:experiments/eval/paired_tests.json:exaone_full_vs_300_ko_test_ec.candidate_better:int -->225<!-- /num -->/<!-- num:experiments/eval/paired_tests.json:exaone_full_vs_300_ko_test_ec.reference_better:int -->22<!-- /num -->개. 직접 보류 <!-- num:experiments/eval/exaone_full_vllm_ko_test/analysis.json:abstain_breakdown.explicit_abstain_outputs:int -->32<!-- /num -->/50건, 정답 문항에 직접 보류 <!-- num:experiments/eval/exaone_full_vllm_ko_test/analysis.json:abstain_breakdown.explicit_abstain_on_answerable:int -->0<!-- /num -->건, 답한 문항 중 오답 <!-- num:experiments/eval/exaone_full_vllm_ko_test/analysis.json:selective.wrong_answer_rate:pct -->13.9<!-- /num -->%. 수작업 30문항 <!-- num:experiments/eval/exaone_full_vllm_ko_custom/metrics.json:metrics.verified_em:pct -->66.7<!-- /num -->%(셀 9/9, 계산 6/6, 단위·기간 4/5, 보류 1/5, 본문 0/5. 본문 예제 없이 학습). vLLM 1장·TP=2·SGLang(우회)이 같은 답(문항 차이 <!-- num:experiments/eval/paired_tests.json:exaone_full_tp2_vs_tp1_ko_test.candidate_better:int -->0<!-- /num -->/<!-- num:experiments/eval/paired_tests.json:exaone_full_tp2_vs_tp1_ko_test.reference_better:int -->0<!-- /num -->, <!-- num:experiments/eval/paired_tests.json:exaone_full_sglang_vs_vllm_ko_test.candidate_better:int -->0<!-- /num -->/<!-- num:experiments/eval/paired_tests.json:exaone_full_sglang_vs_vllm_ko_test.reference_better:int -->1<!-- /num -->). 이것이 이 프로젝트에서 기준선을 넘은 유일한 모델이며, GPU·4배 모델이라는 조건을 붙인다. (11) 전체 데이터 학습을 Colab 무료 T4에서 한 번 더 하자(`*_run2`) verified EM <!-- num:experiments/eval/exaone_full_vllm_ko_test_run2/metrics.json:metrics.verified_em:pct -->87.1<!-- /num -->%로 문항별 <!-- num:experiments/eval/paired_tests.json:exaone_full_run2_vs_run1_ko_test.candidate_better:int -->40<!-- /num -->/<!-- num:experiments/eval/paired_tests.json:exaone_full_run2_vs_run1_ko_test.reference_better:int -->20<!-- /num -->개(p=<!-- num:experiments/eval/paired_tests.json:exaone_full_run2_vs_run1_ko_test.p_display -->0.013<!-- /num -->) 달랐다. 학습 실행만으로 약 3점이 움직이고 잡음 범위를 넘으므로 전체 모델의 점수는 84~87% 범위로 읽는다. 수작업 30문항은 두 실행 다 <!-- num:experiments/eval/exaone_full_vllm_ko_custom_run2/metrics.json:metrics.verified_em:pct -->66.7<!-- /num -->%.

## 19. 보강 측정과 선행 연구 대비 위치 (2026-11-10)

공고 원문을 읽고(§3) 이 프로젝트의 중심을 테이블이해(Table MRC)로 다시 잡았다. 같은 날 공고 주제로 만들어진 다른 프로젝트와 논문을 조사했고(`docs/research/papers.md`), 결론은 이렇다. FastAPI·LangGraph·vLLM 같은 스택은 흔하다. 이 프로젝트에서 다른 곳에 없는 것은 **측정**이다. 그래서 이 절은 세 가지 측정을 통계적으로 보강하고, 가까운 논문 12편을 원문으로 읽어 무엇을 새롭다고 말할 수 있는지 정리한다. 새 모델 학습은 없다. 저장된 예측을 다시 분석했고, CPU에서 mT5 두 모델과 기준선을 새 질문 세트에 한 번씩 돌렸다.

### 19.1 답은 맞는데 근거 셀이 틀린 비율

모델은 `op: lookup ; cells: r3c1 ; answer: …` 형태로 답과 근거 셀을 함께 낸다. 답 텍스트가 정답과 같은 조회 답만 골라, 모델이 인용한 셀(검증기가 손대기 전)에 실제로 그 답이 들어 있는지 셌다.

<!-- results:evidence:start -->
| 모델 | 답 텍스트가 맞은 조회 답 | 인용 셀 = 정답 셀 | 같은 값의 다른 셀 | 인용 셀에 답이 없음 | **인용 셀에 답이 없는 비율 % (95% 구간)** | 그중 행은 맞고 열이 틀림 | 검증기: 근거를 고쳐 답함 / 보류 | verified EM % | 근거 복구 없이 채점한 verified EM % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SFT stage2 = mT5-small 300M | 177 | 83 | 0 | 94 | **53.1 (45.8–60.3)** | 84 | 89 / 5 | 27.5 | **18.9** |
| 화학 SFT (1차 최종 mT5) | 217 | 61 | 0 | 156 | **71.9 (65.6–77.5)** | 148 | 139 / 17 | 29.8 | **13.3** |
| GRPO RL v1 (보상 허점) | 169 | 78 | 0 | 91 | **53.8 (46.3–61.2)** | 82 | 85 / 6 | 26.8 | **18.3** |
| [2차] GRPO RL v3 (mT5 최종) | 209 | 99 | 0 | 110 | **52.6 (45.9–59.3)** | 107 | 105 / 5 | 32.8 | **20.2** |
| EXAONE-4.0-1.2B LoRA 300개, 1번째 학습 | 360 | 168 | 1 | 191 | **53.1 (47.9–58.1)** | 189 | 181 / 10 | 52.2 | **29.3** |
| 같은 설정, 2번째 학습 | 372 | 137 | 0 | 235 | **63.2 (58.2–67.9)** | 231 | 221 / 14 | 53.2 | **24.6** |
| 같은 설정, 3번째 학습 | 376 | 130 | 1 | 245 | **65.2 (60.2–69.8)** | 241 | 227 / 18 | 53.1 | **23.5** |
| **같은 300개, 표 입력에 열 번호(`colid`)** | 347 | 335 | 1 | 11 | **3.2 (1.8–5.6)** | 10 | 9 / 2 | 51.1 | **49.9** |
| EXAONE-4.0-1.2B LoRA 전체 3,587개, 1번째 학습 | 455 | 449 | 0 | 6 | **1.3 (0.6–2.9)** | 6 | 4 / 2 | 84.3 | **83.8** |
| 같은 설정, 2번째 학습 | 458 | 451 | 1 | 6 | **1.3 (0.6–2.8)** | 6 | 5 / 1 | 87.1 | **86.4** |

대상은 한국어 test의 조회 문항 539개(KorWikiTQ 원본) 가운데 모델이 쓴 답 텍스트가 정답과 같은 것이다. 인용 셀은 검증기가 손대기 전 모델 출력의 `cells:` 값이다. 정답 셀은 답 텍스트에서 역으로 찾은 것이므로, 답과 같은 값을 가진 다른 셀을 인용한 경우는 오류로 세지 않았다. 구간은 Wilson 95%다. 마지막 두 열은 test 699문항 전체의 verified EM(검증기 v1)과, 인용 셀에 답이 없을 때 근거를 고치지 않고 보류로 채점한 값이다. `scripts/evidence_error.py`가 저장된 예측에서 다시 계산한다.

<!-- results:evidence:end -->

읽는 법:

1. **약한 모델은 맞힌 답의 절반 이상에서 엉뚱한 셀을 가리킨다.** mT5 최종 모델(RL v3)은 답 텍스트가 맞은 조회 답 <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.correct_lookup_answers:int -->209<!-- /num -->개 가운데 <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.no_answer_in_cell:int -->110<!-- /num -->개(<!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.strict.rate:pct -->52.6<!-- /num -->%, 95% 구간 <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.strict.lo:pct -->45.9<!-- /num -->~<!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.strict.hi:pct -->59.3<!-- /num -->%)에서 답이 없는 셀을 인용했다. EXAONE-4.0-1.2B를 300개로 LoRA 튜닝한 모델은 답은 훨씬 많이 맞히지만(답이 맞은 조회 답 <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.correct_lookup_answers:int -->376<!-- /num -->개) 이 비율은 세 번의 학습에서 <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test_run1.strict.rate:pct -->53.1<!-- /num -->%, <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test_run2.strict.rate:pct -->63.2<!-- /num -->%, <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.strict.rate:pct -->65.2<!-- /num -->%였다. 답 정확도가 오른다고 근거 정확도가 따라 오르지 않는다.
2. **전체 데이터로 학습하면 이 오류가 거의 사라진다.** 같은 EXAONE을 3,587개로 튜닝하면 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.correct_lookup_answers:int -->455<!-- /num -->개 중 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.no_answer_in_cell:int -->6<!-- /num -->개(<!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.strict.rate:pct -->1.3<!-- /num -->%, 구간 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.strict.lo:pct -->0.6<!-- /num -->~<!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.strict.hi:pct -->2.9<!-- /num -->%), 두 번째 학습에서도 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test_run2.correct_lookup_answers:int -->458<!-- /num -->개 중 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test_run2.no_answer_in_cell:int -->6<!-- /num -->개(<!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test_run2.strict.rate:pct -->1.3<!-- /num -->%)다. 300개 모델의 구간과 전혀 겹치지 않는다.
3. **틀리는 방식은 거의 하나다.** 행은 맞고 열이 틀린다. RL v3의 <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.no_answer_in_cell:int -->110<!-- /num -->건 중 <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.strict_where.same_row:int -->107<!-- /num -->건, EXAONE 300개 모델(3번째)의 <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.no_answer_in_cell:int -->245<!-- /num -->건 중 <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.strict_where.same_row:int -->241<!-- /num -->건이 그렇다. 모델은 어느 행인지 찾고 답 글자도 맞게 쓰지만, 그 답이 몇 번째 열에 있는지를 틀린다.
4. **"같은 값의 다른 셀"은 원인이 아니다.** 정답 셀은 답 텍스트에서 역으로 찾은 것이라, 같은 값이 여러 셀에 있으면 다른 셀을 인용해도 틀렸다고 셀 위험이 있다. 그런 경우는 따로 셌고 모든 모델에서 0~1건이다.
5. **검증기는 이 경우 답을 버리지 않고 근거를 고친다. 약한 모델의 점수는 이 복구에 기대고 있다.** 답 텍스트와 같은 셀이 표에 하나뿐이면 그 셀로 근거를 바꾸고, 그 사실을 실패한 검사(`evidence_repaired`)로 남긴다. 복구를 끄고 보류로 채점하면 verified EM은 mT5 최종 <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.verified_em:pct -->32.8<!-- /num -->% → <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.verified_em_no_repair:pct -->20.2<!-- /num -->%, EXAONE 300개(3번째 학습) <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.verified_em:pct -->53.1<!-- /num -->% → <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.verified_em_no_repair:pct -->23.5<!-- /num -->%로 내려간다. 전체 데이터 EXAONE은 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verified_em:pct -->84.3<!-- /num -->% → <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verified_em_no_repair:pct -->83.8<!-- /num -->%로 거의 그대로다(표의 마지막 두 열). 약한 모델의 verified EM은 "모델이 근거를 맞혔다"는 뜻이 아니다.

한계: 조회 문항(KorWikiTQ 원본 539개)만 대상이다. 계산 문항은 합성 템플릿이라 넣지 않았다. 300개 모델은 학습마다 10%p 넘게 움직였다. 전체 데이터 모델은 두 번, mT5 모델들은 한 번씩만 학습했다.

### 19.2 검증기 앞뒤의 운영점

검증기는 틀린 답을 얼마나 막고, 그 대가로 맞는 답을 얼마나 보류하는가. 같은 모델 출력을 세 조건에서 채점했다.

<!-- results:operating:start -->
| 모델 | 조건 | 답한 비율 % | 답한 것 중 정답 % (95% 구간) | 오답이 그대로 나간 비율 % (전체 대비) | 정답 수 / 오답 수 |
|---|---|---:|---:|---:|---:|
| 휴리스틱 기준선 | 모델 출력 그대로 | 54.4 | 37.1 (32.4–42.1) | 34.2 | 141 / 239 |
| 휴리스틱 기준선 | 검증기 v1 | 53.9 | 54.6 (49.6–59.6) | 24.5 | 206 / 171 |
| 휴리스틱 기준선 | 검증기 v2(개체 일치 검사) | 50.6 | 57.3 (52.1–62.4) | 21.6 | 203 / 151 |
| 휴리스틱 기준선 | 검증기 v1에서 근거 복구를 끄고 보류 | 53.9 | 54.6 (49.6–59.6) | 24.5 | 206 / 171 |
| [2차] GRPO RL v3 (mT5 최종) | 모델 출력 그대로 | 81.3 | 36.8 (32.9–40.8) | 51.4 | 209 / 359 |
| [2차] GRPO RL v3 (mT5 최종) | 검증기 v1 | 71.7 | 41.1 (36.9–45.5) | 42.2 | 206 / 295 |
| [2차] GRPO RL v3 (mT5 최종) | 검증기 v2(개체 일치 검사) | 67.2 | 41.9 (37.5–46.4) | 39.1 | 197 / 273 |
| [2차] GRPO RL v3 (mT5 최종) | 검증기 v1에서 근거 복구를 끄고 보류 | 31.2 | 46.3 (39.8–53.0) | 16.7 | 101 / 117 |
| EXAONE LoRA 300개 (3번째 학습) | 모델 출력 그대로 | 99.9 | 54.0 (50.3–57.7) | 45.9 | 377 / 321 |
| EXAONE LoRA 300개 (3번째 학습) | 검증기 v1 | 85.4 | 60.6 (56.7–64.5) | 33.6 | 362 / 235 |
| EXAONE LoRA 300개 (3번째 학습) | 검증기 v2(개체 일치 검사) | 78.1 | 63.4 (59.2–67.3) | 28.6 | 346 / 200 |
| EXAONE LoRA 300개 (3번째 학습) | 검증기 v1에서 근거 복구를 끄고 보류 | 30.6 | 63.1 (56.4–69.3) | 11.3 | 135 / 79 |
| EXAONE LoRA 300개, 열 번호 형식(`colid`) | 모델 출력 그대로 | 99.1 | 50.2 (46.5–53.9) | 49.4 | 348 / 345 |
| EXAONE LoRA 300개, 열 번호 형식(`colid`) | 검증기 v1 | 95.9 | 52.4 (48.6–56.1) | 45.6 | 351 / 319 |
| EXAONE LoRA 300개, 열 번호 형식(`colid`) | 검증기 v2(개체 일치 검사) | 85.8 | 56.5 (52.5–60.4) | 37.3 | 339 / 261 |
| EXAONE LoRA 300개, 열 번호 형식(`colid`) | 검증기 v1에서 근거 복구를 끄고 보류 | 91.8 | 53.3 (49.4–57.1) | 42.9 | 342 / 300 |
| EXAONE LoRA 전체 (1번째 학습) | 모델 출력 그대로 | 95.3 | 77.3 (74.0–80.3) | 21.6 | 515 / 151 |
| EXAONE LoRA 전체 (1번째 학습) | 검증기 v1 | 93.4 | 85.2 (82.2–87.7) | 13.9 | 556 / 97 |
| EXAONE LoRA 전체 (1번째 학습) | 검증기 v2(개체 일치 검사) | 88.7 | 86.5 (83.5–88.9) | 12.0 | 536 / 84 |
| EXAONE LoRA 전체 (1번째 학습) | 검증기 v1에서 근거 복구를 끄고 보류 | 92.0 | 85.9 (82.9–88.3) | 13.0 | 552 / 91 |
| EXAONE LoRA 전체 (2번째 학습) | 모델 출력 그대로 | 92.4 | 82.7 (79.5–85.4) | 16.0 | 534 / 112 |
| EXAONE LoRA 전체 (2번째 학습) | 검증기 v1 | 91.3 | 87.8 (85.0–90.1) | 11.2 | 560 / 78 |
| EXAONE LoRA 전체 (2번째 학습) | 검증기 v2(개체 일치 검사) | 87.0 | 89.1 (86.4–91.4) | 9.4 | 542 / 66 |
| EXAONE LoRA 전체 (2번째 학습) | 검증기 v1에서 근거 복구를 끄고 보류 | 90.1 | 88.1 (85.3–90.4) | 10.7 | 555 / 75 |

한국어 test 699문항 전체(답이 없는 문항 포함) 기준이다. "모델 출력 그대로"는 모델이 쓴 답 텍스트를 채점한 것이고, 답이 없는 문항에 답을 쓰면 오답이다. 검증기 행은 도구가 인용 셀로 다시 계산한 답을 채점하므로 계산 문항에서는 정답 수가 늘 수 있다. 답한 비율이 줄어든 만큼이 보류다. 마지막 조건은 인용 셀에 답이 없을 때 근거를 고치지 않고 보류했다면 어떻게 됐을지를 저장된 출력에서 계산한 값이다(검증기 코드에서 복구 분기 다음은 보류다).

<!-- results:operating:end -->

읽는 법:

1. **검증기는 답하는 비율을 조금 내주고 오답 유출을 크게 줄인다.** 전체 데이터 EXAONE(1번째 학습)은 모델 출력을 그대로 내보내면 전체 문항의 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.raw.wrong_answer_rate.rate:pct -->21.6<!-- /num -->%가 오답으로 나간다. 검증기 v1을 거치면 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier.wrong_answer_rate.rate:pct -->13.9<!-- /num -->%, v2를 거치면 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_subject_check.wrong_answer_rate.rate:pct -->12.0<!-- /num -->%다. 답하는 비율은 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.raw.coverage:pct -->95.3<!-- /num -->% → <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier.coverage:pct -->93.4<!-- /num -->% → <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_subject_check.coverage:pct -->88.7<!-- /num -->%로 줄어든다.
2. **정답 수가 느는 경우가 있다.** 검증기는 계산 문항에서 모델이 쓴 숫자를 믿지 않고 인용 셀로 다시 계산한다. 그래서 같은 모델의 정답 수가 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.raw.answered_correct:int -->515<!-- /num -->개에서 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier.answered_correct:int -->556<!-- /num -->개로 늘었다. 검증기 덕분에 정답이 된 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_changes.gained:int -->44<!-- /num -->개 가운데 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_changes.gained_calculation:int -->39<!-- /num -->개는 계산 문항이고, 전부 셀과 연산은 정확히 골랐지만 모델이 쓴 숫자가 틀린 경우다(예: `op: sum ; cells: r6c0, r1c0 ; answer: 15`, 두 셀의 실제 합은 9). 나머지 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_changes.gained_lookup:int -->5<!-- /num -->개는 조회 문항에서 모델이 셀 내용을 잘라 쓴 것을 셀 원문으로 답한 경우다. 검증기를 거치며 잃은 정답은 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_changes.lost:int -->3<!-- /num -->개다.
3. **검증기 v2는 더 조심스러운 운영점이다.** v1보다 오답을 더 막지만 정답도 더 보류한다(1번째 학습에서 정답 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier.answered_correct:int -->556<!-- /num -->개 → <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_subject_check.answered_correct:int -->536<!-- /num -->개, 오답 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier.answered_wrong:int -->97<!-- /num -->개 → <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_subject_check.answered_wrong:int -->84<!-- /num -->개). 어느 쪽이 나은지는 오답 한 건과 보류 한 건의 비용 비율에 달려 있다. 이 프로젝트는 그 비용을 정하지 않았으므로 두 점을 모두 보고한다.
4. **검증기를 거쳐도 오답은 남는다.** 가장 좋은 조건(2번째 학습, v2)에서도 전체의 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test_run2.verifier_subject_check.wrong_answer_rate.rate:pct -->9.4<!-- /num -->%가 오답으로 나간다. 검증기는 "답이 인용 셀과 일치하는가"를 볼 뿐이다. 모델이 엉뚱한 행의 셀을 인용하고 그 셀의 값을 그대로 답으로 쓰면 통과한다.

5. **근거 복구는 정답과 오답을 함께 내보낸다.** 복구는 "답 텍스트가 표의 한 셀과 같다"는 것만 확인한다. 모델이 다른 셀의 값을 답으로 쓴 경우도 통과한다. mT5 최종 모델에서 복구된 답은 <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.repaired_answers:int -->283<!-- /num -->건이고, 복구를 끄면 오답 유출이 <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.verifier.wrong_answer_rate.rate:pct -->42.2<!-- /num -->% → <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.verifier_no_repair.wrong_answer_rate.rate:pct -->16.7<!-- /num -->%로 줄지만 답하는 비율도 <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.verifier.coverage:pct -->71.7<!-- /num -->% → <!-- num:experiments/eval/evidence_error.json:rl_v3_ko_test.verifier_no_repair.coverage:pct -->31.2<!-- /num -->%로 준다. 전체 데이터 EXAONE에서는 복구된 답이 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.repaired_answers:int -->10<!-- /num -->건뿐이라 차이가 거의 없다(오답 유출 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier.wrong_answer_rate.rate:pct -->13.9<!-- /num -->% → <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.verifier_no_repair.wrong_answer_rate.rate:pct -->13.0<!-- /num -->%). 인용이 정확한 모델에는 복구가 필요 없고, 인용이 부정확한 모델에서는 복구가 점수와 오답을 함께 올린다. 서비스 기본값은 복구를 켠 상태다.

이것은 임계값을 움직여 그린 곡선이 아니다. 이 시스템에는 조절할 신뢰 점수가 없고 조건이 네 개뿐이다.

### 19.3 표가 겹치는 분할은 점수를 얼마나 올리는가

**공개 분할의 겹침.** KorWikiTQ 공개 train 파일과 dev 파일에는 페이지 주소와 모든 셀이 똑같은 표 <!-- num:data/ko/official_split_profile.json:shared_tables_by_url_and_content:int -->1,578<!-- /num -->개가 함께 들어 있다(dev 표 <!-- num:data/ko/official_split_profile.json:dev.unique_tables_by_url_and_content:int -->3,018<!-- /num -->개 중). 공개 dev 질문 <!-- num:data/ko/official_split_profile.json:dev_on_train_table.of:int -->11,771<!-- /num -->개 가운데 <!-- num:data/ko/official_split_profile.json:dev_on_train_table.examples:int -->5,046<!-- /num -->개(<!-- num:data/ko/official_split_profile.json:dev_on_train_table.rate:pct -->42.9<!-- /num -->%)가 train에도 있는 표를 묻는다. 겹치는 것은 표이고 질문이 아니다. 같은 표에서 같은 답을 묻는 질문이 train에도 있는 경우는 <!-- num:data/ko/official_split_profile.json:dev_same_table_same_answer_in_train.examples:int -->51<!-- /num -->개(<!-- num:data/ko/official_split_profile.json:dev_same_table_same_answer_in_train.rate:pct -->0.4<!-- /num -->%), 같은 질문은 <!-- num:data/ko/official_split_profile.json:dev_same_table_same_question_in_train.examples:int -->0<!-- /num -->개다. 원논문과 README는 분할을 어떻게 했는지 밝히지 않는다(§19.4). 이전 판의 "표 1,755개 공유"는 같은 위키 페이지 수였다. 한 페이지에 표가 여러 개 있을 수 있어 이번에 표 내용까지 같은 경우로 다시 셌다(이슈 42).

**효과 측정.** 이 프로젝트는 표 단위로 다시 나눴으므로 평가 표는 학습 때 본 적이 없다. 그 선택이 점수에 얼마나 영향을 주는지 재려고 질문 세트 두 개를 만들었다. 하나는 학습에 쓴 표 <!-- num:data/ko/leak_probe_report.json:seen.tables:int -->882<!-- /num -->개에 대한 **새 질문**(표당 3문항 상한 때문에 학습에 안 들어간 질문) <!-- num:data/ko/leak_probe_report.json:seen.questions:int -->1,497<!-- /num -->개다. 다른 하나는 어떤 모델도 학습하지 않은 표 <!-- num:data/ko/leak_probe_report.json:unseen.tables:int -->879<!-- /num -->개에서 같은 규칙으로 고른 질문 <!-- num:data/ko/leak_probe_report.json:unseen.questions:int -->1,497<!-- /num -->개다. 표는 한 번의 무작위 섞기로 배정되었으므로 두 세트의 차이는 "학습 때 그 표를 봤는가" 하나다. 학습이 없는 휴리스틱 기준선을 대조군으로 함께 돌렸다.

<!-- results:leak:start -->
| 모델 | 지표 | 학습 때 본 표의 새 질문 % (95% 구간) | 본 적 없는 표의 질문 % (95% 구간) | 차이 %p (95% 구간, 표 단위 부트스트랩) |
|---|---|---:|---:|---:|
| 휴리스틱 기준선 (학습 없음, 대조군) | verified EM | 27.9 (25.7–30.2) | 26.7 (24.5–29.0) | +1.2 (-2.1 ~ +4.5) |
| 휴리스틱 기준선 (학습 없음, 대조군) | 모델이 인용한 셀 = 정답 셀 | 27.9 (25.7–30.2) | 26.7 (24.5–28.9) | +1.3 (-2.0 ~ +4.6) |
| SFT stage2 = mT5-small | verified EM | 34.3 (31.9–36.7) | 36.2 (33.8–38.7) | -1.9 (-5.5 ~ +1.8) |
| SFT stage2 = mT5-small | 모델이 인용한 셀 = 정답 셀 | 25.7 (23.5–27.9) | 25.0 (22.9–27.2) | +0.7 (-2.5 ~ +4.0) |
| [2차] GRPO RL v3 (mT5 최종) | verified EM | 38.9 (36.5–41.4) | 41.3 (38.8–43.8) | -2.3 (-6.0 ~ +1.4) |
| [2차] GRPO RL v3 (mT5 최종) | 모델이 인용한 셀 = 정답 셀 | 22.8 (20.7–25.0) | 24.0 (21.9–26.2) | -1.2 (-4.2 ~ +1.9) |

두 세트는 각각 1,497문항이다. 본 표 세트는 train 표 882개에서 학습에 쓰지 않은 질문이고, 안 본 표 세트는 dev·test 표와 미사용 표 879개에서 같은 규칙으로 고른 질문이다. 두 세트가 공유하는 표는 0개, 학습 질문과 겹치는 질문은 0개다. 표는 한 번의 무작위 섞기로 배정했으므로 두 세트의 차이는 "학습 때 그 표를 봤는가"뿐이다(`scripts/data/build_leak_probe.py`, `scripts/leak_effect.py`).

<!-- results:leak:end -->

읽는 법:

1. **mT5에서는 학습 때 본 표라고 점수가 오르지 않았다.** mT5 최종 모델(RL v3)의 verified EM은 본 표의 새 질문에서 <!-- num:experiments/eval/leak_effect.json:planners.rl_v3.verified_em.seen.rate:pct -->38.9<!-- /num -->%, 처음 보는 표에서 <!-- num:experiments/eval/leak_effect.json:planners.rl_v3.verified_em.unseen.rate:pct -->41.3<!-- /num -->%다. 차이는 <!-- num:experiments/eval/leak_effect.json:planners.rl_v3.verified_em.diff:pct -->-2.3<!-- /num -->%p이고 95% 구간은 <!-- num:experiments/eval/leak_effect.json:planners.rl_v3.verified_em.diff_lo:pct -->-6.0<!-- /num --> ~ <!-- num:experiments/eval/leak_effect.json:planners.rl_v3.verified_em.diff_hi:pct -->1.4<!-- /num -->%p다. 이 구간은 0을 포함한다. 구간의 위쪽 끝이 표를 본 이득의 상한에 해당한다. RL 이전 단계인 SFT stage2 모델도 같다. 본 표의 새 질문에서 <!-- num:experiments/eval/leak_effect.json:planners.sft_ko2.verified_em.seen.rate:pct -->34.3<!-- /num -->%, 처음 보는 표에서 <!-- num:experiments/eval/leak_effect.json:planners.sft_ko2.verified_em.unseen.rate:pct -->36.2<!-- /num -->%이고, 차이는 <!-- num:experiments/eval/leak_effect.json:planners.sft_ko2.verified_em.diff:pct -->-1.9<!-- /num -->%p(95% 구간 <!-- num:experiments/eval/leak_effect.json:planners.sft_ko2.verified_em.diff_lo:pct -->-5.5<!-- /num --> ~ <!-- num:experiments/eval/leak_effect.json:planners.sft_ko2.verified_em.diff_hi:pct -->1.8<!-- /num -->%p)다. 이 구간도 0을 포함한다. 두 모델은 같은 학습 표를 쓴 같은 계열이라 독립된 반복은 아니다.
2. **두 세트의 난이도는 비슷하다.** 학습이 없는 기준선의 verified EM은 본 표의 새 질문에서 <!-- num:experiments/eval/leak_effect.json:planners.heuristic.verified_em.seen.rate:pct -->27.9<!-- /num -->%, 처음 보는 표에서 <!-- num:experiments/eval/leak_effect.json:planners.heuristic.verified_em.unseen.rate:pct -->26.7<!-- /num -->%다. 차이는 <!-- num:experiments/eval/leak_effect.json:planners.heuristic.verified_em.diff:pct -->1.2<!-- /num -->%p이고 95% 구간은 <!-- num:experiments/eval/leak_effect.json:planners.heuristic.verified_em.diff_lo:pct -->-2.1<!-- /num --> ~ <!-- num:experiments/eval/leak_effect.json:planners.heuristic.verified_em.diff_hi:pct -->4.5<!-- /num -->%p다.
3. **말할 수 있는 것과 없는 것.** 공개 파일에서 표가 겹친다는 것은 사실이다. 그러나 "겹침 때문에 공개 dev 점수가 부풀려진다"는 것은 이 프로젝트에서 보이지 못했다. 표 단위 재분할은 평가 표가 학습에 없다는 것을 보장하는 설계 선택이다. 그 선택이 점수를 바꿨다는 증거는 없다.
4. **이 측정이 덮지 못하는 조건.** 여기서 잰 모델은 표당 최대 3문항, 표 900개로 학습한 3억 파라미터 모델이다. 공개 train은 표당 평균 <!-- num:data/ko/official_split_profile.json:train.examples_per_table -->4.35<!-- /num -->문항에 표가 <!-- num:data/ko/official_split_profile.json:train.unique_tables_by_url_and_content:int -->13,379<!-- /num -->개다. 더 큰 모델을 더 오래 학습하면 표를 외울 수 있다. 전체 데이터 EXAONE에서는 GPU가 필요해 재지 않았다. 질문 세트(`data/ko/leak_probe_*.jsonl`)가 저장소에 있어 같은 평가 명령으로 잴 수 있다.

### 19.4 선행 연구와의 관계 (논문 12편, 원문 확인)

2026-11-10에 arXiv와 ACL Anthology에서 PDF 전문을 받아 읽었다. 논문별 사실과 인용문은 `docs/research/papers.md`와 `docs/research/fulltext/`에 있다. 조사한 것은 이 12편뿐이므로 아래의 "없다"는 "이 12편에는 없다"는 뜻이다.

| 이 프로젝트의 요소 | 이미 있는 것 | 이 12편에 없는 것 |
|---|---|---|
| "답은 맞는데 근거가 틀린다"는 문제 | TrustTable(ACL 2026)이 Type 2(Spurious)로 이름 붙이고 "정답 예측의 약 5%"라고 적는다. ViTaB-A는 QA 정확도 55.1% 대 셀 인용 정확도 25.6%(4B 모델, Markdown)를 보고한다 | 답과 셀 좌표를 함께 내는 모델에서, 답이 맞은 것만 골라 인용 셀을 정답 셀과 대조한 비율과 그 학습 전후 비교(§19.1). TrustTable의 5%는 큰 API 모델의 풀이 과정 전체에 대한 값이고 측정 절차가 없다. ViTaB-A는 인용 과제에 정답을 주고 따로 잰다 |
| 실행으로 답을 검사 | TrustTable은 LLM이 쓴 Pandas·Z3 코드를 실행한다. TabLaP는 계산을 파이썬으로 실행한다 | 검사 경로에 LLM이 없는 고정 규칙 검증기. TrustTable은 놓친 사례의 약 40%를 LLM의 코드 번역 탓으로 분석한다 |
| 검사에 실패하면 보류 | 없음. TrustTable은 고쳐 쓰기를 최대 3번 시도하고, TabLaP는 신뢰 표시만 붙여 답을 내보낸다. RL 논문 다섯 편은 추론 시 검증기가 없다 | 보류를 결과로 두고 보류 재현율·오보류율·검증된 정답률을 보고(§5, §19.2) |
| 작은 모델에 셀 인용을 학습 | RSAT(1~8B, LoRA SFT 뒤 GRPO, `[행, 열]` 인용). 인용의 옳고 그름을 NLI 점수로 잰다 | 정답 셀과 대조한 인용 정확도. 1.2B 모델에서 SFT만으로 인용 오류가 1%대가 된다는 결과 |
| 근거 셀 보상과 보상 허점 | Reasoning-Table은 "보상을 더하면 답이 틀려도 셀 표시로 점수를 얻는다"고 적고 곱셈으로 막는다. RSAT는 모든 셀을 인용하는 편법을 절제 항으로 막는다. TableGPT-R1은 불필요한 그림 코드 삽입을 보고한다 | 보류가 있는 시스템에서만 생기는 허점(검증기가 거부해 보류된 쓰레기 출력이 의도한 보류와 같은 점수를 받음, §7.2)과 그 건수 추적 |
| 강화학습이 SFT를 못 넘음 | Table-R1(Yale)은 분포 안 과제에서 증류 SFT가 RL과 같거나 낫다. Reasoning-Table은 1.5B에서 이득이 미미하다고 적는다 | 새 결과가 아니다. 3억 파라미터에서도 같았다는 사례 하나를 보탠다 |
| 한국어 표 | KorWikiTQ 원논문(LG AI Research, LREC 2022)은 EM·F1만 잰다 | 한국어 표에서 근거 셀·보류를 잰 것. 나머지 11편에는 한국어 데이터가 없다 |
| 표 단위 재분할 | 원논문과 README는 분할 방식을 밝히지 않는다. RL 논문 한 편(Table-r1, Southeast Univ.)은 한 데이터셋을 질문 기준 8:2로 나눈다고 적는다 | 공개 파일의 표 겹침을 세고(§19.3) 겹침의 효과를 직접 잰 것 |

**새롭다고 쓰면 안 되는 것**: 답과 근거의 불일치라는 문제 제기, 실행 기반 검증이라는 발상, 작은 모델의 셀 인용 강화학습, 근거 셀 보상, 보상 편법의 존재, "RL이 SFT를 못 넘었다"는 관찰.

**쓸 수 있는 것**: "한국어 표 질의응답에서, 답과 근거 셀을 함께 내는 작은 모델의 근거 오류를 정답 셀 기준으로 재고, 고정 규칙 검증기와 보류로 오답 유출을 줄이는 폭을 수치로 보였다." 이 문장의 각 부분은 위 표의 오른쪽 열에 해당한다. "처음"이라는 말은 12편만 본 것으로는 쓸 수 없다.

### 19.5 이 절의 한계

- **반복 수.** mT5 단계별 모델은 시드 1개다. EXAONE은 300개 설정 3회, 전체 데이터 설정 2회다. 구간은 문항 표본의 불확실성만 담고 학습 시드의 변동은 담지 않는다. 전체 데이터 두 번의 학습 사이 verified EM 차이는 약 3%p였다(§18.3).
- **한 데이터셋.** 근거 오류와 겹침 효과는 KorWikiTQ에서만 쟀다. 16행·7열·900자 이하 표만 남긴 필터를 거친 부분집합이다.
- **정답 셀의 출처.** KorWikiTQ는 정답 셀을 주지 않는다. 답 텍스트와 같은 셀을 찾아 정답 셀로 삼았고, 여러 개면 질문과 겹치는 행을 골랐으며 답이 어느 셀인지 정할 수 없는 421건은 뺐다.
- **검증기의 근거 복구.** 약한 모델의 verified EM은 복구된 근거에 기대고 있다(§19.1의 5번, §19.2의 5번). 복구를 끈 조건은 저장소의 검증기를 다시 돌린 값이 아니다. 검증기 코드에서 복구 분기 다음이 보류라는 점에 근거해 저장된 출력에서 계산했다. 다만 명세대로 옵션을 넣은 검증기 사본(저장소에 넣지 않았다)으로 세 평가(mT5 최종, EXAONE 300개, EXAONE 전체)를 다시 검증해 699문항 모두 계산값과 같음을 확인했다. 저장소의 검증기에 옵션이 들어가면(§19.8) 그 측정값으로 바꾼다.
- **겹침 효과는 mT5로만 쟀다.** 가장 좋은 모델(EXAONE 전체 데이터)의 겹침 효과는 GPU가 필요해 재지 않았다. 질문 세트는 저장소에 있다(`data/ko/leak_probe_*.jsonl`).

### 19.6 데모에 반영한 것 (2026-11-10)

공개 데모(GitHub Pages)는 2026-10-30 상태에 머물러 있었다. 저장된 실행은 mT5-small과 휴리스틱뿐이었고, "연구 결과" 탭은 vLLM·SGLang을 "GPU가 없어 실행하지 못함"으로 적고 있었다. README와 어긋나서 다음을 고쳤다.

1. **EXAONE 저장 출력 플래너.** 수작업 30문항 평가에서 받아 둔 EXAONE 전체 데이터 모델의 원문 출력을 대표 질문 16개(한국어)에 대해 실제 그래프·도구·검증기에 다시 넣어 저장했다(`scripts/make_recorded_runs.py --stored`). GPU 없이 재현된다. 화면의 상태 줄과 답변 카드에 "모델 출력은 2026-11-08에 Kaggle T4의 vLLM 서버에서 받아 저장한 것"이라고 표시한다. 저장된 출력이 평가 파일의 출력과 글자까지 같은지는 `tests/test_recorded_demo.py`가 검사한다. 화학 문서에는 EXAONE 기록이 없고 화면이 그렇게 안내한다. 기존 mT5·휴리스틱 실행 32개씩은 다시 돌려 이전 결과와 상태·답·근거·검사가 모두 같음을 확인했다.
2. **모델이 인용한 셀과 근거 셀의 구분.** 첫 제안의 인용 셀이 최종 근거와 다르면 표에 붉은 점선과 "모델" 표시로 따로 그린다. 검증기가 근거를 고쳐 답한 경우 배지는 "검증 통과"가 아니라 "근거를 고쳐 답함"이다. §19.1의 측정을 화면에서 볼 수 있게 한 것이다.
3. **연구 결과 탭 갱신.** §19.1~§19.3의 세 표, EXAONE 행, vLLM·SGLang 벤치, 멀티 GPU 실측을 산출물에서 다시 생성했다(`scripts/build_research.py`).
4. **모바일 배치 오류 수정.** 좁은 화면에서 푸터가 문서 목록 위에 겹쳐 아래쪽 문서를 누를 수 없었다. 페이지 높이를 화면에 고정한 규칙 때문이었고 이전 판에도 있던 문제다(이슈 45). E2E에 겹침 검사를 넣었다.

E2E는 실시간 <!-- num:docs/images/e2e-summary.json:live.passed -->18<!-- /num -->/<!-- num:docs/images/e2e-summary.json:live.total -->18<!-- /num -->, 정적 <!-- num:docs/images/e2e-summary.json:static.passed -->21<!-- /num -->/<!-- num:docs/images/e2e-summary.json:static.total -->21<!-- /num --> 통과다. 데모의 EXAONE 답 가운데에는 틀린 답도 있다. 본문에 답이 있는 질문에 표의 셀을 답한 것(수작업 평가의 본문 범주 0/5와 같은 현상)이 검증을 통과해 나온다. 데모는 이것을 숨기지 않는다.

### 19.7 표 입력에 열 번호를 넣는 형식 — 300개 학습에서 근거 오류 65% → 3% (답 정확도는 그대로)

§19.1에서 근거 오류는 거의 전부 "행은 맞고 열이 틀림"이었다. 모델이 받는 표는 `r0: 2011 | MBC | 놀러와` 형태다. 행에는 번호가 붙어 있지만 열 번호는 구분자를 세어야 알 수 있다. 그래서 셀마다 열 번호를 붙이는 형식을 옵션으로 추가했다(`src/tabletrace/model/serialize.py`).

| 형식 | 모델이 받는 표 |
|---|---|
| `plain` (기본, 저장된 모든 결과) | `header: 연도 \| 방송사 \| 제목 ; r0: 2011 \| MBC \| 놀러와` |
| `colid` (추가) | `header: c0 연도 \| c1 방송사 \| c2 제목 ; r0: c0 2011 \| c1 MBC \| c2 놀러와` |

학습(`scripts/train/exaone_lora_sft.py`, `training/sft.py`), 평가(`eval/run.py`), 엔진 벤치, 서비스(환경 변수 `TABLETRACE_TABLE_FORMAT`)에 `--table-format`으로 연결했고 평가 결과의 `meta.table_format`에 기록된다. 기본값은 `plain`이라 저장된 결과는 그대로 재현된다.

**실행한 것: 토큰 비용.** EXAONE-4.0-1.2B 토크나이저로 세면 `colid`는 입력이 <!-- num:experiments/serialize/table_format_cost.json:colid_extra_tokens_rate:pct -->26.0<!-- /num -->% 길다(문항당 중앙값 <!-- num:experiments/serialize/table_format_cost.json:cases.plain_672.whole_input_tokens_median:int -->438<!-- /num --> → <!-- num:experiments/serialize/table_format_cost.json:cases.colid_672.whole_input_tokens_median:int -->552<!-- /num --> 토큰). 입력 예산을 그대로 672로 두면 test에서 정답 행이 잘리는 문항이 <!-- num:experiments/serialize/table_format_cost.json:cases.plain_672.test_gold_row_cut:int -->24<!-- /num -->개에서 <!-- num:experiments/serialize/table_format_cost.json:cases.colid_672.test_gold_row_cut:int -->63<!-- /num -->개로 늘어 불공정한 비교가 된다. 예산을 800으로 올리면 <!-- num:experiments/serialize/table_format_cost.json:cases.colid_800.test_gold_row_cut:int -->27<!-- /num -->개, 학습 예제는 <!-- num:experiments/serialize/table_format_cost.json:cases.colid_800.train_examples_kept:int -->3,588<!-- /num -->개로 `plain`의 <!-- num:experiments/serialize/table_format_cost.json:cases.plain_672.train_examples_kept:int -->3,587<!-- /num -->개와 거의 같다(`scripts/table_format_cost.py`). 그래서 노트북은 `colid`일 때 `--max-len 896`, 평가 `--max-in 800`을 쓴다.

**실행한 것: 정확도 (소유자가 2026-11-10 Kaggle T4에서 1회 실행).** 기존 300개 실험과 같은 예제 <!-- num:experiments/exaone_lora_colid/train_info.json:n_examples:int -->300<!-- /num -->개, 같은 <!-- num:experiments/exaone_lora_colid/train_info.json:steps:int -->18<!-- /num --> step으로 `colid` 형식만 바꿔 학습하고(LoRA <!-- num:experiments/exaone_lora_colid/train_info.json:wall_s:int -->183<!-- /num -->초) vLLM으로 띄워 같은 test 699문항을 같은 검증기로 평가했다(`experiments/eval/exaone_colid_vllm_ko_test`, 출처는 `experiments/eval/PROVENANCE_exaone.md`의 6차 세션). 비교 대상은 `plain` 300개의 세 번 학습이다.

| 지표 (한국어 test) | `plain` 300개 (3번째 학습) | `colid` 300개 |
|---|---:|---:|
| 답이 맞은 조회 답 가운데 인용 셀에 답이 없는 비율 | <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.strict.rate:pct -->65.2<!-- /num -->% (<!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.strict.lo:pct -->60.2<!-- /num -->~<!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.strict.hi:pct -->69.8<!-- /num -->) | **<!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.strict.rate:pct -->3.2<!-- /num -->%** (<!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.strict.lo:pct -->1.8<!-- /num -->~<!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.strict.hi:pct -->5.6<!-- /num -->) |
| 조회 인용에서 열이 맞은 비율 / 행이 맞은 비율 | <!-- num:experiments/eval/exaone_vllm_ko_test/analysis.json:lookup_citation.col_correct:pct -->33.6<!-- /num -->% / <!-- num:experiments/eval/exaone_vllm_ko_test/analysis.json:lookup_citation.row_correct:pct -->85.1<!-- /num -->% | <!-- num:experiments/eval/exaone_colid_vllm_ko_test/analysis.json:lookup_citation.col_correct:pct -->80.0<!-- /num -->% / <!-- num:experiments/eval/exaone_colid_vllm_ko_test/analysis.json:lookup_citation.row_correct:pct -->81.3<!-- /num -->% |
| 검증기가 근거를 고쳐 준 답 (건) | <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.repaired_answers:int -->383<!-- /num --> | <!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.repaired_answers:int -->28<!-- /num --> |
| verified EM | <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.verified_em:pct -->53.1<!-- /num -->% | <!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.verified_em:pct -->51.1<!-- /num -->% |
| 근거 복구 없이 채점한 verified EM | <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.verified_em_no_repair:pct -->23.5<!-- /num -->% | **<!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.verified_em_no_repair:pct -->49.9<!-- /num -->%** |
| 모델이 쓴 답 텍스트의 정확도 (답 있는 문항) | <!-- num:experiments/eval/exaone_vllm_ko_test/metrics.json:metrics.raw_answer_em_answerable:pct -->58.1<!-- /num -->% | <!-- num:experiments/eval/exaone_colid_vllm_ko_test/metrics.json:metrics.raw_answer_em_answerable:pct -->53.6<!-- /num -->% |
| 검증기를 통과해 나간 오답 (전체 대비) | <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.verifier.wrong_answer_rate.rate:pct -->33.6<!-- /num -->% (<!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.verifier.answered_wrong:int -->235<!-- /num -->건) | <!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.verifier.wrong_answer_rate.rate:pct -->45.6<!-- /num -->% (<!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.verifier.answered_wrong:int -->319<!-- /num -->건) |
| 답한 비율 | <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.verifier.coverage:pct -->85.4<!-- /num -->% | <!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.verifier.coverage:pct -->95.9<!-- /num -->% |

읽는 법:

1. **근거 오류는 입력 형식으로 거의 없어졌다.** 답이 맞은 조회 답 가운데 인용 셀에 답이 없는 비율이 `plain` 세 번의 학습 <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test_run1.strict.rate:pct -->53.1<!-- /num -->%, <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test_run2.strict.rate:pct -->63.2<!-- /num -->%, <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.strict.rate:pct -->65.2<!-- /num -->%에서 <!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.strict.rate:pct -->3.2<!-- /num -->%가 됐다. 95% 구간이 겹치지 않고, 차이는 학습 간 변동보다 훨씬 크다. 전체 데이터로 12배 학습해 얻은 <!-- num:experiments/eval/evidence_error.json:exaone_full_vllm_ko_test.strict.rate:pct -->1.3<!-- /num -->%에 가깝다. §19.1에서 본 "열 번호를 세지 못한다"는 문제는 데이터를 12배로 늘려도 풀리고, 열 번호를 입력에 보여 주면 300개로도 풀린다. 300개로 배우지 못한 것은 구분자를 세어 열 번호를 알아내는 일이었다.
2. **답 정확도는 오르지 않았다.** verified EM은 <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.verified_em:pct -->53.1<!-- /num -->% 대 <!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.verified_em:pct -->51.1<!-- /num -->%이고 같은 문항끼리 짝지으면 차이가 없다(`colid`만 맞힌 문항 <!-- num:experiments/eval/paired_tests.json:exaone_colid_vs_plain300_ko_test.candidate_better:int -->67<!-- /num -->개, `plain`만 맞힌 문항 <!-- num:experiments/eval/paired_tests.json:exaone_colid_vs_plain300_ko_test.reference_better:int -->81<!-- /num -->개, 정확 검정 p=<!-- num:experiments/eval/paired_tests.json:exaone_colid_vs_plain300_ko_test.p_display -->0.285<!-- /num -->). 어느 행을 볼지 고르는 능력은 그대로다. 300개에는 계산·보류 예제가 없어 그 문항들은 두 형식 모두 조회로 답한다. 모델이 쓴 답 텍스트의 정확도는 <!-- num:experiments/eval/exaone_vllm_ko_test/metrics.json:metrics.raw_answer_em_answerable:pct -->58.1<!-- /num -->%에서 <!-- num:experiments/eval/exaone_colid_vllm_ko_test/metrics.json:metrics.raw_answer_em_answerable:pct -->53.6<!-- /num -->%로 조금 낮다. 한 번의 학습이라 형식 때문인지 학습마다의 변동인지는 가릴 수 없다.
3. **근거가 맞아야 정답으로 치면 두 배가 된다.** 복구 없이 채점한 verified EM이 <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.verified_em_no_repair:pct -->23.5<!-- /num -->%에서 <!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.verified_em_no_repair:pct -->49.9<!-- /num -->%로 올랐다. `plain` 모델의 점수는 검증기의 근거 복구(<!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.repaired_answers:int -->383<!-- /num -->건)에 기대고 있었고 `colid` 모델은 거의 기대지 않는다(<!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.repaired_answers:int -->28<!-- /num -->건).
4. **검증기를 통과하는 오답은 늘었다.** <!-- num:experiments/eval/evidence_error.json:exaone_vllm_ko_test.verifier.answered_wrong:int -->235<!-- /num -->건에서 <!-- num:experiments/eval/evidence_error.json:exaone_colid_vllm_ko_test.verifier.answered_wrong:int -->319<!-- /num -->건이다. `plain` 모델은 답과 인용 셀이 자주 어긋나서, 답이 표의 다른 셀과도 맞지 않으면 검증기가 보류했다(답 있는 문항의 `verification_failed` 보류 <!-- num:experiments/eval/exaone_vllm_ko_test/analysis.json:abstain_reason_answerable.verification_failed:int -->72<!-- /num -->건). `colid` 모델은 틀린 행을 골라도 그 행의 셀을 일관되게 인용하고 그 값을 답으로 쓰므로 검증기가 잡을 어긋남이 없다(같은 보류 <!-- num:experiments/eval/exaone_colid_vllm_ko_test/analysis.json:abstain_reason_answerable.verification_failed:int -->14<!-- /num -->건). 검증기는 답과 근거의 불일치를 잡는 장치이고, 일관되게 틀린 답은 잡지 못한다(§19.2의 4번)는 것이 이 실험에서 수치로 드러났다.

한계: `colid`는 한 번만 학습했다. 입력 예산이 다르다(`plain` 672, `colid` 800 토큰. 잘린 정답 행은 <!-- num:experiments/serialize/table_format_cost.json:cases.plain_672.test_gold_row_cut:int -->24<!-- /num -->개 대 <!-- num:experiments/serialize/table_format_cost.json:cases.colid_800.test_gold_row_cut:int -->27<!-- /num -->개로 맞췄다). 전체 데이터에서 `colid`가 더 나은지는 재지 않았다. `plain`도 전체 데이터에서는 근거 오류가 1%대라 얻을 것이 적을 수 있고, 입력이 <!-- num:experiments/serialize/table_format_cost.json:colid_extra_tokens_rate:pct -->26.0<!-- /num -->% 길어지는 비용은 남는다.

### 19.8 검증기의 근거 복구 끄기 옵션 — 명세와 테스트 준비, 구현은 소유자 몫

§19.2의 5번에서 근거 복구는 점수와 오답을 함께 올렸다. 끌 방법이 지금은 없다. `verify/verifier.py`는 소유자가 직접 쓴 모듈이므로 AI 도구는 코드를 쓰지 않고 다음만 준비했다.

- 명세 `docs/rewrite/05_verifier_repair_option.md`: `resolve(..., repair=True)` 인자 하나. 끄면 복구 대신 `verification_failed`로 보류한다.
- 테스트 `tests/test_verifier_repair_option.py`: 인자가 생기기 전에는 건너뛰고, 생기면 실행된다(기본 동작 유지, 끈 경우의 보류, 다른 경로에 영향 없음, 저장된 모델 출력에서의 일치).
- 평가 스크립트의 `--no-repair`와, 재검증 결과를 계산값과 문항 단위로 대조하는 `scripts/evidence_error.py --compare-no-repair`.

