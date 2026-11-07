# 발견한 문제와 수정 기록 (작업 중 실시간 기록)

| # | 단계 | 문제 | 원인 | 수정 | 재검증 |
|---|---|---|---|---|---|
| 1 | 모델 변환 | TF 체크포인트 덤프가 `bfloat16`이라 npz 로드 시 `could not convert string to float` | numpy에 bf16이 없음 | TF 쪽에서 float32로 캐스팅 후 저장 | 변환 재실행, 190 텐서 로드 |
| 2 | 모델 변환 | `transformers 5.21`의 `MT5Config(tie_word_embeddings=False)`가 무시됨 → lm_head가 공유 임베딩에 묶임 | v5 설정 처리 변경 | 생성 후 속성 강제 + config.json 보정, `data_ptr` 단언 | lm_head 비공유 확인, 파라미터 300,176,768 = TF 합계 |
| 3 | 모델 변환 | 이름 매핑 오류(`wi_0.weight.weight`, `decoder.layer_norm` ↔ `final_layer_norm`) | mesh-TF 변수명 규칙 | 매핑 함수 수정, `strict=True` 로드 | `<All keys matched successfully>` |
| 4 | 토크나이저 | `T5TokenizerFast(vocab_file=…)`가 어휘 4개짜리 토크나이저를 만들어 검증 손실 50 nats | v5에서 spm 파일 직접 로드 미지원 | `tokenizers` Unigram을 spm proto에서 직접 구성, 센티널 `▁<extra_id_k>`→`<extra_id_k>` 이름 변경으로 id 250099… 보존 | 디노이징 손실 5–7 nats, 센티널 구조 생성 |
| 5 | 데이터 | KorWikiTQ 공개 train/dev가 표 1,755개 공유 | 질문 단위 분할 | 표 단위 재분할, 누수 0 검사 | `build_report.json`, `check_data.py` |
| 6 | 데이터 | OpenStax 표 134개가 "헤더 행 ≠ 1"로 제외되어 문서 18개뿐 | 제목 행이 `thead`에 함께 있음, 부록 표는 `thead` 없음 | 제목 행→캡션, 첫 본문 행→헤더 승격 | 문서 56, 표 113 |
| 7 | 데이터 | 헤더 단위 파서가 `(no.)`, `[H2O2]`를 단위로 인식 | 괄호·대괄호 모두 허용 + 느슨한 폴백 | 소괄호만, 폴백 문자 제한, 비단위 목록 | 단위 테스트 9건 |
| 8 | 데이터 | 숫자 파서가 `×10^999` 같은 셀에서 `OverflowError` | 지수 범위 미검사 | 지수 ±30 초과 거부 | 합성 생성 재실행 |
| 9 | 휴리스틱 | 단음절 토큰(년·수·명)이 여러 행에 걸려 모호 판정 | 형태소 단위 겹침 | 행 매칭은 2자 이상 토큰만 | 수작업 ko 0.40→0.53 |
| 10 | 휴리스틱 | "합계 차이는?"이 sum으로, "by what factor … increase"가 diff로 분류 | 패턴 우선순위 | ratio→pct→avg→diff→sum 순, 계산 행이 2개 미만이면 lookup으로 폴백 | 단위 테스트 |
| 11 | 휴리스틱 | "water than carbon dioxide"에서 sulfur dioxide 행 선택, 피연산자 순서 반대 | 토큰 수만 셈 | 셀 전체 구절 일치 보너스, 질문 내 언급 순서로 피연산자 정렬 | API 테스트 `374.0 - 31.1` |
| 12 | 검증기 | 제안 답 `9`가 셀 `5,436,789`의 부분 문자열이라 통과 | 포함 규칙이 너무 느슨 | 2자 이상 + 숫자면 값 동일 조건 | 회귀 테스트 추가, RL 보상 −0.6 확인 |
| 13 | 콘솔 | `hidden` 요소가 `display:flex` 때문에 빈 띠로 보임 | CSS 우선순위 | `[hidden]{display:none!important}` | 스크린샷 |
| 14 | 콘솔 | 모바일에서 첫 진입 시 문서 자동 선택이 본문 탭으로 전환해 대표 질문이 안 보임 | 자동 선택과 사용자 선택을 구분 안 함 | `auto` 플래그 | E2E 모바일 통과 |
| 15 | 콘솔 | favicon 404 콘솔 오류 | 아이콘 없음 | 인라인 SVG 아이콘 | E2E 오류 0 |
| 16 | 운영 | 실험 파이프라인이 로그 디렉터리 부재로 시작 즉시 종료 | 리디렉션이 mkdir보다 먼저 | 디렉터리 선생성 | 프로세스 확인 |
| 17 | Docker | 데몬 미실행 → `docker build` 실패; 기동 후 Docker Hub 429 | 컨테이너 환경 제한, 레지스트리 속도 제한 | `dockerd` 수동 기동, `BASE_IMAGE` 빌드 인자(MCR 미러), 컨테이너 안 pip의 프록시 CA 오류는 BuildKit 시크릿 `pipca`로 해결 | 이미지 786 MB 빌드, 컨테이너 smoke 통과(`experiments/docker/smoke.json`) |
| 18 | 운영 | `pkill -f` 패턴이 자기 셸까지 종료(exit 144) 2회 | 패턴이 명령줄에 포함 | PID 지정 kill / `fuser -k` 사용 | — |
| 19 | 서빙 | Docker 이미지가 Docker Hub·ECR에서 429(속도 제한) | 공용 egress IP | MCR 베이스 이미지로 우회(CI는 python:3.13-slim 유지) | 빌드 성공 |
| 20 | Agent | API 응답의 `planner.mode`가 모델 실행 시에도 항상 `heuristic`, 검증 실패 시 보완 제안 분기가 한 번도 실행되지 않음 | LangGraph가 `TypedDict` 상태 스키마에 없는 키(`planner_info`)를 버림 | 스키마에 키 선언 | 모델 테스트 `test_graph_with_neural_planner…` 통과(파이프라인 model_tests 단계) |
| 21 | 운영 | 세션 워커 재시작으로 백그라운드 파이프라인(stage 2 학습 중)이 종료 | 프로세스가 워커에 묶임 | 완료 마커로 건너뛰는 재시작 가능 파이프라인으로 개조 후 재실행 | status.txt의 SKIP/OK 기록 |
| 22 | 모델 | stage 1 SFT가 답 텍스트는 맞히지만(raw EM 30 %) 셀 좌표를 자주 틀려(lookup 인용 중 행 76 %·열 71 %·둘 다 58 %) 검증기가 답을 차단 → verified EM 20.7 % | 좌표 생성 능력 부족(작은 모델·CPU 2 epoch) | 검증기에 "근거 복구"(답 텍스트가 표의 유일한 셀이면 그 셀을 근거로, 실패 검사로 기록) 추가; 모델 인용 정확도는 별도 지표(`evidence_cells_exact_raw`)로 계속 보고 | 파이프라인 재평가 |
| 23 | RL | 첫 RL 실행이 5스텝째 NaN으로 종료. step 1의 KL이 770, 이후 3×10⁶ | 정책은 학습 모드(dropout 0.1), 참조 모델은 평가 모드 → 같은 가중치인데 로그확률이 달라 k3 KL이 폭발 | 정책도 평가 모드에서 로그확률 계산, 로그비율 clamp(±10), 비유한 그래디언트 업데이트 건너뜀 | 3스텝 smoke에서 KL 0.0 / 2e-5 / 6e-5; 이후 60스텝 완주 |
| 24 | RL | **보상 편법 발견**: RL v1에서 최종 보류율 61→68 %인데 모델의 명시적 `op: abstain`은 7→11 %뿐, lookup 57→36 %·diff 30→45 %로 정책 이동, 평균 보상은 −0.007→0.067로 거의 불변 | 답 없는 문항에서 "최종 상태가 보류면 +1.0"으로 채점 → 검증기가 거부한 쓰레기 프로그램도 의도적 보류와 같은 점수 | v2 보상: 모델이 직접 `op: abstain`을 낸 경우만 +1.0, 검증기가 잡은 근거 없는 제안 +0.2, 해석 불가 프로그램 0.0(정답 있는 문항에서는 −0.5); 회귀 테스트 `test_reward_does_not_pay_for_garbage_abstention` | v1 산출물은 `experiments/rl_ko_v1/`에 증거로 보존, v2를 처음부터 재학습·재평가 |
| 25 | 평가 | 정답 행이 512 토큰 예산 때문에 입력에서 잘린 문항을 잘린 표 위에서 채점 → 정답이 존재하지 않는 셀을 가리켜 모델이 억울하게 틀린 것으로 집계 | gold 해석이 입력용(잘린) 표를 사용 | gold는 항상 전체 표·전체 본문에서 해석, 입력은 본문을 300→150→0자로 줄여서 행을 최대한 유지, `truncated_gold_rate`·`verified_em_untruncated` 별도 보고 | 수작업 평가 잘림 3→0건, test 77→62건(8.9 %) |
| 26 | 평가 | 동일 셀을 두 번 쓰는 `diff r6c4, r6c4`(=0)가 "계산 성공"으로 통과(SFT 모델이 자주 냄) | 검증기가 피연산자 중복을 검사하지 않음 | 반복 셀은 `invalid_program`으로 보류, 테스트 추가 | `test_degenerate_calculation_is_rejected` |
| 27 | 벤치 | 첫 추론 벤치가 fp32·int8을 한 프로세스에서 순차 측정해 RSS가 3.15–3.22 GB로 거의 같게 나옴(메모리 비교 무효); 벤치 중 단위 테스트를 돌려 지연 측정을 오염시킴 | 프로세스 RSS는 누적 최댓값 | 정밀도마다 별도 프로세스 + 모델 파일 크기 측정, 오염된 실행은 폐기하고 유휴 상태에서 재실행 | `experiments/bench/inference.json` |
| 28 | E2E | 모바일에서 보이지 않는 플래너 선택창을 눌러 스크립트가 30초 타임아웃으로 종료, 오래된 e2e JSON이 남아 통과처럼 보임 | 플래너 선택창은 오른쪽 패널(모바일에서는 탭) 안에 있음 | 탭을 먼저 전환, 결과 JSON을 실행 시작 시 삭제 | 최종 E2E 실행 |
| 29 | 문서 | README 맨 위 "공개 데모" 주소가 실제로는 배포된 적 없는 주소 | 푸시 불가로 Pages 워크플로 미실행 | "배포되지 않음"으로 정정하고 로컬 실행 경로를 앞에 | README 머리말 |
| 30 | 문서 | README 실패 사례의 열 좌표 예시가 실제 예측과 달랐음(`r2c1`로 적었으나 실제 출력은 `r3c1`) | 사례를 기억에서 옮겨 적고 예측 파일과 대조하지 않음 | 예측 파일(`sft_chem_ko_test`, qid `30350_2`)에서 원문 출력·정답 셀·검사 결과를 직접 확인해 교체. 퇴화 계산·환각 사례도 같은 방식으로 `ko_custom_01`, `ko_custom_08` 실제 출력으로 교체 | README §11 |
| 31 | 평가 | 보류 재현율이 "모델이 근거 부족을 판단한 것"처럼 읽히지만 실제로는 우연한 보류를 포함함: SFT stage 2는 직접 `op: abstain` 0 %인데 최종 보류 재현율은 26 %, 퇴화 계산 출력은 test 699문항에서 SFT stage 2 101건·RL v1 160건 | 지표가 최종 상태만 보고 보류 경로를 구분하지 않음(RL v1 보상 편법과 같은 구조의 지표 허점) | `analysis.json`에 `abstain_breakdown`(직접 보류/해석 불가/검증 실패 경로별 재현율)과 `degenerate_calc_outputs` 추가, README·보고서에 "모델이 근거 부족을 판단해 보류한다는 주장은 뒷받침되지 않는다"고 명시 | `scripts/analyze_predictions.py`, `analysis.json` 24개 전부 재생성 |
| 32 | 검증기 | 표에 없는 대상("보헤미안 랩소디")에도 엉뚱한 셀을 인용해 답하면 검증기가 통과시킴 | 검증기는 답이 인용 셀과 같은지만 보고, 셀이 질문 대상에 대한 것인지는 보지 않음 | **2차에서 부분 해결**: 검증기 v2의 개체 일치 검사(`subject_in_evidence`). 질문의 고유명사가 인용한 행에 없으면 보류. 대가로 정답 프로그램도 한국어 4.3%가 오탐으로 보류됨(#36) | README §9.5, `tests/test_program_verifier.py` |
| 33 | 문서 | int8 설명에 "lm_head는 fp32로 남는다"고 적었으나 실제로는 lm_head도 int8로 양자화됨(모듈 경로 `torch.ao.nn.quantized.dynamic`) | 확인 없이 쓴 가정. 모델 파일이 684 MB로 줄어든 것이 이미 반증이었음 | 양자화 범위를 고르는 `model/quant.py` 추가, 문서 정정, 부분 양자화 측정 | 보고서 §8 |
| 34 | 학습 | 2단계를 실제 표 옆 본문 예제로 재학습한 모델(sft_ko3)이 본문은 풀게 됐지만 표 조회 539문항 중 82문항을 `op: text`로 보내 ko test verified EM이 27.5%에서 24.9%로 떨어짐 | 본문 예제를 늘리자 "본문이 있으면 text"라는 반대편 지름길을 배움 | 표 조회 1,700개를 더한 보강 1 epoch(sft_ko4)와 화학 단계의 본문 550개 재학습 | 보고서 §18 |
| 35 | 운영 | `pkill -f`로 또 자기 셸을 종료(exit 144), #18과 같은 실수 | 명령줄에 패턴이 들어 있음 | PID로 종료, 패턴 종료는 스크립트 파일 안에서만 | — |
| 36 | 검증기 | 개체 일치 검사가 정답 프로그램까지 보류시킴(한국어 정답 문항의 4.3%, 영어 "Arrhenius"·"Celsius" 같은 주제어·단위어) | 고유명사가 표에 다른 표기로 있거나, 질문의 주제어가 행이 아니라 제목·본문에 있음 | 문자 bigram 50% 이상 겹치면 일치, 영어는 화학식만 대상, 제목·헤더에 있는 말은 대상에서 제외. 오탐률을 `gold_subject_fail_rate`로 매 평가에 기록 | `metrics.json` |
| 37 | 서빙 | Kaggle(노트북은 Colab으로 판단, 이슈 38)에서 vLLM 서버가 `OSError: Can't load the configuration of 'experiments/exaone_lora/merged'`로 뜨지 않음. 모델 폴더·토크나이저·vLLM 가상환경의 설정 읽기는 모두 정상이었음 | 노트북이 모델 경로를 상대 경로로 넘겼고 서버 프로세스의 cwd가 저장소 폴더가 아니었음. 또 재검증(`--replay-from`) 명령이 `--tokenizer`와 `--max-in 672`를 빼고 돌아 행 예산이 기본값(근사 토크나이저, 512)으로 다시 계산됨(`truncated_gold_rate` 3.4% → 9.3%, `--tokenizer`만 넣은 재실행은 11.3%). 덤으로 `--dtype auto`가 T4에서 bf16을 골랐음(`is_bf16_supported()`가 에뮬레이션을 포함) | 모델 경로를 절대 경로로, 서버를 `cwd=REPO_DIR`로 시작, 재검증에 `--tokenizer {MERGED} --max-in 672` 추가, dtype 자동 선택을 compute capability 기준으로. 결과는 소유자가 붙여 준 출력을 옮겨 적고 출처를 `PROVENANCE.md`에 남김 | 소유자 재실행에서 서버 기동·평가·벤치 통과(2026-11-07). 같은 인자로 다시 돌린 재검증은 `truncated_gold_rate`가 본 실행과 같은 3.4%로 나와 그 값으로 교체함 |
| 38 | 노트북 | Kaggle에서 결과 압축 파일이 Output 패널에 나타나지 않음. 소유자가 "5번 실행 안됨"으로 보고 | 노트북이 `/content`가 있으면 Colab으로 판단했는데 Kaggle 이미지에도 `/content`가 있어 저장소와 압축 파일이 `/content` 아래에 생김. Kaggle Output 패널은 `/kaggle/working`만 보여 줌. 같은 이유로 앞서 cwd가 `/content/tabletrace`와 `/kaggle/working`으로 엇갈려 보였음 | `/kaggle/working`을 먼저 확인하고, 압축 파일은 플랫폼별 고정 경로에 씀. 자동 내려받기(`files.download`)는 "Javascript Error: download is not defined"로 실패해 수동 내려받기로 안내 | 소유자 세션에서 `/kaggle/working/gpu_results.tgz` 생성 확인(162 KB) |

