"""What the owner's review of the chemistry questions does to the stored chemistry results (docs/rewrite/11_chem_eval_review.md).

The questions are not changed: stored results are tied to them. A question the owner marks `fix` or `drop` is set aside
here, and every stored run on the two reviewed sets is counted again without those questions. Written down before the
review (this file's first commit), the five comparisons the documents rest on:

  1. the paper-table headline: the model tuned on Korean and chemistry, 46 of 62
  2. on the paper tables, Korean-only tuning against Korean + chemistry (7 to 3, not significant)
  3. on the paper tables, the Korean-only model against the untuned model (30 to 3) and against the baseline (24 to 9)
  4. on the textbook questions, Korean + chemistry against Korean-only (5 to 0, p 0.062)
  5. the unanswerable chemistry questions of the three sets, the repeat run against Korean-only (10 to 0, p 0.002);
     the 16 synthetic ones were not reviewed and stay
For each: the counts with and without the set-aside questions, and whether the conclusion (direction, and significant at
0.05 or not) stays the same.

  python scripts/chem_review_analysis.py      # needs both review files complete -> experiments/eval/chem_review_analysis.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chem_rerun_analysis as cr  # noqa: E402
import chem_review_tool as tool  # noqa: E402
import rl2_analysis as rl2  # noqa: E402

EVAL = ROOT / "experiments" / "eval"
SET_OF = {"papers": "chem_papers", "textbook": "chem_custom"}
KOCHEM, REPEAT, KO_ONLY, UNTUNED, BASELINE = "exaone_kochem2_vllm", "exaone_kochem3_vllm", "exaone_koonly_vllm", "ref_1p2b", "heuristic"


def without(rows: dict, flagged: set[str]) -> dict:
    return {q: r for q, r in rows.items() if q.split("/")[-1] not in flagged}


def compare(a: dict, b: dict, flagged: set[str]) -> dict:
    """b against a on all questions and without the set-aside ones."""
    full, kept = cr.paired(a, b), cr.paired(without(a, flagged), without(b, flagged))

    def verdict(p: dict) -> tuple[int, bool]:
        d = (p["only_candidate"] > p["only_reference"]) - (p["only_candidate"] < p["only_reference"])
        return d, p["p_two_sided"] < 0.05
    return {"all": full, "without_set_aside": kept, "questions_set_aside": len(a) - len(without(a, flagged)),
            "same_conclusion": verdict(full) == verdict(kept)}


def count(rows: dict, flagged: set[str]) -> dict:
    kept = without(rows, flagged)
    return {"all": cr.right(rows), "without_set_aside": cr.right(kept) if kept else None,
            "rate_change": round(cr.right(kept)["rate"] - cr.right(rows)["rate"], 4) if kept else None}


def analyse(flagged: set[str]) -> dict:
    load = rl2.load
    out: dict = {"set_aside": sorted(flagged), "runs": {}, "checks": {}}
    for d in sorted(EVAL.iterdir()):
        if d.is_dir() and (d.name.endswith("_chem_papers") or d.name.endswith("_chem_custom")) and (d / "predictions.jsonl").exists():
            out["runs"][d.name] = count(load(d.name), flagged)
    papers = {k: load(f"{k}_chem_papers") for k in (KOCHEM, KO_ONLY, UNTUNED, BASELINE)}
    text = {k: load(f"{k}_chem_custom") for k in (KOCHEM, KO_ONLY)}
    out["checks"]["1_paper_headline"] = count(papers[KOCHEM], flagged)
    out["checks"]["2_papers_korean_only_vs_chemistry"] = compare(papers[KO_ONLY], papers[KOCHEM], flagged)
    out["checks"]["3_papers_untuned_vs_korean_only"] = compare(papers[UNTUNED], papers[KO_ONLY], flagged)
    out["checks"]["3_papers_baseline_vs_korean_only"] = compare(papers[BASELINE], papers[KO_ONLY], flagged)
    out["checks"]["4_textbook_korean_only_vs_chemistry"] = compare(text[KO_ONLY], text[KOCHEM], flagged)
    un = lambda r: cr.kind(r) == "unanswerable"      # noqa: E731
    every = {k: {} for k in (REPEAT, KO_ONLY)}
    for s in cr.CHEM_SETS:
        for k in every:
            every[k].update({f"{s}/{q}": r for q, r in load(f"{k}_{s}").items() if un(r)})
    out["checks"]["5_unanswerable_repeat_vs_korean_only"] = compare(every[KO_ONLY], every[REPEAT], flagged)
    # does the order of any two runs on the paper tables change?
    names = [n for n in out["runs"] if n.endswith("_chem_papers")]
    rev = 0
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            x, y = out["runs"][a], out["runs"][b]
            if x["without_set_aside"] and y["without_set_aside"]:
                before = x["all"]["rate"] - y["all"]["rate"]
                after = x["without_set_aside"]["rate"] - y["without_set_aside"]["rate"]
                rev += before * after < 0
    out["n_runs"] = len(out["runs"])
    out["paper_runs_whose_order_reverses"] = rev
    out["every_conclusion_same"] = all(c["same_conclusion"] for k, c in out["checks"].items() if "same_conclusion" in c)
    return out


def main() -> int:
    flagged, review = set(), {}
    for name, s in tool.SETS.items():
        if not s["review"].exists():
            sys.exit(f"{name}: 검수 파일이 없습니다. python scripts/chem_review_tool.py template {name}")
        rows = tool.load(s["review"])
        errs = tool.check_review(name, rows)
        if errs:
            sys.exit("검수 파일에 문제가 있습니다:\n" + "\n".join(errs))
        review[SET_OF[name]] = {v: [r["qid"] for r in rows if r["verdict"] == v] for v in tool.VERDICTS}
        flagged |= {r["qid"] for r in rows if r["verdict"] != "ok"}
    counts = {s: {v: len(q) for v, q in verdicts.items()} | {"questions": sum(len(q) for q in verdicts.values())} for s, verdicts in review.items()}
    counts["both_sets"] = {k: sum(c[k] for c in counts.values()) for k in ("questions", *tool.VERDICTS)}
    counts["both_sets"]["set_aside"] = len(flagged)
    out = {"review": review, "counts": counts, **analyse(flagged)}
    dest = EVAL / "chem_review_analysis.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for k, c in out["checks"].items():
        if "same_conclusion" in c:
            print(k, c["all"]["only_candidate"], "to", c["all"]["only_reference"], "->", c["without_set_aside"]["only_candidate"], "to",
                  c["without_set_aside"]["only_reference"], f"(p {c['without_set_aside']['p_display']})", "same" if c["same_conclusion"] else "CHANGED")
        else:
            print(k, c["all"]["correct"], "of", c["all"]["n"], "->", c["without_set_aside"]["correct"], "of", c["without_set_aside"]["n"])
    print("paper runs whose order reverses:", out["paper_runs_whose_order_reverses"], "| every conclusion the same:", out["every_conclusion_same"])
    print("wrote", dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
