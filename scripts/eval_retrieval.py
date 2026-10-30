"""Retrieval quality: does BM25 over ALL tables of a corpus put the gold table (and passage) at the top?

Queries are the evaluation questions only (no document id is given). Reported: hit@1, hit@5, MRR@5 for tables,
and hit@3 for the gold passage on questions that name one. Writes experiments/eval/retrieval/metrics.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from tabletrace.corpus.store import CorpusStore
from tabletrace.retrieval.index import CorpusIndex

ROOT = Path(__file__).resolve().parents[1]


def load(p: str) -> list[dict]:
    return [json.loads(line) for line in open(ROOT / p, encoding="utf-8") if line.strip()]


def table_scores(idx: CorpusIndex, recs: list[dict], k: int = 5) -> dict:
    h1 = h5 = 0
    mrr = 0.0
    for r in recs:
        ids = [h.id for h in idx.search_tables(r["question"], k=k)]
        if ids[:1] == [r["table_id"]]:
            h1 += 1
        if r["table_id"] in ids:
            h5 += 1
            mrr += 1.0 / (ids.index(r["table_id"]) + 1)
    n = len(recs)
    return {"n": n, "n_tables_searched": len(idx.tables), "hit_at_1": round(h1 / n, 4), "hit_at_5": round(h5 / n, 4), "mrr_at_5": round(mrr / n, 4)}


def main() -> None:
    store = CorpusStore.from_disk()
    t0 = time.time()
    ko = CorpusIndex(store.corpora["ko_tables"], "ko")
    ch = CorpusIndex(store.corpora["chem_docs"], "en")
    out = {"index_build_s": round(time.time() - t0, 1)}
    ko_test = [r for r in load("data/ko/test.jsonl")]
    out["ko_test_lookup"] = table_scores(ko, ko_test)
    out["ko_custom"] = table_scores(ko, load("data/ko/custom_eval.jsonl"))
    chem = load("data/chem/custom_eval.jsonl")
    out["chem_custom"] = table_scores(ch, chem)
    # passage retrieval for chem questions that name a gold passage
    named = [r for r in chem if r.get("context_passage")]
    hit = sum(1 for r in named if r["context_passage"] in [h.id for h in ch.search_passages(r["question"], k=3, doc_id=r["doc_id"])])
    out["chem_passage_hit_at_3_within_doc"] = {"n": len(named), "hit_at_3": round(hit / len(named), 4) if named else None}
    hit = sum(1 for r in named if r["context_passage"] in [h.id for h in ch.search_passages(r["question"], k=3)])
    out["chem_passage_hit_at_3_all_docs"] = {"n": len(named), "hit_at_3": round(hit / len(named), 4) if named else None}
    dest = ROOT / "experiments" / "eval" / "retrieval"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
