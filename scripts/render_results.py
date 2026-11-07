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
          ("GRPO RL v1 (보상 허점)", "rl_ko_v1"), ("GRPO RL v2 (보상 수정)", "rl_ko"), ("화학 SFT", "sft_chem"), ("화학 SFT + int8 동적 양자화", "sft_chem_int8"),
          ("[2차] SFT stage2 재학습(실제 표 옆 본문 예제)", "sft_ko3"), ("[2차] + 표 조회 보강 epoch", "sft_ko4"), ("[2차] 화학 SFT v2", "sft_chem2"), ("[2차] GRPO RL v3", "rl_v3")]
V2 = "_ec"   # eval dirs written by replaying the stored raw outputs through the verifier WITH the subject check


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def pct(x) -> str:
    return "–" if x is None else f"{100 * x:.1f}"


def eval_table(suffix: str, title: str, ec: bool = False) -> str:
    rows = []
    for name, key in MODELS:
        m = load(EXP / "eval" / f"{key}_{suffix}{V2 if ec else ''}" / "metrics.json")
        if not m:
            continue
        mm = m["metrics"]
        rows.append(f"| {name} | {mm['n']} | **{pct(mm['verified_em'])}** | {pct(mm['raw_answer_em_answerable'])} | {pct(mm['lookup_em'])} | {pct(mm['calc_em'])} | {pct(mm['evidence_cells_exact'])} | {pct(mm.get('evidence_cells_exact_raw'))} | {pct(mm['abstain_recall'])} | {pct(mm['false_abstain_rate'])} | {pct(mm['parse_fail_rate'])} | {mm['mean_ms_per_example']:.0f} |")
    if not rows:
        return f"_{title}: 산출물 없음_\n"
    head = ("| 플래너 / 모델 | n | verified EM % | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % | 오보류율 % | 파싱 실패 % | ms/예제 |\n"
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    return f"**{title}**\n\n{head}" + "\n".join(rows) + "\n"


def category_table(suffix: str, title: str, ec: bool = False) -> str:
    cats: dict[str, dict] = {}
    names = []
    for name, key in MODELS:
        m = load(EXP / "eval" / f"{key}_{suffix}{V2 if ec else ''}" / "metrics.json")
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
    for name, d in [("SFT stage1 (ko 표)", "sft_ko"), ("SFT stage2 (ko 표+본문)", "sft_ko2"), ("SFT chem", "sft_chem"), ("GRPO RL v1 (ko)", "rl_ko_v1"), ("GRPO RL v2 (ko)", "rl_ko"),
                    ("[2차] SFT stage2 재학습", "sft_ko3"), ("[2차] 표 조회 보강 epoch", "sft_ko4"), ("[2차] SFT chem v2", "sft_chem2"), ("[2차] GRPO RL v3 (ko+chem+text)", "rl_v3")]:
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


def rl_table(run: str = "rl_ko") -> str:
    log = EXP / run / "train_log.jsonl"
    if not log.exists():
        return "_RL 로그 없음_\n"
    lines = log.read_text(encoding="utf-8").splitlines()
    steps = [json.loads(line) for line in lines if line.strip() and '"eval"' not in line]
    evals = [json.loads(line)["eval"] for line in lines if '"eval"' in line]
    if not steps:
        return "_RL 스텝 없음_\n"
    k = max(1, len(steps) // 4)
    chunks = [steps[i:i + k] for i in range(0, len(steps), k)]
    avg = lambda xs, key: sum(x[key] for x in xs) / len(xs)  # noqa: E731

    def opshare(ch, op):
        tot = sum(sum(x.get("ops", {}).values()) for x in ch)
        return sum(x.get("ops", {}).get(op, 0) for x in ch) / tot if tot else 0.0

    out = ("| 구간(step) | 평균 보상 | 샘플 정답률 % | 샘플 최종 보류율 % | 모델이 명시적으로 abstain한 비율 % | lookup 비율 % | diff 비율 % | KL | 그룹 분산 0 비율 % |\n"
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for ch in chunks:
        out += (f"| {ch[0]['step']}–{ch[-1]['step']} | {avg(ch, 'reward_mean'):.3f} | {pct(avg(ch, 'correct_rate'))} | {pct(avg(ch, 'abstain_rate'))} | "
                f"{pct(opshare(ch, 'abstain'))} | {pct(opshare(ch, 'lookup'))} | {pct(opshare(ch, 'diff'))} | {avg(ch, 'kl'):.4f} | {pct(avg(ch, 'frac_group_zero_std'))} |\n")
    if evals:
        out += f"\ndev verified EM(n={evals[0].get('n', '?')}): " + " → ".join(f"step {e['step']}: {pct(e['verified_em'])}%" for e in evals) + "\n"
    summ = load(EXP / run / "summary.json")
    if summ:
        last = summ.get("steps")
        why = "dev 최고가 마지막 step과 일치" if summ["best_step"] == last else "dev 최고로 선택; 마지막 step이 아님"
        out += f"\n**평가에 쓴 체크포인트: step {summ['best_step']}** ({why}). {last} step wall time {summ['wall_s'] / 60:.0f} min, CPU 4스레드.\n"
    return out


def bench_table(fname: str = "inference.json", label: str = "1차 최종 모델") -> str:
    b = load(EXP / "bench" / fname)
    if not b:
        return "_추론 벤치 산출물 없음_\n"
    m = b["meta"]
    out = (f"조건: {m['model']}({label}), 입력 {m['n_examples']}개(ko test), max_new_tokens {m['max_new_tokens']}, 워밍업 {m['warmup_rounds']}라운드 + 측정 {m['measured_rounds']}라운드, "
           f"{m['threads']} 스레드, {m['cores']} cores x86_64, torch {m['torch']}, CUDA {m['cuda']}. 정밀도마다 **별도 프로세스**에서 측정(메모리 비교를 위해). 양자화 준비 시간 {', '.join(f'{k} {v}s' for k, v in (m.get('prepare_s') or {'int8': m.get('int8_prepare_s')}).items() if k != 'fp32')}. 모델 실행 조건은 위와 같고 **양자화 범위**는 설정 이름의 `int8`(모든 Linear, lm_head 포함) 또는 `int8-<범위>`(일부)로 구분합니다.\n\n")
    out += "| 설정 | p50 ms | p95 ms | 처리량 예제/s | 모델 파일 MB | 프로세스 peak RSS GB | fp32 bs=1과 출력 문자열 일치 % |\n|---|---:|---:|---:|---:|---:|---:|\n"
    for r in b["results"]:
        out += f"| {r['config']} | {r['p50_ms']} | {r['p95_ms']} | {r['throughput_ex_per_s']} | {r.get('state_dict_mb', '–')} | {r.get('peak_rss_gb', r.get('rss_gb_after', '–'))} | {pct(r['agreement_with_fp32_bs1'])} |\n"
    return out


def pp_table(suffix: str = "", cond: str = "CPU(gloo)") -> str:
    a, b = load(EXP / "bench" / f"pp_single{suffix}.json"), load(EXP / "bench" / f"pp_2stage{suffix}.json")
    if not (a and b):
        return "_파이프라인 병렬 산출물 없음_\n"
    same = a.get("outputs") == b.get("outputs")
    out = f"조건: {cond}, n={a['n']}, bs={a['bs']}, 단일 프로세스 {a.get('params_total', 0):,} 파라미터\n\n"
    out += "| 구성 | 장치 | 스테이지 파라미터 | 처리량 예제/s | 메모리 MB | 평균 배치 지연 s |\n|---|---|---:|---:|---:|---:|\n"
    out += f"| 단일 프로세스 | {a['device']} | {a['params_total']:,} | {a['throughput_ex_per_s']} | {a['mem_mb']:.0f} | {sum(a['batch_latency_s']) / len(a['batch_latency_s']):.2f} |\n"
    for st in b["stages"]:
        out += f"| 파이프라인 rank{st['rank']} ({st['stage']}) | {st['device']} | {st['stage_params']:,} | {b['throughput_ex_per_s'] if st['rank'] == 0 else ''} | {st['mem_mb']:.0f} | {sum(st['batch_latency_s']) / len(st['batch_latency_s']):.2f} |\n"
    out += f"\n단일 프로세스와 2-스테이지의 생성 출력 일치: **{'예' if same else '아니오'}** ({len(a.get('outputs', []))}개 입력)\n"
    return out


def engine_table() -> str:
    """EXAONE LoRA served by vLLM (owner's Kaggle T4 run, files from gpu_results.tgz) next to the CPU mT5 rows, same test set, same verifier."""
    rows = [("휴리스틱 기준선 (CPU)", "heuristic_ko_test"), ("[2차] GRPO RL v3 = mT5-small 300M (CPU 4스레드, bs=1)", "rl_v3_ko_test"),
            ("EXAONE-4.0-1.2B + LoRA 300개, vLLM fp16 (Kaggle T4 1장, 동시 16요청)", "exaone_vllm_ko_test"),
            ("같은 모델, vLLM 텐서 병렬 TP=2 (Kaggle T4 2장, 동시 16요청)", "exaone_vllm_tp2_ko_test")]
    out = ""
    got = [(name, load(EXP / "eval" / f"{key}" / "metrics.json"), load(EXP / "eval" / f"{key}{V2}" / "metrics.json")) for name, key in rows]
    if not got[2][1]:
        return "_EXAONE/vLLM 산출물 없음_\n"
    out += ("| 플래너 / 모델 | n | verified EM % v1 | verified EM % v2 | raw EM % (답 있는 문항) | lookup EM % | calc EM % | 근거 셀 일치 %(최종) | 근거 셀 일치 %(모델 인용) | 보류 재현율 % v1 → v2 | 오보류율 % v1 → v2 | 파싱 실패 % | ms/예제 |\n"
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
    for name, a, b in got:
        if not a:
            continue
        m, e = a["metrics"], (b["metrics"] if b else None)

        def v2(k, e=e):
            return pct(e[k]) if e else "–"
        out += (f"| {name} | {m['n']} | **{pct(m['verified_em'])}** | **{v2('verified_em')}** | {pct(m['raw_answer_em_answerable'])} | {pct(m['lookup_em'])} | {pct(m['calc_em'])} | {pct(m['evidence_cells_exact'])} | {pct(m.get('evidence_cells_exact_raw'))} "
                f"| {pct(m['abstain_recall'])} → {v2('abstain_recall')} | {pct(m['false_abstain_rate'])} → {v2('false_abstain_rate')} | {pct(m['parse_fail_rate'])} | {m['mean_ms_per_example']:.0f} |\n")
    ev = got[2][1]["meta"]
    out += f"\nEXAONE 행의 조건: ko test {ev['n']}문항 전체 {ev['wall_s']}초(동시 16요청, 끝에서 끝까지 {ev['n'] / ev['wall_s']:.1f}문항/s), ms/예제는 동시 요청 중의 요청당 지연. v1 = 개체 일치 검사 없음, v2 = 같은 출력을 개체 일치 검사로 재검증(본 실행과 같은 토크나이저·행 예산, 출처는 `experiments/eval/PROVENANCE_exaone.md`).\n"
    bench = [(label, load(EXP / "bench" / f"engine_vllm{tag}_c{c}.json")) for label, tag in (("GPU 1장", ""), ("TP=2, GPU 2장", "_tp2")) for c in (1, 8, 32)]
    bench = [(label, b) for label, b in bench if b]
    if bench:
        out += "\n**vLLM 엔진 벤치** (`bench/engine_bench.py`, 같은 서버, ko test 앞 64문항, OpenAI 호환 API 왕복 지연)\n\n| 구성 | 동시 요청 수 | n | 총 시간 s | 처리량 요청/s | p50 ms | p95 ms | 프로그램 파싱 성공 % |\n|---|---:|---:|---:|---:|---:|---:|---:|\n"
        for label, b in bench:
            out += f"| {label} | {b['concurrency']} | {b['n']} | {b['wall_s']} | {b['throughput_req_per_s']} | {b['p50_ms']} | {b['p95_ms']} | {pct(b['parse_ok_rate'])} |\n"
    return out


def blocks() -> dict[str, str]:
    v1 = "검증기 v1: 개체 일치 검사 없음 (1차 평가와 같은 조건)"
    v2 = "검증기 v2: 개체 일치 검사 있음 (같은 모델 출력을 다시 검증)"
    return {
        "ko": eval_table("ko_test", f"한국어 표 QA — 독립 test (원본 539 + 합성 160), {v1}") + "\n" + eval_table("ko_test", f"한국어 표 QA — 독립 test, {v2}", ec=True)
        + "\n" + eval_table("ko_custom", f"한국어 표 QA — 수작업 30문항, {v1}") + "\n" + eval_table("ko_custom", f"한국어 표 QA — 수작업 30문항, {v2}", ec=True)
        + "\n" + category_table("ko_custom", "한국어 수작업 (검증기 v2)", ec=True),
        "chem": eval_table("chem_custom", f"영어 화학 문서 — 수작업 32문항 (test 분할 문서), {v1}") + "\n" + eval_table("chem_custom", f"영어 화학 — 수작업 32문항, {v2}", ec=True)
        + "\n" + eval_table("chem_syndev", f"영어 화학 — 합성 dev 80문항(템플릿, 참고용), {v1}") + "\n" + eval_table("chem_syndev", f"영어 화학 — 합성 dev 80문항, {v2}", ec=True)
        + "\n" + category_table("chem_custom", "화학 수작업 (검증기 v2)", ec=True),
        "text": eval_table("text2_test", f"본문 답변·근거 없음 — 실제 표 옆 KorQuAD 150문항(본문 100 + 근거 없음 50), {v1}") + "\n" + eval_table("text2_test", f"본문 답변·근거 없음, {v2}", ec=True),
        "training": training_table(),
        "rl": rl_table("rl_ko"),
        "rl_v1": rl_table("rl_ko_v1"),
        "rl_v3": rl_table("rl_v3"),
        "bench": bench_table(),
        "bench_r2": bench_table("inference_r2.json", "2차 최종 모델 = RL v3"),
        "bench_r2b": bench_table("inference_r2b.json", "2차 최종 모델 = RL v3, fp32 대 lm_head만 int8"),
        "pp": pp_table(),
        "pp_gpu": pp_table("_gpu", "Kaggle Tesla T4 ×2(nccl), 소유자 실행 2026-11-07, 원본 google/mt5-small"),
        "engine": engine_table(),
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


def check_blocks(blk: dict[str, str]) -> int:
    """Fail if a spliced block in README/REPORT differs from what the artifacts render to (stale or hand-edited table)."""
    bad = 0
    for p in [ROOT / "README.md", ROOT / "docs" / "REPORT.md"]:
        text = p.read_text(encoding="utf-8")
        for name, body in blk.items():
            m = re.search(rf"<!-- results:{name}:start -->\n(.*?)\n<!-- results:{name}:end -->", text, re.S)
            if m and m.group(1).strip() != body.strip():
                print(f"{p.name}: block '{name}' is out of date with experiments/ artifacts (run scripts/render_results.py)")
                bad += 1
    print(f"checked result blocks, {bad} stale")
    return 1 if bad else 0


def main() -> None:
    blk = blocks()
    if "--check" in sys.argv:
        sys.exit(check_blocks(blk))
    if "--print" in sys.argv:
        for k, v in blk.items():
            print(f"### {k}\n{v}")
        return
    for p in [ROOT / "README.md", ROOT / "docs" / "REPORT.md"]:
        if p.exists():
            print(p.name, "blocks updated:", splice(p, blk))


if __name__ == "__main__":
    main()
