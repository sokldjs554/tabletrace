"""Extra Korean training data: the filtered KorWikiTQ tables that the main split left unused.

`build_ko.py` keeps 7,294 tables after its filters and uses 1,140 of them (900 train / 60 dev / 180 test) with at
most three questions per table. This script writes the rest as a training pool, with the same filters and the same
record format, so that experiments can ask what more data does:

    data/ko/pool_documents.jsonl.gz   tables that are in neither train, dev nor test
    data/ko/pool_train.jsonl.gz       every usable question on those tables
                                      + the questions on the 900 train tables that the three-per-table cap left out
    data/ko/pool_report.json          counts, and how many tables were dropped to keep dev/test pages unseen

A pool table is dropped when its Wikipedia page also holds a dev or test table (same page URL). The main split only
guarantees that the *tables* differ; the pool is stricter so that scaling results cannot come from a sibling table.

    python scripts/data/build_ko_pool.py
"""
from __future__ import annotations

import gzip
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ko import OUT, document_for, load_and_filter, qa_record, table_id

SEED, USED = 13, 900 + 60 + 180          # must match the defaults of build_ko.py


def main() -> None:
    by_table, _excluded, _n = load_and_filter()
    keys = sorted(by_table)
    random.Random(SEED).shuffle(keys)    # the same first shuffle as build_ko.py, so keys[:USED] are the tables it used
    used, unused = keys[:USED], keys[USED:]
    split_of = {}
    for name in ("train", "dev", "test"):
        for line in open(OUT / f"{name}.jsonl", encoding="utf-8"):
            split_of[json.loads(line)["table_id"]] = name
    if {table_id(k) for k in used} != set(split_of):
        raise SystemExit("the shuffle does not reproduce the tables of data/ko/{train,dev,test}.jsonl; rebuild with build_ko.py first")
    page = {k: by_table[k][0]["U"] for k in keys}
    held_out_pages = {page[k] for k in used if split_of[table_id(k)] in ("dev", "test")}
    train_pages = {page[k] for k in used if split_of[table_id(k)] == "train"}
    report: dict = {"tables_after_filter": len(keys), "tables_used_by_main_split": len(used), "tables_unused": len(unused),
                    "main_split_pages_shared": {                     # disclosed, not changed: the main split is by table, not by page
                        "test_tables_on_a_page_with_a_train_table": sum(page[k] in train_pages for k in used if split_of[table_id(k)] == "test"),
                        "test_tables": sum(split_of[table_id(k)] == "test" for k in used)}}
    kept = [k for k in unused if page[k] not in held_out_pages]
    report["pool_tables_dropped_same_page_as_dev_or_test"] = len(unused) - len(kept)
    report["pool_tables"] = len(kept)

    docs, rows = [], []
    for k in kept:
        exs = by_table[k]
        docs.append(document_for(k, exs[0], f"official split: {exs[0]['_orig_split']}; split here: pool"))
        rows.extend({**qa_record(ex, k), "pool": "unused_table"} for ex in exs)
    main_train_qids = {json.loads(line)["qid"] for line in open(OUT / "train.jsonl", encoding="utf-8")}
    extra = 0
    for k in used:
        if split_of[table_id(k)] != "train":
            continue
        for ex in by_table[k]:
            if ex["QAS"]["qid"] not in main_train_qids:
                rows.append({**qa_record(ex, k), "pool": "train_table_extra"})
                extra += 1
    report["pool_questions"] = dict(Counter(r["pool"] for r in rows))
    report["pool_questions_total"] = len(rows)
    report["official_split_of_pool_questions"] = dict(Counter(r["orig_split"] for r in rows))
    held = {t for t, s in split_of.items() if s in ("dev", "test")}
    report["pool_questions_on_dev_or_test_tables"] = sum(r["table_id"] in held for r in rows)   # must be 0
    assert report["pool_questions_on_dev_or_test_tables"] == 0 and extra == report["pool_questions"].get("train_table_extra", 0)

    for name, items in (("pool_documents.jsonl.gz", docs), ("pool_train.jsonl.gz", rows)):
        with gzip.GzipFile(OUT / name, "wb", mtime=0) as raw:           # mtime=0: the same input gives the same bytes
            raw.write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in items).encode("utf-8"))
    (OUT / "pool_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
