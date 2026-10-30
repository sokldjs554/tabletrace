"""Measure the official KorWikiTQ split (before our re-split): sizes, tables, table overlap, answer-is-a-cell rate.

Reads data/raw/korwikitq/KorWikiTQ_ko_{train,dev}.json (~310 MB, needs ~3 GB RAM) and writes
data/ko/official_split_profile.json, which docs/REPORT.md cites. Reproduces the numbers in docs/research/datasets.md.
"""
from __future__ import annotations

import collections
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "korwikitq"


def norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


def main() -> None:
    out: dict = {}
    urls: dict[str, set] = {}
    qprefix: dict[str, set] = {}
    for split in ("train", "dev"):
        data = json.load(open(RAW / f"KorWikiTQ_ko_{split}.json", encoding="utf-8"))["data"]
        u = collections.Counter(e["U"] for e in data)
        urls[split] = set(u)
        qprefix[split] = {e["QAS"]["qid"].split("_")[0] for e in data}
        cell_hit = sum(1 for e in data if any(norm(e["QAS"]["answer"]) == norm(c) for r in e["TBL"] for c in r))
        rows = [len(e["TBL"]) for e in data]
        out[split] = {"examples": len(data), "unique_tables_by_url": len(u), "unique_table_ids_by_qid_prefix": len(qprefix[split]),
                      "answer_is_cell_pct": round(100 * cell_hit / len(data), 1), "table_rows_median": statistics.median(rows), "table_rows_max": max(rows)}
        del data
    out["shared_tables_by_url"] = len(urls["train"] & urls["dev"])
    out["shared_tables_by_qid_prefix"] = len(qprefix["train"] & qprefix["dev"])
    dest = ROOT / "data" / "ko" / "official_split_profile.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
