# 작업 환경과 제약 (실측, 2026-10-29)

이 문서는 프로젝트가 **실제로 어떤 환경에서 만들어지고 실행되었는지**를 기록한다. 보고서와 README의 "실행함 / 준비만 함" 구분은 이 문서를 근거로 한다.

## 컴퓨팅

| 항목 | 값 | 확인 방법 |
|---|---|---|
| CPU | Intel Xeon @ 2.10GHz, 4 vCPU | `nproc`, `lscpu` |
| 메모리 | 15 GB | `free -g` |
| GPU | **없음** (`nvidia-smi: command not found`) | 셸 실행 |
| 디스크 | 세션 할당량 약 30 GB (venv 5.2 GB, 모델 2.1 GB 사용) | `df -h` |
| OS / Python | Linux 6.18, Python 3.13.17 (uv 가상환경) | `python -V` |
| PyTorch | 2.15.0 (PyPI 휠, CUDA 런타임 동봉이지만 GPU 없음 → CPU 실행) | `torch.cuda.is_available() == False` |
| Transformers | 5.21.0 | `pip list` |

GPU가 없으므로 **모든 모델 학습·추론은 CPU에서 수행**했다. 멀티 GPU Model Parallelism은 코드·설정·명령을 준비하고 CPU 2-프로세스로 기능 검증만 했다(docs/experiments/parallel.md).

## 네트워크 정책 (세션 이그레스 프록시)

허용된 호스트 (실제 200 응답 확인):

- `pypi.org`, `files.pythonhosted.org` — 패키지 설치
- `api.github.com`(세션에 연결된 저장소만), `raw.githubusercontent.com`, `github.com`(공개 저장소 clone), `objects.githubusercontent.com`(릴리스 자산), `media.githubusercontent.com`(LFS 미디어)
- `storage.googleapis.com` — 공개 버킷 중 `t5-data` (mT5/ByT5/T5 체크포인트) 접근 가능
- `cloud.google.com`, `googleapis.com` 일부
- `api.anthropic.com` (키 없음 → 미사용)

차단된 호스트 (CONNECT 403 또는 DNS 실패):

- `www.lgresearch.ai` — **채용 공고·LG 논문 페이지를 열 수 없었다** (docs/research/job-posting.md)
- `huggingface.co`, `hf-mirror.com`, `cdn-lfs.huggingface.co` — **EXAONE 등 HF 모델·데이터셋 다운로드 불가**
- `drive.google.com` — KorWikiTQ readme가 가리키는 Google Drive 링크 (LFS 미디어 경로로 대체 확보)
- `arxiv.org`, `aclanthology.org`, `openreview.net`, `semanticscholar.org` — 논문 원문 접근 불가
- `ko.wikipedia.org`, `en.wikipedia.org`, `openstax.org`, `patents.google.com`, `pubchem`, `chemrxiv.org`, `zenodo.org`, `figshare.com`
- `render.com`, `api.render.com`, `vercel.com`, `netlify`, `fly.io`, `railway.app`, `cloudflare`, `hf.space`, `*.github.io` — **배포 플랫폼 접근 불가**
- `learn.microsoft.com`, `labelstud.io`, `langfuse.com`, `docs.ragas.io` 등 제품 문서 사이트
- `download.pytorch.org` (CPU 전용 휠 → PyPI 일반 휠로 대체), `storage.googleapis.com/bert_models` (403)

**이후 바뀐 것.** 위 목록은 2026-10-29 기준이다. 소유자가 허용 목록을 고쳐 2026-11-10부터 `arxiv.org`, `aclanthology.org`, `huggingface.co`(작은 파일), `www.lgresearch.ai`가 열렸다. 2026-11-11에는 이 저장소용 환경(`tabletrace-research`)을 따로 승인받아 Hugging Face의 큰 파일 서버(`us.aws.cdn.hf.co`, `cas-bridge.xethub.hf.co`, `cas-server.xethub.hf.co`, `cdn-lfs.hf.co`)와 `koreascience.kr`을 더했다. 그 뒤 KoELECTRA-small 가중치를 받았다. `koreascience.kr`은 프록시가 허용해도 사이트가 연결을 끊어 열리지 않았다(이슈 52). EXAONE 가중치는 받을 수 있게 됐지만 이 컨테이너에는 GPU가 없어 돌리지 않았다.

## API 키

- 환경변수 `OpenAI_API_KEY`가 존재하지만 `api.openai.com`이 차단되어 사용 불가.
- Anthropic, HF 토큰 없음.
- 결론: **유료 API를 사용한 실행은 없다.** 모든 모델 추론은 로컬 mT5-small(CPU).

## 저장소 푸시 권한

- `sokldjs554/tabletrace`: 세션에 연결됐지만 **푸시 거부** — `remote: Claude doesn't have GitHub access to sokldjs554/tabletrace for your organization` (Claude GitHub App 미설치). GitHub API 경유 푸시도 `403 Resource not accessible by integration`.
- `sokldjs554/chartwire` 브랜치 `claude/bold-carson-ix16u0`: 세션에 지정된 작업 브랜치(푸시 가능).
- 조치: 프로젝트는 독립 git 저장소(`/home/user/tabletrace`)로 개발하고, 스냅샷을 chartwire의 지정 브랜치에 올려 보존한다. tabletrace로 옮기는 명령은 README와 최종 보고서에 적는다.

## 이 제약이 설계에 미친 영향

| 요구 | 제약 | 선택 |
|---|---|---|
| 한국어 LM 튜닝 (EXAONE 검토) | HF 차단 | GCS에서 받은 **mT5-small**(Google, Apache-2.0)을 TF→PyTorch로 직접 변환해 사용. EXAONE은 라이선스·실행 조건만 GitHub LICENSE/README로 확인 |
| 한국어 표 QA 데이터 | Drive 차단, LFS API 차단 | `media.githubusercontent.com` 경로로 KorWikiTQ 원본(SHA256 일치) 확보 |
| 영어 화학 문서 | 논문·특허 사이트 차단 | OpenStax *Chemistry 2e* 원본 CNXML(GitHub, CC BY-NC-SA 4.0)에서 본문+표 코퍼스 구축 |
| 서빙 엔진 vLLM/SGLang | GPU 없음 | OpenAI 호환 클라이언트·설정·명령 준비, 모의 서버로 연동 테스트. 실측 없음 |
| 공개 배포 | 배포 플랫폼 차단 | 정적 콘솔 + 저장된 실행 결과로 GitHub Pages 배포 워크플로우 준비. FastAPI 백엔드는 Docker로 로컬 실행 |
