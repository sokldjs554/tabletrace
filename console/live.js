/* The "run it here" path of the static demo: loads a Python runtime compiled to WebAssembly (Pyodide), pydantic and
   this repository's own verifier, tools and heuristic planner, and calls them in the visitor's browser.
   Nothing is loaded until the visitor asks for it. The files come from this site (live/, put there by
   scripts/fetch_live_runtime.py at build time), not from a third-party host. No model runs. */
(function () {
  "use strict";
  const BASE = "live/";
  // the build's stamp (scripts/build_static_site.py): this site's own files are asked for under it, so they are never taken from an earlier build
  const V = ((b) => (b ? "?v=" + encodeURIComponent(b) : ""))(((document.querySelector('meta[name="tt-build"]') || {}).content || "").trim());
  let manifest = null, py = null, loading = null, runFn = null;

  async function available() {
    if (manifest) return manifest;
    try { const r = await fetch(BASE + "manifest.json" + V); if (!r.ok) return null; manifest = await r.json(); return manifest; } catch (e) { return null; }
  }
  function loadScript(src) {
    return new Promise((resolve, reject) => { const s = document.createElement("script"); s.src = src; s.onload = resolve;
      s.onerror = () => reject(new Error("스크립트를 불러오지 못했습니다: " + src)); document.head.appendChild(s); });
  }
  async function load(onStep) {
    if (py) return;
    if (!loading) loading = (async () => {
      const m = await available(); if (!m) throw new Error("이 배포에는 실행 환경이 들어 있지 않습니다.");
      const say = (t) => { if (onStep) onStep(t); };
      say("Python 실행 환경을 불러오는 중…");
      await loadScript(BASE + "pyodide/pyodide.js");
      const p = await window.loadPyodide({ indexURL: BASE + "pyodide/" });
      say("pydantic을 불러오는 중…");
      await p.loadPackage(m.wheels.map((w) => new URL(BASE + "wheels/" + w, location.href).href), { messageCallback: () => {} });
      say("이 저장소의 검증기와 도구를 불러오는 중…");
      p.unpackArchive(await (await fetch(BASE + m.own + V)).arrayBuffer(), "zip", { extractDir: "/tt" });
      p.runPython("import sys; sys.path.insert(0, '/tt')");
      const mod = p.pyimport("tt_browser");
      const tok = await fetch("data/recorded/kiwi_tokens.json" + V);       // Korean tokens recorded with the real tokenizer
      if (tok.ok) mod.load_tokens(await tok.text());
      runFn = mod.run_json; py = p;
    })();
    try { await loading; } finally { loading = null; }
  }
  // proposal: a program in the model's output format, or null for the heuristic planner. gold: a stored question's gold, or null.
  function run(doc, tableId, question, proposal, passageId, entityCheck, gold) {
    const t0 = performance.now();
    const res = JSON.parse(runFn(JSON.stringify(doc), tableId, question, proposal == null ? undefined : proposal, passageId == null ? undefined : passageId,
      !!entityCheck, gold ? JSON.stringify(gold) : undefined));
    res.browser_ms = performance.now() - t0;
    return res;
  }
  window.TTLive = { available, load, run, ready: () => !!py };
})();
