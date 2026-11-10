"""Build a probe for the effect of evaluating on tables the model saw during training.

The official KorWikiTQ train/dev files share tables (scripts/data/profile_korwikitq.py), and this project re-split by
table to avoid that. This script builds two question sets that differ only in whether the TABLE was in training:

  seen    questions about the 900 train tables that the per-table cap (3 questions) left out of training
  unseen  questions chosen by the same rule about tables no model here was trained on:
          the dev and test tables (questions the cap left out), then randomly drawn unused tables
          (three random questions set aside per table to mirror the cap) until both sets have the same size

Tables were assigned to train / dev / test / unused by one random shuffle in build_ko.py, and both sets keep only
questions from tables with more than three usable questions, so they are drawn from the same population.
`category` records whether the question asks for a cell that one of the three set-aside questions also asks for.

Input : data/raw/korwikitq/KorWikiTQ_ko_{train,dev}.json, data/ko/{train,dev,test}.jsonl
Output: data/ko/leak_probe_{seen,unseen}.jsonl, data/ko/leak_probe_documents.jsonl (unused tables only),
        data/ko/leak_probe_report.json
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_ko

OUT = build_ko.OUT
SEED = 13


def leftovers(exs: list[dict], used: list[dict]) -> list[dict]:
    """Questions of one table that are not among `used`, without repeats of a used or earlier question text."""
    used_ids = {e["QAS"]["qid"] for e in used}
    seen_text = {build_ko.norm(e["QAS"]["question"]) for e in used}
    out = []
    for e in exs:
        q = build_ko.norm(e["QAS"]["question"])
        if e["QAS"]["qid"] in used_ids or q in seen_text:
            continue
        seen_text.add(q)
        out.append(e)
    return out


def records(key: str, exs: list[dict], used: list[dict], group: str, table_split: str) -> list[dict]:
    used_cells = {e["_gold"] for e in used}
    out = []
    for e in leftovers(exs, used):
        rec = build_ko.qa_record(e, key)
        rec["category"] = "same_cell_as_set_aside" if e["_gold"] in used_cells else "other_cell"
        rec["probe"] = {"group": group, "table_split": table_split}
        out.append(rec)
    return out


def main() -> None:
    by_table, _excluded, _n = build_ko.load_and_filter()
    key_of = {build_ko.table_id(k): k for k in by_table}
    used_qids: dict[str, dict[str, set[str]]] = {}
    for split in ("train", "dev", "test"):
        per_table: dict[str, set[str]] = {}
        with open(OUT / f"{split}.jsonl", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                per_table.setdefault(r["table_id"], set()).add(r["qid"])
        used_qids[split] = per_table

    def split_records(split: str, group: str) -> list[dict]:
        out = []
        for tid in sorted(used_qids[split]):
            key = key_of[tid]
            exs = sorted(by_table[key], key=lambda e: e["QAS"]["qid"])
            used = [e for e in exs if e["QAS"]["qid"] in used_qids[split][tid]]
            out += records(key, exs, used, group, split)
        return out

    seen = split_records("train", "seen")
    unseen = split_records("test", "unseen") + split_records("dev", "unseen")
    from_split_tables = len(unseen)

    assigned = {key_of[tid] for s in used_qids.values() for tid in s}
    unused = sorted(k for k in by_table if k not in assigned)
    rnd = random.Random(SEED)
    rnd.shuffle(unused)
    docs, unused_tables = [], 0
    for key in unused:
        if len(unseen) >= len(seen):
            break
        exs = sorted(by_table[key], key=lambda e: e["QAS"]["qid"])
        rnd.shuffle(exs)
        recs = records(key, exs, exs[:3], "unseen", "unused")
        if not recs:
            continue
        unseen += recs
        unused_tables += 1
        docs.append(build_ko.document_for(key, exs[0], f"official split: {exs[0]['_orig_split']}; split here: unused (leak probe)"))
    unseen = unseen[: len(seen)]

    def write(name: str, rows: list[dict]) -> None:
        with open(OUT / name, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    write("leak_probe_seen.jsonl", seen)
    write("leak_probe_unseen.jsonl", unseen)
    write("leak_probe_documents.jsonl", docs)

    def profile(rows: list[dict]) -> dict:
        tables = {r["table_id"] for r in rows}
        same = sum(1 for r in rows if r["category"] == "same_cell_as_set_aside")
        return {"questions": len(rows), "tables": len(tables), "same_cell_as_set_aside": same, "other_cell": len(rows) - same,
                "by_table_split": {s: sum(1 for r in rows if r["probe"]["table_split"] == s)
                                   for s in sorted({r["probe"]["table_split"] for r in rows})}}

    train_tables = {r["table_id"] for r in seen}
    report = {
        "seed": SEED, "seen": profile(seen), "unseen": profile(unseen),
        "unseen_from_dev_test_tables": from_split_tables, "unused_tables_drawn": unused_tables,
        "shared_tables_between_sets": len(train_tables & {r["table_id"] for r in unseen}),
        "shared_qids_with_training": len({r["qid"] for r in seen} & {q for qs in used_qids["train"].values() for q in qs}),
    }
    (OUT / "leak_probe_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
