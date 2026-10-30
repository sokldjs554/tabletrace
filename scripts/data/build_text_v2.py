"""Text-answer and not-in-document training examples that sit next to a REAL table (fixes the stage-2 shortcut).

Why: in data/ko/text_*.jsonl (build_korquad_text.py) every `op: text` example came with an EMPTY table, and the
stage-2 model learned "table has no rows -> text" instead of "answer is in the passage, not in the table"
(docs/REPORT.md section 5.4, item 8). Here each KorQuAD question is paired with a distractor table copied from
the table sets of the matching split (train tables for train, dev tables for dev; test tables are never used), so the
only cue left is whether the answer span is in the passage.

  positives : question + passage window containing the answer + unrelated real table  -> op: text
  negatives : question + passage window of ANOTHER paragraph (answer absent) + real table -> op: abstain (not_in_document)

KorQuAD v1.0 is CC BY-ND 2.0 KR: the derived files are git-ignored (data/ko/text2_*.jsonl) and not redistributed.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_korquad_text import window  # noqa: E402
from tokenizers import Tokenizer  # noqa: E402

from tabletrace.model.serialize import choose_context_and_rows  # noqa: E402
from tabletrace.schema import Table  # noqa: E402

RAW = ROOT / "data" / "raw" / "korquad"
KO = ROOT / "data" / "ko"
MODEL = ROOT / "models" / "mt5-small-tabletrace"


class Tok:
    """Minimal callable with the interface choose_context_and_rows expects (.input_ids)."""

    def __init__(self, path: Path) -> None:
        self.tk = Tokenizer.from_file(str(path / "tokenizer.json"))

    def __call__(self, text: str):
        class Out:
            pass
        o = Out()
        o.input_ids = self.tk.encode(text).ids
        return o


def table_pool(split_file: str) -> list[dict]:
    wanted = set()
    for line in open(KO / split_file, encoding="utf-8"):
        r = json.loads(line)
        wanted.add((r["doc_id"], r["table_id"]))
    pool = []
    for line in open(KO / "documents.jsonl", encoding="utf-8"):
        d = json.loads(line)
        for t in d["tables"]:
            if (d["id"], t["id"]) in wanted and 3 <= len(t["rows"]) <= 14:
                pool.append(t)
    return pool


def convert(split: str, n_pos: int, n_neg: int, seed: int, pool_file: str, tok: Tok, src: str | None = None, exclude: set[str] | None = None) -> None:
    """`src` is the KorQuAD file to draw from (default: same name as `split`); `exclude` are KorQuAD ids to skip."""
    data = json.load(open(RAW / f"KorQuAD_v1.0_{src or split}.json", encoding="utf-8"))["data"]
    rnd = random.Random(seed)
    pool = table_pool(pool_file)
    items = []
    for art in data:
        for para in art["paragraphs"]:
            for qa in para["qas"]:
                a = qa["answers"][0]
                items.append((art["title"], para["context"], qa["id"], qa["question"], a["text"], a["answer_start"]))
    rnd.shuffle(items)
    docs, recs = [], []
    n_p = n_n = 0

    def make_doc(qid: str, title: str, win: str, question: str):
        """Return (doc, table_id) with a distractor table that leaves the whole window visible, or None."""
        for _ in range(30):
            t = rnd.choice(pool)
            doc_id = f"doc_kq2_{qid}"
            tid = f"kq2_{qid}"
            table = {**t, "id": tid, "doc_id": doc_id}
            ctx, n = choose_context_and_rows(tok, question, Table(**table), win, 512)
            if ctx is not None and len(ctx) == len(win) and n >= len(table["rows"]):
                doc = {"id": doc_id, "corpus": "ko_tables", "lang": "ko", "title": title,
                       "passages": [{"id": f"{doc_id}_p0", "doc_id": doc_id, "order": 0, "text": win}],
                       "tables": [table],
                       "source": {"name": "KorQuAD v1.0 (LG CNS) + KorWikiTQ distractor table",
                                  "url": "https://korquad.github.io/KorQuad%201.0/",
                                  "license": "CC BY-ND 2.0 KR / CC BY-SA 4.0 (not redistributed; derived file is git-ignored)"}}
                return doc, tid
        return None

    for idx, (title, ctx, qid, q, a, st) in enumerate(items):
        if n_p >= n_pos and n_n >= n_neg:
            break
        if exclude and qid in exclude:
            continue
        if len(a) > 40 or len(q) > 120:
            continue
        w = window(ctx, st, st + len(a))
        if a not in w:
            continue
        if n_p < n_pos:
            made = make_doc(qid, title, w, q)
            if made:
                doc, tid = made
                docs.append(doc)
                recs.append({"qid": f"kq2_{split}_{qid}", "question": q, "answer": a, "doc_id": doc["id"], "table_id": tid,
                             "op": "text", "gold_cells": [], "source": "korquad_text2", "needs_text": True})
                n_p += 1
                continue
        if n_n < n_neg:
            # a window from a different paragraph, which must not contain the answer string
            other = items[(idx + 997) % len(items)]
            ow = window(other[1], other[5], other[5] + len(other[4]))
            if a in ow or a in other[1][:0]:
                continue
            made = make_doc(f"neg_{qid}", other[0], ow, q)
            if made:
                doc, tid = made
                docs.append(doc)
                recs.append({"qid": f"kq2neg_{split}_{qid}", "question": q, "answer": None, "doc_id": doc["id"], "table_id": tid,
                             "op": "abstain", "reason": "not_in_document", "gold_cells": [], "source": "korquad_neg", "needs_text": False})
                n_n += 1
    with open(KO / f"text2_documents_{split}.jsonl", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    with open(KO / f"text2_{split}.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(split, "text:", n_p, "abstain:", n_n)


if __name__ == "__main__":
    tok = Tok(MODEL)
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    if only in ("all", "train"):
        convert("train", 600, 250, 11, "train.jsonl", tok)
    if only in ("all", "dev"):
        convert("dev", 100, 50, 12, "dev.jsonl", tok)
    if only in ("all", "test"):
        # independent text/not-in-document evaluation: other KorQuAD dev questions than text2_dev, distractors from TEST tables
        used = {json.loads(line)["qid"].split("_", 2)[-1] for line in open(KO / "text2_dev.jsonl", encoding="utf-8")}
        used |= {u.removeprefix("neg_") for u in used}
        convert("test", 100, 50, 13, "test.jsonl", tok, src="dev", exclude=used)
