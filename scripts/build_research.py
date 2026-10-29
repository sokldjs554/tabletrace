"""Compile experiment artifacts into console/data/research.json (what the 연구 결과 view shows).

Reads experiments/eval/*/metrics.json, experiments/sft_*/summary.json, experiments/rl_ko/summary.json,
experiments/bench/*.json. Missing artifacts are reported as 'prep' (prepared, not run), never invented.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pct(x):
    return "-" if x is None else f"{100 * x:.1f}%"


def eval_row(name: str, key: str) -> list | None:
    m = load(EXP / "eval" / key / "metrics.json")
    if not m:
        return None
    mm = m["metrics"]
    return [name, mm["n"], pct(mm["verified_em"]), pct(mm["lookup_em"]), pct(mm["calc_em"]), pct(mm["evidence_cells_exact"]),
            pct(mm["abstain_recall"]), pct(mm["false_abstain_rate"]), pct(mm["parse_fail_rate"]), f"{mm['mean_ms_per_example']:.0f}"]


def main() -> None:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        commit = "unknown"
    env = load(ROOT / "docs" / "research" / "environment.json") or {}
    sections = []
    cols = ["플래너 / 모델", "n", "verified EM", "lookup EM", "calc EM", "근거 셀 일치", "보류 재현율", "오보류율", "파싱 실패", "ms/예제"]
    models = [("휴리스틱(어휘 겹침) 기준선", "heuristic"), ("mT5-small 기본(변환만)", "base"), ("SFT stage1(표)", "sft_ko"),
              ("SFT stage2(+본문)", "sft_ko2"), ("GRPO RL(stage2에서)", "rl_ko"), ("화학 SFT(stage2에서)", "sft_chem")]
    for title, suffix, desc in [("한국어 표 QA — 독립 test (KorWikiTQ 표 단위 분할 539 + 합성 160)", "ko_test", "표가 학습 분할과 겹치지 않는 539문항(원 데이터, lookup) + 합성 160문항(계산·보류)."),
                                ("한국어 표 QA — 수작업 평가 30문항", "ko_custom", "셀·계산·본문+표·단위/기간·보류 범주. 표본이 작아 참고치."),
                                ("영어 화학 문서 — 수작업 평가 32문항 (test 분할 문서)", "chem_custom", "물질 상수·실험 조건·수치/단위·본문·보류 범주.")]:
        rows = [r for r in (eval_row(n, f"{k}_{suffix}") for n, k in models) if r]
        done = any(r[0] != models[0][0] for r in rows)
        sec = {"title": title, "description": desc, "columns": cols, "rows": rows, "status": "done" if done else "prep",
               "artifact": f"experiments/eval/*_{suffix}/metrics.json"}
        cats = {}
        for n, k in models:
            m = load(EXP / "eval" / f"{k}_{suffix}" / "metrics.json")
            if m and m["metrics"].get("by_category"):
                cats[n] = m["metrics"]["by_category"]
        if cats:
            catnames = sorted({c for v in cats.values() for c in v})
            sec["notes"] = [f"{n}: " + ", ".join(f"{c} {pct(v[c]['verified_em'])} (n={v[c]['n']})" for c in catnames if c in v) for n, v in cats.items()]
        sections.append(sec)
    # training runs
    rows = []
    for name, d in [("SFT stage1 (ko)", "sft_ko"), ("SFT stage2 (ko+text)", "sft_ko2"), ("SFT chem", "sft_chem"), ("GRPO RL (ko)", "rl_ko")]:
        s = load(EXP / d / "summary.json") or load(EXP / d / "config.json")
        if not s:
            continue
        ev = (s.get("dev_history") or [{}])[-1]
        rows.append([name, s.get("n_train", s.get("n_train_prompts", "-")), s.get("steps", "-"), f"{s.get('wall_s', 0) / 60:.0f} min" if s.get("wall_s") else "(진행 중)",
                     f"{s['hardware']['threads']} threads CPU" if s.get("hardware") else "-", pct(s.get("best_dev_verified_em")), str(ev.get("step", "-"))])
    sections.append({"title": "학습 실행 기록", "columns": ["실행", "학습 예제", "스텝", "소요", "하드웨어", "best dev verified EM", "best step"], "rows": rows,
                     "status": "done" if rows else "prep", "artifact": "experiments/*/summary.json, train_log.jsonl",
                     "conditions": {"모델": "mT5-small 300M (gs://t5-data 체크포인트를 직접 변환)", "최적화기": "AdamW, 선형 워밍업 5% + 선형 감쇠, clip 1.0", "입력": "question + title + context(≤300자) + 표 직렬화 ≤512 토큰"}})
    rl = load(EXP / "rl_ko" / "train_log.jsonl".replace("train_log.jsonl", "summary.json"))
    rl_log = EXP / "rl_ko" / "train_log.jsonl"
    if rl_log.exists():
        steps = [json.loads(line) for line in rl_log.read_text(encoding="utf-8").splitlines() if line.strip() and '"eval"' not in line]
        if steps:
            first, last = steps[: max(1, len(steps) // 5)], steps[-max(1, len(steps) // 5):]
            avg = lambda xs, k: sum(x[k] for x in xs) / len(xs)  # noqa: E731
            sections.append({"title": "강화학습(GRPO 방식) 보상 추이", "status": "done",
                             "description": "그룹 정규화 이점으로 정책 경사 업데이트. 보상은 검증기 기반(정답·근거 셀·보류 적절성).",
                             "columns": ["구간", "평균 보상", "정답률(샘플)", "보류율(샘플)", "파싱 성공", "KL"],
                             "rows": [[f"처음 {len(first)} step", f"{avg(first, 'reward_mean'):.3f}", pct(avg(first, 'correct_rate')), pct(avg(first, 'abstain_rate')), pct(avg(first, 'parse_ok')), f"{avg(first, 'kl'):.4f}"],
                                      [f"마지막 {len(last)} step", f"{avg(last, 'reward_mean'):.3f}", pct(avg(last, 'correct_rate')), pct(avg(last, 'abstain_rate')), pct(avg(last, 'parse_ok')), f"{avg(last, 'kl'):.4f}"]],
                             "conditions": (rl or {}).get("args", {}), "artifact": "experiments/rl_ko/train_log.jsonl"})
    b = load(EXP / "bench" / "inference.json")
    if b:
        sections.append({"title": "추론 최적화 (CPU 실측)", "status": "done", "conditions": b["meta"],
                         "columns": ["설정", "p50 ms", "p95 ms", "처리량 (예제/s)", "RSS GB", "fp32 bs=1과 출력 일치"],
                         "rows": [[r["config"], r["p50_ms"], r["p95_ms"], r["throughput_ex_per_s"], r["rss_gb_after"], pct(r["agreement_with_fp32_bs1"])] for r in b["results"]],
                         "artifact": "experiments/bench/inference.json"})
    else:
        sections.append({"title": "추론 최적화 (CPU 실측)", "status": "prep", "description": "src/tabletrace/bench/inference.py — fp32/int8/배치/KV 캐시 비교. 아직 실행 전."})
    pp1, pp2 = load(EXP / "bench" / "pp_single.json"), load(EXP / "bench" / "pp_2stage.json")
    if pp1 and pp2:
        same = pp1.get("outputs") == pp2.get("outputs")
        rows = [["단일 프로세스(전체 모델)", pp1["device"], f"{pp1['params_total']:,}", f"{pp1['throughput_ex_per_s']}", f"{pp1['mem_mb']:.0f}", "-"]]
        for st in pp2["stages"]:
            rows.append([f"파이프라인 rank{st['rank']} ({st['stage']})", st["device"], f"{st['stage_params']:,}", f"{pp2['throughput_ex_per_s']}" if st["rank"] == 0 else "", f"{st['mem_mb']:.0f}", "출력 동일" if same else "출력 다름"])
        sections.append({"title": "멀티 GPU Model Parallelism — 2-스테이지 파이프라인 (CPU gloo 기능 검증)", "status": "done",
                         "description": "rank0=인코더, rank1=디코더+lm_head로 모델을 분할. GPU가 없어 CPU 2프로세스(gloo)로 분할·통신·출력 동일성만 검증했고 GPU 성능은 측정하지 못함.",
                         "columns": ["구성", "장치", "파라미터", "처리량 (예제/s)", "메모리 MB", "검증"], "rows": rows,
                         "notes": ["동일 입력에 대해 단일 프로세스와 2-스테이지의 생성 결과가 " + ("완전히 일치" if same else "일치하지 않음 (확인 필요)"),
                                   "GPU 실행 명령: torchrun --nproc_per_node=2 -m tabletrace.bench.pipeline_parallel --backend nccl (docs/experiments/parallel.md)"],
                         "artifact": "experiments/bench/pp_*.json"})
    else:
        sections.append({"title": "멀티 GPU Model Parallelism", "status": "prep", "description": "src/tabletrace/bench/pipeline_parallel.py 준비, 실행 전."})
    sections.append({"title": "vLLM / SGLang 서빙", "status": "prep",
                     "description": "GPU가 없어 실행하지 못함. OpenAI 호환 클라이언트(EnginePlanner)·TP=2 서빙 스크립트·벤치 스크립트를 준비했고 모의 서버로 왕복 테스트했다(tests/test_engines.py).",
                     "artifact": "scripts/serving/*.sh, src/tabletrace/service/engines.py, docs/experiments/serving.md"})
    data = {"generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "commit": commit,
            "summary": "모든 수치는 이 저장소의 experiments/ 산출물에서 그대로 가져왔다. 실행 환경: 4 vCPU Intel Xeon 2.10GHz, 15 GB RAM, GPU 없음 (docs/research/environment.md). " + json.dumps(env, ensure_ascii=False) if env else "모든 수치는 이 저장소의 experiments/ 산출물에서 그대로 가져왔다. 실행 환경: 4 vCPU Intel Xeon 2.10GHz, 15 GB RAM, GPU 없음.",
            "sections": sections}
    out = ROOT / "console" / "data" / "research.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out, "sections:", [s["title"][:30] + " " + s["status"] for s in sections])


if __name__ == "__main__":
    main()
