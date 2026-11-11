"""Risk-coverage curves from the model's own confidence, with and without the verifier.

    python -m tabletrace.eval.run --planner neural --model experiments/rl_v3/model --confidence ... --out experiments/eval/rl_v3_conf_ko_test
    python scripts/risk_coverage.py rl_v3_conf_ko_test [more runs]        # -> experiments/eval/risk_coverage.json

A run made with `--confidence` stores, for every question, the log-probabilities of the tokens the model generated.
This script asks what an answer threshold on that confidence buys:

    coverage   answers sent / all questions
    risk       wrong answers / answers sent        (an answer to a question that has no answer is wrong)

for two systems that share the same model output:

    model      send the model's answer text unless it wrote `op: abstain` or no program at all
    verifier   send what the verifier accepted (the pipeline of this project)

Each system gives one operating point without a threshold. Raising the threshold moves along its curve to lower
coverage. The summary reports the area under the curve (lower is better), the risk at fixed coverages and the largest
coverage that keeps the risk under 5% and 10%.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_error import wilson  # noqa: E402

SIGNALS = ("mean_logprob", "min_logprob", "sum_logprob")
COVERAGES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def sent_and_right(row: dict, system: str) -> tuple[bool, bool]:
    """-> (an answer goes out, that answer is right)."""
    if system == "verifier":
        sent = row["pred_status"] == "answered"
        return sent, sent and row["gold_status"] == "answered" and row["verified_correct"]
    sent = not row["parse_fail"] and row["pred_op"] != "abstain"
    return sent, sent and row["raw_correct"]


def curve(rows: list[dict], system: str, signal: str) -> dict:
    n = len(rows)
    items = []
    for r in rows:
        sent, right = sent_and_right(r, system)
        if sent:
            items.append((r["confidence"][signal], right))
    items.sort(key=lambda x: -x[0])
    points, wrong = [], 0
    for k, (conf, right) in enumerate(items, start=1):
        wrong += not right
        points.append({"coverage": k / n, "risk": wrong / k, "threshold": conf})
    full = {"coverage": len(items) / n, "risk": wrong / max(1, len(items)), "answers": len(items), "wrong": wrong}
    # area under risk(coverage) over the coverage the system can reach, by the rectangle rule (one step per answer)
    aurc = sum(p["risk"] for p in points) / max(1, len(points))

    def risk_at(c: float) -> float | None:
        k = round(c * n)
        return round(points[k - 1]["risk"], 4) if 1 <= k <= len(points) else None

    def coverage_under(limit: float) -> dict:
        best = None
        for k, p in enumerate(points, start=1):
            if p["risk"] <= limit and k >= 20:                 # fewer than 20 answers is not an operating point
                best = {"coverage": round(p["coverage"], 4), "risk": round(p["risk"], 4), "answers": k, "threshold": round(p["threshold"], 4)}
        return best or {"coverage": 0.0, "risk": None, "answers": 0, "threshold": None}

    # does the confidence separate right answers from wrong ones? (probability that a right answer outranks a wrong one)
    pos = [c for c, right in items if right]
    neg = [c for c, right in items if not right]
    auroc = None
    if pos and neg:
        ranked = sorted(items, key=lambda x: x[0])
        rank_sum, i = 0.0, 0
        while i < len(ranked):
            j = i
            while j < len(ranked) and ranked[j][0] == ranked[i][0]:
                j += 1
            rank_sum += sum((i + j + 1) / 2 for t in range(i, j) if ranked[t][1])     # average rank for ties
            i = j
        auroc = round((rank_sum - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)), 4)
    return {"system": system, "signal": signal, "no_threshold": {**full, "coverage": round(full["coverage"], 4), "risk": round(full["risk"], 4),
                                                                "risk_ci": wilson(wrong, max(1, len(items)))},
            "aurc": round(aurc, 4), "auroc_right_vs_wrong": auroc, "risk_at_coverage": {str(c): risk_at(c) for c in COVERAGES},
            "max_coverage_with_risk_under": {"0.05": coverage_under(0.05), "0.10": coverage_under(0.10)}}


def one_run(name: str, same_outputs_as: str | None) -> dict:
    rows = [json.loads(line) for line in open(ROOT / "experiments" / "eval" / name / "predictions.jsonl", encoding="utf-8")]
    scored = [r for r in rows if r.get("confidence")]
    out: dict = {"run": name, "questions": len(rows), "with_confidence": len(scored),
                 "unanswerable": sum(r["gold_status"] != "answered" for r in rows)}
    if same_outputs_as:
        ref = {json.loads(line)["qid"]: json.loads(line)["raw_output"] for line in open(ROOT / "experiments" / "eval" / same_outputs_as / "predictions.jsonl", encoding="utf-8")}
        out["same_outputs_as"] = {"run": same_outputs_as, "identical": sum(ref.get(r["qid"]) == r["raw_output"] for r in rows), "of": len(rows)}
    if len(scored) != len(rows):
        out["note"] = "questions without a confidence (no tokens returned) are treated as the least confident"
        for r in rows:
            r.setdefault("confidence", None)
            if not r["confidence"]:
                r["confidence"] = {s: float("-inf") for s in SIGNALS}
    out["curves"] = {f"{system}/{signal}": curve(rows, system, signal) for system in ("model", "verifier") for signal in SIGNALS}
    best = min(SIGNALS, key=lambda s: out["curves"][f"verifier/{s}"]["aurc"])
    out["best_signal_for_verifier"] = best
    # the question the table answers: at the verifier's own coverage, what would the model alone risk?
    v = out["curves"][f"verifier/{best}"]["no_threshold"]
    m_rows = sorted(((r["confidence"][best], sent_and_right(r, "model")[1]) for r in rows if sent_and_right(r, "model")[0]), key=lambda x: -x[0])
    k = min(len(m_rows), v["answers"])
    out["model_at_verifier_coverage"] = {"answers": k, "risk": round(sum(not right for _, right in m_rows[:k]) / max(1, k), 4), "signal": best}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="eval directories under experiments/eval made with --confidence; `name=other` also checks that the raw outputs equal those of `other`")
    a = ap.parse_args()
    dest = ROOT / "experiments" / "eval" / "risk_coverage.json"
    result = json.loads(dest.read_text(encoding="utf-8")) if dest.exists() else {"runs": {}}
    for spec in a.runs:
        name, _, same = spec.partition("=")
        result["runs"][name] = one_run(name, same or None)
        r = result["runs"][name]
        print(name, {k: (c["no_threshold"]["coverage"], c["no_threshold"]["risk"], c["aurc"], c["auroc_right_vs_wrong"]) for k, c in r["curves"].items()})
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
