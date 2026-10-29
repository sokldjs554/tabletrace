"""README / REPORT numbers must come from artifacts.

Any number wrapped as <!-- num:path/to/file.json:dotted.key --> 12.3 <!-- /num --> in README.md or
docs/REPORT.md is compared with the JSON artifact. Mismatch -> non-zero exit. Run `--fix` to rewrite.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAT = re.compile(r"<!-- num:(?P<file>[^:\s]+):(?P<key>[^\s]+) -->(?P<val>.*?)<!-- /num -->", re.S)


def lookup(obj, key: str):
    for part in key.split("."):
        if isinstance(obj, list):
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return obj


def fmt(v) -> str:
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:.3f}".rstrip("0").rstrip(".") if abs(v) < 1 else f"{v:,.1f}".rstrip("0").rstrip(".")
    return str(v)


def main() -> int:
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
                actual = fmt(lookup(json.loads(path.read_text(encoding="utf-8")), m.group("key")))
            except Exception as e:
                print(f"{name}: cannot resolve {m.group('file')}:{m.group('key')} ({e})")
                bad += 1
                return m.group(0)
            shown = m.group("val").strip()
            if shown != actual:
                print(f"{name}: {m.group('file')}:{m.group('key')} shows {shown!r}, artifact says {actual!r}")
                bad += 1
                if fix:
                    return f"<!-- num:{m.group('file')}:{m.group('key')} -->{actual}<!-- /num -->"
            return m.group(0)

        new = PAT.sub(repl, text)
        if fix and new != text:
            md.write_text(new, encoding="utf-8")
    n = sum(len(PAT.findall((ROOT / f).read_text(encoding="utf-8"))) for f in ["README.md", "docs/REPORT.md"] if (ROOT / f).exists())
    print(f"checked {n} numbers, {bad} mismatches{' (fixed)' if fix and bad else ''}")
    return 0 if (bad == 0 or fix) else 1


if __name__ == "__main__":
    sys.exit(main())
