"""Fetch the in-browser runtime of the demo's "run it here" path into a site folder.

  python scripts/fetch_live_runtime.py --out _site/live            # what the Pages build runs
  python scripts/fetch_live_runtime.py --out _site/live --lock     # re-resolve URLs and digests into console/live/runtime.lock.json

The static demo can run the repository's own verifier, tools and heuristic planner inside the visitor's browser. That
needs a Python runtime compiled to WebAssembly (Pyodide) and pydantic. Nothing binary is kept in the repository: this
script downloads the pinned files named in console/live/runtime.lock.json from the npm registry and PyPI, checks each
against its recorded SHA-256, and writes them next to the site. The repository's own code is added as a zip of the
modules that path uses (src/tabletrace: schema, agent.program, agent.heuristic, tools, verify, retrieval.tokenize,
eval.metrics) together with console/live/tt_browser.py and the stand-in for the Korean tokenizer.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "console" / "live" / "runtime.lock.json"
PYODIDE = "314.0.8"
PYODIDE_FILES = ["pyodide.js", "pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"]
WHEELS = {"pydantic": "2.14.3", "pydantic-core": "2.50.4", "typing-extensions": "4.16.0", "annotated-types": "0.8.0", "typing-inspection": "0.4.5"}
# The modules of this repository the browser path imports (none of them needs torch, LangGraph or the Korean tokenizer's
# compiled extension; the tokenizer is replaced by console/live/shim/kiwipiepy.py, which reads tokens recorded with the real one).
OWN = ["__init__.py", "schema.py", "agent/__init__.py", "agent/program.py", "agent/heuristic.py", "tools/__init__.py", "tools/numbers.py",
       "tools/calculator.py", "tools/cells.py", "tools/registry.py", "verify/__init__.py", "verify/verifier.py", "verify/guard.py",
       "retrieval/__init__.py", "retrieval/tokenize.py", "eval/__init__.py", "eval/metrics.py"]


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def resolve() -> dict:
    """Look the pinned versions up in the registries and record URL, size and SHA-256 of every file."""
    npm = json.loads(_get(f"https://registry.npmjs.org/pyodide/{PYODIDE}"))
    tarball = _get(npm["dist"]["tarball"])
    lock = {"pyodide": {"version": PYODIDE, "url": npm["dist"]["tarball"], "sha256": hashlib.sha256(tarball).hexdigest(), "files": {}}, "wheels": []}
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
        for name in PYODIDE_FILES:
            data = tar.extractfile(f"package/{name}").read()
            lock["pyodide"]["files"][name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    for name, version in WHEELS.items():
        meta = json.loads(_get(f"https://pypi.org/pypi/{name}/{version}/json"))
        files = [u for u in meta["urls"] if u["filename"].endswith(".whl") and ("-none-any" in u["filename"] or "pyemscripten" in u["filename"])]
        assert len(files) == 1, (name, [u["filename"] for u in meta["urls"]])
        u = files[0]
        lock["wheels"].append({"name": name, "version": version, "filename": u["filename"], "url": u["url"], "size": u["size"], "sha256": u["digests"]["sha256"]})
    # what a visitor downloads when they ask for the runtime (the repository's own code adds about 0.06 MB)
    lock["download_mb"] = round((sum(f["size"] for f in lock["pyodide"]["files"].values()) + sum(w["size"] for w in lock["wheels"])) / 1e6, 1)
    return lock


def own_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in OWN:
            z.writestr(zipfile.ZipInfo(f"tabletrace/{rel}", date_time=(2026, 1, 1, 0, 0, 0)), (ROOT / "src" / "tabletrace" / rel).read_bytes())
        # the tokenizer stand-in lives in its own folder so that nothing on a server can import it by accident
        for name, rel in (("tt_browser.py", "tt_browser.py"), ("kiwipiepy.py", "shim/kiwipiepy.py")):
            z.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), (ROOT / "console" / "live" / rel).read_bytes())
    return buf.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site/live")
    ap.add_argument("--lock", action="store_true", help="re-resolve the pinned versions and rewrite the lock file first")
    a = ap.parse_args()
    if a.lock:
        LOCK.write_text(json.dumps(resolve(), indent=1) + "\n", encoding="utf-8")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    out = Path(a.out)
    (out / "pyodide").mkdir(parents=True, exist_ok=True)
    (out / "wheels").mkdir(parents=True, exist_ok=True)
    tarball = _get(lock["pyodide"]["url"])
    assert hashlib.sha256(tarball).hexdigest() == lock["pyodide"]["sha256"], "pyodide tarball does not match the lock"
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
        for name, want in lock["pyodide"]["files"].items():
            data = tar.extractfile(f"package/{name}").read()
            assert hashlib.sha256(data).hexdigest() == want["sha256"], name
            (out / "pyodide" / name).write_bytes(data)
    for w in lock["wheels"]:
        data = _get(w["url"])
        assert hashlib.sha256(data).hexdigest() == w["sha256"], w["filename"]
        (out / "wheels" / w["filename"]).write_bytes(data)
    own = own_zip()
    (out / "tabletrace.zip").write_bytes(own)
    size = sum(f["size"] for f in lock["pyodide"]["files"].values()) + sum(w["size"] for w in lock["wheels"]) + len(own)
    manifest = {"pyodide": lock["pyodide"]["version"], "wheels": [w["filename"] for w in lock["wheels"]], "own": "tabletrace.zip",
                "bytes": size, "download_mb": lock["download_mb"], "own_sha256": hashlib.sha256(own).hexdigest()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"live runtime -> {out}: pyodide {lock['pyodide']['version']}, {len(lock['wheels'])} wheels, own code {len(own) / 1e3:.0f} kB, total {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
