"""Helper for the owner's review of the chemistry evaluation questions (docs/rewrite/11_chem_eval_review.md).

The 94 hand-made chemistry questions were written by the AI coding tool and nobody has checked them:
  papers    data/chem_papers/custom_eval.jsonl   62 questions on 20 tables from 12 arXiv papers
  textbook  data/chem/custom_eval.jsonl          32 questions on OpenStax Chemistry 2e tables
The owner gives one verdict per question in a review file next to each set. This script only shows the questions and
checks the review files. It gives no verdict.

  python scripts/chem_review_tool.py review papers | less     # every question next to its table, gold cells between >> <<
  python scripts/chem_review_tool.py review textbook | less
  python scripts/chem_review_tool.py template papers          # the review file with every verdict left blank
  python scripts/chem_review_tool.py template textbook
  python scripts/chem_review_tool.py check                    # validate the review files that exist
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from owner_eval_tool import VERDICTS, load, render  # noqa: E402
from tabletrace.schema import Table  # noqa: E402

SETS = {
    "papers": {"questions": ROOT / "data/chem_papers/custom_eval.jsonl", "corpus": ROOT / "data/chem_papers/documents.jsonl",
               "review": ROOT / "data/chem_papers/custom_eval_review.jsonl"},
    "textbook": {"questions": ROOT / "data/chem/custom_eval.jsonl", "corpus": ROOT / "data/chem/documents.jsonl",
                 "review": ROOT / "data/chem/custom_eval_review.jsonl"},
}


def tables(corpus: Path) -> dict[str, tuple[dict, Table]]:
    out = {}
    for d in load(corpus):
        for t in d["tables"]:
            out[t["id"]] = (d, Table.model_validate(t))
    return out


def cmd_review(name: str) -> None:
    s = SETS[name]
    tabs = tables(s["corpus"])
    for r in load(s["questions"]):
        d, t = tabs[r["table_id"]]
        print("=" * 100)
        print(f"{r['qid']} | category {r['category']} | op {r['op']} | table {t.id}")
        print(f"source: {t.title}" + (f" ({t.source_url})" if t.source_url else ""))
        if t.caption:
            print("caption:", t.caption)
        print("question:", r["question"])
        print("answer:", r["answer"], "| other forms:", r.get("alt_answers"), "| unit:", r.get("unit"), "| reason:", r.get("reason"))
        if r["gold_cells"]:
            print("gold cells:", [(f"r{x}c{y}", t.cell(x, y)) for x, y in r["gold_cells"]])
        print(render(t, {(x, y) for x, y in r["gold_cells"]}))
        if r["op"] == "text" or r.get("needs_text"):
            for p in d.get("passages") or []:
                print(f"[passage {p['id']}] {p['text'][:900]}")


def cmd_template(name: str) -> int:
    """One line per question with the verdict left empty. An empty verdict does not pass the check, so nothing counts as
    reviewed before it was looked at."""
    s = SETS[name]
    if s["review"].exists():
        print(f"이미 있습니다: {s['review'].relative_to(ROOT)} (덮어쓰지 않습니다. 새로 만들려면 그 파일을 지우고 다시 실행하세요.)")
        return 1
    lines = [json.dumps({"qid": r["qid"], "verdict": "", "comment": ""}, ensure_ascii=False) for r in load(s["questions"])]
    s["review"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"만들었습니다: {s['review'].relative_to(ROOT)} ({len(lines)}줄). 줄마다 verdict에 ok, fix, drop 가운데 하나를 적으세요. "
          "fix와 drop에는 comment에 까닭을 적습니다.")
    return 0


def check_review(name: str, rows: list[dict]) -> list[str]:
    qids = [r["qid"] for r in load(SETS[name]["questions"])]
    errs = []
    seen = set()
    for n, r in enumerate(rows, start=1):
        q = r.get("qid")
        if q not in qids:
            errs.append(f"{name} 줄 {n}: 없는 문항 번호 {q!r}")
        if q in seen:
            errs.append(f"{name} 줄 {n}: {q} 가 두 번 나옵니다")
        seen.add(q)
        if set(r) - {"qid", "verdict", "comment"}:
            errs.append(f"{name} 줄 {n}: 모르는 칸 {sorted(set(r) - {'qid', 'verdict', 'comment'})}")
        if r.get("verdict") not in VERDICTS:
            errs.append(f"{name} 줄 {n} ({q}): verdict는 {', '.join(VERDICTS)} 가운데 하나여야 합니다 (지금 {r.get('verdict')!r})")
        elif r["verdict"] != "ok" and not str(r.get("comment", "")).strip():
            errs.append(f"{name} 줄 {n} ({q}): {r['verdict']}이면 comment에 까닭을 적습니다")
    missing = [q for q in qids if q not in seen]
    if missing:
        errs.append(f"{name}: 판정이 없는 문항 {len(missing)}개, 예: {missing[:5]}")
    return errs


def cmd_check() -> int:
    errs, done = [], []
    for name, s in SETS.items():
        if not s["review"].exists():
            print(f"{name}: 검수 파일이 아직 없습니다 ({s['review'].relative_to(ROOT)})")
            continue
        try:
            rows = load(s["review"])
        except json.JSONDecodeError as e:
            errs.append(f"{name}: JSON으로 읽히지 않는 줄이 있습니다 ({e})")
            continue
        e = check_review(name, rows)
        errs += e
        if not e:
            counts = {v: sum(r["verdict"] == v for r in rows) for v in VERDICTS}
            done.append(name)
            print(f"{name}: {len(rows)}문항 검수 끝. " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    for e in errs:
        print("문제:", e)
    return 1 if errs else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("review", "template"):
        p = sub.add_parser(c)
        p.add_argument("set", choices=sorted(SETS))
    sub.add_parser("check")
    a = ap.parse_args()
    if a.cmd == "review":
        cmd_review(a.set)
        return 0
    if a.cmd == "template":
        return cmd_template(a.set)
    return cmd_check()


if __name__ == "__main__":
    sys.exit(main())
