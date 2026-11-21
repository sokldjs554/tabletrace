"""A short animated walk through the static demo for the top of the README (docs/images/demo.gif).

  python scripts/make_demo_gif.py --site _site --frames /tmp/frames [--chromium PATH]    # step 1: Playwright (the project venv)
  python3 scripts/make_demo_gif.py --frames /tmp/frames --gif docs/images/demo.gif   # step 2: Pillow

Two steps because the capture needs Playwright and the assembly needs Pillow, and the project environment does not
carry Pillow. Each frame is a real screen of the static build with a caption bar added at the bottom; nothing is drawn
by hand. The first three frames are the first screen's three scenes; the others replay stored results and, in the last
two, run the verifier in the browser (the build must have been made with --live for those).
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import re
import socket
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W, H = 1280, 760
CAPTION = """(text) => { let b = document.getElementById('gifcap');
  if (!b) { b = document.createElement('div'); b.id = 'gifcap'; document.body.appendChild(b);
    b.style.cssText = 'position:fixed;left:0;right:0;bottom:0;z-index:99;background:#1d2733;color:#fff;font:600 19px/1.4 -apple-system,"Noto Sans KR",sans-serif;padding:11px 20px;'; }
  b.textContent = text; }"""


def capture(site: Path, frames: Path, chromium: str | None) -> None:
    from playwright.sync_api import sync_playwright

    frames.mkdir(parents=True, exist_ok=True)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}/"
    shots: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"], **({"executable_path": chromium} if chromium else {}))
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)

        def shot(caption: str, seconds: float) -> None:
            page.evaluate(CAPTION, caption)
            page.wait_for_timeout(350)
            name = f"{len(shots):02d}.png"
            page.screenshot(path=str(frames / name))
            shots.append({"file": name, "caption": caption, "seconds": seconds})

        def go(target: str) -> None:
            page.goto(base + target, wait_until="networkidle")
            page.wait_for_timeout(600)

        # the first screen: three stored results, one question at a time (which three is in index.tour)
        go("")
        page.wait_for_selector(".tour-q", timeout=15000)
        shot("첫 화면은 문항 하나를 따라갑니다. 모델의 제안, 도구의 계산, 검증, 정답.", 3.4)
        go("#tour/2")
        shot("답은 맞았지만 모델이 가리킨 셀(붉은 점선)은 틀린 경우. 검증기가 근거 셀을 고칩니다.", 3.4)
        go("#tour/3")
        shot("표에 없는 것을 물으면 모델이 낸 답을 내보내지 않습니다.", 3.2)
        idx = json.loads((site / "data/recorded/index.json").read_text(encoding="utf-8"))
        go("#workbench/ko_owner_17/exaone")
        page.evaluate("document.querySelector('.pv').scrollIntoView({block: 'center'})")
        shot("전체 문항 탐색: 모델이 적은 숫자와 도구가 다시 계산한 값이 다르면 계산한 값으로 답합니다.", 3.2)
        go("#matrix")
        page.evaluate("window.scrollTo(0, 150)")
        shot("표로 한꺼번에: 소유자가 직접 쓴 30문항 전체를 플래너 일곱에 대해.", 3.2)
        if (site / "live" / "manifest.json").exists():
            ko = next(r for r in idx["planners"]["exaone"]["runs"] if r["set"] == "ko_owner" and r["mark"] == "correct" and "lookup" in r["result"]["planner"]["raw_output"])
            go(f"#workbench/{ko['id']}/exaone")
            page.click("#livebox summary")
            page.click("#liveload")
            page.wait_for_selector("#liveform:not([hidden])", timeout=180000)
            raw = page.input_value("#liveprop")
            shot("직접 실행해 보기: 저장소의 검증기를 이 브라우저에 불러옵니다. 모델의 제안이 칸에 있습니다.", 3.2)
            page.fill("#liveprop", re.sub(r"cells: r(\d+)c(\d+)", lambda m: f"cells: r{int(m[1]) + 1}c{m[2]}", raw, count=1))
            page.click("#liveverify")
            page.wait_for_function("() => (document.querySelector('.badge-live') || {}).textContent && document.querySelector('.badge-live').textContent.includes('이 브라우저')", timeout=30000)
            page.evaluate("document.querySelector('#result').scrollIntoView({block: 'start'})")
            shot("인용 셀을 한 칸 옮기면 검증기가 그 자리에서 다시 판정합니다.", 3.6)
        browser.close()
    (frames / "frames.json").write_text(json.dumps(shots, ensure_ascii=False, indent=1), encoding="utf-8")
    print("captured", len(shots), "frames ->", frames)


def assemble(frames: Path, gif: Path, width: int) -> None:
    from PIL import Image

    shots = json.loads((frames / "frames.json").read_text(encoding="utf-8"))
    images = []
    for s in shots:
        im = Image.open(frames / s["file"]).convert("RGB")
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        images.append(im.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE))
    gif.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(gif, save_all=True, append_images=images[1:], duration=[round(1000 * s["seconds"]) for s in shots], loop=0, optimize=True, disposal=1)
    meta = {"frames": len(shots), "seconds": round(sum(s["seconds"] for s in shots), 1), "width": width, "height": images[0].height,
            "bytes": gif.stat().st_size, "captions": [s["caption"] for s in shots]}
    gif.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {gif} ({gif.stat().st_size / 1e3:.0f} kB, {len(shots)} frames, {meta['seconds']} s)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", help="a static build of the demo (scripts/build_static_site.py --live); captures frames when given")
    ap.add_argument("--frames", required=True, help="folder for the captured frames")
    ap.add_argument("--gif", help="assemble the frames in --frames into this GIF")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--chromium", default=os.environ.get("TT_CHROMIUM"), help="path of a Chromium to use (as for scripts/console_screenshots.py)")
    a = ap.parse_args()
    if a.site:
        capture(Path(a.site), Path(a.frames), a.chromium)
    if a.gif:
        assemble(Path(a.frames), Path(a.gif), a.width)


if __name__ == "__main__":
    main()
