"""Summarise the small CPU measurement of the tool-calling planner with a real model -> experiments/eval/tool_calling_cpu.json.

Two runs of the same untuned model on the same hand-written questions:

    tools     the model reads the table through tools it chooses and ends with submit / abstain (agent/toolcall.py)
    fewshot   the model sees the whole table and three demonstrations and writes one program line

plus, for context, the stored results of the other planners on the same questions.

    python scripts/tool_calling_summary.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_error import wilson  # noqa: E402

EVAL = ROOT / "experiments" / "eval"
RUNS = {"tools": "exaone_base_tools_cpu_ko_custom", "fewshot": "exaone_base_fewshot_cpu_ko_custom"}
REFERENCE = {"heuristic": "heuristic_ko_custom", "mt5_final": "rl_v3_ko_custom", "exaone_tuned_full": "exaone_full_vllm_ko_custom"}


def load(d: str):
    path = EVAL / d
    if not (path / "predictions.jsonl").exists():
        return None, None
    return [json.loads(line) for line in open(path / "predictions.jsonl", encoding="utf-8")], json.loads((path / "metrics.json").read_text(encoding="utf-8"))


def block(rows: list[dict]) -> dict:
    n = len(rows)
    cats = sorted({r["category"] for r in rows})
    return {"n": n, "verified_em": wilson(sum(r["verified_correct"] for r in rows), n), "withheld": wilson(sum(r["pred_abstained"] for r in rows), n),
            "wrong_answer_sent": wilson(sum((not r["pred_abstained"]) and not r["verified_correct"] for r in rows), n),
            "by_category": {c: {"k": sum(r["verified_correct"] for r in rows if r["category"] == c), "n": sum(r["category"] == c for r in rows)} for c in cats}}


def main() -> None:
    out: dict = {"runs": {}, "reference": {}}
    kept = {}
    for name, d in RUNS.items():
        rows, info = load(d)
        if rows is None:
            continue
        kept[name] = {r["qid"]: r for r in rows}
        run = {"dir": d, "model": info["meta"]["model"], "hardware": info["meta"].get("label"), "wall_s": info["meta"]["wall_s"],
               "seconds_per_question": round(info["meta"]["wall_s"] / len(rows), 1), **block(rows)}
        if name == "tools":
            t = [r["tool_calling"] for r in rows]
            run["tool_calling"] = {"model_calls_mean": round(sum(x["model_calls"] for x in t) / len(t), 2), "tool_calls_mean": round(sum(x["tool_calls"] for x in t) / len(t), 2),
                                   "tool_errors": sum(x["tool_errors"] for x in t), "finished_by": dict(Counter(x["finished_by"] for x in t)),
                                   "tools_used": dict(Counter(tool for x in t for tool in x["tools"])),
                                   "episodes_that_read_the_table": sum(bool(x["tools"]) for x in t)}
        else:
            run["few_shot"] = info["meta"].get("few_shot")
        out["runs"][name] = run
    for name, d in REFERENCE.items():
        rows, _ = load(d)
        if rows:
            out["reference"][name] = {"dir": d, **block(rows)}
    if len(kept) == 2:
        a, b = kept["fewshot"], kept["tools"]
        only_tools = sum(b[q]["verified_correct"] and not a[q]["verified_correct"] for q in a)
        only_few = sum(a[q]["verified_correct"] and not b[q]["verified_correct"] for q in a)
        n, k = only_tools + only_few, min(only_tools, only_few)
        p = 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
        out["paired_tools_vs_fewshot"] = {"n": len(a), "tools_only": only_tools, "fewshot_only": only_few, "p_two_sided": p, "p_display": "<0.001" if p < 0.001 else f"{p:.3f}"}
    (EVAL / "tool_calling_cpu.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, r in {**out["runs"], **out["reference"]}.items():
        print(f"{name:20s} n {r['n']} verified EM {r['verified_em']['rate']:.3f} withheld {r['withheld']['rate']:.3f} wrong sent {r['wrong_answer_sent']['rate']:.3f} {r['by_category']}")
    print(out.get("paired_tools_vs_fewshot"), out["runs"].get("tools", {}).get("tool_calling"))


if __name__ == "__main__":
    main()
