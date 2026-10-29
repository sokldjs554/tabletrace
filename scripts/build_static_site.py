"""Assemble the static demo (console + recorded runs + research results) into a folder for GitHub Pages."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    ap.add_argument("--commit", default="unknown")
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "console", out)
    (out / ".nojekyll").write_text("")
    (out / "BUILD.txt").write_text(f"commit {a.commit}\n")
    for p in ["data/recorded/index.json", "data/recorded/documents.json", "data/research.json", "data/graph.json", "data/examples.json"]:
        print(("ok     " if (out / p).exists() else "MISSING") + " " + p)


if __name__ == "__main__":
    main()
