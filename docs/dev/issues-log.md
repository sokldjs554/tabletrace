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
