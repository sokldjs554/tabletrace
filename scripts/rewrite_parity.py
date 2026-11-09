"""Behaviour check for the owner's rewrite of a core module (docs/rewrite/README.md).

Unit tests check a few examples; this script runs the reference implementation (taken from a git ref,
default origin/main) and the working-tree implementation over the project's REAL data and stored model
outputs, and reports every input on which they disagree. A rewrite that passes the tests but parses
2,000 corpus cells differently would change the saved evaluation results; this is how that shows up.

  python scripts/rewrite_parity.py numbers      # tools/numbers.py: parse_number on every table cell, header_unit on every header, format_number
  python scripts/rewrite_parity.py calculator   # tools/calculator.py: compute() on every gold calculation in the datasets
  python scripts/rewrite_parity.py program      # agent/program.py: parse()+serialize() on every stored model output and gold program
  python scripts/rewrite_parity.py cells        # tools/cells.py: normalize_text, lookup_cell, find_cells, row/column overlap scores over the corpora and every question
  python scripts/rewrite_parity.py verifier     # verify/verifier.py: resolve() on every stored model output (8.6k) and gold program, 3 settings each; find_span probes
  python scripts/rewrite_parity.py numbers --ref <commit>     # compare against another commit

Each side runs in its own Python process (reference from `git archive <ref> src`), so the two packages
never mix. Exit code 1 when anything differs. Written by the AI coding tool as review tooling; it is
not part of the rewrite.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPORA = ["data/ko/documents.jsonl", "data/chem/documents.jsonl"]
CALC_RECORDS = ["data/ko/synthetic_train.jsonl", "data/ko/synthetic_dev.jsonl", "data/ko/synthetic_test.jsonl",
                "data/chem/synthetic_train.jsonl", "data/chem/synthetic_dev.jsonl", "data/ko/custom_eval.jsonl",
                "data/chem/custom_eval.jsonl"]

# Runs inside the child process with PYTHONPATH pointing at one implementation. Prints one JSON object.
CHILD = r'''
import glob, json, sys
mode, root = sys.argv[1], sys.argv[2]
out = {}
def tables():
    for path in __CORPORA__:
        for line in open(f"{root}/{path}", encoding="utf-8"):
            for t in json.loads(line).get("tables", []):
                yield t
if mode == "numbers":
    from tabletrace.tools.numbers import format_number, header_unit, parse_number
    values = set()
    for t in tables():
        for h in t["header"]:
            out["header:" + h] = header_unit(h)
        for row in t["rows"]:
            for c in row:
                p = parse_number(c)
                out["cell:" + c] = None if p is None else [round(p.value, 9), p.unit]
                if p is not None:
                    values.add(p.value)
    for v in sorted(values) + [0.0, 1e-4, 9.99e-4, 1e-3, 99999.5, 1e5 + 0.5, 123456.7, 1e15, 2.5e15, -0.5, -123456.7]:
        out["format:" + repr(v)] = format_number(v)
elif mode == "calculator":
    from tabletrace.schema import CellRef, Table
    from tabletrace.tools.calculator import CalcError, compute
    by_id = {t["id"]: Table(**t) for t in tables()}
    for path in __RECORDS__:
        try:
            lines = open(f"{root}/{path}", encoding="utf-8").readlines()
        except FileNotFoundError:
            continue
        for line in lines:
            r = json.loads(line)
            op, cells, tid = r.get("op"), r.get("gold_cells") or [], r.get("table_id")
            if op not in ("diff", "sum", "avg", "ratio", "pct_change", "count") or tid not in by_id:
                continue
            refs = [CellRef(table_id=tid, row=a, col=b) for a, b in cells]
            key = f"{r['qid']}:{op}"
            try:
                c = compute(by_id[tid], op, refs)
                out[key] = [c.expression, round(c.result, 9), c.unit, c.formatted]
            except CalcError as e:
                out[key] = ["CalcError", str(e).split(":")[0][:40]]
            # every op on the same cells too, so ops the datasets never use are exercised
            for other in ("diff", "sum", "avg", "ratio", "pct_change", "count"):
                try:
                    c = compute(by_id[tid], other, refs)
                    out[f"{key}->{other}"] = [c.expression, round(c.result, 9), c.unit, c.formatted]
                except CalcError:
                    out[f"{key}->{other}"] = "CalcError"
elif mode == "cells":
    import re
    from tabletrace.schema import Table
    from tabletrace.tools.cells import column_overlap_scores, find_cells, lookup_cell, normalize_text, row_overlap_scores
    by_id = {}
    for t in tables():
        tab = Table(**t)
        by_id[tab.id] = tab
        for h in tab.header:
            out["norm:" + h] = normalize_text(h)
        for row in tab.rows:
            for c in row:
                out["norm:" + c] = normalize_text(c)
        # every row's first and last cell, plus one cell past each edge
        for r in range(-1, len(tab.rows) + 1):
            for c in (-1, 0, len(tab.header) - 1, len(tab.header)):
                try:
                    out[f"lookup:{tab.id}:{r}:{c}"] = lookup_cell(tab, r, c)
                except Exception as e:
                    out[f"lookup:{tab.id}:{r}:{c}"] = type(e).__name__
    qfiles = ["data/ko/test.jsonl", "data/ko/synthetic_test.jsonl", "data/ko/dev.jsonl", "data/ko/custom_eval.jsonl",
              "data/chem/custom_eval.jsonl", "data/chem/synthetic_dev.jsonl"]
    for path in qfiles:
        try:
            lines = open(f"{root}/{path}", encoding="utf-8").readlines()
        except FileNotFoundError:
            continue
        for line in lines:
            r = json.loads(line)
            tab = by_id.get(r.get("table_id"))
            if tab is None:
                continue
            q = r.get("question", "")
            out["normq:" + q] = normalize_text(q)
            toks = {normalize_text(t) for t in q.split()} | {normalize_text(t) for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9\.\-]+", q)} | {""}
            out[f"rows:{r['qid']}"] = row_overlap_scores(tab, toks)
            out[f"rows-ex0:{r['qid']}"] = row_overlap_scores(tab, toks, exclude_col=0)
            out[f"cols:{r['qid']}"] = column_overlap_scores(tab, toks)
            for probe in (str(r.get("answer", "")), q[:6], " " + str(r.get("answer", "")).upper() + " ", ""):
                out[f"find:{r['qid']}:{probe}:exact"] = [c.cid for c in find_cells(tab, probe)]
                out[f"find:{r['qid']}:{probe}:contains"] = [c.cid for c in find_cells(tab, probe, exact=False)]
elif mode == "verifier":
    from pathlib import Path
    from tabletrace.agent.program import ProgramParseError, parse
    from tabletrace.model.approx_tokenizer import ApproxTokenizer
    from tabletrace.training.data import build_examples, load_docs
    from tabletrace.verify.verifier import find_span, resolve
    def summary(res):
        return {"status": res.status, "answer": res.answer, "cells": [c.cid for c in res.cells],
                "reason": res.verdict.reason, "checks": [[c.name, c.passed] for c in res.verdict.checks],
                "calc": None if res.calculation is None else [res.calculation.op, res.calculation.expression, res.calculation.formatted],
                "spans": [[s.passage_id, s.start, s.end, s.text] for s in res.spans],
                "trace": [[t.step, t.tool, t.status, json.dumps(t.input, sort_keys=True, ensure_ascii=False)] for t in res.trace]}
    sets = [(["data/ko/test.jsonl", "data/ko/synthetic_test.jsonl", "data/ko/dev.jsonl", "data/ko/synthetic_dev.jsonl", "data/ko/custom_eval.jsonl"], ["data/ko/documents.jsonl"]),
            (["data/chem/custom_eval.jsonl", "data/chem/synthetic_dev.jsonl"], ["data/chem/documents.jsonl"])]
    examples = {}
    tok = ApproxTokenizer()
    for recs_paths, corpus in sets:
        docs = load_docs(*[Path(root) / c for c in corpus])
        recs = [json.loads(line) for p in recs_paths for line in open(f"{root}/{p}", encoding="utf-8")]
        for e in build_examples(recs, docs, tok, 512):
            examples[e.qid] = e
    raws = {}
    for path in sorted(glob.glob(f"{root}/experiments/eval/*/predictions.jsonl")):
        for line in open(path, encoding="utf-8"):
            r = json.loads(line)
            if r["qid"] in examples:
                raws.setdefault((r["qid"], r.get("raw_output") or ""), None)
    for (qid, raw) in sorted(raws):
        e = examples[qid]
        try:
            prog = parse(raw, e.table.id)
        except ProgramParseError:
            prog = None
        for name, kw in (("v1", {"entity_check": False}), ("v2", {"entity_check": True}), ("v2col", {"entity_check": True, "column_check": True})):
            out[f"pred:{name}:{qid}:{raw}"] = summary(resolve(e.question, e.table, prog, context=e.context, **kw))
    for qid, e in sorted(examples.items()):
        out[f"gold:{qid}"] = summary(resolve(e.question, e.table_full or e.table, e.gold, context=e.context_full or e.context, entity_check=True))
        out[f"noretrieval:{qid}"] = summary(resolve(e.question, e.table, e.gold, retrieval_ok=False))
        out[f"notable:{qid}"] = summary(resolve(e.question, None, e.gold))
    # find_span: passages from the corpora, probed with exact, case-changed, whitespace-changed and absent strings
    for c in __CORPORA__ + ["data/ko/documents.jsonl"]:
        for line in open(f"{root}/{c}", encoding="utf-8"):
            for ps in json.loads(line).get("passages", [])[:2]:
                t = ps.get("text", "")[:600]
                if len(t) < 40:
                    continue
                for probe in (t[10:30], t[10:30].upper(), t[10:30].replace(" ", ""), t[10:30].replace(" ", "  "), " " + t[200:215] + " ", "zzz_not_there", "", t[:5] * 50):
                    sp = find_span(probe, t, "p")
                    out[f"span:{t[:20]}:{probe[:40]}"] = None if sp is None else [sp.passage_id, sp.start, sp.end, sp.text]
elif mode == "program":
    from tabletrace.agent.program import ProgramParseError, parse, serialize
    raws = set()
    for path in glob.glob(f"{root}/experiments/eval/*/predictions.jsonl"):
        for line in open(path, encoding="utf-8"):
            raws.add(json.loads(line).get("raw_output") or "")
    for raw in sorted(raws):
        try:
            p = parse(raw, "t")
            out["raw:" + raw] = serialize(p)
        except ProgramParseError:
            out["raw:" + raw] = "ProgramParseError"
print(json.dumps(out, ensure_ascii=False))
'''.replace("__CORPORA__", repr(CORPORA)).replace("__RECORDS__", repr(CALC_RECORDS))


def run(mode: str, src: Path) -> dict:
    r = subprocess.run([sys.executable, "-c", CHILD, mode, str(ROOT)], capture_output=True, text=True,
                       env={"PYTHONPATH": str(src), "PATH": "/usr/bin:/bin:/usr/local/bin"}, cwd=ROOT)
    if r.returncode != 0:
        sys.exit(f"{src}: child failed\n{r.stderr[-2000:]}")
    return json.loads(r.stdout)


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] not in ("numbers", "calculator", "program", "cells", "verifier"):
        sys.exit(__doc__)
    mode = args[0]
    ref = args[args.index("--ref") + 1] if "--ref" in args else "origin/main"
    with tempfile.TemporaryDirectory() as tmp:
        archive = subprocess.run(["git", "archive", ref, "src"], capture_output=True, cwd=ROOT)
        if archive.returncode != 0:
            sys.exit(f"git archive {ref} failed: {archive.stderr.decode()[-500:]}")
        subprocess.run(["tar", "-x", "-C", tmp], input=archive.stdout, check=True)
        reference = run(mode, Path(tmp) / "src")
    current = run(mode, ROOT / "src")
    keys = sorted(set(reference) | set(current))
    diffs = [(k, reference.get(k, "<missing>"), current.get(k, "<missing>")) for k in keys if reference.get(k) != current.get(k)]
    kinds: dict[str, int] = {}
    for k, _, _ in diffs:
        kind = ("other op " + k.split("->")[1]) if "->" in k else ("gold op " + k.rsplit(":", 1)[1]) if mode == "calculator" else k.split(":")[0]
        kinds[kind] = kinds.get(kind, 0) + 1
    print(f"{mode}: {len(keys)} inputs compared against {ref}, {len(diffs)} differ {kinds or ''}")
    for k, a, b in diffs[:25]:
        print(f"  {k[:90]!r}\n      reference: {a}\n      yours:     {b}")
    if len(diffs) > 25:
        print(f"  ... {len(diffs) - 25} more")
    sys.exit(1 if diffs else 0)


if __name__ == "__main__":
    main()
