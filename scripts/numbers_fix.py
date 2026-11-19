"""Regenerate the data that tools/numbers.py feeds, and measure what a change to it does (docs/rewrite/09_numbers_fix.md).

`header_unit` runs when the corpora are built and its result is stored with each table (`units` in data/*/documents.jsonl).
The synthetic questions take their answers from the calculator, which writes numbers with `format_number` and units
from those stored units. The raw sources the corpora were built from are not in the repository, so after a change to
either function this script refreshes the stored units from the stored headers and rebuilds the synthetic sets.

  python scripts/numbers_fix.py data      # refresh `units` in the three documents files, rebuild data/{ko,chem}/synthetic_*.jsonl
  python scripts/numbers_fix.py impact    # compare with origin/main: cells, headers, number formats, stored units, synthetic answers,
                                          # and the verdict on every stored model output (takes about 20 minutes)
  python scripts/numbers_fix.py impact --ref 4fdbbd8 --out experiments/eval/numbers_fix_impact.json     # the owner's fix (PR #10) against main before it

`data` keeps units that were set by hand (a table whose stored units are neither what the reference implementation
nor what the working tree gives). Written by the AI coding tool; it does not change tools/numbers.py.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))      # this checkout's code, not an installed copy
CORPORA = ["data/ko/documents.jsonl", "data/chem/documents.jsonl", "data/chem_papers/documents.jsonl"]
SYNTHETIC = ["data/ko/synthetic_train.jsonl", "data/ko/synthetic_dev.jsonl", "data/ko/synthetic_test.jsonl",
             "data/chem/synthetic_train.jsonl", "data/chem/synthetic_dev.jsonl"]


def archive(ref: str, paths: list[str], into: Path) -> None:
    a = subprocess.run(["git", "archive", ref, *paths], capture_output=True, cwd=ROOT)
    if a.returncode != 0:
        sys.exit(f"git archive {ref} failed: {a.stderr.decode()[-500:]}")
    subprocess.run(["tar", "-x", "-C", str(into)], input=a.stdout, check=True)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def derive(hu, header: list[str]) -> dict[str, str]:
    return {str(j): u for j, h in enumerate(header) if (u := hu(h))}


# ---------------------------------------------------------------- data

def cmd_data(ref: str) -> None:
    from tabletrace.tools.numbers import header_unit as new_hu
    with tempfile.TemporaryDirectory() as tmp:
        archive(ref, ["src/tabletrace/tools/numbers.py"], Path(tmp))
        old_hu = load_module(Path(tmp) / "src/tabletrace/tools/numbers.py", "reference_numbers").header_unit
    for corpus in CORPORA:
        path = ROOT / corpus
        lines = path.read_text(encoding="utf-8").splitlines()
        out, changed, kept = [], 0, []
        for line in lines:
            d = json.loads(line)
            for t in d.get("tables", []):
                stored = {str(k): v for k, v in (t.get("units") or {}).items()}
                new = derive(new_hu, t["header"])
                if stored in (derive(old_hu, t["header"]), new):
                    if stored != new:
                        t["units"] = new
                        changed += 1
                else:
                    kept.append(t["id"])               # set by hand when the corpus was built: leave it
            out.append(json.dumps(d, ensure_ascii=False))
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"{corpus}: units changed in {changed} tables" + (f", kept the hand-set units of {kept}" if kept else ""))
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    for script in ("scripts/data/synth_ko.py", "scripts/data/synth_chem.py"):
        subprocess.run([sys.executable, script], cwd=ROOT, env=env, check=True, stdout=subprocess.DEVNULL)
    print("rebuilt the synthetic sets. What changed in the data:")
    subprocess.run(["git", "diff", "--stat", "--", "data"], cwd=ROOT)


# ---------------------------------------------------------------- impact

def child(code: str, mode: str, src: Path, root: Path) -> dict:
    r = subprocess.run([sys.executable, "-c", code, mode, str(root)], capture_output=True, text=True, cwd=root,
                       env={"PYTHONPATH": str(src), "PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    if r.returncode != 0:
        sys.exit(f"{src}: child failed\n{r.stderr[-2000:]}")
    return json.loads(r.stdout)


def records(root: Path, rel: str) -> dict[str, dict]:
    return {r["qid"]: r for r in map(json.loads, (root / rel).read_text(encoding="utf-8").splitlines())}


def cmd_impact(ref: str, out_path: str | None) -> None:
    from rewrite_parity import CHILD
    from rewrite_parity import CORPORA as PARITY_CORPORA
    assert f"for path in {PARITY_CORPORA!r}:" in CHILD, "rewrite_parity.py changed: update numbers_fix.py"
    code = CHILD.replace(f"for path in {PARITY_CORPORA!r}:", f"for path in {[*PARITY_CORPORA, 'data/chem_papers/documents.jsonl']!r}:")
    old_sets = '''(["data/chem/custom_eval.jsonl", "data/chem/synthetic_dev.jsonl"], ["data/chem/documents.jsonl"])]'''
    assert old_sets in code, "rewrite_parity.py changed: update numbers_fix.py"
    code = code.replace(old_sets, old_sets[:-1] + ''',
            (["data/chem_papers/custom_eval.jsonl"], ["data/chem_papers/documents.jsonl"])]''')
    report: dict = {"reference": ref}
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        archive(ref, ["src", "data"], base)
        os.symlink(ROOT / "experiments", base / "experiments")      # the stored model outputs are the same on both sides
        # 1. the functions themselves: parse_number on every cell, header_unit on every header, format_number on every number read
        old, new = child(code, "numbers", base / "src", base), child(code, "numbers", ROOT / "src", ROOT)
        diffs = {k: [old.get(k), new.get(k)] for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)}
        report["functions"] = {"inputs": len(set(old) | set(new)), "differ": diffs}
        print(f"functions: {len(set(old) | set(new))} inputs, {len(diffs)} differ")
        for k, (a, b) in list(diffs.items())[:40]:
            print(f"  {k[:70]!r}: {a!r} -> {b!r}")
        # 2. stored units
        units = []
        for corpus in CORPORA:
            ot = {t["id"]: t for line in (base / corpus).read_text(encoding="utf-8").splitlines() for t in json.loads(line).get("tables", [])}
            for line in (ROOT / corpus).read_text(encoding="utf-8").splitlines():
                for t in json.loads(line).get("tables", []):
                    if t["id"] in ot and ot[t["id"]].get("units") != t.get("units"):
                        units.append([t["id"], ot[t["id"]].get("units"), t.get("units")])
        report["table_units"] = units
        print(f"stored units: {len(units)} tables changed")
        for u in units:
            print(f"  {u[0]}: {u[1]} -> {u[2]}")
        # 3. synthetic questions
        synth = {}
        for rel in SYNTHETIC:
            a, b = records(base, rel), records(ROOT, rel)
            changed = {q: [a.get(q, {}).get("answer"), b.get(q, {}).get("answer")] for q in sorted(set(a) | set(b)) if a.get(q) != b.get(q)}
            synth[rel] = changed
            print(f"{rel}: {len(changed)} of {len(b)} records changed")
            for q, (x, y) in list(changed.items())[:12]:
                print(f"  {q}: {x!r} -> {y!r}")
        report["synthetic"] = synth
        # 4. the verdict on every stored model output (3 verifier settings) and every gold program
        old, new = child(code, "verifier", base / "src", base), child(code, "verifier", ROOT / "src", ROOT)
        keys = sorted(set(old) | set(new))
        vd = {k: [old.get(k), new.get(k)] for k in keys if old.get(k) != new.get(k)}
        report["verdicts"] = {"inputs": len(keys), "differ": vd}
        print(f"verdicts: {len(keys)} stored outputs and gold programs re-verified, {len(vd)} differ")
        for k, (a, b) in list(vd.items())[:12]:
            print(f"  {k[:90]!r}\n     before: {a and {x: a[x] for x in ('status', 'answer', 'reason')}}\n     after:  {b and {x: b[x] for x in ('status', 'answer', 'reason')}}")
    fd = report["functions"]["differ"]
    report["summary"] = {                       # the counts the documents quote
        "reference_commit": subprocess.run(["git", "rev-parse", "--short", ref], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
        "function_inputs": report["functions"]["inputs"],
        "cells_read_differently": sum(k.startswith("cell:") for k in fd),
        "headers_changed": sum(k.startswith("header:") for k in fd),
        "formats_changed": sum(k.startswith("format:") for k in fd),
        "tables_whose_units_changed": len(report["table_units"]),
        "synthetic_answers_changed": {rel.split("data/")[1].replace("/", "_").replace(".jsonl", ""): len(ch) for rel, ch in report["synthetic"].items()},
        "synthetic_answers_changed_total": sum(len(ch) for ch in report["synthetic"].values()),
        "verdict_inputs": report["verdicts"]["inputs"],
        "verdicts_changed": len(report["verdicts"]["differ"]),
    }
    print("summary:", report["summary"])
    if out_path:
        Path(out_path).write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("wrote", out_path)


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] not in ("data", "impact"):
        sys.exit(__doc__)
    ref = args[args.index("--ref") + 1] if "--ref" in args else "origin/main"
    if args[0] == "data":
        cmd_data(ref)
    else:
        cmd_impact(ref, args[args.index("--out") + 1] if "--out" in args else None)


if __name__ == "__main__":
    main()
