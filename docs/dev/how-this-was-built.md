# 이 저장소가 만들어진 방식

한 세션(2026-10-29, 약 6시간)에 Claude Code가 사용자의 지시서를 따라 만들었다. 순서와 근거를 남긴다.

1. **환경 확인** — GPU·네트워크·API 키·푸시 권한을 먼저 실측(docs/research/environment.md). 결과가 설계를 결정했다: HF 차단 → GCS mT5 변환, GPU 없음 → CPU 실험 + 병렬·서빙은 준비만, 푸시 거부 → 로컬 보존.
2. **조사** — 공고(차단, 기록), KorWikiTQ 저장소·논문 초록·라이선스, EXAONE 라이선스, 표 QA 연구 README, UI 스크린샷 13종, README 6종.
3. **데이터** — KorWikiTQ 표 단위 재분할(누수 검사), 합성 계산·보류, KorQuAD 텍스트, OpenStax CNXML 파싱, 수작업 평가 62문항(자동 검수).
4. **핵심 라이브러리** — 스키마, 숫자·단위 파서, 제한 계산기, 프로그램 문법, 검증기·보류 정책, 휴리스틱 플래너, BM25(Kiwi). 단위 테스트 70+.
5. **모델** — mT5-small 변환·검증(두 번의 실패를 기록), SFT 트레이너, 평가 러너, GRPO 방식 RL, 벤치·파이프라인 병렬.
6. **서비스·Agent·콘솔** — FastAPI + 작업 러너, LangGraph 그래프, 정적 콘솔(실시간/저장 결과), Playwright E2E.
7. **실험 파이프라인** — stage1 → base/stage1 평가 → stage2 → 화학 SFT → RL → 벤치 → 파이프라인 병렬 → 저장 결과 생성 → E2E. 순차 실행(동시 실행 시 OpenMP 초과 구독으로 5배 느려짐을 겪음).
8. **문서** — README·보고서의 수치는 `scripts/render_results.py`가 산출물에서 생성하고 `scripts/check_numbers.py`가 대조한다.

실패와 수정은 docs/dev/issues-log.md에 번호로 남겼다.
