# 국내 관련 연구 원 메모 (2026-11-11 조사)

## 읽기 수준 표기
- **전문 열람**: 원문 PDF를 직접 내려받아 텍스트로 읽음 (arXiv / ACL Anthology).
- **스니펫만**: 이 세션에서 koreascience.kr, koreascience.or.kr, dbpia.co.kr, earticle.net, doaj.org, api.semanticscholar.org 접속이 모두 막혀(DNS 해석 실패, 세션 네트워크 허용 목록 밖) 원문을 열지 못함. 검색엔진 결과 요약에 나온 내용만 옮겼고, 저자·수치는 원문으로 다시 확인해야 함. 검색엔진 요약 자체가 틀릴 수 있으므로 인용할 때는 반드시 원문 확인 후 사용.
- 원문에서 확인하지 못한 항목은 "확인 못 함"으로 표기.

내려받아 읽은 원문: arXiv 2201.06223, ACL Anthology 2022.lrec-1.657, arXiv 2505.17503, 2501.10487, 2404.19205, 2507.11407, 2408.03541, 2508.10355, 2601.05459, 2604.06173, 2504.13216, 2411.19103. PDF는 저장소에 넣지 않았다(저작권). 요약본은 `docs/research/papers.md`의 "국내 연구" 절이다.

---

## A. 한국어 표 질의응답 직접 선행연구

### A1. Korean-Specific Dataset for Table Question Answering (KorWikiTQ / KorWikiTabular / KO-TaBERT) — 전문 열람
- 저자: Changwook Jun, Jooyoung Choi, Myoseop Sim, Hyun Kim, Hansol Jang, Kyungkoo Min (LG AI Research)
- 학회: LREC 2022, pp. 6114–6120. URL: https://aclanthology.org/2022.lrec-1.657.pdf (열람), arXiv 2201.06223v2
- 과제/데이터: 한국어 위키백과 표 QA. KorWikiTabular 1.4M 표(사전학습용, 표를 문장열로 변환), KorWikiTQ 70k QA (유급 크라우드 작업자, 약 20k 표 선택, "rows greater than 5 and less than 15", 열 10개 초과 표 제외; 3.2절). 질문 난이도 Level1–5 (Level5 = min/max 등; 3.2절). 숫자 표에 대해 "minimum, maximum, count, or average" 질문 생성(3.2절).
- 모델: KO-TaBERT (BERT-base, 119,547 한국어 word-piece 어휘, MLM만, NSP 미사용; 4.1절). 정답은 **스팬 추출**(start/end 예측; 4.2절). 프로그램/연산 출력 없음.
- 지표/수치 (EM/F1): Table 1 — KorQuAD 2.0 64.5/74.5, Crowd-sourced 83.9/87.2, Overall 82.8/86.5. Table 2 — Level1 89.6/93.1 … Level5 67.8/70.6. Table 3 — 표 변환 포맷 v2(첫 열 값=행 헤더를 각 셀에 붙임; Figure 4) 사용 시 KorQuAD 2.0 69.1/78.4, Crowd-sourced 87.2/91.2.
- 분할: "We split the selected KorQuAD 2.0 corpus and the crowdsourced dataset with a 20% ratio respectively as the test dataset" (4.2절). **표 단위 분할인지 질문 단위 분할인지는 논문에 명시 없음 → 확인 못 함.** KorQuAD 2.0 표 질문 수는 서론에서 "around 10k", 4.2절에서 "about 2k pairs"로 서로 다르게 적혀 있음.
- GitHub README (https://github.com/LG-NLP/KorWikiTableQuestions, WebFetch로 열람): train 58,221 / dev 11,771 (합 69,992), test 공개 없음, CC BY-SA 4.0, 분할 방법 설명 없음. (11,771/69,992 ≈ 16.8%로 논문의 20%와 다름 — 이는 제가 계산한 값이며, 공개 dev가 논문의 test와 같은지 **확인 못 함**.)
- 근거 셀/귀속 별도 측정: 없음. 답변 보류/검증기: 없음. RL: 없음.
- TableTrace와의 관계: 같은 데이터, 그리고 "표 직렬화 방식이 성능을 바꾼다"(Table 3)는 결과는 이미 이 논문에 있음. TableTrace는 생성형 소형 모델이 셀 좌표(r{i}c{j})와 연산을 내고 규칙 검증기로 근거 셀을 재확인·보류한다는 점, 그리고 train/dev 간 표 중복을 직접 측정한다는 점이 다름.

### A2. Korean TableQA: Structured data question answering based on span prediction style with S3-NET — 서지는 A1 참고문헌으로 확인, 초록은 스니펫만
- 저자: Cheoneum Park, Myungji Kim, Soyoon Park, Seungyoung Lim, Jooyoul Lee, Changki Lee (A1 참고문헌 목록에 기재). 소속: 확인 못 함.
- 학회: ETRI Journal 42(6):899–911, 2020 (A1 참고문헌), DOI 10.4218/etrij.2019-0189(검색 결과). 열람 시도: doaj.org, koreascience.kr — 접속 차단.
- 검색 결과 요약 내용(원문 미확인): 표를 MRC용 레코드 형식으로 변환해 S3-NET 적용, novice/intermediate 과제, EM 96.48/F1 97.06(novice), EM 99.30/F1 99.55(intermediate). 데이터 규모·분할: 확인 못 함.
- KorWikiTQ의 질문 유형 정의가 이 논문을 확장했다고 A1이 명시 ("extending to the previous work (Park et al., 2020)", 3.2절).
- 근거/보류/RL: 확인 못 함.
- TableTrace와의 관계: 한국어 TableQA의 가장 이른 축에 해당하는 스팬 예측 방식. TableTrace는 생성+검증 방식.

### A3. 「TAPAS를 이용한 사전학습 언어 모델 기반의 표 질의응답」(제32회 HCLT, 2020) — 스니펫만
- URL(열지 못함): https://www.koreascience.kr/article/CFKO202030060597810.pdf
- 저자: 검색엔진 요약에 "조상현, 김민호, 권혁철"로 나옴 — 원문 확인 못 함. 소속: 확인 못 함.
- 검색 결과 요약 내용: TAPAS 기반 한국어 표 언어모델 사전학습, KorQuAD 2.0 표 데이터, 기계독해 모델 적용 시 EM 46.8%/F1 63.8%, 행·열 임베딩 결합 시 EM 63.6%/F1 76.0%. 분할·데이터 크기: 확인 못 함.
- 근거/보류/RL: 확인 못 함.
- TableTrace와의 관계: 행·열 구조 정보를 넣으면 성능이 오른다는 국내 결과(임베딩 방식). TableTrace의 "직렬화에 열 id 추가" 실험은 입력 텍스트 수준이라는 점이 다름.

### A4. 위키 표·인포박스 사전학습 기반 표 기계독해 (제33회 HCLT, 2021) — 스니펫만
- URL(열지 못함): https://www.koreascience.kr/article/CFKO202130060657822.pdf
- 제목·저자·소속: 확인 못 함 (한 검색 요약은 LG AI연구원 연구라고 했으나 원문 확인 못 함).
- 검색 결과 요약 내용: 위키 표·인포박스 144만 건 사전학습, 표 QA 약 7만 건 미세조정, 표 포맷 변경으로 BERT 구조 변경 없이 구조 반영, KorQuAD 2.0 표 관련 개발 데이터 약 1천 건 평가에서 EM 69.07/F1 78.34. (수치가 A1 Table 3의 69.1/78.4와 매우 가까움 — A1의 국문 버전일 가능성이 있으나 **확인 못 함**.)

### A5. 나무위키 표 전처리를 이용한 표 언어모형 사전학습 (제33회 HCLT, 2021) — 스니펫만
- URL(열지 못함): https://www.koreascience.kr/article/CFKO202130060703831.pdf
- 제목·저자·소속: 확인 못 함.
- 검색 결과 요약 내용: 나무위키 표를 의미 있는/없는 표로 분류해 정제 후 사전학습, F1 19.38·EM 4.22 향상(비교 기준 확인 못 함).

### A6. 「생성형 언어모델을 이용한 테이블 질의응답 평가」(제35회 HCLT, 2023) — 스니펫만
- URL(열지 못함): https://www.koreascience.kr/article/CFKO202306643315767.pdf
- 저자: 확인 못 함. 소속: 검색 요약상 LG AI연구원 (원문 확인 못 함).
- 검색 결과 요약 내용: 생성형 LM을 테이블 QA에 적용, 모델·프롬프트 변경 비교(GPT-3.5, GPT-4, 자체 모델), KorWikiTQ와 KorQuad2Table 사용, 자체 EXAONE 1.7B 미세조정 EM 92.49/F1 94.81, 생성형 답이 문장으로 나와 EM/F1이 맞지 않는 문제와 그에 맞는 평가 방법 제안.
- TableTrace와의 관계: **KorWikiTQ에서 생성형 소형 모델 미세조정이 이미 높은 EM을 낸다는 국내 보고**가 있음(원문 확인 필요). TableTrace가 "EM이 낮다/높다"를 주장하기보다 "정답 중 근거 셀이 틀린 비율"이라는 다른 축을 재야 하는 이유가 됨.

### A7. 「한국어 표 질의응답 성능 향상을 위한 데이터 전처리 기법 분석」(2025) — 스니펫만
- 저자: 검색 요약에 "배한나 외". 학술지: 검색 요약에 제27권 제2호(2025.05) pp.71–87, 학술지명 확인 못 함. URL(열지 못함): https://www.earticle.net/Article/A467785 (유료).
- 내용: 표 전처리 방법이 한국어 표 QA 성능에 미치는 영향 분석 — 그 이상은 확인 못 함.

---

## B. 한국어 표 이해/요약 (QA 아님, 직렬화 관련)

### B1. Theme-Explanation Structure for Table Summarization using LLMs: A Case Study on Korean Tabular Data (Tabular-TX) — 전문 열람
- 저자: TaeYoon Kwack, Jisoo Kim, Ki Yong Jung, Heesun Park (성균관대), DongGeon Lee (POSTECH)
- 학회: 4th Table Representation Learning Workshop (TRL 2025, ACL Anthology 2025.trl-1.1; 제목 페이지로 확인), arXiv 2501.10487v3
- 데이터: 국립국어원 표 해석 말뭉치(NIKL 2024), "7,170 training tables, 876 validation tables, and 876 test tables" (5.1절). 강조 셀(highlighted_cells)을 한 문장으로 요약.
- 모델·수치 (Table 1, ROUGE-1/ROUGE-L/BLEU/평균): KoBART 미세조정 평균 0.33, EXAONE 3.0 7.8B ICL 0.12 / LoRA 0.17 / Tabular-TX 0.45, Bllossom-8B ICL 0.28 / Tabular-TX 0.43.
- 직렬화: 표를 `{"row": i, "col": j, "value": ...}` 키-값 사전 목록으로 변환, 병합 셀 복제, 강조 셀과 같은 행/열의 헤더만 유지 (부록 C.1, Figure 7).
- 본문에서 EXAONE 3.0이 "ranking first on the KorWikiTableQuestions"라고 서술(5.1절) — 출처 수치는 이 논문에 없음.
- 근거/보류/RL: 없음.
- TableTrace와의 관계: **한국어 표를 LLM에 넣을 때 행·열 좌표를 셀마다 명시하는 직렬화는 이미 국내 연구에 있음.** TableTrace는 그 좌표를 모델 출력의 근거로 쓰고 검증한다는 점이 다름.

### B2. TableVQA-Bench (NAVER Cloud AI) — 전문 열람
- 저자: Yoonsik Kim, Moonbin Yim, Ka Yeon Song (NAVER Cloud AI). arXiv 2404.19205 (2024). 정식 학회: 확인 못 함.
- 데이터: 영어 표(WTQ, TabFact, FinTabNet 등에서 파생), "894 images and 1500 QA pairs" (Table 1 설명). 한국어 데이터 아님(본문에 Korean 언급 없음).
- 결과(본문 서술): 텍스트 형식 표가 이미지 형식보다 정확도가 높고, "HTML format … can achieve better performance than markdown format" (Figure 2 설명).
- TableTrace와의 관계: 한국 기업의 표 직렬화 형식 비교. 다만 영어·멀티모달.

---

## C. 근거(인용)·답변 보류

### C1. CReSt: A Comprehensive Benchmark for RAG with Complex Reasoning over Structured Documents — 전문 열람
- 저자: Minsoo Khang, Sangjun Park, Teakgyu Hong, Dawoon Jung (Upstage AI). arXiv 2505.17503v1 (2025). 정식 학회: 확인 못 함.
- 데이터: 영어·한국어 2,245개 사람 주석 예제 (Table 7: Refusal 1013 / Non-refusal 1232, English 1048 / Korean 1197). 한국어 원문은 국회도서관(NANET) 문서 이미지, HTML(~55%)·평문 청크, 표 포함 구조 문서 (3절). train/test 분할: 평가용 벤치마크, 분할 언급 확인 못 함.
- 평가: 답 정확도는 LLM 평가(Correct/Partial/Wrong), **거부(refusal) 정확도**, Unified Score(답 가능 질문에서 거부하면 −1.0; Table 2), **인용 정밀도/재현율을 답 정확도와 별도로 측정**(4.3.2절, Table 4). 인용은 문서(청크) 단위로만 평가, 구절 단위 주석은 있으나 미사용(6절 Limitations).
- 수치(한국어): o4-mini Unified 0.4458, Refusal Acc 23.01% (Table 3); 인용 F1 o4-mini 79.09%, GPT-4.1 77.23% (Table 4). 본문: "citation capability generally correlates with answer correctness", 그러나 Qwen2.5-72B는 인용 점수가 더 높아도 Unified는 32B보다 낮음(4.3.2절).
- 검증기/RL: 없음 (평가 벤치마크).
- TableTrace와의 관계: **한국어 문서(표 포함)에서 인용 정확도를 답 정확도와 분리해 재고, 답변 보류를 함께 채점하는 국내 기업 연구가 이미 있음.** 차이: CReSt는 청크 단위 인용·LLM 채점·대형 모델 평가, TableTrace는 셀 단위 인용·고정 규칙 검증기·소형 모델 학습.

### C2. Evaluating Structure-Aware Retrieval and Safety in Statute-Centric Legal QA (SearchFireSafety) — 전문 열람(arXiv v2)
- 저자: Kyubyung Chae 외, Taesup Kim (서울대 데이터사이언스대학원). ACL 2026 long (aclanthology 2026.acl-long.2112, 제목 페이지 확인; arXiv 제목은 "Beyond Case Law: …"), arXiv 2604.06173v2.
- 한국 소방안전 법령 QA. Partial Context(증거 부족, 정답 "Cannot be determined")에서 보류 능력 측정. Table 5: Exaone3.5-7.8B 52.31, HyperClovaX-14B 42.97, Qwen3-32B 54.38, GPT-4o 72.10 (Partial Ctx 정확도 %). 연속 사전학습(CPT)이 보류 성능을 낮춘다는 관찰(Figure 3).
- 표 아님. 검증기/RL 없음.
- TableTrace와의 관계: 한국어 QA에서 "증거가 불충분하면 답하지 않아야 한다"는 평가는 국내에 이미 있음. TableTrace는 표 셀 근거에 대해 규칙 검증기로 보류를 결정.

---

## D. 한국어 LLM 강화학습(검증 가능 보상, 보상 해킹)

### D1. EXAONE 4.0 기술 보고서 (LG AI Research) — 해당 절만 열람
- arXiv 2507.11407v2. 저자 표기 "LG AI Research".
- RL: GRPO 변형 **AGAPO**, 검증 가능 보상 r∈[0,1]; 수학은 "rule-based verifier", 과학은 규칙 검증기 후 LLM-judge (2.4절). 표 QA를 RL 데이터로 쓴다는 서술은 확인 못 함 (데이터 범주: math, code, science, instruction following).
- Ko-LongBench(사내): "Long Structued QA – Table QA – 300" 샘플 (Table 12), 예시는 HTML 표 + 4지선다 수치 문제 (Figure 6). EXAONE 4.0 1.2B 평균 72.0(32K)/69.8(64K) (Table 13, 전 과제 평균; 표 QA 단독 수치는 확인 못 함).
- TableTrace와의 관계: TableTrace가 쓰는 EXAONE-4.0-1.2B 자체가 규칙 검증기 보상 RL로 학습됨. "규칙 검증기 보상으로 RL" 자체는 새롭지 않음.

### D2. Making Qwen3 Think in Korean with Reinforcement Learning — 전문 열람
- 저자: Jungyup Lee, Jemin Kim, Sang Park, SeungJae Lee. 소속: 본문에서 확인 못 함. arXiv 2508.10355 (2025).
- SFT 후 Oracle-Guided Dr.GRPO. 보상 해킹 관찰: "the model would output excessively verbose or structured answers that superficially satisfied format requirements to get a higher format reward" (3절 부근). 외부 oracle judge로 보정.
- 표 아님. TableTrace와의 관계: 한국어 RL에서 **형식 보상 해킹**이 보고됨 — TableTrace의 검증기 보상도 형식(op/cells) 충족만으로 보상을 받는지 점검해야 함.

### D3. Do LLMs Need Inherent Reasoning Before RL? A Study in Korean Self-Correction — 초록·방법 일부 열람
- 저자: Hongjin Kim, Jaewook Lee, Kiyoung Lee, Jong-hun Shin, Soojong Lim, Oh-Woog Kwon (ETRI). arXiv 2601.05459 (2026).
- MathDial 기반 한국어 자기수정, GRPO 보상 = 결과 보상 + `<THINK>` 형식 보상. 수치는 이번에 정리하지 않음(확인 못 함).

---

## E. 검토했으나 관련성 낮아 제외
- KFinEval-Pilot (arXiv 2504.13216; 금융결제원·Teddysum·SELECTSTAR): 한국어 금융 벤치마크이나 표 기반 수치 추론 과제 여부 확인 못 함(본문 정독 안 함).
- VARCO-VISION / K-DTCBench (NCSOFT, arXiv 2411.19103): 문서·표·차트 이미지 VLM 벤치마크. 텍스트 표 QA 아님.
- "The Table Says Otherwise" (arXiv 2606.23667): 저자 Xinzhi Wang, Chunwei Liu — 국내 소속 확인 못 함, 제외.
- HCLT 2023 LG AI연구원 한국어 Text-to-SQL 평가(CFKO202306643316111), 2024 RAG 기반 테이블 데이터 처리 성능 분석(CFKO202433162262523): 검색 결과에 제목 단서만, 원문·저자 확인 못 함.

---

## TableTrace가 새롭다고 쓰면 안 되는 것(국내 연구 기준)
1. 한국어 표 QA 데이터·모델 자체, 표 직렬화(행 헤더/구조 정보 포함)가 성능을 바꾼다는 관찰 — A1 Table 3 (LREC 2022), A3(행·열 임베딩, 스니펫).
2. 셀마다 행·열 좌표를 붙인 한국어 표 직렬화 — B1 (TRL 2025, 부록 C.1).
3. KorWikiTQ에서 소형 생성형 모델 미세조정으로 높은 EM — A6 (HCLT 2023, 스니펫; 원문 확인 필요).
4. 한국어 QA에서 인용(근거) 정확도를 답 정확도와 분리 측정 + 답변 보류 채점 — C1 CReSt (청크 단위).
5. 한국어 QA에서 증거 부족 시 보류 평가 — C1, C2.
6. 규칙 기반 검증기 보상 GRPO류 RL, 한국어 RL의 형식 보상 해킹 — D1(EXAONE 4.0 AGAPO), D2.

## 국내 연구에서 찾지 못한 것(검색어 포함)
(접속 차단으로 koreascience/DBpia 원문 검색은 못 했으므로 "없다"가 아니라 "이번 검색에서 못 찾음"임)
1. 한국어 표 QA에서 **정답 중 인용 셀이 틀린 비율**(셀 단위 근거 정확도)을 잰 연구 — 검색어: "Korean question answering attribution evidence citation hallucination verification", "한국어 표 질의응답 근거 셀", "KorWikiTQ 활용 테이블 질의응답 LLM".
2. KorWikiTQ train/dev **표 중복(누수) 분석** 또는 재분할 — 검색어: "KorWikiTQ 활용 테이블 질의응답 LLM 한국어 논문", "KorWikiTQ Korean table question answering LREC 2022". A1 논문·README 모두 분할 방법 미기재.
3. 한국어 표 QA에서 **산술 재계산 규칙 검증기 + 보류** — 검색어: 위 1과 동일, "Korean table question answering benchmark LLM arXiv 2024 2025".
4. 한국어 표 QA에 **RL(GRPO/RLVR) 적용** — 검색어: "한국어 LLM 강화학습 GRPO 검증가능 보상 RLVR 한국어 추론 논문 arXiv".
5. 한국어 FinQA식 **표 수치 추론 공개 데이터셋** — 검색어: "Korean financial table question answering dataset numerical reasoning arXiv Korean FinQA".
6. AI-Hub "표 정보 질의응답 데이터" 페이지 — 검색어: "AI-Hub 표 정보 질의응답 데이터 구축 표 질의응답" (해당 데이터셋 페이지 검색 결과 없음, aihub.or.kr 접속은 시도 안 함).
7. KorQuAD 2.0 원 논문(표 질문 비중) — 이번에 열람 못 함.

## 접속 실패 기록
- www.koreascience.kr, koreascience.or.kr, www.dbpia.co.kr, www.earticle.net, doaj.org, api.semanticscholar.org: WebFetch "getaddrinfo ENOTFOUND"(세션 네트워크 허용 목록 밖). curl로 koreascience.kr: "CONNECT tunnel failed, response 403".
