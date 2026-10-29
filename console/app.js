/* TableTrace console — vanilla JS, no build step.
   Live mode: talks to the FastAPI backend on the same origin.
   Recorded mode: loads data/recorded/*.json produced by scripts/make_recorded_runs.py. */
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtMs = (ms) => (ms >= 1000 ? (ms / 1000).toFixed(2) + " s" : Math.round(ms) + " ms");

  const REASONS = {
    not_in_document: "문서에 근거가 없음", ambiguous_question: "질문이 모호함(후보가 여럿)", unit_mismatch: "단위·기간 불일치로 계산 거부",
    verification_failed: "모델 제안이 검증에 실패", retrieval_low: "관련 표를 찾지 못함", invalid_program: "모델 출력을 해석할 수 없음", timeout: "시간 초과",
  };
  const CHECKS = {
    cells_in_range: "셀 좌표가 표 범위 안", period_consistent: "질문의 연도와 근거 행의 연도 일치", answer_matches_cell: "답이 근거 셀의 텍스트와 일치",
    calculation: "제한 계산기 재계산", units_consistent: "계산 입력의 단위 일치", answer_matches_calc: "모델의 숫자와 계산값 일치",
    answer_in_passage: "답이 본문 문장에 존재", abstain: "보류 판정",
  };
  const CATS = { cell: "셀 근거", calc: "계산", text_table: "본문+표", unit_period: "단위·기간 주의", abstain: "답 없음 → 보류" };

  const state = { mode: null, corpus: "ko_tables", docs: [], doc: null, tableId: null, examples: [], recorded: null, release: null, busy: false, timer: null, lastEvidence: null };

  async function fetchJSON(url, opts = {}, timeoutMs = 8000) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const r = await fetch(url, { ...opts, signal: ctrl.signal, headers: { "content-type": "application/json", ...(opts.headers || {}) } });
      const body = await r.json().catch(() => null);
      if (!r.ok) { const e = new Error((body && (body.detail || body.error)) || `HTTP ${r.status}`); e.status = r.status; e.body = body; throw e; }
      return body;
    } finally { clearTimeout(t); }
  }

  // ---------- boot ----------
  async function init() {
    if (localStorage.getItem("tt.intro") === "closed") $("#intro").hidden = true;
    $("#introclose").addEventListener("click", () => { $("#intro").hidden = true; localStorage.setItem("tt.intro", "closed"); });
    try {
      state.release = await fetchJSON("v1/release", {}, 3000);
      state.mode = "live";
    } catch (e) {
      state.mode = "recorded";
    }
    if (state.mode === "recorded") {
      try { state.recorded = await fetchJSON("data/recorded/index.json", {}, 8000); state.recordedDocs = await fetchJSON("data/recorded/documents.json", {}, 8000); }
      catch (e) { state.recorded = null; }
    }
    renderMode();
    try { state.examples = await fetchJSON("data/examples.json", {}, 8000); } catch (e) { state.examples = []; }
    bindUI();
    await loadDocs();
    route();
  }

  function renderMode() {
    const b = $("#modebadge"), t = $("#modetext");
    if (state.mode === "live") {
      const r = state.release;
      b.className = "modebadge live";
      t.textContent = `실시간 실행 · ${r.planner === "neural" ? "모델 " + r.model_id : "휴리스틱 플래너"} · ${r.version} (${r.commit})`;
      $("#apidocs").hidden = false;
      $("#footrelease").textContent = `백엔드 ${r.version} · commit ${r.commit} · 동시 작업 ${r.max_concurrent_jobs} · 작업 시간 제한 ${r.job_timeout_s}s`;
    } else if (state.recorded) {
      const r = state.recorded;
      b.className = "modebadge rec";
      t.textContent = `저장된 실행 결과 · ${r.model_id || r.planner} · ${r.generated_at} · commit ${r.commit}`;
      $("#recordednotice").hidden = false;
      $("#footrelease").textContent = `정적 데모: 결과는 ${r.generated_at}에 ${r.planner} 플래너(${r.model_id || "-"})로 실행해 저장한 것입니다.`;
    } else {
      b.className = "modebadge";
      t.textContent = "백엔드도 저장된 결과도 없음";
      showError("백엔드에 연결할 수 없고 저장된 실행 결과(data/recorded)도 없습니다. docker compose up 으로 백엔드를 띄우세요.");
    }
  }

  function bindUI() {
    $$(".segbtn").forEach((b) => b.addEventListener("click", async () => {
      $$(".segbtn").forEach((x) => { x.classList.toggle("is-active", x === b); x.setAttribute("aria-selected", x === b); });
      state.corpus = b.dataset.corpus; state.doc = null; state.tableId = null;
      clearResult(); await loadDocs();
    }));
    $$(".mtab").forEach((b) => b.addEventListener("click", () => showPane(b.dataset.pane)));
    $("#docfilter").addEventListener("input", () => renderDocList());
    $("#doclist").addEventListener("keydown", (e) => {
      const items = $$("li", $("#doclist")); if (!items.length) return;
      let i = items.findIndex((li) => li.getAttribute("aria-selected") === "true");
      if (e.key === "ArrowDown") { e.preventDefault(); selectDoc(items[Math.min(items.length - 1, i + 1)].dataset.id); }
      if (e.key === "ArrowUp") { e.preventDefault(); selectDoc(items[Math.max(0, i - 1)].dataset.id); }
      if (e.key === "Enter" && i >= 0) { e.preventDefault(); $("#question").focus(); }
    });
    $("#askform").addEventListener("submit", (e) => { e.preventDefault(); ask($("#question").value.trim()); });
    $("#question").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#askform").requestSubmit(); } });
    window.addEventListener("hashchange", route);
    $$(".navlink[data-view]").forEach((a) => a.addEventListener("click", () => setTimeout(route, 0)));
  }

  function route() {
    const h = (location.hash || "#workbench").replace("#", "");
    const view = ["workbench", "research", "about"].includes(h) ? h : "workbench";
    $$(".navlink[data-view]").forEach((a) => a.classList.toggle("is-active", a.dataset.view === view));
    $$(".view").forEach((v) => (v.hidden = v.id !== "view-" + view));
    $("#main").dataset.view = view;
    if (view === "research") loadResearch();
    if (view === "about") loadGraph();
  }

  function showPane(name) {
    $$(".mtab").forEach((b) => b.classList.toggle("is-active", b.dataset.pane === name));
    $$(".pane").forEach((p) => p.classList.toggle("is-visible", p.id === "pane-" + name));
  }
  showPane("left");

  // ---------- documents ----------
  async function loadDocs() {
    const list = $("#doclist");
    list.innerHTML = '<li class="skeleton"></li><li class="skeleton"></li><li class="skeleton"></li>';
    try {
      if (state.mode === "live") {
        const r = await fetchJSON(`v1/documents?corpus=${state.corpus}&limit=2000`, {}, 10000);
        state.docs = r.items;
      } else if (state.recordedDocs) {
        state.docs = Object.values(state.recordedDocs).filter((d) => d.corpus === state.corpus)
          .map((d) => ({ id: d.id, title: d.title, n_tables: d.tables.length, n_passages: d.passages.length }));
      } else { state.docs = []; }
    } catch (e) { state.docs = []; showError("문서 목록을 불러오지 못했습니다: " + e.message); }
    $("#doccount").textContent = `${state.docs.length}개`;
    renderDocList();
    $("#docempty").hidden = false; $("#docview").hidden = true;
    renderExamples();
    // auto-select the first document that has representative questions so the page is never empty
    const ex = state.examples.find((x) => x.corpus === state.corpus && state.docs.some((d) => d.id === x.doc_id));
    if (ex) selectDoc(ex.doc_id, { auto: true });
  }

  function renderDocList() {
    const q = $("#docfilter").value.trim().toLowerCase();
    const list = $("#doclist");
    const withEx = new Set(state.examples.filter((x) => x.corpus === state.corpus).map((x) => x.doc_id));
    const docs = state.docs.filter((d) => !q || d.title.toLowerCase().includes(q));
    docs.sort((a, b) => (withEx.has(b.id) - withEx.has(a.id)) || a.title.localeCompare(b.title));
    list.innerHTML = docs.slice(0, 400).map((d) => `<li role="option" data-id="${esc(d.id)}" aria-selected="${state.doc && state.doc.id === d.id}" title="${esc(d.title)}">
        <span class="title">${withEx.has(d.id) ? "★ " : ""}${esc(d.title)}</span><span class="ntab">표 ${d.n_tables}</span></li>`).join("") || '<li class="muted">문서 없음</li>';
    $$("li[data-id]", list).forEach((li) => li.addEventListener("click", () => selectDoc(li.dataset.id)));
  }

  async function selectDoc(id, opts = {}) {
    let doc;
    try {
      doc = state.mode === "live" ? await fetchJSON(`v1/documents/${encodeURIComponent(id)}`, {}, 10000) : state.recordedDocs[id];
    } catch (e) { showError("문서를 불러오지 못했습니다: " + e.message); return; }
    if (!doc) return;
    state.doc = doc; state.tableId = doc.tables.length ? doc.tables[0].id : null;
    $$("li[data-id]", $("#doclist")).forEach((li) => li.setAttribute("aria-selected", li.dataset.id === id));
    renderDoc(doc);
    renderExamples();
    $("#question").disabled = state.mode !== "live"; $("#askbtn").disabled = state.mode !== "live";
    if (state.mode === "live") $("#question").placeholder = "이 문서에 대해 질문하세요 (Enter로 실행)";
    clearResult();
    if (window.innerWidth <= 1000 && !opts.auto) showPane("center");
  }

  function renderDoc(doc) {
    $("#docempty").hidden = true; $("#docview").hidden = false;
    $("#doctitle").textContent = doc.title;
    const src = doc.source || {};
    $("#docmeta").innerHTML = `${esc(src.name || "")} · ${esc(src.license || "")}${src.url ? ` · <a href="${esc(src.url)}" target="_blank" rel="noopener">출처</a>` : ""} · 문단 ${doc.passages.length} · 표 ${doc.tables.length}`;
    const body = $("#docbody");
    const parts = [];
    const maxP = Math.min(doc.passages.length, 60);
    doc.passages.slice(0, maxP).forEach((p) => parts.push(`<p class="passage" id="p-${esc(p.id)}" data-pid="${esc(p.id)}">${p.section ? `<span class="sec">${esc(p.section)}</span>` : ""}<span class="ptext">${esc(p.text)}</span></p>`));
    if (doc.passages.length > maxP) parts.push(`<p class="muted">… 문단 ${doc.passages.length - maxP}개 생략</p>`);
    doc.tables.forEach((t) => parts.push(renderTable(t)));
    body.innerHTML = parts.join("");
    $$(".tablewrap", body).forEach((w) => w.addEventListener("click", () => { state.tableId = w.dataset.tid; $$(".tablewrap", body).forEach((x) => x.classList.toggle("is-selected", x === w)); }));
    $$("td[data-rc]", body).forEach((td) => td.addEventListener("click", (e) => {
      e.stopPropagation();
      const w = td.closest(".tablewrap"); state.tableId = w.dataset.tid;
      $$(".tablewrap", body).forEach((x) => x.classList.toggle("is-selected", x === w));
      const info = $(".cellinfo", w);
      info.textContent = `${td.dataset.rc} · ${td.dataset.header}${td.dataset.unit ? " (" + td.dataset.unit + ")" : ""} = ${td.dataset.text}`;
    }));
    const first = $(".tablewrap", body); if (first) first.classList.add("is-selected");
  }

  function renderTable(t) {
    const head = t.header.map((h, c) => `<th>${esc(h)}${t.units && t.units[c] ? `<span class="unit">[${esc(t.units[c])}]</span>` : ""}</th>`).join("");
    const rows = t.rows.map((r, i) => `<tr><td class="rc">r${i}</td>${r.map((v, c) => `<td data-rc="r${i}c${c}" data-header="${esc(t.header[c])}" data-unit="${esc((t.units || {})[c] || "")}" data-text="${esc(v)}" title="r${i}c${c} · ${esc(t.header[c])}">${esc(v)}</td>`).join("")}</tr>`).join("");
    return `<div class="tablewrap" id="t-${esc(t.id)}" data-tid="${esc(t.id)}">
      <div class="tablecap"><span><b>${esc(t.caption || t.title)}</b> <span class="muted">· ${t.rows.length}행 × ${t.header.length}열 · id ${esc(t.id)}</span></span><span class="muted">셀을 누르면 좌표·헤더·단위</span></div>
      <div style="overflow:auto"><table class="tt"><thead><tr><th class="rc">r\\c</th>${head}</tr></thead><tbody>${rows}</tbody></table></div>
      <div class="cellinfo" aria-live="polite"></div></div>`;
  }

  function renderExamples() {
    const box = $("#examples");
    if (!state.doc) { box.innerHTML = '<p class="muted">문서를 고르면 그 문서의 대표 질문이 나옵니다.</p>'; return; }
    let ex = state.examples.filter((x) => x.doc_id === state.doc.id);
    if (state.mode === "recorded" && state.recorded) {
      const have = new Set(state.recorded.runs.map((r) => r.id));
      ex = ex.filter((x) => have.has(x.id));
    }
    box.innerHTML = ex.length ? ex.map((x) => `<button type="button" class="chip" data-ex="${esc(x.id)}"><span class="cat">${esc(CATS[x.category] || x.category)} · ${esc(x.label || "")}</span><br>${esc(x.question)}</button>`).join("")
      : '<p class="muted">이 문서에는 대표 질문이 없습니다. 직접 질문해 보세요.</p>';
    $$(".chip", box).forEach((b) => b.addEventListener("click", () => {
      const x = state.examples.find((y) => y.id === b.dataset.ex);
      $("#question").value = x.question; state.tableId = x.table_id;
      if (state.mode === "live") ask(x.question, x.table_id); else showRecorded(x.id);
      if (window.innerWidth <= 1000) showPane("right");
    }));
  }

  // ---------- asking ----------
  function clearResult() { $("#result").hidden = true; $("#result").innerHTML = ""; $("#resultempty").hidden = false; $("#status").hidden = true; $("#errorbar").hidden = true; clearEvidence(); }
  function showError(msg, retry) {
    const bar = $("#errorbar"); bar.hidden = false;
    bar.innerHTML = `<span>${esc(msg)}</span>${retry ? '<button type="button" class="btn" id="retrybtn">다시 시도</button>' : ""}`;
    if (retry) $("#retrybtn").addEventListener("click", retry);
  }
  function setStatus(text, spinning) {
    const s = $("#status"); s.hidden = false; s.innerHTML = `${spinning ? '<span class="spin" aria-hidden="true"></span>' : ""}<span>${esc(text)}</span>`;
  }

  async function ask(question, tableId) {
    if (!question || state.busy || state.mode !== "live" || !state.doc) return;
    state.busy = true; $("#askbtn").disabled = true; $("#errorbar").hidden = true; $("#result").hidden = true; $("#resultempty").hidden = true; clearEvidence();
    const body = { question, corpus: state.corpus, doc_id: state.doc.id, table_id: tableId || state.tableId || undefined, planner: $("#planner").value };
    const t0 = performance.now();
    state.timer = setInterval(() => setStatus(`실행 중 · ${fmtMs(performance.now() - t0)} · 검색 → 제안 → 도구 → 검증`, true), 250);
    setStatus("작업을 제출했습니다…", true);
    try {
      let job = await fetchJSON("v1/ask?wait=1", { method: "POST", body: JSON.stringify(body) }, 90000);
      while (job.status === "queued" || job.status === "running") {
        await new Promise((r) => setTimeout(r, 400));
        job = await fetchJSON(`v1/jobs/${job.id}`, {}, 8000);
      }
      clearInterval(state.timer);
      if (job.status !== "done") { setStatus(`작업 ${job.id} · ${job.status}`, false); showError(`작업이 ${job.status === "timeout" ? "시간 초과" : "실패"}했습니다: ${job.error || ""}`, () => ask(question, tableId)); return; }
      setStatus(`완료 · ${fmtMs(job.elapsed_ms)} · 작업 ${job.id}`, false);
      renderResult(job.result, { kind: "live" });
    } catch (e) {
      clearInterval(state.timer);
      setStatus("오류", false);
      showError(e.status === 429 ? "대기열이 가득 찼습니다. 잠시 후 다시 시도하세요." : e.status === 422 ? "입력이 잘못되었습니다: " + e.message : "요청 실패: " + e.message, () => ask(question, tableId));
    } finally { state.busy = false; $("#askbtn").disabled = state.mode !== "live"; }
  }

  function showRecorded(exId) {
    const run = state.recorded.runs.find((r) => r.id === exId);
    if (!run) return;
    $("#errorbar").hidden = true; $("#resultempty").hidden = true;
    setStatus(`저장된 결과 · 기록 ${state.recorded.generated_at} · ${fmtMs(run.result.elapsed_ms)}`, false);
    renderResult(run.result, { kind: "recorded", at: state.recorded.generated_at, model: state.recorded.model_id, commit: state.recorded.commit });
  }

  // ---------- result rendering ----------
  function renderResult(res, meta) {
    const box = $("#result"); box.hidden = false;
    const modeBadge = meta.kind === "live" ? '<span class="badge badge-live">실시간 실행</span>' : `<span class="badge badge-rec" title="commit ${esc(meta.commit)}">저장된 실행 결과 · ${esc(meta.at)}</span>`;
    const plannerBadge = res.planner ? `<span class="badge badge-mode">${res.planner.mode === "neural" ? "모델 " + esc(res.planner.model_id || "") : "휴리스틱"}${res.trace && res.trace.some((s) => s.input && s.input.fallback) ? " → 휴리스틱 보완" : ""}</span>` : "";
    let head, bodyHtml;
    if (res.status === "answered") {
      head = '<span class="badge badge-ok">완료 · 검증 통과</span>';
      bodyHtml = `<div class="answer">${esc(res.answer)}</div>`;
    } else if (res.status === "abstained") {
      head = '<span class="badge badge-hold">답변 보류</span>';
      const reason = res.verdict && res.verdict.reason;
      bodyHtml = `<div class="answer hold">답변을 보류했습니다</div><div class="reason">${esc(REASONS[reason] || reason || "")}</div>`;
    } else {
      head = '<span class="badge badge-err">오류</span>';
      bodyHtml = `<div class="answer hold">${esc(res.error || "실행 오류")}</div>`;
    }
    const evidence = renderEvidence(res);
    const calc = res.calculation ? renderCalc(res.calculation) : "";
    const checks = res.verdict && res.verdict.checks ? `<ul class="checks">${res.verdict.checks.map((c) => `<li><span class="${c.passed ? "ok" : "ng"}">${c.passed ? "✓" : "✗"}</span><span><b>${esc(CHECKS[c.name] || c.name)}</b><br><span class="d">${esc(c.detail)}</span></span></li>`).join("")}</ul>` : '<p class="muted">검사 없음</p>';
    const trace = (res.trace || []).map((s) => `<li><details><summary><b>${esc(s.step)}</b>${s.tool ? ` <span class="muted">${esc(s.tool)}</span>` : ""}${s.status !== "ok" ? ` <span class="badge badge-err">${esc(s.status)}</span>` : ""}<span class="ms">${fmtMs(s.ms || 0)}</span></summary><pre>${esc(JSON.stringify({ input: s.input, output: s.output }, null, 1))}</pre></details></li>`).join("");
    box.innerHTML = `
      <div class="card"><div class="card-head"><span>답변 ${modeBadge} ${plannerBadge}</span>${head}</div><div class="card-body">${bodyHtml}
        <p class="muted" style="margin:8px 0 0;font-size:12px">질문: ${esc(res.question)} · 표 ${esc(res.table_id || "-")} · ${fmtMs(res.elapsed_ms || 0)}</p></div></div>
      <div class="card"><div class="card-head"><span>근거</span><span>${res.evidence_cells.length}개 셀 · ${res.evidence_spans.length}개 문장</span></div><div class="card-body">${evidence}</div></div>
      ${calc ? `<div class="card"><div class="card-head"><span>계산</span><span>제한 계산기(사칙연산, 단위 검사)</span></div><div class="card-body calc">${calc}</div></div>` : ""}
      <div class="card"><div class="card-head"><span>검증 항목</span><span>${res.verdict ? res.verdict.checks.filter((c) => c.passed).length + "/" + res.verdict.checks.length + " 통과" : ""}</span></div><div class="card-body">${checks}</div></div>
      <div class="card"><div class="card-head"><span>실행 추적</span><span>LangGraph 노드 · 도구 호출</span></div><div class="card-body"><ul class="trace">${trace}</ul>
        ${res.planner && res.planner.raw_output ? `<details style="margin-top:8px"><summary class="muted">플래너 원문 출력</summary><div class="raw">${esc(res.planner.raw_output)}</div></details>` : ""}</div></div>`;
    $$(".evbtn", box).forEach((b) => b.addEventListener("click", () => focusEvidence(b.dataset.target, b.dataset.kind)));
    highlightEvidence(res);
  }

  function renderEvidence(res) {
    const items = [];
    (res.evidence_cells || []).forEach((c, i) => {
      const td = findCell(c); const h = td ? td.dataset.header : ""; const u = td ? td.dataset.unit : ""; const v = td ? td.dataset.text : "";
      items.push(`<li><button type="button" class="evbtn" data-kind="cell" data-target="${esc(c.table_id)}|r${c.row}c${c.col}" aria-label="근거 ${i + 1} 셀로 이동">${i + 1} · r${c.row}c${c.col}</button><span class="evtext"><b>${esc(v)}</b>${u ? ` <span class="muted">${esc(u)}</span>` : ""}<br><span class="h">${esc(h)} · 표 ${esc(c.table_id)}</span></span></li>`);
    });
    (res.evidence_spans || []).forEach((s, i) => {
      items.push(`<li><button type="button" class="evbtn" data-kind="span" data-target="${esc(s.passage_id)}" aria-label="근거 문장으로 이동">문장</button><span class="evtext">“${esc(s.text)}”<br><span class="h">문단 ${esc(s.passage_id)} · 위치 ${s.start}–${s.end}</span></span></li>`);
    });
    return items.length ? `<ul class="evlist">${items.join("")}</ul>` : '<p class="muted">근거가 제시되지 않았습니다(보류).</p>';
  }

  function renderCalc(c) {
    return `<div class="expr">${esc(c.op)}: ${esc(c.expression)} = <b>${esc(c.formatted)}</b></div>
      <table><thead><tr><th>셀</th><th>원문</th><th>값</th><th>단위</th></tr></thead><tbody>${c.inputs.map((i) => `<tr><td>r${i.cell.row}c${i.cell.col}</td><td>${esc(i.raw)}</td><td>${i.value}</td><td>${esc(i.unit || "-")}</td></tr>`).join("")}</tbody></table>`;
  }

  function findCell(c) { return document.querySelector(`#t-${CSS.escape(c.table_id)} td[data-rc="r${c.row}c${c.col}"]`); }
  function clearEvidence() {
    $$("td.is-evidence").forEach((td) => { td.classList.remove("is-evidence", "is-focus"); const n = $(".evn", td); if (n) n.remove(); });
    $$(".passage.is-evidence").forEach((p) => { p.classList.remove("is-evidence"); const t = $(".ptext", p); if (t) t.textContent = t.textContent; });
  }
  function highlightEvidence(res) {
    clearEvidence();
    (res.evidence_cells || []).forEach((c, i) => { const td = findCell(c); if (td) { td.classList.add("is-evidence"); td.insertAdjacentHTML("beforeend", `<span class="evn">${i + 1}</span>`); } });
    (res.evidence_spans || []).forEach((s) => {
      const p = document.getElementById("p-" + s.passage_id); if (!p) return;
      p.classList.add("is-evidence");
      const t = $(".ptext", p); const txt = t.textContent;
      if (s.start >= 0 && s.end <= txt.length && txt.slice(s.start, s.end) === s.text) t.innerHTML = `${esc(txt.slice(0, s.start))}<mark class="span">${esc(s.text)}</mark>${esc(txt.slice(s.end))}`;
    });
    const first = (res.evidence_cells || [])[0]; if (first) { const td = findCell(first); if (td && window.innerWidth > 1000) td.scrollIntoView({ block: "center", behavior: "smooth" }); }
  }
  function focusEvidence(target, kind) {
    if (window.innerWidth <= 1000) showPane("center");
    if (kind === "cell") { const [tid, rc] = target.split("|"); const td = document.querySelector(`#t-${CSS.escape(tid)} td[data-rc="${rc}"]`); if (td) { $$("td.is-focus").forEach((x) => x.classList.remove("is-focus")); td.classList.add("is-focus"); td.scrollIntoView({ block: "center", behavior: "smooth" }); } }
    else { const p = document.getElementById("p-" + target); if (p) p.scrollIntoView({ block: "center", behavior: "smooth" }); }
  }

  // ---------- research + about ----------
  let researchLoaded = false;
  async function loadResearch() {
    if (researchLoaded) return;
    const box = $("#research");
    try {
      const data = await fetchJSON("data/research.json", {}, 10000);
      box.innerHTML = renderResearch(data); researchLoaded = true;
    } catch (e) { box.innerHTML = `<p class="muted">연구 결과 파일(data/research.json)을 아직 만들지 않았습니다: ${esc(e.message)}</p>`; }
  }
  function renderResearch(d) {
    const pill = (s) => s === "done" ? '<span class="pill done">실행·측정 완료</span>' : s === "prep" ? '<span class="pill prep">구현 후 미실행</span>' : s === "fail" ? '<span class="pill fail">실행했으나 실패/미달</span>' : s === "none" ? '<span class="pill">미구현</span>' : "";
    const cond = (c) => c && Object.keys(c).length ? `<div class="condbox"><dl>${Object.entries(c).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</dd>`).join("")}</dl></div>` : "";
    const table = (cols, rows) => `<table class="res"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((v, i) => `<td class="${typeof v === "number" || /^[\d.,%\s−-]+$/.test(String(v)) ? "num" : ""}">${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    return `<h2>연구 결과 <span class="muted" style="font-weight:400;font-size:13px">생성 ${esc(d.generated_at)} · commit ${esc(d.commit)}</span></h2>
      <p>${esc(d.summary || "")}</p>
      ${(d.sections || []).map((s) => `<section><h3>${esc(s.title)} ${pill(s.status)}</h3>${s.description ? `<p>${esc(s.description)}</p>` : ""}${cond(s.conditions)}${s.columns ? table(s.columns, s.rows || []) : ""}${(s.notes || []).length ? `<ul>${s.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}${s.artifact ? `<p class="muted">산출물: <code>${esc(s.artifact)}</code></p>` : ""}</section>`).join("")}`;
  }
  async function loadGraph() {
    const pre = $("#graphsrc"); if (pre.textContent) return;
    try { const g = state.mode === "live" ? (await fetchJSON("v1/graph", {}, 5000)).mermaid : (await fetchJSON("data/graph.json", {}, 5000)).mermaid; pre.textContent = g; }
    catch (e) { pre.textContent = "graph TD; retrieve --> propose --> verify; verify -->|retry| propose_fallback --> verify; verify -->|done| finalize"; }
  }

  init();
})();
