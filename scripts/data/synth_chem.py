"""Templated English chemistry QA from OpenStax tables (train/dev splits only) + abstentions.

SYNTHETIC: template questions, calculator answers. Hand-written test cases live in
data/chem/custom_eval.jsonl and come from documents in the *test* split only.
Output: data/chem/synthetic_{train,dev}.jsonl
"""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from tabletrace.schema import CellRef, Table
from tabletrace.tools.calculator import CalcError, compute
from tabletrace.tools.numbers import parse_number

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "data" / "chem"

LOOKUP_T = ["What is the {h} of {k}?", "According to the table, what is the {h} for {k}?", "Find the {h} listed for {k}.",
            "For {k}, what value of {h} does the table give?"]
DIFF_T = ["How much larger is the {h} of {k1} than that of {k2}?", "What is the difference in {h} between {k1} and {k2}?"]
RATIO_T = ["What is the ratio of the {h} of {k1} to that of {k2}?", "By what factor is the {h} of {k1} greater than that of {k2}?"]
SUM_T = ["What is the combined {h} of {k1} and {k2}?", "What is the sum of the {h} values for {k1} and {k2}?"]
ABST_T = ["What is the {h} of {k}?", "Does the table give the {h} of {k}? If so, what is it?", "What value of {h} is listed for {k}?"]


def key_col(t: Table) -> int | None:
    for c in range(t.n_cols):
        vals = t.column(c)
        if len(set(vals)) == len(vals) and all(v.strip() for v in vals) and sum(parse_number(v) is not None for v in vals) <= len(vals) // 3:
            return c
    return None


def numeric_cols(t: Table) -> list[int]:
    out = []
    for c in range(t.n_cols):
        vals = [parse_number(v, t.units.get(c)) for v in t.column(c)]
        ok = [v for v in vals if v is not None]
        if len(ok) >= max(2, int(0.8 * len(vals))) and len({v.unit for v in ok}) == 1 and len({v.value for v in ok}) >= 2:
            out.append(c)
    return out


def clean_header(h: str) -> str:
    return h.split("(")[0].strip().rstrip(",") or h


def main() -> None:
    docs = {json.loads(line)["id"]: json.loads(line) for line in open(D / "documents.jsonl", encoding="utf-8")}
    split = json.load(open(D / "split.json"))
    all_keys = []
    for d in docs.values():
        for tb in d["tables"]:
            t = Table.model_validate(tb)
            kc = key_col(t)
            if kc is not None:
                all_keys += [(t.id, k) for k in t.column(kc)]
    for name, quota in (("train", {"lookup": 420, "diff": 120, "ratio": 60, "sum": 60, "abstain": 160}),
                        ("dev", {"lookup": 40, "diff": 12, "ratio": 6, "sum": 6, "abstain": 16})):
        rnd = random.Random(3 if name == "train" else 4)
        tables = [Table.model_validate(tb) for did in split[name] for tb in docs[did]["tables"]]
        made: Counter = Counter()
        out = []
        for _ in range(40):
            rnd.shuffle(tables)
            for t in tables:
                kc = key_col(t)
                if kc is None:
                    continue
                keys = t.column(kc)
                numc = numeric_cols(t)
                if made["lookup"] < quota["lookup"]:
                    r = rnd.randrange(t.n_rows)
                    cols = [c for c in range(t.n_cols) if c != kc and t.cell(r, c).strip()]
                    if cols:
                        c = rnd.choice(cols)
                        out.append({"qid": f"synchem_{name}_{len(out)}", "question": rnd.choice(LOOKUP_T).format(h=clean_header(t.header[c]), k=keys[r]),
                                    "answer": t.cell(r, c), "doc_id": t.doc_id, "table_id": t.id, "op": "lookup", "gold_cells": [[r, c]],
                                    "source": "synthetic", "needs_text": False})
                        made["lookup"] += 1
                for op, tpl in (("diff", DIFF_T), ("ratio", RATIO_T), ("sum", SUM_T)):
                    if made[op] >= quota[op] or not numc:
                        continue
                    c = rnd.choice(numc)
                    rows = [r for r in range(t.n_rows) if parse_number(t.cell(r, c), t.units.get(c)) is not None]
                    if len(rows) < 2:
                        continue
                    r1, r2 = rnd.sample(rows, 2)
                    v1, v2 = parse_number(t.cell(r1, c), t.units.get(c)).value, parse_number(t.cell(r2, c), t.units.get(c)).value
                    if op in ("diff", "ratio") and v1 < v2:
                        r1, r2 = r2, r1
                    if op == "ratio" and v2 == 0:
                        continue
                    cells = [CellRef(table_id=t.id, row=r1, col=c), CellRef(table_id=t.id, row=r2, col=c)]
                    try:
                        calc = compute(t, op, cells)
                    except CalcError:
                        continue
                    out.append({"qid": f"synchem_{name}_{len(out)}", "question": rnd.choice(tpl).format(h=clean_header(t.header[c]), k1=keys[r1], k2=keys[r2]),
                                "answer": calc.formatted, "doc_id": t.doc_id, "table_id": t.id, "op": op, "gold_cells": [[r1, c], [r2, c]],
                                "source": "synthetic", "needs_text": False, "unit": calc.unit})
                    made[op] += 1
                if made["abstain"] < quota["abstain"]:
                    cells_text = (" ".join(" ".join(r) for r in t.rows) + " " + " ".join(t.header)).lower()
                    for _try in range(20):
                        otid, k = rnd.choice(all_keys)
                        if otid != t.id and len(k) >= 2 and k.lower() not in cells_text:
                            h = clean_header(t.header[rnd.choice([c for c in range(t.n_cols) if c != kc])])
                            out.append({"qid": f"synchem_{name}_{len(out)}", "question": rnd.choice(ABST_T).format(h=h, k=k), "answer": None,
                                        "doc_id": t.doc_id, "table_id": t.id, "op": "abstain", "reason": "not_in_document", "gold_cells": [],
                                        "source": "synthetic", "needs_text": False})
                            made["abstain"] += 1
                            break
            if all(made[k] >= v for k, v in quota.items()):
                break
        rnd.shuffle(out)
        with open(D / f"synthetic_{name}.jsonl", "w", encoding="utf-8") as f:
            for r in out:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(name, dict(made), "written", len(out))


if __name__ == "__main__":
    main()
