"""Build ONE self-contained HTML page of the static demo (console + recorded runs + research results).

  python scripts/build_artifact_page.py --out dist/artifact/tabletrace-workbench.html --commit <sha>

Used for hosting the stored-results demo as a claude.ai Artifact when GitHub Pages is not reachable. The page has no
backend, so it always runs in the "stored results" mode: `fetchJSON` answers `data/...` from an embedded object and
refuses `v1/...` (the live API), which is exactly what the console already treats as "no backend". Nothing is fetched
from the network. The Artifact skeleton supplies <html>/<head>/<body>, so the output has only <title>, <style>, the body
content and scripts.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "console"
DATA_FILES = ["data/examples.json", "data/recorded/index.json", "data/recorded/documents.json", "data/research.json", "data/graph.json"]
TITLE = "TableTrace Workbench"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/artifact/tabletrace-workbench.html")
    ap.add_argument("--commit", default="unknown")
    a = ap.parse_args()
    html = (CONSOLE / "index.html").read_text(encoding="utf-8")
    css = (CONSOLE / "styles.css").read_text(encoding="utf-8")
    js = (CONSOLE / "app.js").read_text(encoding="utf-8")
    body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    body = re.sub(r'<script src="app.js"></script>', "", body).strip()
    data = {p: json.loads((CONSOLE / p).read_text(encoding="utf-8")) for p in DATA_FILES}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    old = "async function fetchJSON(url, opts = {}, timeoutMs = 8000) {"
    assert old in js, "fetchJSON signature changed; update build_artifact_page.py"
    js = js.replace(old, old + '''
    // single-file build: data files come from the embedded object, the live API does not exist
    if (url.startsWith("data/")) { if (window.__TT_DATA__[url] === undefined) throw new Error("missing " + url); return JSON.parse(JSON.stringify(window.__TT_DATA__[url])); }
    if (url.startsWith("v1/")) throw new Error("no backend in the single-file demo");''', 1)
    out = f"""<title>{TITLE}</title>
<meta name="description" content="Stored-results demo of TableTrace. Build {a.commit}.">
<style>
{css}
</style>
{body}
<script>window.__TT_DATA__ = {blob};</script>
<script>
{js}
</script>
"""
    dest = ROOT / a.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out, encoding="utf-8")
    print(f"wrote {dest} ({dest.stat().st_size / 1e3:.0f} kB)")


if __name__ == "__main__":
    main()
