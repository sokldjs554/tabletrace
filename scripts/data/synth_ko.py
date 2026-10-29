"""Templated Korean calculation / abstention examples built from KorWikiTQ tables.

These are SYNTHETIC: question text comes from templates, answers from the restricted calculator.
They exist so the model sees the `diff/sum/avg/abstain` program ops during SFT. They are generated
per split from that split's own tables only (no table crosses splits), and the hand-written
evaluation cases (data/ko/custom_eval.jsonl) are the real test of these abilities.

Output: data/ko/synthetic_{train,dev,test}.jsonl
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path

from tabletrace.schema import CellRef, Table
from tabletrace.tools.calculator import CalcError, compute
from tabletrace.tools.numbers import parse_number

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "ko"
YEAR_HDR = re.compile(r"연도|년도|년|시즌|회차|순위|등번호|번호|코드|일자|날짜|기간|순서|세대|대수|기수|차수|대\b|회\b")


def jong(word: str) -> bool:
    ch = word.strip()[-1:]
    if not ch:
        return False
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 != 0
    if ch.isdigit():
        return ch in "013678"
    return False


def josa(word: str, with_j: str, without_j: str) -> str:
    return word + (with_j if jong(word) else without_j)


def key_column(t: Table) -> int | None:
    for c in range(t.n_cols):
        vals = t.column(c)
        if len(set(vals)) == len(vals) and all(v.strip() for v in vals) and sum(parse_number(v) is not None for v in vals) < len(vals) / 2 and all(len(v) <= 40 for v in vals):
            return c
    return None


def numeric_columns(t: Table) -> list[int]:
    out = []
    for c in range(t.n_cols):
        h = t.header[c]
        if YEAR_HDR.search(h):
            continue
        vals = [parse_number(v, t.units.get(c)) for v in t.column(c)]
        ok = [v for v in vals if v is not None]
        if len(ok) < max(3, int(0.8 * len(vals))):
            continue
        if all(1900 <= v.value <= 2100 and float(v.value).is_integer() for v in ok):  # years in disguise
            continue
        units = {v.unit for v in ok}
        if len(units) != 1:
            continue
        if len({v.value for v in ok}) < 3:
            continue
        out.append(c)
    return out


def main() -> None:
    rnd = random.Random(21)
    docs = {json.loads(l)["id"]: json.loads(l) for l in open(D / "documents.jsonl", encoding="utf-8")}
    quotas = {"train": {"diff": 400, "sum": 150, "avg": 150, "abstain": 260}, "dev": {"diff": 25, "sum": 10, "avg": 10, "abstain": 20},
              "test": {"diff": 60, "sum": 25, "avg": 25, "abstain": 50}}
    for split, quota in quotas.items():
        recs = [json.loads(l) for l in open(D / f"{split}.jsonl", encoding="utf-8")]
        table_ids = sorted({r["table_id"] for r in recs})
        tables = {tid: Table.model_validate(docs[r["doc_id"]]["tables"][0]) for r in recs for tid in [r["table_id"]]}
        all_keys = []
        for tid in table_ids:
            t = tables[tid]
            kc = key_column(t)
            if kc is not None:
                all_keys += [(tid, v) for v in t.column(kc)]
        out, made = [], Counter()
        rnd.shuffle(table_ids)
        for _round in range(6):
            for tid in table_ids:
                t = tables[tid]
                kc = key_column(t)
                if kc is None:
                    continue
                numc = numeric_columns(t)
                keys = t.column(kc)
                # calculation ops
                for op in ("diff", "sum", "avg"):
                    if made[op] >= quota[op] or not numc:
                        continue
                    c = rnd.choice(numc)
                    rows = [r for r in range(t.n_rows) if parse_number(t.cell(r, c), t.units.get(c)) is not None]
                    if len(rows) < 2:
                        continue
                    r1, r2 = rnd.sample(rows, 2)
                    v1, v2 = parse_number(t.cell(r1, c)).value, parse_number(t.cell(r2, c)).value
                    if op == "diff" and v1 < v2:
                        r1, r2 = r2, r1
                    h = t.header[c].strip()
                    k1, k2 = keys[r1], keys[r2]
                    if op == "diff":
                        q = rnd.choice([f"{josa(k1, '과', '와')} {k2}의 {h} 차이는 얼마입니까?",
                                        f"{josa(k1, '은', '는')} {k2}보다 {josa(h, '이', '가')} 얼마나 더 많습니까?",
                                        f"{k1}의 {h}에서 {k2}의 {h}를 빼면 얼마야?"])
                    elif op == "sum":
                        q = rnd.choice([f"{josa(k1, '과', '와')} {k2}의 {h}를 합하면 얼마입니까?",
                                        f"{josa(k1, '과', '와')} {k2}의 {h} 합계는 얼마야?"])
                    else:
                        q = rnd.choice([f"{josa(k1, '과', '와')} {k2}의 {h} 평균은 얼마입니까?",
                                        f"{josa(k1, '과', '와')} {k2}의 평균 {josa(h, '은', '는')}?"])
                    cells = [CellRef(table_id=tid, row=r1, col=c), CellRef(table_id=tid, row=r2, col=c)]
                    try:
                        calc = compute(t, op, cells)
                    except CalcError:
                        continue
                    out.append({"qid": f"syn_{split}_{len(out)}", "question": q, "answer": calc.formatted, "doc_id": "doc_" + tid,
                                "table_id": tid, "op": op, "gold_cells": [[r1, c], [r2, c]], "source": "synthetic",
                                "needs_text": False, "unit": calc.unit})
                    made[op] += 1
                # abstention: an entity from another table, or an attribute this table lacks
                if made["abstain"] < quota["abstain"]:
                    kind = rnd.choice(["entity", "attribute"])
                    cells_text = " ".join(" ".join(r) for r in t.rows).lower() + " " + " ".join(t.header).lower()
                    if kind == "entity":
                        for _ in range(20):
                            otid, k = rnd.choice(all_keys)
                            if otid != tid and len(k) >= 2 and k.lower() not in cells_text:
                                h = t.header[rnd.choice([c for c in range(t.n_cols) if c != kc])].strip()
                                q = rnd.choice([f"{k}의 {josa(h, '은', '는')} 무엇입니까?", f"{k}의 {h}를 알려줘.", f"표에서 {k}의 {josa(h, '은', '는')}?"])
                                out.append({"qid": f"syn_{split}_{len(out)}", "question": q, "answer": None, "doc_id": "doc_" + tid, "table_id": tid,
                                            "op": "abstain", "reason": "not_in_document", "gold_cells": [], "source": "synthetic", "needs_text": False})
                                made["abstain"] += 1
                                break
                    else:
                        for _ in range(20):
                            ot = tables[rnd.choice(table_ids)]
                            h = rnd.choice(ot.header).strip()
                            if ot.id != tid and len(h) >= 2 and h.lower() not in cells_text:
                                k = rnd.choice(keys)
                                q = rnd.choice([f"{k}의 {josa(h, '은', '는')} 무엇입니까?", f"{k}의 {h}를 알려줘."])
                                out.append({"qid": f"syn_{split}_{len(out)}", "question": q, "answer": None, "doc_id": "doc_" + tid, "table_id": tid,
                                            "op": "abstain", "reason": "not_in_document", "gold_cells": [], "source": "synthetic", "needs_text": False})
                                made["abstain"] += 1
                                break
            if all(made[k] >= v for k, v in quota.items()):
                break
        rnd.shuffle(out)
        with open(D / f"synthetic_{split}.jsonl", "w", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(split, dict(made), "written", len(out))


if __name__ == "__main__":
    main()
