"""The demo's "run it here" path: the verifier, tools and heuristic planner called in the visitor's browser
(console/live/tt_browser.py under Pyodide). These tests hold that file against the agent graph on every stored question,
the tokenizer stand-in against the real Korean tokenizer, and the runtime bundle against what it claims to contain.
The browser itself is exercised by scripts/console_screenshots.py, which compares each in-browser result with the
same call made on the server."""
import ast
import importlib.util
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from tabletrace.agent.graph import AgentRuntime
from tabletrace.retrieval.index import CorpusIndex
from tabletrace.retrieval.tokenize import _kiwi
from tabletrace.schema import Document

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console" / "live"))
sys.path.insert(0, str(ROOT / "scripts"))
import tt_browser  # noqa: E402

import fetch_live_runtime  # noqa: E402
from make_recorded_runs import StoredOutputPlanner  # noqa: E402

REC = ROOT / "console" / "data" / "recorded"
INDEX = json.loads((REC / "index.json").read_text(encoding="utf-8"))
DOCS = {i: Document.model_validate(d) for i, d in json.loads((REC / "documents.json").read_text(encoding="utf-8")).items()}
EXAMPLES = json.loads((ROOT / "console" / "data" / "examples.json").read_text(encoding="utf-8"))["examples"]
TOKENS = json.loads((REC / "kiwi_tokens.json").read_text(encoding="utf-8"))
OWNER_FILES = ["tools/numbers.py", "tools/calculator.py", "tools/cells.py", "agent/program.py", "verify/verifier.py"]


def _indexes():
    return {c: CorpusIndex([d for d in DOCS.values() if d.corpus == c], "ko" if c == "ko_tables" else "en") for c in ("ko_tables", "chem_docs")}


def _inputs(ex):
    """What the browser path gives the verifier for a stored question: the whole table and the first 300 characters of the passage."""
    doc = DOCS[ex["doc_id"]]
    passage = doc.passages[0] if doc.passages else None
    return doc, {"table": doc.table(ex["table_id"]), "context": passage.text[:300] if passage else None, "context_id": passage.id if passage else None}


def _core(res: dict) -> dict:
    return {k: res[k] for k in ("status", "answer", "program", "evidence_cells", "evidence_spans", "calculation", "verdict")}


@pytest.mark.parametrize("entity_check", [False, True])
def test_the_browser_runner_gives_what_the_agent_graph_gives(entity_check):
    """Every stored question, with the heuristic planner and with the stored EXAONE and mT5 proposals: the file the
    browser runs and the LangGraph agent, given the same table and passage, return the same result."""
    indexes = _indexes()
    compared = 0
    for key in ("heuristic", "exaone", "neural"):
        stored = INDEX["planners"][key]
        if key == "heuristic":
            rt, mode, outputs = AgentRuntime(indexes, None, entity_check=entity_check, fallback=False), "heuristic", None
        else:
            planner = StoredOutputPlanner([ROOT / d for d in stored["source"]["eval_dirs"].values()], stored["model_id"])
            rt, mode, outputs = AgentRuntime(indexes, planner, entity_check=entity_check, fallback=False), "neural", planner.rows
        ids = {r["id"] for r in stored["runs"]}
        for ex in [e for e in EXAMPLES if e["id"] in ids]:
            doc, given = _inputs(ex)
            graph = json.loads(rt.run(ex["question"], ex["corpus"], doc_id=ex["doc_id"], table_id=ex["table_id"], planner_mode=mode, given=given).model_dump_json())
            proposal = outputs[ex["question"]]["raw_output"] if outputs else None
            here = tt_browser.run(doc, ex["table_id"], ex["question"], proposal, given["context_id"], entity_check)
            assert _core(here) == _core(graph), (key, ex["id"])
            assert [s["step"] for s in here["trace"]] == [s["step"] for s in graph["trace"]], (key, ex["id"])
            compared += 1
    assert compared == len(EXAMPLES) + 60 + len(EXAMPLES)


def test_marks_and_cell_values_are_the_recorders():
    for run in INDEX["planners"]["heuristic"]["runs"][:40]:
        ex = next(e for e in EXAMPLES if e["id"] == run["id"])
        assert tt_browser.mark_of(run["result"]["status"], run["result"]["answer"], ex["gold"]) == run["mark"]


def _shim():
    spec = importlib.util.spec_from_file_location("kiwipiepy_standin", ROOT / "console" / "live" / "shim" / "kiwipiepy.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.load(TOKENS)
    return mod


def test_recorded_tokens_are_the_real_tokenizers_for_every_korean_question_and_header():
    wanted = {e["question"] for e in EXAMPLES if e["corpus"] == "ko_tables"}
    wanted |= {h for e in EXAMPLES if e["corpus"] == "ko_tables" for t in DOCS[e["doc_id"]].tables for h in t.header if h.strip()}
    assert wanted <= set(TOKENS)
    shim = _shim().Kiwi()
    for text in sorted(TOKENS):
        assert [(t.form, t.tag) for t in shim.tokenize(text)] == [(t.form, t.tag) for t in _kiwi().tokenize(text)], text


def test_the_stand_in_refuses_a_text_it_has_no_tokens_for():
    mod = _shim()
    assert mod.Kiwi().tokenize("  ") == []
    with pytest.raises(mod.MissingTokens):
        mod.Kiwi().tokenize("기록해 두지 않은 한국어 질문입니다")


def test_the_verifier_gives_the_same_verdicts_on_recorded_tokens(monkeypatch):
    """The subject check with the stand-in in place of the tokenizer, on every stored Korean EXAONE proposal."""
    real = {}
    runs = [r for r in INDEX["planners"]["exaone"]["runs"]]
    exs = {e["id"]: e for e in EXAMPLES}
    for r in runs:
        ex = exs[r["id"]]
        doc, given = _inputs(ex)
        real[r["id"]] = _core(tt_browser.run(doc, ex["table_id"], ex["question"], r["result"]["planner"]["raw_output"], given["context_id"], True))
    import tabletrace.retrieval.tokenize as tok

    shim = _shim().Kiwi()
    monkeypatch.setattr(tok, "_kiwi", lambda: shim)
    for r in runs:
        ex = exs[r["id"]]
        doc, given = _inputs(ex)
        assert _core(tt_browser.run(doc, ex["table_id"], ex["question"], r["result"]["planner"]["raw_output"], given["context_id"], True)) == real[r["id"]], r["id"]
    assert any(any(c["name"] == "subject_in_evidence" for c in v["verdict"]["checks"]) for v in real.values())


def test_the_bundle_carries_the_owners_files_unchanged_and_nothing_it_cannot_import():
    """tabletrace.zip holds the repository's modules byte for byte; every import inside it resolves inside it, to pydantic,
    to the tokenizer stand-in or to the standard library (so no torch, no LangGraph, no compiled tokenizer)."""
    assert all(f in fetch_live_runtime.OWN for f in OWNER_FILES)
    names = {"tabletrace." + f[:-3].replace("/", ".").removesuffix(".__init__") for f in fetch_live_runtime.OWN} | {"tabletrace"}
    with zipfile.ZipFile(io.BytesIO(fetch_live_runtime.own_zip())) as z:
        for rel in fetch_live_runtime.OWN:
            assert z.read(f"tabletrace/{rel}") == (ROOT / "src" / "tabletrace" / rel).read_bytes(), rel
        assert z.read("kiwipiepy.py") == (ROOT / "console/live/shim/kiwipiepy.py").read_bytes()
        sources = {n: z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".py")}
    for name, src in sources.items():
        for node in ast.walk(ast.parse(src)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            for m in mods:
                top = m.split(".")[0]
                if top == "tabletrace":
                    assert m in names, (name, m)
                else:
                    assert top in {"pydantic", "kiwipiepy", "__future__"} or top in sys.stdlib_module_names, (name, m)


def test_the_runtime_is_pinned_with_checksums():
    lock = json.loads((ROOT / "console/live/runtime.lock.json").read_text(encoding="utf-8"))
    assert lock["pyodide"]["version"] == fetch_live_runtime.PYODIDE and len(lock["pyodide"]["sha256"]) == 64
    assert set(lock["pyodide"]["files"]) == set(fetch_live_runtime.PYODIDE_FILES)
    assert {w["name"]: w["version"] for w in lock["wheels"]} == fetch_live_runtime.WHEELS
    assert all(len(w["sha256"]) == 64 and w["url"].startswith("https://files.pythonhosted.org/") for w in lock["wheels"])
    assert lock["pyodide"]["url"].startswith("https://registry.npmjs.org/")


def test_a_build_without_the_runtime_offers_no_run_it_here(tmp_path):
    """Without --live the site has no manifest, and the page keeps the panel hidden."""
    out = tmp_path / "site"
    subprocess.run([sys.executable, str(ROOT / "scripts/build_static_site.py"), "--out", str(out), "--commit", "test"], check=True, capture_output=True)
    assert not (out / "live" / "manifest.json").exists() and not list((out / "live").glob("*.py"))
    html = (out / "index.html").read_text(encoding="utf-8")
    assert '<details class="chatbox" id="livebox" hidden>' in html and '<script src="live.js?v=test"></script>' in html
    assert "TTLive.available()" in (out / "app.js").read_text(encoding="utf-8")


def test_a_build_stamps_the_page_so_a_browser_does_not_keep_an_earlier_one(tmp_path):
    """GitHub Pages lets a browser reuse a file for ten minutes and an open tab keeps what it loaded. The owner saw an
    earlier build after a deploy (2026-11-22). The built page names its own files with ?v=<commit>, asks for its data
    under the same stamp, and reads BUILD.txt past the cache to learn of a newer build; the page in the repository,
    which a backend serves, carries no stamp."""
    import re

    out = tmp_path / "site"
    subprocess.run([sys.executable, str(ROOT / "scripts/build_static_site.py"), "--out", str(out), "--commit", "abc1234"], check=True, capture_output=True)
    html = (out / "index.html").read_text(encoding="utf-8")
    assert '<meta name="tt-build" content="abc1234">' in html and (out / "BUILD.txt").read_text() == "commit abc1234\n"
    own = re.findall(r'(?:src|href)="([^":]+\.(?:js|css)[^"]*)"', html)
    assert sorted(own) == ["app.js?v=abc1234", "charts.js?v=abc1234", "live.js?v=abc1234", "styles.css?v=abc1234"]
    source = (ROOT / "console" / "index.html").read_text(encoding="utf-8")
    assert "tt-build" not in source and "?v=" not in source
    js = (ROOT / "console" / "app.js").read_text(encoding="utf-8")
    assert "fetch(stamped(url)," in js and 'fetch(`BUILD.txt?t=${Date.now()}`, { cache: "no-store" })' in js and "location.reload()" in js
    assert 'sessionStorage.getItem("tt-build-reload") === now' in js                      # one reload per build, never a loop
    assert js.count("fetch(") == 2                                                         # every other request goes through fetchJSON
    live = (ROOT / "console" / "live.js").read_text(encoding="utf-8")
    assert live.count(" + V)") == 3 and "tt-build" in live
