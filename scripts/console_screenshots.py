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
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console" / "live"))
import tt_browser  # noqa: E402  (the file the browser runs; called here too, to compare)

from tabletrace.schema import Document  # noqa: E402


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

    for stale in (out / f"e2e-{tag}.json",):   # never leave an old passing report behind if this run crashes
        stale.unlink(missing_ok=True)
    report = {"mode": tag, "checks": [], "console_errors": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)

    try:
        with sync_playwright() as p:
            kw = {"executable_path": a.chromium} if a.chromium else {}
            browser = p.chromium.launch(args=["--no-sandbox"], **kw)
            for label, vp in (("desktop", {"width": 1440, "height": 900}), ("mobile", {"width": 390, "height": 844})):
                page = None
                try:
                    page = browser.new_page(viewport=vp, device_scale_factor=1)
                    page.on("console", lambda m: report["console_errors"].append(m.text) if m.type == "error" else None)
                    page.on("pageerror", lambda e: report["console_errors"].append("page error: " + str(e)))
                    mobile = label == "mobile"

                    def pane(name: str, mobile: bool = mobile, page=page) -> None:
                        if mobile:
                            page.click(f".mtab[data-pane='{name}']")

                    def shown(page=page) -> None:
                        page.wait_for_function("() => !document.querySelector('#result').hidden || !document.querySelector('#errorbar').hidden", timeout=120000)
                        page.wait_for_timeout(300)

                    def open_question(qid: str, planner: str, page=page) -> None:
                        """Open one prepared question: a link in recorded mode; in live mode the link selects it and the chip runs it."""
                        page.goto(f"{base}#workbench/{qid}/{planner}", wait_until="networkidle")
                        page.wait_for_selector(f".chip[data-ex='{qid}']", state="attached", timeout=15000)
                        if tag == "live":
                            pane("left")
                            page.click(f".chip[data-ex='{qid}']")
                        shown()

                    page.goto(base, wait_until="networkidle")
                    page.wait_for_timeout(800)
                    badge = page.text_content("#modetext") or ""
                    check(f"{label}: mode badge", ("실시간" in badge) if tag == "live" else ("저장된" in badge), badge)
                    data = page.evaluate("async () => (await (await fetch('data/examples.json')).json())")
                    examples = data["examples"]
                    if tag == "static":
                        # The static demo opens on a walk through three stored results, one question at a time. Which three is decided
                        # when the results are recorded (index.tour); here the page is held against those runs.
                        page.wait_for_selector(".tour-q", timeout=15000)
                        idx0 = page.evaluate("async () => (await (await fetch('data/recorded/index.json')).json())")
                        scenes = idx0["tour"]["scenes"]

                        def scene(page=page) -> dict:
                            return page.evaluate("""() => { const g = document.querySelector('.tour-grid'), a = document.querySelector('.tv-answer');
                                const cells = (c) => [...document.querySelectorAll('td.' + c)].map((e) => e.dataset.trc);
                                return { kind: g.dataset.kind, ex: g.dataset.ex, answer: a.textContent, held: a.classList.contains('tv-held'), top: a.getBoundingClientRect().top,
                                    gold: document.querySelector('.tour-gold').textContent, ev: cells('tv-ev'), cited: cells('tv-cited'), written: (document.querySelector('.tv-kv .tv-off') || {}).textContent || '',
                                    verdict: document.querySelector('.tour-steps > li:nth-child(3)').textContent, tool: document.querySelector('.tour-steps > li:nth-child(2)').textContent,
                                    steps: document.querySelectorAll('.tour-steps > li').length, tabs: document.querySelectorAll('.navlink[data-view]').length,
                                    active: (document.querySelector('.navlink.is-active') || {}).textContent || '', why: document.querySelector('.tour-why').textContent,
                                    over: document.documentElement.scrollWidth - document.documentElement.clientWidth }; }""")

                        def stored(i: int, idx0=idx0, scenes=scenes) -> dict:
                            return next(r for r in idx0["planners"][scenes[i]["planner"]]["runs"] if r["id"] == scenes[i]["id"])["result"]

                        def to_scene(n: int, kind: str, page=page) -> dict:
                            page.locator(".tour-tab").nth(n).click()
                            page.wait_for_function(f"() => document.querySelector('.tour-grid').dataset.kind === '{kind}'", timeout=15000)
                            page.wait_for_timeout(200)
                            return scene()

                        ids = lambda cells: [f"r{c['row']}c{c['col']}" for c in cells]  # noqa: E731
                        s1 = scene()
                        check(f"{label}: the first screen walks through one question: the proposal, the tool, the verifier, the answer and its gold answer, without a click",
                              s1["kind"] == "recalc" and s1["ex"] == scenes[0]["id"] and s1["answer"] == stored(0)["answer"] and "정답" in s1["gold"] and "맞음" in s1["gold"]
                              and sorted(s1["ev"]) == sorted(ids(stored(0)["evidence_cells"])) and s1["steps"] == 3 and (mobile or 0 < s1["top"] < vp["height"]),
                              f"answer {s1['answer']!r} at y={s1['top']:.0f} of {vp['height']}, cells {s1['ev']}, {s1['gold'][:20]!r}")
                        # the first scene: the model wrote a number that is not what its two cells give; the answer shown is the tool's value
                        wrote = next(t["output"]["parsed"]["answer"] for t in stored(0)["trace"] if t["step"] == "propose" and t["output"] and t["output"].get("parsed"))
                        computed = stored(0)["calculation"]["formatted"]
                        check(f"{label}: first scene: the number the model wrote is struck out and the tool's value is the answer",
                              s1["written"] == wrote != computed == s1["answer"] and wrote in s1["verdict"] and computed in s1["verdict"] and computed in s1["tool"]
                              and not s1["cited"], f"model wrote {s1['written']!r}, tool {computed!r}, answer {s1['answer']!r}")
                        check(f"{label}: two tabs, and the first screen fits the width", s1["tabs"] == 2 and "한눈에" in s1["active"] and s1["over"] <= 1,
                              f"{s1['tabs']} tabs, active {s1['active']!r}, overflow {s1['over']}px")
                        page.screenshot(path=str(out / f"{tag}-{label}-00-tour.png"), full_page=mobile)
                        s2 = to_scene(1, "repair")
                        check(f"{label}: second scene: a right answer whose cited cell the verifier replaced",
                              s2["answer"] == stored(1)["answer"] and s2["ev"] == ids(stored(1)["evidence_cells"]) and bool(s2["cited"]) and not set(s2["cited"]) & set(s2["ev"])
                              and "맞음" in s2["gold"], f"cited {s2['cited']}, evidence {s2['ev']}, {s2['answer']!r}")
                        side = page.evaluate("""() => { const sc = document.querySelector('.tour-doc .tablescroll'), h = document.querySelector('.tv-side'), edge = sc.getBoundingClientRect().right;
                            return { over: sc.scrollWidth - sc.clientWidth, shown: !h.hidden, text: h.textContent,
                                     out: [...sc.querySelectorAll('td.tv-ev, td.tv-cited')].filter(td => td.getBoundingClientRect().right > edge + 1).length }; }""")
                        check(f"{label}: a table wider than the screen says so, and says when a marked cell is out of view",
                              side["shown"] == (side["over"] > 20) and ((("오른쪽" in side["text"]) == (side["out"] > 0)) if side["shown"] else side["out"] == 0),
                              f"overflow {side['over']}px, {side['out']} marked cell(s) out of view, " + (f"hint {side['text'][:26]!r}" if side["shown"] else "no hint"))
                        page.screenshot(path=str(out / f"{tag}-{label}-00-tour-2.png"), full_page=mobile)
                        s3 = to_scene(2, "hold")
                        check(f"{label}: third scene: an answer to an unanswerable question that was not sent", s3["held"] and stored(2)["status"] == "abstained" and not s3["ev"]
                              and bool(s3["cited"]) and "보류" in s3["gold"] and "✓" in s3["gold"], f"cited {s3['cited']}, {s3['gold'][:30]!r}")
                        page.screenshot(path=str(out / f"{tag}-{label}-00-tour-3.png"), full_page=mobile)
                        missed = idx0["tour"].get("missed")
                        check(f"{label}: the third scene links to a question the verifier let through", bool(missed)
                              and page.locator(f".tour-why a[href='#workbench/{missed['id']}/{missed['planner']}']").count() == 1 if missed else False, str(missed))
                        # The research summary is not a tab and the first screen does not repeat it: one link at the foot of the page leads there.
                        foot = page.evaluate("""() => ({ tabs: [...document.querySelectorAll('.navlink[data-view]')].map(a => a.dataset.view),
                            link: (document.querySelector('.foot a[href="#research"]') || {}).textContent || '', inTour: document.querySelectorAll('#tour a[href="#research"]').length,
                            tourEnds: (document.querySelector('#tour').lastElementChild || {}).className || '' })""")
                        check(f"{label}: the research summary is a link at the foot of the page, not a tab, and the first screen ends with its scene",
                              foot["tabs"] == ["tour", "workbench"] and "연구 결과" in foot["link"] and foot["inTour"] == 0 and foot["tourEnds"] == "tour-grid", str(foot))
                        # from a scene to the full record of that question
                        page.locator(".tour-actions a").nth(0).click()
                        shown()
                        check(f"{label}: a scene opens its question in the question browser", f"#workbench/{scenes[2]['id']}/{scenes[2]['planner']}" in page.url
                              and page.locator(".badge-hold").count() > 0 and "전체 문항" in (page.text_content(".navlink.is-active") or ""), page.url.split("#")[-1])
                        page.goto("about:blank")
                        page.goto(base + "#workbench", wait_until="networkidle")          # a fresh load of the question browser
                        page.wait_for_timeout(800)
                    page.screenshot(path=str(out / f"{tag}-{label}-01-home.png"), full_page=mobile)
                    if tag == "static":
                        # the question browser already holds a result: an answer, its gold answer and a mark, with no click
                        first = page.evaluate("""() => ({ answer: (document.querySelector('.answer') || {}).textContent || '',
                            gold: (document.querySelector('.goldline') || {}).textContent || '', evidence: document.querySelectorAll('td.is-evidence').length,
                            top: document.querySelector('.answer') ? document.querySelector('.answer').getBoundingClientRect().top : -1 })""")
                        check(f"{label}: the question browser opens with an answer and its gold answer, without a click",
                              bool(first["answer"]) and "정답" in first["gold"] and "맞음" in first["gold"] and first["evidence"] >= 1 and 0 < first["top"] < vp["height"],
                              f"answer {first['answer']!r} at y={first['top']:.0f} of {vp['height']}, {first['gold'][:30]!r}")
                    # a document of the first question set is open, with its questions
                    pane("left")
                    page.wait_for_selector(".chip", timeout=15000)
                    check(f"{label}: document + questions rendered", page.locator("table.tt").count() >= 1 and page.locator(".chip").count() >= 1
                          and page.locator("#setsel option").count() >= 1, page.text_content("#setnote") or "")
                    if mobile:
                        pane("center")
                        page.screenshot(path=str(out / f"{tag}-{label}-02-doc.png"), full_page=False)
                        pane("left")
                    # a prepared question: the first one whose answer comes with an evidence cell (the live heuristic planner
                    # withholds some of them; the abstain state has its own check below)
                    page.locator(".chip:not([disabled])").nth(0).click()
                    shown()
                    for ex in [e for e in examples if e["corpus"] == "ko_tables"][:15]:
                        if page.locator(".evlist .evbtn[data-kind='cell']").count():
                            break
                        open_question(ex["id"], "auto")
                    status = page.text_content("#status") or ""
                    has_badge = page.locator(".badge-ok, .badge-fix, .badge-hold").count() > 0
                    check(f"{label}: first question produced a result", has_badge, status)
                    check(f"{label}: the result states the gold answer", "정답" in (page.text_content(".goldline") or ""), (page.text_content(".goldline") or "")[:60])
                    page.screenshot(path=str(out / f"{tag}-{label}-03-result.png"), full_page=mobile)
                    ev = page.locator(".evlist .evbtn[data-kind='cell']")
                    check(f"{label}: an answer with an evidence cell is among the first questions", ev.count() >= 1)
                    if ev.count():
                        ev.nth(0).click()
                        page.wait_for_timeout(500)
                        check(f"{label}: evidence highlighted in table", page.locator("td.is-evidence").count() >= 1)
                        pane("right")
                    if tag == "static":
                        # the same question under the other stored planners; a name switches to that planner's result
                        rows = page.locator(".cmp button[data-planner]")
                        n_rows = rows.count()
                        other = rows.nth(n_rows - 1).get_attribute("data-planner") if n_rows else None
                        if other:
                            rows.nth(n_rows - 1).click()
                            page.wait_for_timeout(300)
                        check(f"{label}: planners are compared on the same question", n_rows >= 2 and page.input_value("#planner") == other
                              and page.locator(".cmp .mark").count() == n_rows, f"{n_rows} planners, switched to {other}")
                        page.select_option("#planner", "auto")
                    # Abstain-state rendering with the heuristic planner on the questions whose gold is "no answer".
                    shown_hold = False
                    for ex in [e for e in examples if e["corpus"] == "ko_tables" and e["gold"]["status"] == "abstained"]:
                        open_question(ex["id"], "heuristic")
                        if page.locator(".badge-hold").count() > 0:
                            shown_hold = True
                            break
                    why = (page.text_content(".reason") or "") + " / " + (page.text_content(".holdwhy") or "") if shown_hold else ""
                    check(f"{label}: abstain state renders 답변 보류 with its reason (heuristic planner)", shown_hold and len(why) > 5, why[:90])
                    page.screenshot(path=str(out / f"{tag}-{label}-04-abstain.png"), full_page=mobile)
                    # the footer must sit below the panes (with a fixed page height it used to overlap them on narrow screens)
                    gap = page.evaluate("() => document.querySelector('.foot').getBoundingClientRect().top - document.querySelector('#main').getBoundingClientRect().bottom")
                    check(f"{label}: footer below the workbench", gap >= -1, f"gap {gap:.0f}px")
                    if tag == "static":
                        idx = page.evaluate("async () => (await (await fetch('data/recorded/index.json')).json())")
                        recorded_docs = json.loads((ROOT / a.static / "data" / "recorded" / "documents.json").read_text(encoding="utf-8"))
                        runs = [(k, r) for k in idx["planner_order"] for r in idx["planners"][k]["runs"]]
                        # stored outputs of a GPU-served model, and an answer whose evidence the verifier repaired
                        target = next(((k, r) for k, r in runs if "EXAONE" in (idx["planners"][k]["model_id"] or "")
                                       and any(c["name"] == "evidence_repaired" for c in r["result"]["verdict"]["checks"])), None)
                        check(f"{label}: stored EXAONE outputs are present", target is not None)
                        if target:
                            open_question(target[1]["id"], target[0])
                            check(f"{label}: stored EXAONE result is labelled with its model", "EXAONE" in (page.text_content(".badge-mode") or ""), page.text_content(".badge-mode") or "")
                            cited = page.eval_on_selector_all("td.is-cited", "els => els.map(e => e.dataset.rc)")
                            seen = page.eval_on_selector_all("td.is-evidence", "els => els.map(e => e.dataset.rc)")
                            check(f"{label}: repaired answer shows the model-cited cell apart from the evidence cell",
                                  bool(cited) and bool(seen) and not set(cited) & set(seen) and page.locator(".badge-fix").count() > 0
                                  and page.locator(".pv tr.is-diff").count() >= 1 and "표 위의 표시" in (page.text_content(".legend") or ""), f"cited {cited}, evidence {seen}")
                            pane("center")
                            page.screenshot(path=str(out / f"{tag}-{label}-08-repaired.png"), full_page=False)
                        # a wrong answer: the gold cell is marked where it is not the evidence cell
                        by_id = {e["id"]: e for e in examples}
                        wrong = next(((k, r) for k, r in runs if r["mark"] == "wrong" and r["result"]["evidence_cells"] and by_id[r["id"]]["gold"]["cells"]
                                      and not {f"r{c['row']}c{c['col']}" for c in r["result"]["evidence_cells"]} & set(by_id[r["id"]]["gold"]["cells"])), None)
                        if wrong:
                            open_question(wrong[1]["id"], wrong[0])
                            check(f"{label}: a wrong answer shows the gold cell apart from the evidence cell",
                                  page.locator("td.is-gold").count() >= 1 and "틀림" in (page.text_content(".goldline") or ""), (page.text_content(".goldline") or "")[:50])
                        # a table too long for the input budget: the rows the planner did not see are dimmed, and the card says so
                        cut = next(((k, r) for k, r in runs if "rows_shown" in r), None)
                        if cut:
                            open_question(cut[1]["id"], cut[0])
                            check(f"{label}: rows the planner was not shown are marked", page.locator("tr.is-unseen").count() == cut[1]["rows_shown"][1] - cut[1]["rows_shown"][0]
                                  and str(cut[1]["rows_shown"][0]) in (page.text_content(".unseennote") or ""), (page.text_content(".unseennote") or "")[:60])
                        # the chemistry documents: left on "auto", a question shows the EXAONE tuned on Korean and chemistry
                        chem = next((r for r in idx["planners"]["kochem"]["runs"] if by_id[r["id"]]["set"] == "chem_papers" and r["mark"] == "correct" and r["result"]["calculation"]), None)
                        check(f"{label}: stored EXAONE outputs on the chemistry papers are present", chem is not None)
                        if chem:
                            open_question(chem["id"], "auto")
                            said = page.text_content(".badge-mode") or ""
                            check(f"{label}: a chemistry question shows the EXAONE tuned on chemistry by default",
                                  "EXAONE" in said and "화학" in said and "Colab" in (page.text_content(".provenance") or "") and page.locator("td.is-evidence").count() >= 1, said[:70])
                            pane("center")
                            page.screenshot(path=str(out / f"{tag}-{label}-12-chem-exaone.png"), full_page=False)
                        # an unanswerable chemistry question on which the two tuned models part: the Korean-only model sent an answer, the other withheld
                        held = {r["id"] for r in idx["planners"]["kochem"]["runs"] if r["mark"] == "hold_ok"}
                        apart = next((r for r in idx["planners"]["koonly"]["runs"] if by_id[r["id"]]["set"] == "chem_papers" and r["mark"] == "answered_unanswerable" and r["id"] in held), None)
                        check(f"{label}: stored outputs of the Korean-only EXAONE on the chemistry papers are present", apart is not None)
                        if apart:
                            open_question(apart["id"], "koonly")
                            said = page.text_content(".badge-mode") or ""
                            rows_ = page.eval_on_selector_all("table.cmp tr", "els => els.map(e => [e.querySelector('button').dataset.planner, e.classList.contains('is-current'), e.querySelector('.mk').textContent])")
                            both = {k: mk for k, _, mk in rows_}
                            check(f"{label}: the Korean-only model's answer to an unanswerable question is shown beside the other planners",
                                  "한국어만" in said and [k for k, cur, _ in rows_ if cur] == ["koonly"] and len(rows_) == 5 and "✗" in both.get("koonly", "") and "✓" in both.get("kochem", "")
                                  and "답 없음" in (page.text_content(".goldline") or ""), f"{said[:40]} | {both}")
                            pane("right")
                            page.screenshot(path=str(out / f"{tag}-{label}-13-chem-share.png"), full_page=False)
                        if chem or apart:
                            open_question(idx["featured"], "auto")          # back to the Korean corpus for the checks below
                        # every question against every planner
                        page.goto(base + "#matrix", wait_until="networkidle")
                        page.wait_for_selector("table.mx", timeout=15000)
                        owner = idx["planners"]["exaone"]["totals"]["ko_owner"]
                        text = page.text_content("#matrix") or ""
                        n_marks = page.locator("table.mx td.mk .mark").count()
                        want = sum(len([r for r in idx["planners"][k]["runs"] if by_id[r["id"]]["corpus"] == "ko_tables"]) for k in idx["planner_order"])
                        check(f"{label}: per-question view lists every question of the corpus under every planner",
                              n_marks == want and f"{owner['right']}/{owner['n']}" in text and "소유자 작성" in text, f"{n_marks} marks, EXAONE {owner['right']}/{owner['n']}")
                        over = page.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
                        check(f"{label}: per-question view does not widen the page", over <= 1, f"overflow {over}px")
                        gap = page.evaluate("() => document.querySelector('.foot').getBoundingClientRect().top - document.querySelector('#matrix').getBoundingClientRect().bottom")
                        check(f"{label}: footer below the per-question view", gap >= -1, f"gap {gap:.0f}px")
                        page.screenshot(path=str(out / f"{tag}-{label}-10-matrix.png"), full_page=False)
                        page.locator("table.mx td.mk a").nth(0).click()
                        shown()
                        check(f"{label}: a mark opens that question in the workbench", "#workbench/" in page.url and page.locator(".badge-ok, .badge-fix, .badge-hold").count() > 0, page.url.split("#")[-1])
                        # the two ways of looking at every question sit under one tab
                        sub = page.eval_on_selector_all(".subbtn", "els => els.map(e => [e.dataset.sub, e.classList.contains('is-active')])")
                        check(f"{label}: one tab holds both the one-question view and the table of every question", sub == [["workbench", True], ["matrix", False]]
                              and "전체 문항" in (page.text_content(".navlink.is-active") or ""), str(sub))
                    if tag == "static" and (ROOT / a.static / "live" / "manifest.json").exists():
                        # "Run it here": the repository's verifier in this browser (Pyodide). Each result is held against the same
                        # call made here on the server with the real Korean tokenizer; they must agree in every field but the timings.
                        def here(page=page) -> dict:
                            page.wait_for_function("() => window.__ttLast !== undefined", timeout=30000)
                            got = page.evaluate("() => { const r = window.__ttLast; window.__ttLast = undefined; return r; }")
                            page.wait_for_timeout(200)
                            return got

                        def same(got: dict, ref: dict) -> bool:
                            def strip(r: dict) -> dict:
                                r = json.loads(json.dumps(r))
                                for k in ("elapsed_ms", "browser_ms", "mark"):
                                    r.pop(k, None)
                                for s in r["trace"]:
                                    s["ms"] = 0
                                return r
                            return strip(got) == strip(ref)

                        ko = next(e for e in examples if e["set"] == "ko_owner" and e["category"] == "cell")
                        stored = next(r for r in idx["planners"]["exaone"]["runs"] if r["id"] == ko["id"])
                        raw = stored["result"]["planner"]["raw_output"]
                        pid = next(s for s in stored["result"]["trace"] if s["step"] == "retrieve")["output"]["context_passage"]
                        doc = Document.model_validate(recorded_docs[ko["doc_id"]])
                        open_question(ko["id"], "exaone")
                        pane("right")
                        page.click("#livebox summary")
                        t_load = time.time()
                        page.click("#liveload")
                        page.wait_for_selector("#liveform:not([hidden])", timeout=180000)
                        check(f"{label}: the verifier loads into the browser", page.input_value("#liveprop") == raw and not page.locator("#question").is_disabled(),
                              f"loaded in {time.time() - t_load:.1f}s; proposal {raw!r}")
                        # the model's proposal with its cell moved one row away: the verifier must repair or withhold, as on a server
                        moved = re.sub(r"cells: r(\d+)c(\d+)", lambda m: f"cells: r{int(m[1]) + 1}c{m[2]}", raw, count=1)
                        page.fill("#liveprop", moved)
                        page.click("#liveverify")
                        got = here()
                        ref = tt_browser.run(doc, ko["table_id"], ko["question"], moved, pid, False)
                        check(f"{label}: a changed proposal is verified in the browser as on a server", same(got, ref) and got["planner"]["mode"] == "visitor"
                              and "이 브라우저" in (page.text_content(".badge-live") or ""), f"{moved!r} -> {got['status']}, {[c['name'] for c in got['verdict']['checks'] if not c['passed']]}")
                        page.screenshot(path=str(out / f"{tag}-{label}-11-here.png"), full_page=mobile)
                        # the subject check needs the Korean tokenizer: the browser reads recorded tokens, the server runs the tokenizer
                        # Take a stored model answer that the subject check withholds on a server, and ask the browser for the same verdict.
                        flip = None
                        for k in [k for k in idx["planner_order"] if idx["planners"][k]["source"]]:
                            for r in idx["planners"][k]["runs"]:
                                e = by_id[r["id"]]
                                if e["corpus"] != "ko_tables" or r["result"]["status"] != "answered":
                                    continue
                                d = Document.model_validate(recorded_docs[e["doc_id"]])
                                out_k = r["result"]["planner"]["raw_output"]
                                pid_k = next(s for s in r["result"]["trace"] if s["step"] == "retrieve")["output"]["context_passage"]
                                on = tt_browser.run(d, e["table_id"], e["question"], out_k, pid_k, True)
                                if on["status"] == "abstained" and tt_browser.run(d, e["table_id"], e["question"], out_k, pid_k, False)["status"] == "answered":
                                    flip = (k, e, on)
                                    break
                            if flip:
                                break
                        check(f"{label}: a stored answer that the subject check withholds exists", flip is not None)
                        if flip:
                            open_question(flip[1]["id"], flip[0])
                            pane("right")
                            page.check("#liveentity")
                            page.click("#liveverify")
                            got = here()
                            check(f"{label}: the subject check agrees with the real Korean tokenizer", same(got, flip[2]) and got["settings"]["entity_check"] is True
                                  and got["status"] == "abstained", f"{flip[1]['id']} ({flip[0]}): {[c['name'] for c in got['verdict']['checks'] if not c['passed']]}")
                            page.uncheck("#liveentity")
                            open_question(ko["id"], "exaone")
                            pane("right")
                        page.click("#liveheur")
                        got = here()
                        ref = tt_browser.run(doc, ko["table_id"], ko["question"], None, pid, False)
                        check(f"{label}: the heuristic planner runs in the browser on a stored Korean question", same(got, ref) and got["planner"]["mode"] == "heuristic",
                              f"{got['planner']['raw_output']!r} -> {got['status']}")
                        # a Korean question nobody recorded cannot be tokenized here, and the page says so
                        page.fill("#question", "이 표에서 가장 최근에 방송된 프로그램은 무엇입니까?")
                        page.click("#liveheur")
                        page.wait_for_selector("#errorbar:not([hidden])", timeout=15000)
                        check(f"{label}: an unrecorded Korean question is refused with the reason", "형태소 분석기" in (page.text_content("#errorbar") or ""), (page.text_content("#errorbar") or "")[:50])
                        # English needs no recorded tokens: a question typed by the visitor runs end to end
                        en = next(e for e in examples if e["set"] == "chem_papers" and e["category"] == "cell")
                        en_doc = Document.model_validate(recorded_docs[en["doc_id"]])
                        open_question(en["id"], "heuristic")
                        pane("right")
                        typed = "Which " + en["question"].split(" ", 1)[1]
                        page.fill("#question", typed)
                        page.click("#liveheur")
                        got = here()
                        ref = tt_browser.run(en_doc, page.evaluate("() => document.querySelector('.tablewrap.is-selected').dataset.tid"), typed, None, None, False)
                        check(f"{label}: a typed English question runs in the browser as on a server", same(got, ref) and typed != en["question"], f"{typed[:50]!r} -> {got['status']} {got['answer']!r}")
                    if tag == "live" and label == "desktop":
                        # typed question + keyboard submit + invalid input handling
                        page.goto(base, wait_until="networkidle")
                        page.wait_for_selector(".chip", timeout=15000)
                        page.select_option("#setsel", "ko_custom")
                        page.wait_for_selector("#doclist li[data-id='doc_ko_8bcc6a21a4']", timeout=15000)
                        page.locator("#doclist li[data-id='doc_ko_8bcc6a21a4']").click()
                        page.wait_for_selector("table.tt", timeout=15000)
                        page.fill("#question", "x")
                        page.press("#question", "Enter")
                        page.wait_for_timeout(1500)
                        check("desktop: too-short question shows an error", not page.locator("#errorbar").is_hidden())
                        page.fill("#question", "국도 1호 자동차 전용도로 구간 중 호남로의 총연장은 몇 km입니까?")
                        page.press("#question", "Enter")
                        page.wait_for_function("() => document.querySelector('#status') && /완료|보류|오류/.test(document.querySelector('#status').textContent)", timeout=120000)
                        check("desktop: typed question executed", True, page.text_content("#status") or "")
                        page.screenshot(path=str(out / f"{tag}-{label}-05-typed.png"))
                        # conversation mode: the second and third turns only make sense with the session's memory
                        page.click("#chatbox summary")
                        page.check("#chatmode")
                        done = "() => /완료|보류|오류/.test(document.querySelector('#status').textContent) && document.querySelectorAll('#transcript li').length === %d"
                        for n, said in enumerate(["국도 1호 자동차 전용도로 구간 중 호남로의 총연장은 몇 km입니까?", "그럼 서부간선도로는?", "차로수는?"], start=1):
                            page.fill("#question", said)
                            page.press("#question", "Enter")
                            page.wait_for_function(done % n, timeout=120000)
                        turns = page.locator("#transcript li").all_text_contents()
                        check("desktop: conversation keeps three turns", len(turns) == 3, " / ".join(t[:60] for t in turns))
                        check("desktop: follow-up answered from memory (row switch, then column switch)",
                              len(turns) == 3 and "22.8" in turns[0] and "10.8" in turns[1] and "서부간선도로" in turns[2], " / ".join(t[-70:] for t in turns))
                        check("desktop: result card says what memory filled in", "서부간선도로의 차로수" in (page.text_content(".memline") or ""), (page.text_content(".memline") or "")[:120])
                        page.screenshot(path=str(out / f"{tag}-{label}-09-chat.png"))
                        page.uncheck("#chatmode")
                        # chemistry corpus
                        page.click(".segbtn[data-corpus='chem_docs']")
                        page.wait_for_selector(".chip", timeout=15000)
                        page.locator(".chip").nth(0).click()
                        page.wait_for_function("() => !document.querySelector('#result').hidden", timeout=120000)
                        page.wait_for_timeout(300)
                        check("desktop: chemistry question produced a result", page.locator(".badge-ok, .badge-fix, .badge-hold").count() > 0)
                        page.screenshot(path=str(out / f"{tag}-{label}-06-chem.png"))
                        # beside a running backend the walk-through is one tab away (it reads the stored results)
                        page.goto(base + "#tour", wait_until="networkidle")
                        page.wait_for_selector(".tour-q", timeout=15000)
                        check("desktop: the walk-through of stored results is available beside a running backend", page.locator(".tour-tab").count() == 3
                              and page.locator("td.tv-ev").count() >= 1 and "실시간" in (page.text_content("#modetext") or ""), (page.text_content(".tour-q") or "")[:50])
                    # research view
                    page.goto(base + "#research", wait_until="networkidle")
                    page.wait_for_timeout(800)
                    check(f"{label}: research view renders", "연구 결과" in (page.text_content("#research") or ""))
                    if a.static:
                        page.goto(base, wait_until="networkidle")
                        page.wait_for_selector(".tour-q", timeout=15000)
                        page.locator('.foot a[href="#research"]').click()
                        page.wait_for_selector("#research article.hl", timeout=15000)
                        check(f"{label}: the link at the foot opens the research summary, with no tab lit", page.url.endswith("#research")
                              and page.locator(".navlink.is-active").count() == 0 and page.locator("#view-research:not([hidden])").count() == 1, page.url.split("/")[-1])
                    # the view opens with a few conclusions, each with a chart and the same values as a table; the detail is folded
                    top = page.evaluate("""() => { const hl = [...document.querySelectorAll('.hl')];
                        return { cards: hl.length, charts: hl.filter((c) => c.querySelector('.viz')).length, tables: hl.filter((c) => c.querySelector('.viz-table tbody tr')).length,
                                 titles: hl.filter((c) => /\\d/.test(c.querySelector('h3').textContent)).length, groups: document.querySelectorAll('details.grp').length,
                                 open: document.querySelectorAll('details.grp[open]').length, sections: document.querySelectorAll('details.grp section[data-title]').length,
                                 height: document.documentElement.scrollHeight, over: document.documentElement.scrollWidth - document.documentElement.clientWidth }; }""")
                    research = page.evaluate("async () => (await (await fetch('data/research.json')).json())")
                    check(f"{label}: research view leads with conclusions, each with a chart and a table of its values",
                          top["cards"] == len(research["highlights"]) >= 5 and top["charts"] == top["tables"] == top["cards"] and top["titles"] >= 4, str(top))
                    check(f"{label}: every experiment is kept below, folded by topic", top["groups"] == len(research["groups"]) and top["open"] == 0
                          and top["sections"] == len(research["sections"]), f"{top['sections']} sections in {top['groups']} groups")
                    check(f"{label}: research view fits the screen width and is short", top["over"] <= 1 and top["height"] < 6000, f"height {top['height']}px, overflow {top['over']}px")
                    page.screenshot(path=str(out / f"{tag}-{label}-07-research.png"), full_page=True)
                    # a chart mark answers hover and keyboard focus with its value
                    page.locator(".hl .vb-bar").nth(0).focus()
                    tip = page.text_content("#viztip") or ""
                    check(f"{label}: a chart mark shows its value on focus", "%" in tip and not page.locator("#viztip").is_hidden(), tip[:60])
                    # "세부 기록 보기" opens the group that holds the experiment
                    page.locator(".hl a[data-more]").nth(0).click()
                    page.wait_for_timeout(600)
                    check(f"{label}: a conclusion links to its experiment record", page.locator("details.grp[open] section.is-target").count() == 1,
                          (page.text_content("details.grp[open] section.is-target h3") or "")[:60])
                    page.close()
                except Exception as e:  # a crash must show up as a FAILED check, never as a missing report
                    check(f"{label}: unexpected error", False, f"{type(e).__name__}: {str(e)[:240]}")
                finally:
                    if page is not None and not page.is_closed():
                        page.close()
            browser.close()
    finally:
        if proc:
            proc.terminate()
    # the intentional too-short question returns 422 by design; browsers log that as a console error
    report["console_errors"] = [e for e in report["console_errors"] if "favicon" not in e and "status of 422" not in e]
    if tag == "static":  # the backend probe (v1/release) is expected to 404 on a static host
        report["console_errors"] = [e for e in report["console_errors"] if "404" not in e]
    check("no browser console errors", not report["console_errors"], "; ".join(report["console_errors"][:3]))
    (out / f"e2e-{tag}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    failed = [c for c in report["checks"] if not c["ok"]]
    print(f"{len(report['checks']) - len(failed)}/{len(report['checks'])} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
