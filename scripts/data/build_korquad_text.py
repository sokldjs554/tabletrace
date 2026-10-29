"""Text-answer training examples from KorQuAD v1.0 (train split only; dev for checkpoint selection).

KorQuAD 1.0 (LG CNS) is distributed under CC BY-ND 2.0 KR. We do not redistribute it: this script
downloads the original JSON and writes derived examples to data/ko/text_*.jsonl (git-ignored).
Each example pairs a question with a ~300-char window of its paragraph as `context` and an empty
placeholder table, so the model learns `op: text` = "copy the answer span from the passage".
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "korquad"
OUT = ROOT / "data" / "ko"
WINDOW = 300


def window(context: str, start: int, end: int) -> str:
    """Sentence-aligned window around [start, end) of at most WINDOW chars that keeps the answer."""
    left = max(0, start - WINDOW // 2)
    right = min(len(context), end + WINDOW // 2)
    seg = context[left:right]
    # trim to sentence boundaries when possible
    m = re.search(r"[.!?。]\s", seg[: start - left])
    if m and left > 0:
        seg = seg[m.end():]
        left += m.end()
    m = list(re.finditer(r"[.!?。](\s|$)", seg[end - left:]))
    if m:
        seg = seg[: end - left + m[0].end()]
    return seg[:WINDOW] if len(seg) <= WINDOW else context[start: min(len(context), start + WINDOW)]


def convert(split: str, n: int, seed: int) -> None:
    data = json.load(open(RAW / f"KorQuAD_v1.0_{split}.json", encoding="utf-8"))["data"]
    rnd = random.Random(seed)
    items = []
    for art in data:
        for para in art["paragraphs"]:
            for qa in para["qas"]:
                ans = qa["answers"][0]
                items.append((art["title"], para["context"], qa["id"], qa["question"], ans["text"], ans["answer_start"]))
    rnd.shuffle(items)
    docs, recs = [], []
    for title, ctx, qid, q, a, st in items:
        if len(a) > 40 or len(q) > 120:
            continue
        w = window(ctx, st, st + len(a))
        if a not in w:
            continue
        doc_id = f"doc_kq_{qid}"
        tid = f"kq_{qid}"
        docs.append({"id": doc_id, "corpus": "ko_tables", "lang": "ko", "title": title,
                     "passages": [{"id": f"{doc_id}_p0", "doc_id": doc_id, "order": 0, "text": w}],
                     "tables": [{"id": tid, "doc_id": doc_id, "title": title, "header": ["항목"], "rows": [], "units": {}, "lang": "ko"}],
                     "source": {"name": "KorQuAD v1.0 (LG CNS)", "url": "https://korquad.github.io/KorQuad%201.0/",
                                "license": "CC BY-ND 2.0 KR (not redistributed; derived file is git-ignored)"}})
        recs.append({"qid": f"kq_{split}_{qid}", "question": q, "answer": a, "doc_id": doc_id, "table_id": tid, "op": "text",
                     "gold_cells": [], "source": "korquad_text", "needs_text": True})
        if len(recs) >= n:
            break
    with open(OUT / f"text_documents_{split}.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with open(OUT / f"text_{split}.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(split, len(recs), "examples")


if __name__ == "__main__":
    convert("train", 700, 1)
    convert("dev", 100, 2)
