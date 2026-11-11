"""One summary of the table-encoder experiments -> experiments/encoder/summary.json.

    variants      test / dev accuracy of every finished run under experiments/encoder/
    paired        exact two-sided sign tests on the 539 test questions (which run alone picked the gold cell)
    generative    on the same questions, how often the generative planners cited the gold cell (before the verifier
                  touched anything) and how often the verified pipeline ended on it
    pretraining   corrupt-cell detection before and after pretraining, on held-out tables

    python scripts/encoder_summary.py
"""
from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_error import wilson  # noqa: E402

ENC = ROOT / "experiments" / "encoder"
# `structure` uses the encoder half of mT5-small (the model the generative planner is built on); the ko_* runs use KoELECTRA-small
VARIANTS = ["structure", "ko_plain", "ko_structure", "ko_structure_pt", "ko_structure_pool"]
PAIRS = [("structure_vs_plain", "ko_plain", "ko_structure"), ("pretraining_vs_none", "ko_structure", "ko_structure_pt"),
         ("pool_vs_main", "ko_structure", "ko_structure_pool"), ("koelectra_vs_mt5", "structure", "ko_structure")]
GENERATIVE = [("heuristic", "heuristic_ko_test"), ("mt5_final", "rl_v3_ko_test"), ("exaone_300", "exaone_vllm_ko_test"), ("exaone_300_colid", "exaone_colid_vllm_ko_test"),
              ("exaone_full", "exaone_full_vllm_ko_test"), ("exaone_full_run2", "exaone_full_vllm_ko_test_run2")]


def sign_test(a_only: int, b_only: int) -> float:
    n, k = a_only + b_only, min(a_only, b_only)
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def preds(name: str) -> dict[str, dict] | None:
    f = ENC / name / "test_predictions.jsonl"
    return {json.loads(line)["qid"]: json.loads(line) for line in open(f, encoding="utf-8")} if f.exists() else None


def main() -> None:
    out: dict = {"variants": {}, "paired": {}, "generative": {}, "pretraining": None}
    for name in VARIANTS:
        f = ENC / name / "metrics.json"
        if f.exists():
            m = json.loads(f.read_text(encoding="utf-8"))
            out["variants"][name] = {k: m[k] for k in ("structure_embeddings", "init", "train_set", "pool_n", "train_questions", "epochs", "steps", "minutes", "trainable_parameters",
                                                       "row_embedding_norm", "col_embedding_norm", "backbone", "dev_by_epoch", "dev", "test") if k in m}
    for key, ref, cand in PAIRS:
        a, b = preds(ref), preds(cand)
        if a and b:
            only_a = sum(a[q]["cell"] and not b[q]["cell"] for q in a)
            only_b = sum(b[q]["cell"] and not a[q]["cell"] for q in a)
            p = sign_test(only_a, only_b)
            out["paired"][key] = {"reference": ref, "candidate": cand, "n": len(a), "candidate_only": only_b, "reference_only": only_a, "both": sum(a[q]["cell"] and b[q]["cell"] for q in a),
                                  "p_two_sided": p, "p_display": "<0.001" if p < 0.001 else f"{p:.3f}",
                                  "difference": round((only_b - only_a) / len(a), 4)}
    qids = set(next(iter(p for p in map(preds, VARIANTS) if p), {}))
    for key, run in GENERATIVE:
        f = ROOT / "experiments" / "eval" / run / "predictions.jsonl"
        if f.exists() and qids:
            rows = [r for r in map(json.loads, open(f, encoding="utf-8")) if r["qid"] in qids]
            n = len(rows)
            out["generative"][key] = {"run": run, "n": n, "cited_gold_cell": wilson(sum(r["cells_exact_raw"] for r in rows), n),
                                      "verified_on_gold_cell": wilson(sum(r["cells_exact"] and r["pred_status"] == "answered" for r in rows), n),
                                      "verified_em": wilson(sum(r["verified_correct"] for r in rows), n)}
    f = ENC / "ko_pretrain" / "metrics.json"
    if f.exists():
        m = json.loads(f.read_text(encoding="utf-8"))
        out["pretraining"] = {k: m[k] for k in ("objective", "backbone", "tables", "probe_tables", "steps", "batch", "rate", "minutes", "probe_before", "probe_after")}
    (ENC / "summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, v in out["variants"].items():
        t = v["test"]
        print(f"{name:16s} train {v['train_questions']:6d} steps {v['steps']:4d} test cell {t['cell']['rate']:.3f} ({t['cell']['lo']:.3f}-{t['cell']['hi']:.3f}) row {t['row']['rate']:.3f} col {t['col']['rate']:.3f}")
    for key, v in out["paired"].items():
        print(f"{key:22s} {v['candidate']} only {v['candidate_only']} / {v['reference']} only {v['reference_only']} p {v['p_display']}")
    for key, v in out["generative"].items():
        print(f"{key:18s} cited gold {v['cited_gold_cell']['rate']:.3f} verified on gold {v['verified_on_gold_cell']['rate']:.3f}")
    if out["pretraining"]:
        print("pretraining", out["pretraining"]["probe_before"], "->", out["pretraining"]["probe_after"])


if __name__ == "__main__":
    main()
