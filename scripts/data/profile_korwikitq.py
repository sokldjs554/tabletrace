"""Measure the official KorWikiTQ split (before our re-split): sizes, tables, table overlap, answer-is-a-cell rate.

Overlap is counted three ways, from loosest to strictest:
  by URL                 the same Wikipedia page appears in both files (a page can hold several tables)
  by qid prefix          the dataset's own table number (the part of the qid before "_")
  by URL and content     the same page AND cell-for-cell identical table (the identity build_ko.py splits on)

Reads data/raw/korwikitq/KorWikiTQ_ko_{train,dev}.json (~310 MB, needs ~3 GB RAM) and writes
data/ko/official_split_profile.json, which docs/REPORT.md cites. Reproduces the numbers in docs/research/datasets.md.
"""
from __future__ import annotations

import collections
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "korwikitq"


def norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


def table_key(ex: dict) -> str:
    """Same table identity as scripts/data/build_ko.py: page URL plus a hash of every cell."""
    h = hashlib.sha1(json.dumps(ex["TBL"], ensure_ascii=False).encode()).hexdigest()[:12]
    return f"{ex['U']}#{h}"


def main() -> None:
    out: dict = {}
    urls: dict[str, set] = {}
    qprefix: dict[str, set] = {}
    exact: dict[str, set] = {}
    answers: dict[str, set] = {}
    questions: dict[str, set] = {}
    dev_rows: list[tuple[str, str, str, str]] = []
    for split in ("train", "dev"):
        data = json.load(open(RAW / f"KorWikiTQ_ko_{split}.json", encoding="utf-8"))["data"]
        u = collections.Counter(e["U"] for e in data)
        urls[split] = set(u)
        qprefix[split] = {e["QAS"]["qid"].split("_")[0] for e in data}
        keys = [table_key(e) for e in data]
        exact[split] = set(keys)
        answers[split] = {(k, norm(e["QAS"]["answer"])) for k, e in zip(keys, data, strict=True)}
        questions[split] = {(k, norm(e["QAS"]["question"])) for k, e in zip(keys, data, strict=True)}
        if split == "dev":
            dev_rows = [(e["U"], k, norm(e["QAS"]["answer"]), norm(e["QAS"]["question"])) for k, e in zip(keys, data, strict=True)]
        cell_hit = sum(1 for e in data if any(norm(e["QAS"]["answer"]) == norm(c) for r in e["TBL"] for c in r))
        rows = [len(e["TBL"]) for e in data]
        out[split] = {"examples": len(data), "unique_tables_by_url": len(u), "unique_table_ids_by_qid_prefix": len(qprefix[split]),
                      "unique_tables_by_url_and_content": len(exact[split]),
                      "examples_per_table": round(len(data) / len(exact[split]), 2),
                      "answer_is_cell_pct": round(100 * cell_hit / len(data), 1), "table_rows_median": statistics.median(rows), "table_rows_max": max(rows)}
        del data
    out["shared_tables_by_url"] = len(urls["train"] & urls["dev"])
    out["shared_tables_by_qid_prefix"] = len(qprefix["train"] & qprefix["dev"])
    out["shared_tables_by_url_and_content"] = len(exact["train"] & exact["dev"])
    n_dev = len(dev_rows)

    def share(count: int) -> dict:
        return {"examples": count, "of": n_dev, "rate": round(count / n_dev, 4)}

    # How much of the official dev file is asked about material that is also in the official train file.
    out["dev_on_train_url"] = share(sum(1 for u, _k, _a, _q in dev_rows if u in urls["train"]))
    out["dev_on_train_table"] = share(sum(1 for _u, k, _a, _q in dev_rows if k in exact["train"]))
    out["dev_same_table_same_answer_in_train"] = share(sum(1 for _u, k, a, _q in dev_rows if (k, a) in answers["train"]))
    out["dev_same_table_same_question_in_train"] = share(sum(1 for _u, k, _a, q in dev_rows if (k, q) in questions["train"]))
    dest = ROOT / "data" / "ko" / "official_split_profile.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
