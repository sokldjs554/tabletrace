"""Data integrity checks used by CI and before every evaluation.

1. Every gold lookup answer equals its cell; every calc answer equals the restricted calculator;
   every text answer occurs in its passage (custom eval sets, both corpora).
2. Train / dev / test splits share no table (ko) and no document (chem).
3. Every record references an existing document / table.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

from tabletrace.schema import CellRef, Table
from tabletrace.tools.calculator import compute

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def load(p: Path) -> list[dict]:
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def check_records(recs: list[dict], docs: dict, name: str, verify_gold: bool) -> None:
    for r in recs:
        d = docs.get(r["doc_id"])
        if d is None:
            errors.append(f"{name}:{r['qid']} unknown doc {r['doc_id']}")
            continue
        tbl = next((t for t in d["tables"] if t["id"] == r["table_id"]), None)
        if tbl is None:
            errors.append(f"{name}:{r['qid']} unknown table {r['table_id']}")
            continue
        if not verify_gold:
            continue
        t = Table.model_validate(tbl)
        if r["op"] == "lookup":
            (rr, cc), = r["gold_cells"]
            if t.cell(rr, cc) != r["answer"]:
                errors.append(f"{name}:{r['qid']} lookup answer {r['answer']!r} != cell {t.cell(rr, cc)!r}")
        elif r["op"] in ("diff", "sum", "avg", "ratio", "pct_change"):
            try:
                c = compute(t, r["op"], [CellRef(table_id=t.id, row=a, col=b) for a, b in r["gold_cells"]])
            except Exception as e:
                errors.append(f"{name}:{r['qid']} calc error {e}")
                continue
            if c.formatted != r["answer"]:
                errors.append(f"{name}:{r['qid']} calc answer {r['answer']!r} != {c.formatted!r}")
        elif r["op"] == "text":
            pid = r.get("context_passage")
            texts = [p["text"] for p in d["passages"] if (pid is None or p["id"] == pid)]
            if not any(r["answer"] in x for x in texts):
                errors.append(f"{name}:{r['qid']} text answer {r['answer']!r} not in passage")
        elif r["op"] != "abstain":
            errors.append(f"{name}:{r['qid']} unknown op {r['op']}")


def main() -> int:
    ko_docs = {d["id"]: d for d in load(ROOT / "data/ko/documents.jsonl")}
    chem_docs = {d["id"]: d for d in load(ROOT / "data/chem/documents.jsonl")}
    ko = {s: load(ROOT / f"data/ko/{s}.jsonl") for s in ("train", "dev", "test")}
    for s, recs in ko.items():
        check_records(recs, ko_docs, f"ko/{s}", verify_gold=True)
    for s in ("train", "dev", "test"):
        check_records(load(ROOT / f"data/ko/synthetic_{s}.jsonl"), ko_docs, f"ko/synthetic_{s}", verify_gold=True)
    check_records(load(ROOT / "data/ko/custom_eval.jsonl"), ko_docs, "ko/custom", verify_gold=True)
    tabs = {s: {r["table_id"] for r in recs} for s, recs in ko.items()}
    for a in tabs:
        for b in tabs:
            if a < b and tabs[a] & tabs[b]:
                errors.append(f"ko split leak {a}&{b}: {len(tabs[a] & tabs[b])} shared tables")
    # the extra training pool: gold cells hold the answers, and nothing in it touches a dev or test table
    pool_docs = {d["id"]: d for d in load(ROOT / "data/ko/pool_documents.jsonl.gz")}
    pool = load(ROOT / "data/ko/pool_train.jsonl.gz")
    check_records(pool, {**ko_docs, **pool_docs}, "ko/pool", verify_gold=True)
    held = tabs["dev"] | tabs["test"]
    if any(r["table_id"] in held for r in pool) or any(t["id"] in held for d in pool_docs.values() for t in d["tables"]):
        errors.append("ko/pool contains a dev or test table")
    if set(pool_docs) & set(ko_docs):
        errors.append("ko/pool documents repeat documents of the main split")
    main_qids = {r["qid"] for recs in ko.values() for r in recs}
    if any(r["qid"] in main_qids for r in pool):
        errors.append("ko/pool repeats a question of the main split")
    # two-turn dialogs: built on test tables only, and the follow-up's gold cell holds its answer
    dialogs = load(ROOT / "data/ko/dialog_eval.jsonl")
    for d in dialogs:
        tbl = next(t for t in ko_docs[d["doc_id"]]["tables"] if t["id"] == d["table_id"])
        (rr, cc), = d["gold_cells"]
        if d["table_id"] not in tabs["test"] or Table.model_validate(tbl).cell(rr, cc) != d["answer"]:
            errors.append(f"ko/dialog:{d['id']} is not a test table or its gold cell does not hold the answer")
    split = json.load(open(ROOT / "data/chem/split.json"))
    for a in split:
        for b in split:
            if a < b and set(split[a]) & set(split[b]):
                errors.append(f"chem split leak {a}&{b}")
    for s in ("train", "dev"):
        recs = load(ROOT / f"data/chem/synthetic_{s}.jsonl")
        check_records(recs, chem_docs, f"chem/synthetic_{s}", verify_gold=True)
        bad = [r["qid"] for r in recs if r["doc_id"] not in split[s]]
        if bad:
            errors.append(f"chem/synthetic_{s}: {len(bad)} records from other splits")
    custom = load(ROOT / "data/chem/custom_eval.jsonl")
    check_records(custom, chem_docs, "chem/custom", verify_gold=True)
    bad = [r["qid"] for r in custom if r["doc_id"] not in split["test"]]
    if bad:
        errors.append(f"chem/custom: records outside the test split: {bad}")
    summary = {"ko": {s: len(v) for s, v in ko.items()}, "ko_custom": len(load(ROOT / "data/ko/custom_eval.jsonl")),
               "ko_pool": {"tables": len(pool_docs), "questions": len(pool)}, "ko_dialogs": len(dialogs),
               "chem_split": {k: len(v) for k, v in split.items()}, "chem_custom": len(custom), "errors": len(errors)}
    print(json.dumps(summary, ensure_ascii=False))
    for e in errors[:50]:
        print("ERROR", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
