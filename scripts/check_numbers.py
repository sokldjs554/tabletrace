"""README / REPORT numbers must come from artifacts.

Any number wrapped as <!-- num:path/to/file.json:dotted.key[:pct|:int] --> 12.3 <!-- /num --> in README.md or
docs/REPORT.md is compared with the JSON artifact (`:pct` shows 100*value with one decimal, `:int` a rounded integer).
Mismatch -> non-zero exit. Run `--fix` to rewrite. Zero markers is reported as a failure in --strict mode so the
check cannot silently pass on an empty set.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAT = re.compile(r"<!-- num:(?P<file>[^:\s]+):(?P<key>[^:\s]+)(?::(?P<fmt>pct|int))? -->(?P<val>.*?)<!-- /num -->", re.S)


def lookup(obj, key: str):
    for part in key.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return obj


def fmt(v, mode: str | None = None) -> str:
    if mode == "pct":
        return f"{100 * float(v):.1f}"
    if mode == "int":
        return f"{round(float(v)):,}"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:.3f}".rstrip("0").rstrip(".") if abs(v) < 1 else f"{v:,.2f}".rstrip("0").rstrip(".")
    return str(v)


MACRO = re.compile(r"\{\{(?P<file>[^|{}\s]+)\|(?P<key>[^|{}\s]+)(?:\|(?P<fmt>pct|int))?\}\}")


def expand() -> int:
    """Turn {{file|key|fmt}} macros written in README/REPORT prose into verified <!-- num --> markers."""
    n = 0
    for md in [ROOT / "README.md", ROOT / "docs" / "REPORT.md"]:
        if not md.exists():
            continue
        text = md.read_text(encoding="utf-8")

        def sub(m: re.Match) -> str:
            nonlocal n
            v = fmt(lookup(json.loads((ROOT / m.group("file")).read_text(encoding="utf-8")), m.group("key")), m.group("fmt"))
            f_ = f":{m.group('fmt')}" if m.group("fmt") else ""
            n += 1
            return f"<!-- num:{m.group('file')}:{m.group('key')}{f_} -->{v}<!-- /num -->"

        new = MACRO.sub(sub, text)
        if new != text:
            md.write_text(new, encoding="utf-8")
    print(f"expanded {n} macros")
    return 0


def main() -> int:
    if "--expand" in sys.argv:
        return expand()
    fix = "--fix" in sys.argv
    bad = 0
    for md in [ROOT / "README.md", ROOT / "docs" / "REPORT.md"]:
        if not md.exists():
            continue
        text = md.read_text(encoding="utf-8")
        name = md.name

        def repl(m: re.Match, name: str = name) -> str:
            nonlocal bad
            path = ROOT / m.group("file")
            try:
                actual = fmt(lookup(json.loads(path.read_text(encoding="utf-8")), m.group("key")), m.group("fmt"))
            except Exception as e:
                print(f"{name}: cannot resolve {m.group('file')}:{m.group('key')} ({e})")
                bad += 1
                return m.group(0)
            shown = m.group("val").strip()
            if shown != actual:
                print(f"{name}: {m.group('file')}:{m.group('key')} shows {shown!r}, artifact says {actual!r}")
                bad += 1
                if fix:
                    f_ = f":{m.group('fmt')}" if m.group("fmt") else ""
                    return f"<!-- num:{m.group('file')}:{m.group('key')}{f_} -->{actual}<!-- /num -->"
            return m.group(0)

        new = PAT.sub(repl, text)
        if fix and new != text:
            md.write_text(new, encoding="utf-8")
    n = sum(len(PAT.findall((ROOT / f).read_text(encoding="utf-8"))) for f in ["README.md", "docs/REPORT.md"] if (ROOT / f).exists())
    print(f"checked {n} numbers, {bad} mismatches{' (fixed)' if fix and bad else ''}")
    if "--strict" in sys.argv:
        leftovers = []
        for md in [ROOT / "README.md", ROOT / "docs" / "REPORT.md"]:
            if md.exists():
                t = md.read_text(encoding="utf-8")
                leftovers += [f"{md.name}: {tok}" for tok in ("(채움)", "@@PENDING", "{{") if tok in t]
        if leftovers:
            print("unfinished placeholders:", leftovers)
            return 1
    if "--strict" in sys.argv and n == 0:
        print("no <!-- num:... --> markers found: nothing was checked")
        return 1
    return 0 if (bad == 0 or fix) else 1


if __name__ == "__main__":
    sys.exit(main())
