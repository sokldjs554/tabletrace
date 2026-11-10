"""Does a model score higher on questions about tables it saw in training?  (reads stored predictions)

Inputs are the two probe sets from scripts/data/build_leak_probe.py, evaluated with the ordinary runner:
  experiments/eval/<planner>_leak_seen     questions about train tables that were not used for training
  experiments/eval/<planner>_leak_unseen   questions chosen the same way about tables never trained on

For every planner it reports accuracy on both sets (Wilson 95% intervals) and the difference seen - unseen with
a 95% interval from a bootstrap that resamples TABLES (questions about one table are not independent).
The heuristic planner has no training, so its difference estimates how much the two sets differ in difficulty;
`minus_heuristic` subtracts it from each trained planner's difference.

  python scripts/leak_effect.py            # writes experiments/eval/leak_effect.json
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence_error import wilson  # noqa: E402

EVAL = ROOT / "experiments" / "eval"
DATA = ROOT / "data" / "ko"
REPS, SEED = 10000, 13
MEASURES = {"verified_em": "verified_correct", "raw_answer_em": "raw_correct", "cited_cell_exact": "cells_exact_raw"}


def load(planner: str, group: str) -> dict[str, list[dict]] | None:
    path = EVAL / f"{planner}_leak_{group}" / "predictions.jsonl"
    if not path.exists():
        return None
    table_of = {}
    with open(DATA / f"leak_probe_{group}.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            table_of[r["qid"]] = r["table_id"]
    by_table: dict[str, list[dict]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            by_table.setdefault(table_of[r["qid"]], []).append(r)
    return by_table


def mean_of(tables: list[list[dict]], key: str) -> float:
    k = sum(1 for t in tables for r in t if r[key])
    return k / sum(len(t) for t in tables)


def bootstrap_diff(seen: list[list[dict]], unseen: list[list[dict]], key: str) -> tuple[float, float]:
    rnd = random.Random(SEED)
    # per-table (correct, total) so a resample is two sums
    s = [(sum(1 for r in t if r[key]), len(t)) for t in seen]
    u = [(sum(1 for r in t if r[key]), len(t)) for t in unseen]
    diffs = []
    for _ in range(REPS):
        a = rnd.choices(s, k=len(s))
        b = rnd.choices(u, k=len(u))
        diffs.append(sum(x for x, _ in a) / sum(n for _, n in a) - sum(x for x, _ in b) / sum(n for _, n in b))
    diffs.sort()
    return diffs[int(0.025 * REPS)], diffs[int(0.975 * REPS) - 1]


def main() -> None:
    planners = sorted({p.name[: -len("_leak_seen")] for p in EVAL.glob("*_leak_seen")})
    out: dict = {"bootstrap": {"unit": "table", "reps": REPS, "seed": SEED}, "planners": {}}
    for planner in planners:
        seen, unseen = load(planner, "seen"), load(planner, "unseen")
        if not seen or not unseen:
            continue
        st, ut = list(seen.values()), list(unseen.values())
        res = {"seen": {"questions": sum(map(len, st)), "tables": len(st)}, "unseen": {"questions": sum(map(len, ut)), "tables": len(ut)}}
        for name, key in MEASURES.items():
            ks, ku = sum(1 for t in st for r in t if r[key]), sum(1 for t in ut for r in t if r[key])
            lo, hi = bootstrap_diff(st, ut, key)
            diff = mean_of(st, key) - mean_of(ut, key)
            res[name] = {"seen": wilson(ks, res["seen"]["questions"]), "unseen": wilson(ku, res["unseen"]["questions"]),
                         "diff": round(diff, 4), "diff_lo": round(lo, 4), "diff_hi": round(hi, 4),
                         "diff_excludes_zero": bool(lo > 0 or hi < 0)}
        out["planners"][planner] = res
    base = out["planners"].get("heuristic")
    if base:
        for planner, res in out["planners"].items():
            if planner != "heuristic":
                res["minus_heuristic"] = {m: round(res[m]["diff"] - base[m]["diff"], 4) for m in ("verified_em", "raw_answer_em")}
    dest = EVAL / "leak_effect.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for planner, res in out["planners"].items():
        for m in MEASURES:
            r = res[m]
            print(f"{planner:10s} {m:17s} seen {r['seen']['rate']:.4f} unseen {r['unseen']['rate']:.4f} diff {r['diff']:+.4f} [{r['diff_lo']:+.4f}, {r['diff_hi']:+.4f}]")
    print("->", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
