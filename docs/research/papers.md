# 관련 연구 노트 — 무엇을 이해했고 무엇을 반영했나

네트워크 정책 때문에 arXiv·ACL Anthology 원문은 열 수 없었다. 아래는 (a) 이 세션에서 직접 읽은 GitHub README/문서와 (b) 사전 지식(원문 미확인, 표시함)을 구분해 적는다.

## 직접 읽은 자료

| 자료 | 읽은 곳 | 이해한 내용 | 반영 |
|---|---|---|---|
| **KorWikiTQ / KorWikiTabular** (Jun et al., LREC 2022) | 공식 저장소 README·데이터 | 1.4M 한국어 위키 표 사전학습 코퍼스 + 70k 크라우드소싱 QA. 정답은 거의 항상 셀 값. 공개 분할은 표를 공유 | 표 단위 재분할, 셀 선택을 프로그램(`lookup r{i}c{j}`)으로 표현, 산술·보류는 합성·수작업으로 보강 |
| **TAPAS** (google-research/tapas README) | README | 셀 선택 + 집계 연산자를 약지도로 학습, WTQ에서 "모호한 셀 매치 질문은 버린다"가 정확도를 올림, 질문과 겹치는 열만 남기는 HEM 필터 | 정답 셀이 유일하지 않은 421건 제외(같은 원칙), 휴리스틱 플래너의 열 겹침 점수 |
| **TAPEX** (microsoft/Table-Pretraining README) | README | 합성 SQL 실행을 흉내 내는 사전학습으로 표 이해를 얻음(seq2seq) | seq2seq(mT5)로 표를 직렬화해 프로그램을 생성하는 설계, 합성 계산 질문으로 연산을 가르침 |
| **Binder** (xlang-ai/Binder README) | README | LM이 SQL/Python 프로그램을 생성하고 실행기가 답을 계산, 적은 주석으로 SOTA급 | "모델은 제안, 도구는 실행·검증" 분리: 모델이 셀·연산을 내고 제한 계산기가 값을 계산 |
| **TableLlama / TableInstruct** (OSU-NLP README) | README | 표 과제 14개를 instruction으로 통합한 일반 모델 | 한국어 표·영어 화학 표를 같은 입출력 형식으로 통합 |
| **HybridQA** (wenhuchen/HybridQA README) | README | 표와 연결된 본문을 함께 읽어야 하는 다중 홉 QA | `op: text`와 본문 스니펫(context)을 입력에 포함, `text_table` 평가 범주 |
| **DeepSeekMath / GRPO** (deepseek-ai README) | README | DeepSeekMath-RL은 Instruct 모델 위에 GRPO로 학습 | 강화학습 알고리즘으로 GRPO 선택 |
| **TRL GRPOTrainer 문서** | docs/source/grpo_trainer.md | G개 샘플 → 그룹 평균(표준편차 정규화 선택) 이점 → 토큰별 정책 경사, KL(β) 기본 0, 길이 편향 논의 | `training/rl_grpo.py`를 같은 수식으로 직접 구현(β=0.02, 그룹 정규화). TRL 자체는 causal LM 전용이라 mT5(seq2seq)에는 쓰지 않음 |
| **vLLM 분산 서빙 문서** | docs/serving/parallelism_scaling.md | `--tensor-parallel-size`, `--pipeline-parallel-size`, 노드 간 Ray | `scripts/serving/vllm_tp2.sh`, docs/experiments/parallel.md |
| **EXAONE 3.5/4.0 README·LICENSE** | GitHub raw | 2.4B/7.8B/32B(3.5), 1.2B/32B(4.0), transformers≥4.43/4.54, vLLM·SGLang·llama.cpp 지원, 라이선스 1.1/1.2-NC(연구 목적만, 상업 금지) | docs/experiments/exaone.md |

## 사전 지식 (원문 미확인)

- 셀 선택·집계(TAPAS) vs 프로그램 생성(Binder, Chain-of-Table) vs 직접 생성(TableLlama)의 세 갈래가 있으며, 검증 가능성 면에서 프로그램 생성이 유리하다는 점을 설계 근거로 삼았다.
- GRPO의 원 논문(DeepSeekMath, arXiv 2402.03300)과 PPO/REINFORCE의 차이: GRPO는 가치 모델 없이 같은 프롬프트의 샘플 그룹으로 베이스라인을 만든다. 이 프로젝트의 구현은 이 설명에 따른다.

## 이 프로젝트의 문제 정의가 기존 연구와 다른 점

1. 정답뿐 아니라 **근거 셀·연산·계산값**이 함께 나와야 정답으로 친다(verified EM).
2. 답이 없거나 단위가 다르면 **보류**가 정답이다(abstain recall / false abstain).
3. 한국어 표와 영어 화학 문서를 **같은 모델·같은 형식**으로 다룬다.
