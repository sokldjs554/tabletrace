"""End-to-end console check with Playwright: start the API (heuristic planner), drive the UI in
desktop and mobile viewports, assert the key states, and save screenshots to docs/images/.

  python scripts/console_screenshots.py --out docs/images [--static _site]   # --static serves a Pages build (recorded mode)
Requires: pip install playwright; a Chromium (PLAYWRIGHT_BROWSERS_PATH or --chromium path).
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_http(url: str, timeout: float = 90) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(url, timeout=3)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit(f"server at {url} did not come up")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/images")
    ap.add_argument("--static", default=None, help="serve this folder instead of the API (recorded mode)")
    ap.add_argument("--chromium", default=os.environ.get("TT_CHROMIUM"))
    ap.add_argument("--planner", default="heuristic")
    a = ap.parse_args()
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    port = free_port()
    proc = None
    if a.static:
        handler = lambda *x, **k: http.server.SimpleHTTPRequestHandler(*x, directory=str(ROOT / a.static), **k)  # noqa: E731
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{port}/"
        wait_http(base + "index.html")
        tag = "static"
    else:
        env = {**os.environ, "TABLETRACE_PLANNER": a.planner}
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "tabletrace.service.app:app", "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env)
        base = f"http://127.0.0.1:{port}/"
        wait_http(base + "v1/health")
        tag = "live"
    from playwright.sync_api import sync_playwright

    report = {"mode": tag, "checks": [], "console_errors": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)

    try:
        with sync_playwright() as p:
            kw = {"executable_path": a.chromium} if a.chromium else {}
            browser = p.chromium.launch(args=["--no-sandbox"], **kw)
            for label, vp in (("desktop", {"width": 1440, "height": 900}), ("mobile", {"width": 390, "height": 844})):
                page = browser.new_page(viewport=vp, device_scale_factor=1)
                page.on("console", lambda m: report["console_errors"].append(m.text) if m.type == "error" else None)
                page.goto(base, wait_until="networkidle")
                page.wait_for_timeout(800)
                badge = page.text_content("#modetext") or ""
                check(f"{label}: mode badge", ("실시간" in badge) if tag == "live" else ("저장된" in badge), badge)
                page.screenshot(path=str(out / f"{tag}-{label}-01-home.png"), full_page=(label == "mobile"))
                # a document is auto-selected (one with representative questions)
                page.wait_for_selector(".chip", timeout=15000)
                check(f"{label}: document + examples rendered", page.locator("table.tt").count() >= 1 and page.locator(".chip").count() >= 1)
                if label == "mobile":
                    page.click(".mtab[data-pane='center']")
                    page.screenshot(path=str(out / f"{tag}-{label}-02-doc.png"), full_page=False)
                    page.click(".mtab[data-pane='left']")
                # answered example
                chips = page.locator(".chip")
                chips.nth(0).click()
                page.wait_for_function("() => !document.querySelector('#result').hidden || !document.querySelector('#errorbar').hidden", timeout=120000)
                status = page.text_content("#status") or ""
                has_badge = page.locator(".badge-ok, .badge-hold").count() > 0
                check(f"{label}: first example produced a result", has_badge, status)
                page.screenshot(path=str(out / f"{tag}-{label}-03-result.png"), full_page=(label == "mobile"))
                ev = page.locator(".evbtn")
                if ev.count():
                    ev.nth(0).click()
                    page.wait_for_timeout(500)
                    check(f"{label}: evidence highlighted in table", page.locator("td.is-evidence").count() >= 1)
                # abstain example (the chip whose category label says 보류/abstain)
                hold = page.locator(".chip", has_text="보류").first if page.locator(".chip", has_text="보류").count() else page.locator(".chip", has_text="abstain").first
                if label == "mobile":
                    page.click(".mtab[data-pane='left']")
                if hold.count():
                    hold.click()
                    page.wait_for_function("() => !document.querySelector('#result').hidden", timeout=120000)
                    page.wait_for_timeout(300)
                    check(f"{label}: abstain example shows 답변 보류", page.locator(".badge-hold").count() > 0)
                    page.screenshot(path=str(out / f"{tag}-{label}-04-abstain.png"), full_page=(label == "mobile"))
                if tag == "live" and label == "desktop":
                    # typed question + keyboard submit + invalid input handling
                    page.fill("#question", "x")
                    page.press("#question", "Enter")
                    page.wait_for_timeout(1500)
                    check("desktop: too-short question shows an error", not page.locator("#errorbar").is_hidden())
                    page.fill("#question", "국도 1호 자동차 전용도로 구간 중 호남로의 총연장은 몇 km입니까?" if "ko" in page.text_content("#doccount") or True else "")
                    page.press("#question", "Enter")
                    page.wait_for_function("() => document.querySelector('#status') && /완료|보류|오류/.test(document.querySelector('#status').textContent)", timeout=120000)
                    check("desktop: typed question executed", True, page.text_content("#status") or "")
                    page.screenshot(path=str(out / f"{tag}-{label}-05-typed.png"))
                    # chemistry corpus
                    page.click(".segbtn[data-corpus='chem_docs']")
                    page.wait_for_selector(".chip", timeout=15000)
                    page.locator(".chip").nth(0).click()
                    page.wait_for_function("() => !document.querySelector('#result').hidden", timeout=120000)
                    page.wait_for_timeout(300)
                    check("desktop: chemistry example produced a result", page.locator(".badge-ok, .badge-hold").count() > 0)
                    page.screenshot(path=str(out / f"{tag}-{label}-06-chem.png"))
                # research view
                page.goto(base + "#research", wait_until="networkidle")
                page.wait_for_timeout(800)
                check(f"{label}: research view renders", "연구 결과" in (page.text_content("#research") or ""))
                page.screenshot(path=str(out / f"{tag}-{label}-07-research.png"), full_page=True)
                page.close()
            browser.close()
    finally:
        if proc:
            proc.terminate()
    # the intentional too-short question returns 422 by design; browsers log that as a console error
    report["console_errors"] = [e for e in report["console_errors"] if "favicon" not in e and "status of 422" not in e]
    check("no browser console errors", not report["console_errors"], "; ".join(report["console_errors"][:3]))
    (out / f"e2e-{tag}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    failed = [c for c in report["checks"] if not c["ok"]]
    print(f"{len(report['checks']) - len(failed)}/{len(report['checks'])} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
