"""Render experiment artifacts into Markdown tables and splice them into README.md / docs/REPORT.md
between <!-- results:NAME:start --> and <!-- results:NAME:end --> markers, so no number is typed by hand.

  python scripts/render_results.py            # update README.md and docs/REPORT.md in place
  python scripts/render_results.py --print    # just print the blocks
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments"
MODELS = [("휴리스틱 기준선", "heuristic"), ("mT5-small 기본(미튜닝)", "base"), ("SFT stage1", "sft_ko"), ("SFT stage2(+본문)", "sft_ko2"),
          ("GRPO RL", "rl_ko"), ("화학 SFT", "sft_chem")]


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pct(x) -> str:
    return "–" if x is None else f"{100 * x:.1f}"


def eval_table(suffix: str, title: str) -> str:
    rows = []
    for name, key in MODELS:
        m = load(EXP / "eval" / f"{key}_{suffix}" / "metrics.json")
        if not m:
            continue
        mm = m["metrics"]
        rows.append(f"| {name} | {mm['n']} | **{pct(mm['verified_em'])}** | {pct(mm['raw_answer_em_answerable'])} | {pct(mm['lookup_em'])} | {pct(mm['calc_em'])} | {pct(mm['evidence_cells_exact'])} | {pct(mm['abstain_recall'])} | {pct(mm['false_abstain_rate'])} | {pct(mm['parse_fail_rate'])} | {mm['mean_ms_per_example']:.0f} |")
    if not rows:
        return f"_{title}: 산출물 없음_\n"
    head = ("| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 % | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |\n"
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    return f"**{title}**\n\n{head}" + "\n".join(rows) + "\n"


def category_table(suffix: str, title: str) -> str:
    cats: dict[str, dict] = {}
    names = []
    for name, key in MODELS:
        m = load(EXP / "eval" / f"{key}_{suffix}" / "metrics.json")
        if m and m["metrics"].get("by_category"):
            cats[name] = m["metrics"]["by_category"]
            names.append(name)
    if not cats:
        return ""
    cnames = sorted({c for v in cats.values() for c in v})
    out = f"**{title} — 범주별 verified EM % (n)**\n\n| 범주 | " + " | ".join(names) + " |\n|---|" + "---:|" * len(names) + "\n"
    for c in cnames:
        out += f"| {c} | " + " | ".join(f"{pct(cats[n][c]['verified_em'])} ({cats[n][c]['n']})" if c in cats[n] else "–" for n in names) + " |\n"
    return out + "\n"


def training_table() -> str:
    rows = []
    for name, d in [("SFT stage1 (ko 표)", "sft_ko"), ("SFT stage2 (ko 표+본문)", "sft_ko2"), ("SFT chem", "sft_chem"), ("GRPO RL (ko)", "rl_ko")]:
        s = load(EXP / d / "summary.json")
        if not s:
            c = load(EXP / d / "config.json")
            if c:
                rows.append(f"| {name} | {c.get('n_train', c.get('n_train_prompts', '–'))} | {c.get('total_steps', c['args'].get('steps', '–'))} | (미완료) | – | – |")
            continue
        hist = s.get("dev_history") or []
        rows.append(f"| {name} | {s.get('n_train', s.get('n_train_prompts', '–'))} | {s.get('steps', '–')} | {s.get('wall_s', 0) / 60:.0f} min | {pct(s.get('best_dev_verified_em'))} | {', '.join(pct(h.get('verified_em')) for h in hist)} |")
    if not rows:
        return "_학습 기록 없음_\n"
    return ("| 실행 | 학습 예제/프롬프트 | 스텝 | 소요 (CPU 4스레드) | best dev verified EM % | dev 추이 % |\n|---|---:|---:|---:|---:|---|\n" + "\n".join(rows) + "\n")


def rl_table() -> str:
    log = EXP / "rl_ko" / "train_log.jsonl"
    if not log.exists():
        return "_RL 로그 없음_\n"
    steps = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip() and '"eval"' not in line]
    evals = [json.loads(line)["eval"] for line in log.read_text(encoding="utf-8").splitlines() if '"eval"' in line]
    if not steps:
        return "_RL 스텝 없음_\n"
    k = max(1, len(steps) // 4)
    chunks = [steps[i:i + k] for i in range(0, len(steps), k)]
    avg = lambda xs, key: sum(x[key] for x in xs) / len(xs)  # noqa: E731
    out = "| 구간(step) | 평균 보상 | 보상 표준편차 | 샘플 정답률 % | 샘플 보류율 % | 파싱 성공 % | KL | 그룹 분산 0 비율 % |\n|---|---:|---:|---:|---:|---:|---:|---:|\n"
    for ch in chunks:
        out += f"| {ch[0]['step']}–{ch[-1]['step']} | {avg(ch, 'reward_mean'):.3f} | {avg(ch, 'reward_std'):.3f} | {pct(avg(ch, 'correct_rate'))} | {pct(avg(ch, 'abstain_rate'))} | {pct(avg(ch, 'parse_ok'))} | {avg(ch, 'kl'):.4f} | {pct(avg(ch, 'frac_group_zero_std'))} |\n"
    if evals:
        out += "\ndev verified EM: " + " → ".join(f"step {e['step']}: {pct(e['verified_em'])}%" for e in evals) + "\n"
    ops = {}
    for s_ in steps:
        for op, n in s_.get("ops", {}).items():
            ops[op] = ops.get(op, 0) + n
    out += "샘플 연산 분포(전체): " + ", ".join(f"{k_}: {v}" for k_, v in sorted(ops.items(), key=lambda x: -x[1])) + "\n"
    return out


def bench_table() -> str:
    b = load(EXP / "bench" / "inference.json")
    if not b:
        return "_추론 벤치 산출물 없음_\n"
    m = b["meta"]
    out = (f"조건: {m['model']}, 입력 {m['n_examples']}개(ko test), max_new_tokens {m['max_new_tokens']}, 워밍업 {m['warmup_rounds']}라운드 + 측정 {m['measured_rounds']}라운드, "
           f"{m['threads']} 스레드, {m['cpu']} ({m['cores']} cores), torch {m['torch']}, CUDA {m['cuda']}, 양자화 소요 {m['quantize_time_s']} s, fp32 가중치 {m['fp32_state_dict_mb']} MB\n\n")
    out += "| 설정 | p50 ms | p95 ms | 처리량 예제/s | RSS GB | fp32 bs=1과 출력 일치 % |\n|---|---:|---:|---:|---:|---:|\n"
    for r in b["results"]:
        out += f"| {r['config']} | {r['p50_ms']} | {r['p95_ms']} | {r['throughput_ex_per_s']} | {r['rss_gb_after']} | {pct(r['agreement_with_fp32_bs1'])} |\n"
    return out


def pp_table() -> str:
    a, b = load(EXP / "bench" / "pp_single.json"), load(EXP / "bench" / "pp_2stage.json")
    if not (a and b):
        return "_파이프라인 병렬 산출물 없음_\n"
    same = a.get("outputs") == b.get("outputs")
    out = f"조건: CPU(gloo), n={a['n']}, bs={a['bs']}, 단일 프로세스 {a.get('params_total', 0):,} 파라미터\n\n"
    out += "| 구성 | 장치 | 스테이지 파라미터 | 처리량 예제/s | 메모리 MB | 평균 배치 지연 s |\n|---|---|---:|---:|---:|---:|\n"
    out += f"| 단일 프로세스 | {a['device']} | {a['params_total']:,} | {a['throughput_ex_per_s']} | {a['mem_mb']:.0f} | {sum(a['batch_latency_s']) / len(a['batch_latency_s']):.2f} |\n"
    for st in b["stages"]:
        out += f"| 파이프라인 rank{st['rank']} ({st['stage']}) | {st['device']} | {st['stage_params']:,} | {b['throughput_ex_per_s'] if st['rank'] == 0 else ''} | {st['mem_mb']:.0f} | {sum(st['batch_latency_s']) / len(st['batch_latency_s']):.2f} |\n"
    out += f"\n단일 프로세스와 2-스테이지의 생성 출력 일치: **{'예' if same else '아니오'}** ({len(a.get('outputs', []))}개 입력)\n"
    return out


def blocks() -> dict[str, str]:
    return {
        "ko": eval_table("ko_test", "한국어 표 QA — 독립 test (원본 539 + 합성 160)") + "\n" + eval_table("ko_custom", "한국어 표 QA — 수작업 30문항") + "\n" + category_table("ko_custom", "한국어 수작업"),
        "chem": eval_table("chem_custom", "영어 화학 문서 — 수작업 32문항 (test 분할 문서)") + "\n" + eval_table("chem_syndev", "영어 화학 — 합성 dev 80문항(템플릿, 참고용)") + "\n" + category_table("chem_custom", "화학 수작업"),
        "training": training_table(),
        "rl": rl_table(),
        "bench": bench_table(),
        "pp": pp_table(),
    }


def splice(path: Path, blk: dict[str, str]) -> int:
    text = path.read_text(encoding="utf-8")
    n = 0
    for name, body in blk.items():
        pat = re.compile(rf"(<!-- results:{name}:start -->)(.*?)(<!-- results:{name}:end -->)", re.S)
        if pat.search(text):
            text = pat.sub(lambda m, b=body: f"{m.group(1)}\n{b}\n{m.group(3)}", text)
            n += 1
    path.write_text(text, encoding="utf-8")
    return n


def main() -> None:
    blk = blocks()
    if "--print" in sys.argv:
        for k, v in blk.items():
            print(f"### {k}\n{v}")
        return
    for p in [ROOT / "README.md", ROOT / "docs" / "REPORT.md"]:
        if p.exists():
            print(p.name, "blocks updated:", splice(p, blk))


if __name__ == "__main__":
    main()
