"""Build two-turn dialogs for the conversational agent from the Korean test split.

Turn 1 is an original KorWikiTQ test question (gold cell known). Turn 2 is a follow-up written by template:

  row_switch     "그럼 {another row's label}는?"   gold = same column, the other row
  column_switch  "그럼 {another column's name}은?"  gold = same row, the other column

A follow-up is only generated when the first question names its row (some other cell of the gold row occurs in the
question text), so that a reader could complete the follow-up from the first turn. The follow-ups are templates,
not natural dialogue: they test whether memory completes an elliptical question, on exactly the two patterns the
resolver implements. Output: data/ko/dialog_eval.jsonl, data/ko/dialog_eval_report.json.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tabletrace.chat.resolve import _header_name, _surface  # noqa: E402
from tabletrace.tools.cells import normalize_text  # noqa: E402
from tabletrace.training.data import load_docs, read_records  # noqa: E402

SEED = 13


def topic(word: str) -> str:
    """Attach the topic particle: 받침이 있으면 '은', 없으면 '는'."""
    last = word.strip()[-1]
    if "가" <= last <= "힣":
        return word + ("은" if (ord(last) - ord("가")) % 28 else "는")
    return word + "는"


def usable(text: str) -> bool:
    t = normalize_text(text)
    return 2 <= len(t) <= 30 and not re.fullmatch(r"[\d\s.,%:/-]+", t)      # a bare number is not a name one would ask by


def main() -> None:
    docs = load_docs(ROOT / "data/ko/documents.jsonl")
    recs = read_records([ROOT / "data/ko/test.jsonl"])
    rnd = random.Random(SEED)
    out, skipped = [], {"no_row_label_in_question": 0}
    for rec in recs:
        table = docs[rec["doc_id"]].table(rec["table_id"])
        (r, c), = rec["gold_cells"]
        labels = [(cc, s) for cc in range(table.n_cols) if cc != c and usable(table.cell(r, cc)) and (s := _surface(rec["question"], table.cell(r, cc)))]
        if not labels:
            skipped["no_row_label_in_question"] += 1
            continue
        label_col, label = max(labels, key=lambda x: len(x[1]))
        base = {"first": {"qid": rec["qid"], "question": rec["question"], "answer": rec["answer"], "gold_cells": rec["gold_cells"]},
                "doc_id": rec["doc_id"], "table_id": rec["table_id"], "row_label": label}
        column = [table.cell(i, label_col) for i in range(table.n_rows)]
        rows = [i for i in range(table.n_rows) if i != r and usable(column[i]) and table.cell(i, c).strip()
                and sum(1 for v in column if normalize_text(v) == normalize_text(column[i])) == 1
                and normalize_text(column[i]) not in normalize_text(rec["question"])]
        if rows:
            r2 = rnd.choice(rows)
            out.append({**base, "id": f"{rec['qid']}_row", "kind": "row_switch", "follow_up": f"그럼 {topic(column[r2].strip())}?",
                        "answer": table.cell(r2, c), "gold_cells": [[r2, c]]})
        names = [_header_name(h) for h in table.header]
        cols = [j for j in range(table.n_cols) if j not in (c, label_col) and usable(names[j]) and table.cell(r, j).strip()
                and sum(1 for h in names if normalize_text(h) == normalize_text(names[j])) == 1
                and normalize_text(names[j]) not in normalize_text(rec["question"])]
        if cols:
            c2 = rnd.choice(cols)
            out.append({**base, "id": f"{rec['qid']}_col", "kind": "column_switch", "follow_up": f"그럼 {topic(names[c2])}?",
                        "answer": table.cell(r, c2), "gold_cells": [[r, c2]]})
    dest = ROOT / "data/ko/dialog_eval.jsonl"
    with open(dest, "w", encoding="utf-8") as f:
        for d in out:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    report = {"seed": SEED, "test_questions": len(recs), "skipped": skipped, "dialogs": len(out),
              "row_switch": sum(1 for d in out if d["kind"] == "row_switch"), "column_switch": sum(1 for d in out if d["kind"] == "column_switch"),
              "tables": len({d["table_id"] for d in out})}
    (ROOT / "data/ko/dialog_eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    for d in out[:4]:
        print(d["kind"], "|", d["first"]["question"], "->", d["follow_up"], "=>", d["answer"])


if __name__ == "__main__":
    main()
