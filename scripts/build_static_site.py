"""Assemble the static demo (console + recorded runs + research results) into a folder for GitHub Pages."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    ap.add_argument("--commit", default="unknown")
    ap.add_argument("--live", action="store_true",
                    help="also fetch the in-browser runtime (scripts/fetch_live_runtime.py) into <out>/live so the demo can run the verifier in the browser")
    a = ap.parse_args()
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "console", out, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (out / ".nojekyll").write_text("")
    (out / "BUILD.txt").write_text(f"commit {a.commit}\n")
    if a.live:
        # A failed download must not take the demo down: without the runtime the page simply does not offer "run it here".
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "fetch_live_runtime.py"), "--out", str(out / "live")])
        print("ok      live runtime" if r.returncode == 0 else "MISSING live runtime (the download failed; the demo is built without it)")
        if r.returncode != 0:
            shutil.rmtree(out / "live", ignore_errors=True)
            (out / "live").mkdir()
    for keep in ("tt_browser.py", "shim", "runtime.lock.json"):      # the sources of the runtime are in tabletrace.zip; the folder holds only what is served
        target = out / "live" / keep
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    for p in ["data/recorded/index.json", "data/recorded/documents.json", "data/research.json", "data/graph.json", "data/examples.json"]:
        print(("ok     " if (out / p).exists() else "MISSING") + " " + p)


if __name__ == "__main__":
    main()
