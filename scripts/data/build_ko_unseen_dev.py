"""Official-dev questions on tables this project never trained on, at every table size.

The main test split only holds tables of at most 16 rows, 7 columns and 900 characters, because the first model
(mT5-small, 512 input tokens) could not read more. That left out almost half of KorWikiTQ. This script keeps the
official dev questions whose table

  * has a non-empty header, rectangular rows and exactly one cell equal to the answer (the same checks as build_ko.py,
    without the size limits), and
  * is not a table of the official train file, and not a table of this project's train split or training pool.

    data/ko/unseen_dev.jsonl                 questions (same fields as test.jsonl, plus `size` and `page_seen`)
    data/ko/unseen_dev_documents.jsonl.gz    their tables
    data/ko/unseen_dev_report.json           counts

`size` is "small" when the table would have passed the old limits and "large" otherwise. `page_seen` marks a table
whose Wikipedia page also holds a table seen in training (another table of the same article).

    python scripts/data/build_ko_unseen_dev.py
"""
from __future__ import annotations

import gzip
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ko import (
    MAX_CHARS,
    MAX_COLS,
    MAX_ROWS,
    OUT,
    RAW,
    document_for,
    gold_cell,
    qa_record,
    table_id,
    table_key,
)


def main() -> None:
    examples = []
    for split in ("train", "dev"):
        for ex in json.load(open(RAW / f"KorWikiTQ_ko_{split}.json", encoding="utf-8"))["data"]:
            ex["_orig_split"] = split
            examples.append(ex)
    official_train_tables = {table_key(e) for e in examples if e["_orig_split"] == "train"}
    ours = {}
    for name in ("train", "dev", "test"):
        for line in open(OUT / f"{name}.jsonl", encoding="utf-8"):
            ours[json.loads(line)["table_id"]] = name
    with gzip.open(OUT / "pool_documents.jsonl.gz", "rt", encoding="utf-8") as f:
        pool_docs = [json.loads(line) for line in f]
    trained_tables = {t for t, s in ours.items() if s == "train"} | {t["id"] for d in pool_docs for t in d["tables"]}
    main_docs = {json.loads(line)["id"]: json.loads(line) for line in open(OUT / "documents.jsonl", encoding="utf-8")}
    trained_pages = {t["source_url"] for d in pool_docs for t in d["tables"]}
    trained_pages |= {t["source_url"] for d in main_docs.values() for t in d["tables"] if ours.get(t["id"]) == "train"}
    trained_pages |= {e["U"] for e in examples if e["_orig_split"] == "train"}

    counts: Counter = Counter()
    docs, rows, seen_docs = [], [], set()
    for ex in examples:
        if ex["_orig_split"] != "dev":
            continue
        counts["official_dev_questions"] += 1
        tbl = ex["TBL"]
        if not tbl or len(tbl) < 3 or len(tbl[0]) < 2:
            counts["excluded_table_too_small"] += 1
            continue
        header, body = tbl[0], tbl[1:]
        if any(len(r) != len(header) for r in body):
            counts["excluded_ragged_rows"] += 1
            continue
        if any(not h.strip() for h in header):
            counts["excluded_empty_header"] += 1
            continue
        g = gold_cell(ex)
        if g is None:
            counts["excluded_answer_not_unique_cell"] += 1
            continue
        key = table_key(ex)
        tid = table_id(key)
        if key in official_train_tables:
            counts["excluded_table_in_official_train"] += 1
            continue
        if tid in trained_tables:
            counts["excluded_table_in_this_projects_training"] += 1
            continue
        ex["_gold"] = g
        large = len(body) > MAX_ROWS or len(header) > MAX_COLS or sum(len(c) for r in tbl for c in r) > MAX_CHARS
        rec = {**qa_record(ex, key), "size": "large" if large else "small", "page_seen": ex["U"] in trained_pages,
               "n_rows": len(body), "n_cols": len(header)}
        rows.append(rec)
        if tid not in seen_docs:
            seen_docs.add(tid)
            docs.append(document_for(key, ex, "official split: dev; table not seen in training (unseen_dev)"))
    report = {**dict(counts), "questions": len(rows), "tables": len(docs),
              "by_size": dict(Counter(r["size"] for r in rows)), "page_seen": sum(r["page_seen"] for r in rows),
              "also_in_main_split": dict(Counter(ours[r["table_id"]] for r in rows if r["table_id"] in ours)),
              "over_limit": {"rows_over_16": sum(r["n_rows"] > MAX_ROWS for r in rows), "cols_over_7": sum(r["n_cols"] > MAX_COLS for r in rows)},
              "max_rows": max(r["n_rows"] for r in rows), "max_cols": max(r["n_cols"] for r in rows)}
    with open(OUT / "unseen_dev.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with gzip.GzipFile(OUT / "unseen_dev_documents.jsonl.gz", "wb", mtime=0) as raw:
        raw.write("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in docs).encode("utf-8"))
    (OUT / "unseen_dev_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
