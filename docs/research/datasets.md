# 데이터 조사와 구축 기록

## 1. KorWikiTQ / KorWikiTabular (LG AI연구원)

| 항목 | 확인 내용 |
|---|---|
| 출처 | <https://github.com/LG-NLP/KorWikiTableQuestions> (공식 저장소, clone 성공) |
| 논문 | Jun et al., *Korean-Specific Dataset for Table Question Answering*, LREC 2022 (arXiv 2201.06223). 저장소 README의 초록으로 확인. arXiv 원문은 네트워크 차단으로 열지 못함 |
| 라이선스 | **CC BY-SA 4.0** (저장소 `LICENSE` 파일 전문 확인) |
| 접근 | README가 가리키는 Google Drive 링크는 차단됐고, 저장소의 JSON은 Git LFS 포인터였다. LFS API도 프록시에 막혔으나 `media.githubusercontent.com/media/LG-NLP/KorWikiTableQuestions/main/KorWikiTQ/*.json` 경로로 원본을 받았고 **SHA256이 LFS 포인터의 oid와 일치**한다 (dev `b44b1e60…`, train `dc3bcfe7…`) |
| 구성 | `KorWikiTQ_ko_train.json` 58,221쌍 / `KorWikiTQ_ko_dev.json` 11,771쌍. 필드: `U`(위키 URL), `T`(제목+본문 설명), `QAS{qid, question, answer}`, `TBL`(2차원 리스트, 첫 행이 헤더). 표 크기 중앙값 14행×5열 |
| KorWikiTabular | 1.4M 표 사전학습 코퍼스. Google Drive 전용 링크라 **접근 불가** — 이 프로젝트에서는 사용하지 않았다 |

### 공개 분할의 특성과 한계 (직접 측정)

- 정답이 표의 **어떤 셀과 정확히 일치**하는 비율: train 99.6 %, dev 99.5 % → 셀 선택 과제. 산술 연산·보류 사례는 없다.
- **train과 dev가 1,755개의 표(URL 기준)를 공유**한다 (qid 접두사 기준 1,554개). 즉 공개 분할은 질문 단위 분할이며 표가 겹친다. 표 내용을 외우는 모델이 dev에서 유리할 수 있다.
- 그래서 **표 단위로 다시 분할**했다(`scripts/data/build_ko.py`): URL+표 내용 해시로 표를 식별하고, 표를 섞어 test 180 / dev 60 / train 900개 표에 배정. 분할 간 공유 표 0개(`data/ko/build_report.json`의 `leak_check_shared_tables`).

### 전처리·제외 기준 (`data/ko/build_report.json`)

| 기준 | 제외 건수 |
|---|---|
| 표가 16행 또는 7열 초과 (mT5-small 512 토큰 예산) | 31,864 |
| 표 전체 문자 수 900 초과 | 2,098 |
| 빈 헤더 셀 | 1,503 |
| 정답 셀이 유일하지 않음(동일 값 셀이 여러 개이고 질문으로 구분 불가) | 421 |
| 행 길이 불일치 | 173 |
| 남은 표 | 7,294개 중 1,140개 사용 (표당 최대 3문항) |

결과: train 2,694 / dev 180 / test 539 문항. 학습 시 직렬화가 512 토큰을 넘어 정답 행이 잘리는 223건은 **학습에서 제외**하고 기록했다(test에서는 제외하지 않고 `truncated_gold_rate`로 보고).

### 합성 데이터 (`scripts/data/synth_ko.py`, `source: synthetic`)

표의 숫자 열 두 행을 골라 템플릿으로 만든 차이·합·평균 질문과, 다른 표의 개체/속성을 물어보는 보류 질문. 분할별로 그 분할의 표만 사용. train 960 / dev 65 / test 160. **합성 test는 수작업 평가와 별도로 보고**한다.

### 텍스트 답변 학습용 (KorQuAD v1.0, `scripts/data/build_korquad_text.py`)

`op: text`(본문에서 답 복사)를 가르치기 위해 KorQuAD v1.0 train에서 700문항, dev에서 100문항을 300자 창으로 잘라 사용했다. 원본 JSON은 `korquad/korquad.github.io` 저장소에서 받았다. 라이선스는 KorQuAD 사이트 기준 CC BY-ND 2.0 KR로 알려져 있으나 사이트 자체는 열지 못했고, 파생 파일은 git에 넣지 않는다(`data/ko/text_*.jsonl`은 .gitignore).

### 수작업 평가 사례 (`data/ko/custom_eval.jsonl`, 30문항, `source: custom`)

test 분할 표 6개 위에 직접 작성했다. 범주: 셀 근거(cell 9) · 계산(calc 6) · 본문+표(text_table 5) · 단위·기간 주의(unit_period 5) · 답 없음→보류(abstain 5). **검수 방법**: 작성 직후 스크립트로 (1) lookup 정답이 지정 셀 텍스트와 정확히 같은지, (2) 계산 정답이 제한 계산기 결과와 같은지, (3) 텍스트 정답이 해당 문단에 실제로 포함되는지 자동 검증했고 30/30 통과. 소규모이므로 비율은 참고치다.

## 2. 영어 화학 문서 — OpenStax *Chemistry 2e*

| 항목 | 확인 내용 |
|---|---|
| 출처 | <https://github.com/openstax/osbooks-chemistry-bundle> (Rice University OpenStax, CNXML 원본) |
| 라이선스 | **CC BY-NC-SA 4.0** (저장소 LICENSE·collection.xml의 `md:license` 확인). 비상업 연구 용도로 사용 |
| 구성 | 149 모듈(장·절) 중 사용 가능한 표가 있는 **56 문서, 113 표, 3,780 문단** |
| 파싱 | `scripts/data/build_chem.py`: MathML을 평문으로(`msub`→`H2O`, `msup`→`10^−6`), 제목 행이 있는 `thead`는 캡션으로, `thead`가 없는 부록 표는 첫 행을 헤더로. 다단 헤더·병합 셀은 제외(헤더 병합 13, 본문 병합 9, 다단 0, 헤더 없음 34 등) |
| 분할 | **문서(모듈) 단위**: test 11 / dev 5 / train 40 (`data/chem/split.json`) |

왜 논문·특허가 아닌 교과서인가: arXiv, PMC, ChemRxiv, Google Patents, Zenodo, figshare가 모두 차단되어 이 환경에서 받을 수 있는 "본문+표"가 있는 영어 화학 문서는 GitHub에 원본이 공개된 OpenStax 교과서뿐이었다. 문서에는 실험 데이터 표(반응 속도 실험 trial별 농도·속도, Arrhenius 상수, 임계 온도·압력, 할로겐 끓는점 등)와 단위가 포함돼 있어 "물질·실험 조건·측정값·단위" 질문을 만들 수 있다.

조사했으나 쓰지 못한 후보: ChemTables(표 분류용, 데이터는 특허 XML 별도 다운로드 필요), ChemRxnExtractor(문장 단위 반응 역할 추출, 모델은 Google Drive), Open Reaction Database(반응 레코드, 문서 아님), PubChem·ChEMBL(차단).

### 합성 학습 데이터 (`scripts/data/synth_chem.py`)

train/dev 분할 표에서 lookup 420 / diff 120 / ratio 60 / sum 60 / abstain 160 (train 820건), dev 80건. 템플릿 질문이므로 표현 다양성이 낮다는 한계가 있다.

### 수작업 평가 사례 (`data/chem/custom_eval.jsonl`, 32문항)

test 분할 문서 8개 위에 작성. 범주: cell 10 · calc 7 · text_table 6 · unit_period 5 · abstain 5 (한 문항은 두 범주 성격). 검수: 한국어와 같은 자동 검증 32/32 통과. 숫자·단위 문항은 셀의 단위(kPa, K, °C, L/mol)를 정답에 포함했다.

## 3. 사용하지 않은/못한 데이터

- EXAONE 계열 모델·HF 데이터셋: `huggingface.co` 차단.
- AI Hub 표 QA, KLUE(표 과제 없음), 한국어 위키 덤프: 차단 또는 과제 불일치.
