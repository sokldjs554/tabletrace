# UI 조사 — 문서 검토·데이터 검증·표 탐색·연구 워크벤치 제품

구현 전에 아래 제품·도구의 실제 화면(스크린샷 또는 공식 소개 페이지)을 확인했다. 네트워크 정책으로 대부분의 제품 사이트가 차단되어, **GitHub에 공개된 스크린샷·README**와 **Google Cloud 제품 페이지**를 1차 자료로 썼다. 확인하지 못한 것은 "미확인"으로 적는다.

| # | 제품 | 확인한 자료 | 확인한 화면 |
|---|---|---|---|
| 1 | Microsoft Document Intelligence — Sample Labeling Tool (OCR Form Tools) | github.com/microsoft/OCR-Form-Tools `docs/images/apply-labels.png`, `analyze-form.png`, `train-model.png`, `compose.png` (직접 열어 봄). learn.microsoft.com의 "try-sample-label-tool" 페이지는 차단 | 라벨링 화면, 예측(Analyze) 화면 |
| 2 | Google Document AI Workbench | cloud.google.com/document-ai-workbench 제품 페이지(HTML 텍스트 추출). 콘솔 스크린샷은 gstatic 차단으로 미확인 | 제품 소개·워크플로(가져오기→라벨→학습→평가→배포) 텍스트 |
| 3 | Label Studio | github.com/HumanSignal/label-studio README + 템플릿 그리드 이미지 | 과제 템플릿 목록(데이터 유형별 라벨링) |
| 4 | doccano | github.com/doccano/doccano README (시연 GIF) | 텍스트 어노테이션 흐름 |
| 5 | MLflow | github.com/mlflow/mlflow README 이미지 2장: 트레이스 뷰(트리+상세 탭), AI Gateway 대시보드 | 트레이스 분해(왼쪽 트리 · 오른쪽 Chat/Inputs/Outputs/Attributes/Events 탭), 지표 대시보드 |
| 6 | promptfoo | github.com/promptfoo/promptfoo README 이미지 | 평가 결과 표(변수 × 모델 출력, PASS/FAIL 배지, 지표 요약, 필터 칩) |
| 7 | Marker (datalab) | github.com/datalab-to/marker README 이미지 | 벤치마크 산점도(품질 vs 처리량, 조건 각주) |
| 8 | Tabula | github.com/tabulapdf/tabula README | PDF 표 영역 선택→추출(스크린샷 1장은 후원 로고라 화면 미확인, README 설명으로 흐름 확인) |
| 9 | PaddleOCR (PP-Structure) | README 이미지 | 문서 파싱 결과 레이아웃(히어로 이미지만 확인, 데모 UI 미확인) |
| 10 | Hypothesis(웹 주석), Datasette, OpenRefine, Langfuse, Phoenix, Inspect AI, Argilla, Docling | README 텍스트만(이미지는 외부 호스트 차단) | 미확인 — README의 기능 설명만 참고 |

## 비교 항목별 관찰

### 문서와 표를 탐색하는 방식
- OCR Form Tools: **왼쪽 세로 썸네일 목록 → 가운데 큰 문서 뷰어 → 오른쪽 태그 패널**의 3단. 문서 전환은 왼쪽 목록 클릭, 표는 문서 위에 격자 오버레이로 표시되고 표 아이콘으로 표 모드 진입.
- Tabula: 문서 페이지 위에 영역을 끌어 표를 선택, 추출 결과를 표로 미리보기 후 내보내기.
- Document AI Workbench(텍스트): 문서를 가져와 스키마(필드) 정의 → 라벨 → 학습 → 평가 단계가 좌측 내비게이션에 고정.

### 질문·검색과 결과를 보여주는 방식
- promptfoo: 결과를 **표**로 — 행은 입력, 열은 모델/프롬프트, 셀 안에 PASS/FAIL 배지와 출력. 상단에 통과율·토큰·지연 요약, 필터 칩(All/Failures/Passes/Errors).
- MLflow 트레이스: 왼쪽에 호출 트리(스팬 이름·소요), 오른쪽에 선택 스팬의 입력/출력/속성 탭.

### 원문·셀·답변 근거를 연결하는 방식
- OCR Form Tools: 문서 위 값에 **색 테두리**, 오른쪽 태그 패널의 같은 색 라벨에 값·신뢰도. 즉 "문서 위 하이라이트 ↔ 오른쪽 필드"가 색으로 짝지어짐.
- Analyze 화면: 예측값 옆 **신뢰도(%)**와 페이지 번호 배지(P.1).

### 작업 상태와 오류를 보여주는 방식
- OCR Form Tools 하단 상태 바(저장소, 태그 수, 문서 수, 버전), 상단 "Run OCR on all files" 같은 긴 작업 버튼.
- MLflow 대시보드: 요청 수·지연 p50/p90/p99·오류율을 작은 카드로.
- promptfoo: 셀 단위 PASS/FAIL, 실패만 필터.

### 많은 정보를 한 화면에 배치하는 방식
- 3단(목록 / 본문 / 속성)이 공통. 오른쪽 패널은 접을 수 있는 섹션. 수치는 카드(제목·큰 숫자·보조 설명).

### 처음 들어온 사용자가 이해하는 흐름
- Document AI 제품 페이지: 제품 정의 한 문장 → "Try Workbench" → 기능 카드 → 튜토리얼 목록(가져오기/라벨/학습/평가).
- Label Studio: 템플릿 그리드로 "무엇을 할 수 있는지"를 먼저 보여 줌.

## TableTrace에 반영한 것

| 관찰 | 반영 |
|---|---|
| 3단 구조(목록·문서·속성) | 왼쪽 문서/표 목록, 가운데 본문+표 뷰어, 오른쪽 질문·답변·검토 패널. 모바일은 탭으로 전환 |
| 문서 위 하이라이트 ↔ 오른쪽 필드의 색 짝짓기 | 근거 셀에 테두리+번호 배지, 오른쪽 근거 목록의 같은 번호를 클릭하면 해당 셀로 스크롤·강조. 본문 근거는 문장 하이라이트 |
| 예측값 옆 신뢰도·페이지 배지 | 답변 옆에 **검증 결과**(통과한 검사 수, 보류 사유)와 셀 좌표(r/c) 배지. 모델 확률 대신 검증기 판정을 보여 줌(모델 신뢰도는 과신 유발) |
| 긴 작업의 상태 바 | 질문 제출 후 `대기→실행 중(경과 ms)→완료/보류/오류/시간 초과` 상태 띠, 작업 ID |
| 트레이스 트리 + 상세 탭 | 결과 아래 "실행 추적": retrieve → propose → tool → verify 단계와 소요 ms, 각 단계 입력/출력 펼치기 |
| 결과 표 + PASS/FAIL 배지 + 조건 요약 | 연구 결과 화면: 모델 비교·추론 최적화·병렬 실험을 표로, 각 표 위에 **실행 조건(하드웨어·데이터 크기·반복 수)** 고정 표시 |
| 튜토리얼식 첫 화면 | 첫 방문 시 "문서 선택 → 질문 → 검색·도구 실행 → 근거 검토" 4단계 안내 띠(닫기 가능), 각 문서에 대표 질문 칩 |
| 실시간/저장 결과 구분 | 상단 배지: `실시간 실행(백엔드 연결)` / `저장된 실행 결과(백엔드 없음)`; 저장 결과에는 기록 시각·모델·커밋을 표시 |
