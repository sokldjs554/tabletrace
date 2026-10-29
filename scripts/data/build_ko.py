"""Build the Korean table-QA corpus and table-disjoint splits from KorWikiTQ.

Input : data/raw/korwikitq/KorWikiTQ_ko_{train,dev}.json  (LG AI Research, CC BY-SA 4.0)
Output: data/ko/documents.jsonl            every kept table as a Document (title+description passage)
        data/ko/{train,dev,test}.jsonl     QA records with gold cell(s); splits share NO table
        data/ko/build_report.json          counts and exclusion reasons

Why our own split: the official train/dev share 1,755 table URLs (docs/research/datasets.md),
so a model could memorise table content. We re-split by table identity (URL + content hash).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "korwikitq"
OUT = ROOT / "data" / "ko"

MAX_ROWS, MAX_COLS, MAX_CHARS = 16, 7, 900


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def table_key(ex: dict) -> str:
    h = hashlib.sha1(json.dumps(ex["TBL"], ensure_ascii=False).encode()).hexdigest()[:12]
    return f"{ex['U']}#{h}"


def split_title(t: str) -> tuple[str, str]:
    """KorWikiTQ 'T' holds the title and (sometimes) the article description separated by spaces."""
    t = t.strip()
    m = re.match(r"^(.{2,60}?)\s{2,}(.+)$", t)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return t, ""


def gold_cell(ex: dict) -> tuple[int, int] | None:
    tbl, ans = ex["TBL"], ex["QAS"]["answer"]
    rows = tbl[1:]
    hits = [(r, c) for r, row in enumerate(rows) for c, v in enumerate(row) if norm(v) == norm(ans)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return None
    # several identical cells: prefer the row sharing most question tokens (excluding the answer cell)
    q = norm(ex["QAS"]["question"])
    best, best_s = None, -1
    for r, c in hits:
        s = sum(1 for cc, v in enumerate(rows[r]) if cc != c and len(norm(v)) > 1 and norm(v) in q)
        if s > best_s:
            best, best_s = (r, c), s
        elif s == best_s:
            best = None  # tie -> ambiguous
    return best if best_s > 0 else None


def make_units(header: list[str]) -> dict[int, str]:
    from tabletrace.tools.numbers import header_unit

    return {i: u for i, h in enumerate(header) if (u := header_unit(h))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--train-tables", type=int, default=900)
    ap.add_argument("--dev-tables", type=int, default=60)
    ap.add_argument("--test-tables", type=int, default=180)
    ap.add_argument("--max-q-per-table", type=int, default=3)
    a = ap.parse_args()
    rnd = random.Random(a.seed)

    examples = []
    for split in ("train", "dev"):
        d = json.load(open(RAW / f"KorWikiTQ_ko_{split}.json", encoding="utf-8"))["data"]
        for ex in d:
            ex["_orig_split"] = split
            examples.append(ex)
    excluded: Counter = Counter()
    report: dict = {"input_examples": len(examples)}

    by_table: dict[str, list[dict]] = defaultdict(list)
    for ex in examples:
        tbl = ex["TBL"]
        if not tbl or len(tbl) < 3 or len(tbl[0]) < 2:
            excluded["table_too_small"] += 1
            continue
        header, rows = tbl[0], tbl[1:]
        if any(len(r) != len(header) for r in rows):
            excluded["ragged_rows"] += 1
            continue
        if len(rows) > MAX_ROWS or len(header) > MAX_COLS:
            excluded["table_too_large"] += 1
            continue
        if sum(len(c) for r in tbl for c in r) > MAX_CHARS:
            excluded["table_too_long"] += 1
            continue
        if any(not h.strip() for h in header):
            excluded["empty_header"] += 1
            continue
        g = gold_cell(ex)
        if g is None:
            excluded["answer_not_unique_cell"] += 1
            continue
        ex["_gold"] = g
        by_table[table_key(ex)].append(ex)
    report["excluded"] = dict(excluded)
    report["tables_after_filter"] = len(by_table)

    keys = sorted(by_table)
    rnd.shuffle(keys)
    need = a.train_tables + a.dev_tables + a.test_tables
    if len(keys) < need:
        raise SystemExit(f"only {len(keys)} tables after filtering, need {need}")
    assignment = {}
    for k in keys[: a.test_tables]:
        assignment[k] = "test"
    for k in keys[a.test_tables: a.test_tables + a.dev_tables]:
        assignment[k] = "dev"
    for k in keys[a.test_tables + a.dev_tables: need]:
        assignment[k] = "train"
    report["tables_used"] = {"train": a.train_tables, "dev": a.dev_tables, "test": a.test_tables,
                             "unused": len(keys) - need}

    docs, qa = [], defaultdict(list)
    for k in keys[:need]:
        exs = by_table[k]
        ex0 = exs[0]
        tbl = ex0["TBL"]
        header, rows = tbl[0], tbl[1:]
        title, desc = split_title(ex0["T"])
        tid = "ko_" + hashlib.sha1(k.encode()).hexdigest()[:10]
        doc_id = "doc_" + tid
        passages = [{"id": f"{doc_id}_p0", "doc_id": doc_id, "order": 0, "text": desc}] if desc else []
        docs.append({
            "id": doc_id, "corpus": "ko_tables", "lang": "ko", "title": title, "passages": passages,
            "tables": [{"id": tid, "doc_id": doc_id, "title": title, "caption": None, "header": header,
                        "rows": rows, "units": make_units(header), "lang": "ko", "source_url": ex0["U"]}],
            "source": {"name": "KorWikiTQ (LG AI Research)",
                       "url": "https://github.com/LG-NLP/KorWikiTableQuestions",
                       "license": "CC BY-SA 4.0", "note": f"official split: {ex0['_orig_split']}; split here: {assignment[k]}"},
        })
        rnd.shuffle(exs)
        for ex in exs[: a.max_q_per_table]:
            r, c = ex["_gold"]
            qa[assignment[k]].append({
                "qid": ex["QAS"]["qid"], "question": ex["QAS"]["question"], "answer": ex["QAS"]["answer"],
                "doc_id": doc_id, "table_id": tid, "op": "lookup", "gold_cells": [[r, c]],
                "source": "korwikitq", "orig_split": ex["_orig_split"], "needs_text": False,
            })
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "documents.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    for split, rows_ in qa.items():
        with open(OUT / f"{split}.jsonl", "w", encoding="utf-8") as f:
            for r_ in rows_:
                f.write(json.dumps(r_, ensure_ascii=False) + "\n")
        report[f"{split}_examples"] = len(rows_)
    report["kept_examples"] = sum(len(v) for v in qa.values())
    tabs = {s: {r_["table_id"] for r_ in rows_} for s, rows_ in qa.items()}
    report["leak_check_shared_tables"] = {f"{x}&{y}": len(tabs[x] & tabs[y]) for x in tabs for y in tabs if x < y}
    report["params"] = vars(a) | {"max_rows": MAX_ROWS, "max_cols": MAX_COLS, "max_chars": MAX_CHARS}
    json.dump(report, open(OUT / "build_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
