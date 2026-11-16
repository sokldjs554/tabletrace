"""Helper for the evaluation questions the repository owner writes and reviews by hand.

The 30 hand-made Korean questions in data/ko/custom_eval.jsonl were written by the AI coding tool. Two tasks belong to
the owner (docs/rewrite/07_owner_eval_questions.md):

  1. review those 30 questions      -> data/ko/custom_eval_review.jsonl   (one verdict per question)
  2. write new questions by hand    -> data/ko/owner_eval.jsonl

This script only shows tables, formats calculator answers and checks the two files. It writes no question.

  python scripts/owner_eval_tool.py tables                 # test-split tables to choose from
  python scripts/owner_eval_tool.py show ko_29fbd6328d     # one table with its cell ids and passages
  python scripts/owner_eval_tool.py calc ko_29fbd6328d diff 0,4 1,4      # the answer text of a calculation
  python scripts/owner_eval_tool.py review                 # the 30 existing questions next to their tables
  python scripts/owner_eval_tool.py template               # an empty review file: 30 lines with the verdicts left blank
  python scripts/owner_eval_tool.py check                  # validate the two owner files
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tabletrace.schema import CellRef, Table  # noqa: E402
from tabletrace.tools.calculator import compute  # noqa: E402

KO = ROOT / "data" / "ko"
OWNER_FILE = KO / "owner_eval.jsonl"
REVIEW_FILE = KO / "custom_eval_review.jsonl"
CATEGORY_OPS = {"cell": {"lookup"}, "calc": {"diff", "sum", "avg", "ratio", "pct_change"}, "unit_period": {"lookup", "text"},
                "text_table": {"text"}, "abstain": {"abstain"}}
REQUIRED = ("qid", "category", "question", "answer", "doc_id", "table_id", "op", "gold_cells", "source", "needs_text")
VERDICTS = ("ok", "fix", "drop")


def load(p: Path) -> list[dict]:
    with open(p, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def documents() -> dict[str, dict]:
    return {d["id"]: d for d in load(KO / "documents.jsonl")}


def table_of(docs: dict[str, dict], table_id: str) -> tuple[dict, Table]:
    for d in docs.values():
        for t in d["tables"]:
            if t["id"] == table_id:
                return d, Table.model_validate(t)
    raise SystemExit(f"표를 찾지 못했습니다: {table_id}")


def split_tables() -> dict[str, set[str]]:
    out = {s: {r["table_id"] for r in load(KO / f"{s}.jsonl")} for s in ("train", "dev", "test")}
    for s in ("train", "dev", "test"):
        out[s] |= {r["table_id"] for r in load(KO / f"synthetic_{s}.jsonl")}
    return out


def width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def pad(s: str, n: int) -> str:
    return s + " " * max(0, n - width(s))


def render(t: Table, mark: set[tuple[int, int]] = frozenset()) -> str:
    """The table as text. Rows carry r0, r1, ...; columns c0, c1, ... A marked cell is shown between >> <<."""
    head = [f"c{j} {h}" + (f" [{t.units[j]}]" if j in t.units else "") for j, h in enumerate(t.header)]
    body = [[(f">>{c}<<" if (i, j) in mark else c) for j, c in enumerate(row)] for i, row in enumerate(t.rows)]
    w = [min(28, max(width(x) for x in col)) for col in zip(head, *body, strict=True)]
    cut = lambda s, n: s if width(s) <= n else s[: max(1, n - 1)] + "…"      # noqa: E731
    lines = ["     " + " | ".join(pad(cut(h, w[j]), w[j]) for j, h in enumerate(head))]
    for i, row in enumerate(body):
        lines.append(pad(f"r{i}", 4) + " " + " | ".join(pad(cut(c, w[j]), w[j]) for j, c in enumerate(row)))
    return "\n".join(lines)


def cmd_tables(a) -> None:
    docs, splits = documents(), split_tables()
    used = Counter(r["table_id"] for r in load(KO / "custom_eval.jsonl"))
    mine = Counter(r["table_id"] for r in load(OWNER_FILE)) if OWNER_FILE.exists() else Counter()
    rows = []
    for d in docs.values():
        for t in d["tables"]:
            if t["id"] in splits["test"]:
                rows.append((t["id"], len(t["rows"]), len(t["header"]), len(t.get("units") or {}), bool(d.get("passages")), used[t["id"]], mine[t["id"]], t["title"]))
    rows.sort(key=lambda r: (r[5] > 0, r[0]))
    print("시험 분할의 표", len(rows), "개 (학습에 쓰이지 않은 표). 열: 표 ID, 행×열, 단위가 있는 열 수, 본문 유무, 기존 수작업 문항 수, 내가 쓴 문항 수, 제목")
    for tid, nr, nc, nu, has_p, n_used, n_mine, title in rows:
        if a.with_passage and not has_p:
            continue
        if a.unused and n_used:
            continue
        print(f"{tid}  {nr:2d}×{nc:<2d}  단위열 {nu}  본문 {'있음' if has_p else '없음'}  기존 {n_used}  내 문항 {n_mine}  {title}")


def cmd_show(a) -> None:
    docs = documents()
    d, t = table_of(docs, a.table_id)
    splits = split_tables()
    where = [s for s, ids in splits.items() if t.id in ids]
    print(f"표 {t.id} | 문서 {d['id']} | 분할 {where} | 제목: {t.title}")
    if t.id not in splits["test"]:
        print("주의: 이 표는 시험 분할의 표가 아닙니다. 평가 문항은 시험 분할의 표로만 씁니다.")
    print(render(t))
    for p in d.get("passages") or []:
        print(f"\n[본문 {p['id']}] {p['text']}")
    if not d.get("passages"):
        print("\n(이 문서에는 본문이 없습니다. 본문에서 답을 찾는 문항(op: text)은 쓸 수 없습니다.)")


def cells_arg(items: list[str]) -> list[list[int]]:
    out = []
    for x in items:
        r, c = x.replace("r", "").replace("c", ",").strip(",").split(",")
        out.append([int(r), int(c)])
    return out


def cmd_calc(a) -> None:
    d, t = table_of(documents(), a.table_id)
    cells = cells_arg(a.cells)
    c = compute(t, a.op, [CellRef(table_id=t.id, row=r, col=k) for r, k in cells])
    print("입력 셀:", [(f"r{r}c{k}", t.cell(r, k)) for r, k in cells])
    print("정답 문자열(answer에 그대로 넣는다):", c.formatted)
    print("gold_cells:", json.dumps(cells), "| doc_id:", d["id"])


def cmd_review(a) -> None:
    docs = documents()
    for r in load(KO / "custom_eval.jsonl"):
        d, t = table_of(docs, r["table_id"])
        print("=" * 100)
        print(f"{r['qid']} | 범주 {r['category']} | op {r['op']} | 표 {t.id} ({t.title})")
        print("질문:", r["question"])
        print("정답:", r["answer"], "| 다른 표기:", r.get("alt_answers"), "| 보류 사유:", r.get("reason"), "| 메모:", r.get("note"))
        if r["gold_cells"]:
            print("정답 셀:", [(f"r{x}c{y}", t.cell(x, y)) for x, y in r["gold_cells"]])
        print(render(t, {(x, y) for x, y in r["gold_cells"]}))
        if r["op"] == "text" or r.get("needs_text"):
            for p in d.get("passages") or []:
                print(f"[본문 {p['id']}] {p['text'][:600]}")


def cmd_template(a) -> int:
    """Write the review file with one line per question and the verdict left empty. The owner fills in every verdict;
    an empty one does not pass the check, so nothing counts as reviewed before it was looked at."""
    if REVIEW_FILE.exists():
        print(f"이미 있습니다: {REVIEW_FILE.relative_to(ROOT)} (덮어쓰지 않습니다. 새로 만들려면 그 파일을 지우고 다시 실행하세요.)")
        return 1
    lines = [json.dumps({"qid": r["qid"], "verdict": "", "comment": ""}, ensure_ascii=False) for r in load(KO / "custom_eval.jsonl")]
    REVIEW_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"만들었습니다: {REVIEW_FILE.relative_to(ROOT)} ({len(lines)}줄). 줄마다 verdict에 ok, fix, drop 가운데 하나를 적으세요. fix와 drop에는 comment에 까닭을 적습니다.")
    return 0


def check_owner(recs: list[dict], docs: dict[str, dict]) -> list[str]:
    import check_data

    errs: list[str] = []
    splits = split_tables()
    other = {r["question"].strip() for f in ("test", "synthetic_test", "custom_eval") for r in load(KO / f"{f}.jsonl")}
    seen_q, seen_id = set(), set()
    for n, r in enumerate(recs, start=1):
        qid = r.get("qid", f"(줄 {n})")
        missing = [k for k in REQUIRED if k not in r]
        if missing:
            errs.append(f"{qid}: 빠진 항목 {missing}")
            continue
        if not str(qid).startswith("ko_owner_") or qid in seen_id:
            errs.append(f"{qid}: qid는 ko_owner_01처럼 쓰고 겹치면 안 됩니다")
        seen_id.add(qid)
        if r["source"] != "owner":
            errs.append(f'{qid}: source는 "owner"여야 합니다')
        if r["category"] not in CATEGORY_OPS or r["op"] not in CATEGORY_OPS.get(r["category"], set()):
            errs.append(f"{qid}: 범주 {r['category']!r}와 op {r['op']!r}가 맞지 않습니다. 가능한 조합: " + ", ".join(f"{k}→{'/'.join(sorted(v))}" for k, v in CATEGORY_OPS.items()))
        q = str(r["question"]).strip()
        if len(q) < 8:
            errs.append(f"{qid}: 질문이 너무 짧습니다")
        if q in other:
            errs.append(f"{qid}: 기존 평가 문항과 글자까지 같은 질문입니다")
        if q in seen_q:
            errs.append(f"{qid}: 같은 질문이 두 번 있습니다")
        seen_q.add(q)
        if r["table_id"] not in splits["test"] or r["table_id"] in splits["train"] | splits["dev"]:
            errs.append(f"{qid}: 표 {r['table_id']}는 시험 분할의 표가 아닙니다")
        if (r["op"] == "abstain") != (r["answer"] is None):
            errs.append(f"{qid}: 답이 없는 질문(op: abstain)만 answer가 null입니다")
        if r["op"] == "abstain" and r.get("reason") != "not_in_document":
            errs.append(f'{qid}: 보류 문항에는 "reason": "not_in_document"를 적습니다')
        if r["op"] in ("abstain", "text") and r["gold_cells"]:
            errs.append(f"{qid}: op {r['op']}에는 gold_cells를 비웁니다([])")
        if r["op"] == "lookup" and len(r["gold_cells"]) != 1:
            errs.append(f"{qid}: 조회 문항의 gold_cells는 셀 하나입니다([[행, 열]])")
        if bool(r["needs_text"]) != (r["op"] == "text"):
            errs.append(f"{qid}: needs_text는 op가 text일 때만 true입니다")
    ok = [r for r in recs if all(k in r for k in REQUIRED)]
    check_data.errors.clear()
    try:
        check_data.check_records(ok, docs, "ko/owner", verify_gold=True)
    except Exception as e:                       # a malformed gold_cells entry and the like
        errs.append(f"정답 확인 중 오류: {e!r}")
    errs += [e.replace("ko/owner:", "") for e in check_data.errors]
    check_data.errors.clear()
    return errs


def check_review(recs: list[dict]) -> list[str]:
    errs: list[str] = []
    wanted = [r["qid"] for r in load(KO / "custom_eval.jsonl")]
    got = Counter(r.get("qid") for r in recs)
    errs += [f"{q}: 판정이 없습니다" for q in wanted if got[q] == 0]
    errs += [f"{q}: 판정이 {n}번 있습니다" for q, n in got.items() if n > 1]
    errs += [f"{q}: 기존 문항에 없는 qid입니다" for q in got if q not in wanted]
    for r in recs:
        if r.get("verdict") not in VERDICTS:
            errs.append(f"{r.get('qid')}: verdict는 {'/'.join(VERDICTS)} 가운데 하나입니다")
        elif r["verdict"] != "ok" and len(str(r.get("comment", "")).strip()) < 5:
            errs.append(f"{r.get('qid')}: verdict가 {r['verdict']}이면 comment에 까닭을 적습니다")
    return errs


def cmd_check(a) -> int:
    docs = documents()
    bad = 0
    for path, check, label in ((OWNER_FILE, lambda rs: check_owner(rs, docs), "직접 쓴 문항"), (REVIEW_FILE, check_review, "기존 30문항 검수")):
        if not path.exists():
            print(f"{label}: 파일이 아직 없습니다 ({path.relative_to(ROOT)})")
            continue
        try:
            recs = load(path)
        except json.JSONDecodeError as e:
            print(f"{label}: JSON 형식 오류 (줄 {e.lineno}): {e.msg}")
            bad += 1
            continue
        errs = check(recs)
        if path == OWNER_FILE:
            print(f"{label}: {len(recs)}문항 | 범주 {dict(Counter(r.get('category') for r in recs))} | 표 {len({r.get('table_id') for r in recs})}개")
        else:
            print(f"{label}: {len(recs)}건 | 판정 {dict(Counter(r.get('verdict') for r in recs))}")
        for e in errs:
            print("  문제:", e)
        print("  →", "통과" if not errs else f"고칠 것 {len(errs)}건")
        bad += bool(errs)
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tables")
    p.add_argument("--with-passage", action="store_true", help="본문이 있는 문서의 표만")
    p.add_argument("--unused", action="store_true", help="기존 수작업 문항이 쓰지 않은 표만")
    p.set_defaults(fn=cmd_tables)
    p = sub.add_parser("show")
    p.add_argument("table_id")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("calc")
    p.add_argument("table_id")
    p.add_argument("op", choices=sorted(CATEGORY_OPS["calc"]))
    p.add_argument("cells", nargs="+", help="행,열 (예: 0,4 1,4) 또는 r0c4 r1c4")
    p.set_defaults(fn=cmd_calc)
    sub.add_parser("review").set_defaults(fn=cmd_review)
    sub.add_parser("template").set_defaults(fn=cmd_template)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    a = ap.parse_args()
    return a.fn(a) or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:              # output piped into `head` and the like
        sys.exit(0)
