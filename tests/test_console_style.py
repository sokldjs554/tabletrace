"""The console must keep a flat, content-first canvas: no decorative gradients, blur, textures or media backdrops.

Motivation: docs/design/ui-research.md ("데모 배경 조사"). Product UIs we inspected use flat neutral surfaces;
loading skeletons are the only place a gradient is allowed because it is a state indicator.
"""
from __future__ import annotations

import re
from pathlib import Path

CONSOLE = Path(__file__).resolve().parents[1] / "console"
BANNED_CSS = ["radial-gradient", "conic-gradient", "backdrop-filter", "blur(", "background-image", "mix-blend-mode"]
BANNED_HTML = ["<canvas", "<video", "<iframe"]


def _css() -> str:
    return (CONSOLE / "styles.css").read_text(encoding="utf-8")


def test_no_decorative_css() -> None:
    css = _css()
    found = [token for token in BANNED_CSS if token in css]
    assert not found, f"decorative CSS found: {found}"


def test_gradient_only_in_loading_skeleton() -> None:
    css = _css()
    for rule in re.findall(r"([^{}]+)\{([^{}]*linear-gradient[^{}]*)\}", css):
        selector = rule[0].strip()
        assert selector.endswith(".skeleton"), f"linear-gradient outside the loading skeleton: {selector}"


def test_body_background_is_a_flat_token() -> None:
    css = _css()
    body = re.search(r"\nbody\s*\{([^}]*)\}", css)
    assert body, "body rule not found"
    assert re.search(r"background:\s*var\(--bg\)", body.group(1))
    root = re.search(r":root\s*\{([^}]*)\}", css)
    assert root and re.search(r"--bg:\s*#[0-9a-fA-F]{6}", root.group(1))


def test_only_state_animations() -> None:
    css = _css()
    names = set(re.findall(r"@keyframes\s+([\w-]+)", css))
    assert names <= {"spin", "sk"}, f"unexpected animations: {names}"


def test_no_media_backdrops_in_html() -> None:
    html = (CONSOLE / "index.html").read_text(encoding="utf-8").lower()
    found = [t for t in BANNED_HTML if t in html]
    assert not found, f"media backdrop elements found: {found}"
