/* TableTrace console — vanilla JS, no build step.
   Live mode: talks to the FastAPI backend on the same origin.
   Recorded mode: loads data/recorded/*.json produced by scripts/make_recorded_runs.py.
   Both modes read data/examples.json: the evaluation question sets with their gold answers. */
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtMs = (ms) => (ms >= 1000 ? (ms / 1000).toFixed(2) + " s" : Math.round(ms) + " ms");
  const fmtNum = (v) => Number(v).toLocaleString("ko-KR", { maximumFractionDigits: 6 });
  const cut = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + "…" : String(s));

  const REASONS = {
    not_in_document: "문서에 근거가 없음", ambiguous_question: "질문이 모호함(후보가 여럿)", unit_mismatch: "단위·기간 불일치로 계산 거부",
    verification_failed: "모델 제안이 검증에 실패", retrieval_low: "관련 표를 찾지 못함", invalid_program: "모델 출력을 해석할 수 없음", timeout: "시간 초과",
  };
  const CHECKS = {
    cells_in_range: "셀 좌표가 표 범위 안", period_consistent: "질문의 연도와 근거 행의 연도 일치", answer_matches_cell: "답이 근거 셀의 텍스트와 일치",
    calculation: "제한 계산기 재계산", units_consistent: "계산 입력의 단위 일치", answer_matches_calc: "모델의 숫자와 계산값 일치",
    answer_in_passage: "답이 본문 문장에 존재", abstain: "보류 판정",
    evidence_repaired: "모델이 인용한 셀에 답이 없어 근거를 고침", subject_in_evidence: "질문의 대상이 근거 행에 있음",
    column_repaired: "질문이 가리키는 열로 근거를 옮김", distinct_cells: "계산에 쓴 셀이 서로 다름",
  };
  const CATS = { cell: "셀 근거", calc: "계산", text_table: "본문+표", unit_period: "단위·기간 주의", abstain: "답 없음 → 보류" };
  const OPS = { lookup: "셀 조회", text: "본문에서 답", abstain: "보류", diff: "두 셀의 차이", sum: "합", avg: "평균", ratio: "비율", pct_change: "변화율" };
  // How a stored result compares with the gold answer. The sign says whether the system did the right thing; the word says what it did.
  const MARKS = {
    correct: { sym: "✓", word: "맞음", cls: "ok" }, wrong: { sym: "✗", word: "틀림", cls: "ng" },
    hold_ok: { sym: "✓", word: "보류", cls: "ok" }, hold_miss: { sym: "✗", word: "보류", cls: "ng" },
    answered_unanswerable: { sym: "✗", word: "답함", cls: "ng" },
  };
  const VIEWS = ["workbench", "matrix", "research", "about"];

  const state = { mode: null, corpus: "ko_tables", set: null, docs: [], doc: null, tableId: null, sets: [], marks: {}, examples: [], exById: {},
    recorded: null, runs: {}, release: null, busy: false, timer: null, shown: null, chat: { session: null, turns: [] } };

  const markTitle = (m) => state.marks[m] || m;
  const markHtml = (m, long) => { const k = MARKS[m]; return k ? `<span class="mark mark-${k.cls}" title="${esc(markTitle(m))}">${k.sym} ${esc(long ? markTitle(m) : k.word)}</span>` : ""; };
  const goldText = (ex) => (ex.gold.status === "abstained" ? "답 없음(보류가 맞음)" : ex.gold.answers.join(" 또는 "));

  // Recorded mode: runs are stored per planner. "auto" shows, for each question, the planner with the most right answers on that question's set.
  const plannerKeys = () => (state.recorded ? state.recorded.planner_order.filter((k) => state.recorded.planners[k]) : []);
  const plannerShort = (k) => (state.recorded && state.recorded.planners[k] ? state.recorded.planners[k].short : k);
  function bestPlanner(setKey) {
    let best = null, n = -1;
    for (const k of plannerKeys()) { const t = state.recorded.planners[k].totals[setKey]; if (t && t.right > n) { best = k; n = t.right; } }
    return best;
  }
  function recordedRun(exId, planner) {
    const ex = state.exById[exId]; if (!ex || !state.recorded) return null;
    const sel = planner || $("#planner").value;
    const key = sel === "auto" ? bestPlanner(ex.set) : sel;
    const run = key && state.runs[key] && state.runs[key][exId];
    return run ? { run, key, set: state.recorded.planners[key] } : null;
  }

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

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage can be blocked (private window, sandboxed frame) */ } },
  };

  // ---------- boot ----------
  async function init() {
    if (store.get("tt.intro") === "closed") $("#intro").hidden = true;
    $("#introclose").addEventListener("click", () => { $("#intro").hidden = true; store.set("tt.intro", "closed"); });
    try {
      state.release = await fetchJSON("v1/release", {}, 3000);
      state.mode = "live";
    } catch (e) {
      state.mode = "recorded";
    }
    if (state.mode === "recorded") {
      try { await loadRecorded(); state.recordedDocs = await fetchJSON("data/recorded/documents.json", {}, 15000); }
      catch (e) { state.recorded = null; }
    }
    try {
      const ex = await fetchJSON("data/examples.json", {}, 8000);
      state.sets = ex.sets; state.marks = ex.marks; state.examples = ex.examples;
    } catch (e) { state.sets = []; state.examples = []; }
    state.exById = Object.fromEntries(state.examples.map((x) => [x.id, x]));
    renderMode();
    bindUI();
    showPane(state.mode === "recorded" ? "right" : "left");
    await loadDocs({ open: false });
    const h = parseHash();
    if (h.ex && state.exById[h.ex]) await openExample(h.ex, h.planner);
    else if (state.mode === "recorded" && state.recorded && state.exById[state.recorded.featured]) await openExample(state.recorded.featured);
    else selectFirstDoc();
    route(true);
    initLive();
  }

  async function loadRecorded() {
    if (state.recorded) return;
    const r = await fetchJSON("data/recorded/index.json", {}, 20000);
    state.runs = Object.fromEntries(Object.entries(r.planners).map(([k, p]) => [k, Object.fromEntries(p.runs.map((x) => [x.id, x]))]));
    state.recorded = r;
  }

  function renderMode() {
    const b = $("#modebadge"), t = $("#modetext"), sel = $("#planner");
    if (state.mode === "live") {
      const r = state.release;
      b.className = "modebadge live";
      t.textContent = `실시간 실행 · ${r.planner === "neural" ? "모델 " + r.model_id : "휴리스틱 플래너"} · ${r.version} (${r.commit})`;
      $("#apidocs").hidden = false;
      $("#footrelease").textContent = `백엔드 ${r.version} · commit ${r.commit} · 동시 작업 ${r.max_concurrent_jobs} · 작업 시간 제한 ${r.job_timeout_s}s`;
      sel.innerHTML = '<option value="auto">자동(모델 → 보완)</option><option value="neural">신경망(mT5)</option><option value="heuristic">휴리스틱(어휘 겹침)</option>';
    } else if (state.recorded) {
      const r = state.recorded;
      b.className = "modebadge rec";
      t.textContent = window.innerWidth <= 480 ? `저장된 실행 결과 · ${r.generated_at.slice(0, 10)}` : `저장된 실행 결과 · ${r.generated_at} · commit ${r.commit}`;
      t.title = `commit ${r.commit} · ` + plannerKeys().map(plannerShort).join(" / ");
      sel.innerHTML = '<option value="auto">자동(가장 많이 맞힌 플래너)</option>' + plannerKeys().map((k) => `<option value="${esc(k)}" title="${esc(r.planners[k].model_id || "")}">${esc(r.planners[k].short)}</option>`).join("");
      $("#recordednotice").hidden = false;
      $("#footrelease").textContent = `정적 데모: 저장된 모델 출력을 저장소의 파이프라인에 넣어 ${r.generated_at}에 기록한 결과입니다. 평가와 같은 설정이라 맞음·틀림이 보고서의 수치와 같습니다.`;
      $("#chatbox").hidden = true; $("#askbtn").hidden = true;      // nothing can be asked without a backend: no dead controls
    } else {
      b.className = "modebadge";
      t.textContent = "백엔드도 저장된 결과도 없음";
      showError("백엔드에 연결할 수 없고 저장된 실행 결과(data/recorded)도 없습니다. docker compose up 으로 백엔드를 띄우세요.");
    }
  }

  function bindUI() {
    $$(".segbtn").forEach((b) => b.addEventListener("click", async () => {
      if (b.dataset.corpus === state.corpus) return;
      state.corpus = b.dataset.corpus; state.set = null;
      await loadDocs({ open: true });
      if (state.view === "matrix") renderMatrix();
    }));
    $$(".mtab").forEach((b) => b.addEventListener("click", () => showPane(b.dataset.pane)));
    $("#setsel").addEventListener("change", () => { state.set = $("#setsel").value; state.doc = null; clearResult(); renderSetSel(); renderDocList(); selectFirstDoc(); });
    $("#docfilter").addEventListener("input", () => renderDocList());
    $("#doclist").addEventListener("keydown", (e) => {
      const items = $$("li[data-id]", $("#doclist")); if (!items.length) return;
      let i = items.findIndex((li) => li.getAttribute("aria-selected") === "true");
      if (e.key === "ArrowDown") { e.preventDefault(); selectDoc(items[Math.min(items.length - 1, i + 1)].dataset.id); }
      if (e.key === "ArrowUp") { e.preventDefault(); selectDoc(items[Math.max(0, i - 1)].dataset.id); }
      if (e.key === "Enter" && i >= 0) { e.preventDefault(); $("#question").focus(); }
    });
    $("#askform").addEventListener("submit", (e) => { e.preventDefault(); ask($("#question").value.trim()); });
    $("#question").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#askform").requestSubmit(); } });
    $("#planner").addEventListener("change", () => { if (state.mode === "recorded") { renderExamples(); if (state.shown) showRecorded(state.shown); } });
    $("#chatnew").addEventListener("click", resetChat);
    $("#chatmode").addEventListener("change", resetChat);
    $("#chatuser").value = store.get("tt.user") || "";
    $("#chatuser").addEventListener("change", () => store.set("tt.user", $("#chatuser").value.trim()));
    if (state.mode !== "live") { $("#chatmode").disabled = true; $("#chatuser").disabled = true; $("#chatnew").disabled = true; $("#chatbox summary .muted").textContent = "백엔드가 연결된 실시간 모드에서만 쓸 수 있습니다"; }
    window.addEventListener("hashchange", () => route(false));
  }

  // "#workbench/<question id>/<planner>" opens one stored result, so a result can be linked to.
  function parseHash() {
    const parts = (location.hash || "#workbench").slice(1).split("/");
    return { view: VIEWS.includes(parts[0]) ? parts[0] : "workbench", ex: parts[1] ? decodeURIComponent(parts[1]) : null, planner: parts[2] || null };
  }
  function route(first) {
    const h = parseHash();
    state.view = h.view;
    $$(".navlink[data-view]").forEach((a) => a.classList.toggle("is-active", a.dataset.view === h.view));
    $$(".view").forEach((v) => (v.hidden = v.id !== "view-" + h.view));
    $("#main").dataset.view = h.view;
    $(".corpusbar").hidden = !(h.view === "workbench" || h.view === "matrix");
    $(".mobiletabs").hidden = h.view !== "workbench";
    if (h.view === "research") loadResearch();
    if (h.view === "about") loadGraph();
    if (h.view === "matrix") renderMatrix();
    if (h.view === "workbench" && !first && h.ex && state.exById[h.ex] && (h.ex !== state.shown || (h.planner && h.planner !== $("#planner").value))) openExample(h.ex, h.planner);
  }

  function showPane(name) {
    $$(".mtab").forEach((b) => b.classList.toggle("is-active", b.dataset.pane === name));
    $$(".pane").forEach((p) => p.classList.toggle("is-visible", p.id === "pane-" + name));
  }

  // ---------- question sets and documents ----------
  // A set is listed when it belongs to the corpus and at least one of its documents can be opened here
  // (the chemistry paper tables exist in the stored results only, not in the backend's corpus).
  function corpusSets() {
    const have = new Set(state.docs.map((d) => d.id));
    return state.sets.filter((s) => s.corpus === state.corpus && state.examples.some((x) => x.set === s.key && have.has(x.doc_id)));
  }
  function renderSetSel() {
    const sets = corpusSets();
    const opts = sets.map((s) => `<option value="${esc(s.key)}">${esc(s.title)}</option>`);
    if (state.mode === "live" || !sets.length) opts.push('<option value="all">모든 문서</option>');
    if (state.set !== "all" && !sets.some((s) => s.key === state.set)) state.set = sets.length ? sets[0].key : "all";
    $("#setsel").innerHTML = opts.join(""); $("#setsel").value = state.set;
    const s = sets.find((x) => x.key === state.set);
    $("#setnote").textContent = s ? s.note : "이 코퍼스의 모든 문서입니다. 문서를 고르고 질문을 직접 입력하세요.";
  }
  const inSet = (x) => state.set === "all" || x.set === state.set;
  function setDocs() {
    if (state.set === "all") return state.docs.slice().sort((a, b) => a.title.localeCompare(b.title));
    const order = []; state.examples.filter(inSet).forEach((x) => { if (!order.includes(x.doc_id)) order.push(x.doc_id); });
    return order.map((id) => state.docs.find((d) => d.id === id)).filter(Boolean);
  }
  const docExamples = (docId) => state.examples.filter((x) => x.doc_id === docId && inSet(x));

  async function loadDocs(opts = {}) {
    $$(".segbtn").forEach((x) => { const on = x.dataset.corpus === state.corpus; x.classList.toggle("is-active", on); x.setAttribute("aria-selected", on); });
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
    state.doc = null; state.tableId = null;
    clearResult(); renderSetSel(); renderDocList();
    $("#docempty").hidden = false; $("#docview").hidden = true;
    renderExamples();
    if (opts.open !== false) selectFirstDoc();
  }
  // the page is never empty: the first document of the set is opened, and in recorded mode its first question too
  function selectFirstDoc() { const d = setDocs()[0]; if (d) selectDoc(d.id, { auto: true }); }

  function renderDocList() {
    const q = $("#docfilter").value.trim().toLowerCase();
    const list = $("#doclist");
    const docs = setDocs().filter((d) => !q || d.title.toLowerCase().includes(q));
    $("#doccount").textContent = `${docs.length}개`;
    list.innerHTML = docs.slice(0, 400).map((d) => { const n = docExamples(d.id).length;
      return `<li role="option" data-id="${esc(d.id)}" aria-selected="${!!state.doc && state.doc.id === d.id}" title="${esc(d.title)}">
        <span class="title">${esc(d.title)}</span><span class="ntab">${n ? "질문 " + n : "표 " + d.n_tables}</span></li>`; }).join("") || '<li class="muted">문서 없음</li>';
    $$("li[data-id]", list).forEach((li) => li.addEventListener("click", () => selectDoc(li.dataset.id)));
  }

  async function selectDoc(id, opts = {}) {
    let doc;
    try {
      doc = state.mode === "live" ? await fetchJSON(`v1/documents/${encodeURIComponent(id)}`, {}, 10000) : state.recordedDocs[id];
    } catch (e) { showError("문서를 불러오지 못했습니다: " + e.message); return; }
    if (!doc) return;
    state.doc = doc; state.tableId = doc.tables.length ? doc.tables[0].id : null;
    resetChat();                                   // another document starts another conversation
    $$("li[data-id]", $("#doclist")).forEach((li) => li.setAttribute("aria-selected", li.dataset.id === id));
    renderDoc(doc);
    const here = !!(window.TTLive && window.TTLive.ready());        // the verifier is loaded in this browser: a question can be typed
    $("#question").disabled = state.mode !== "live" && !here; $("#askbtn").disabled = state.mode !== "live";
    $("#question").placeholder = state.mode === "live" ? "이 문서에 대해 질문하세요 (Enter로 실행)" : here ? "질문 (영어 화학 문서에서는 직접 써도 됩니다)" : "저장된 결과에서는 왼쪽의 질문을 골라 주세요";
    clearResult();
    renderExamples();
    const first = docExamples(id).find((x) => state.mode !== "recorded" || recordedRun(x.id));
    if (state.mode === "recorded" && opts.open !== false && first) showRecorded(first.id);     // a result is on screen without another click
    if (window.innerWidth <= 1000 && !opts.auto) showPane("center");
  }

  function renderDoc(doc) {
    $("#docempty").hidden = true; $("#docview").hidden = false;
    $("#doctitle").textContent = doc.title;
    const src = doc.source || {};
    $("#docmeta").innerHTML = `${esc(src.name || "")} · ${esc(src.license || "")}${src.url ? ` · <a href="${esc(src.url)}" target="_blank" rel="noopener">출처</a>` : ""} · 문단 ${doc.passages.length} · 표 ${doc.tables.length}${src.note ? `<br><span class="srcnote">출처 메모: ${esc(src.note)}</span>` : ""}`;
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
      <div class="tablescroll"><table class="tt"><thead><tr><th class="rc">r\\c</th>${head}</tr></thead><tbody>${rows}</tbody></table></div>
      <div class="cellinfo" aria-live="polite"></div></div>`;
  }

  function renderExamples() {
    const box = $("#examples");
    if (!state.doc) { $("#excount").textContent = ""; box.innerHTML = '<p class="muted">문서를 고르면 그 문서의 질문이 나옵니다.</p>'; return; }
    const ex = docExamples(state.doc.id);
    $("#excount").textContent = ex.length ? `${ex.length}개` : "";
    if (!ex.length) { box.innerHTML = '<p class="muted">이 문서에는 준비된 질문이 없습니다. 직접 질문해 보세요.</p>'; return; }
    box.innerHTML = ex.map((x) => {
      const hit = state.mode === "recorded" ? recordedRun(x.id) : null;
      const review = x.review && x.review.verdict !== "ok" ? ' <span class="flag" title="소유자의 검수에서 고쳐야 한다고 적힌 문항입니다">검수: 고쳐야 함</span>' : "";
      const tail = state.mode !== "recorded" ? "" : hit ? markHtml(hit.run.mark) : '<span class="mark mark-none">저장 결과 없음</span>';
      return `<button type="button" class="chip${state.shown === x.id ? " is-active" : ""}" data-ex="${esc(x.id)}"${state.mode === "recorded" && !hit ? " disabled" : ""}>
        <span class="chiptop"><span class="cat">${esc(CATS[x.category] || x.category)}${x.label ? " · " + esc(x.label) : ""}</span>${tail}</span>${esc(x.question)}${review}</button>`; }).join("");
    $$(".chip", box).forEach((b) => b.addEventListener("click", () => runExample(state.exById[b.dataset.ex])));
  }

  function runExample(x) {
    $("#question").value = x.question; state.tableId = x.table_id;
    if (state.mode === "live") ask(x.question, x.table_id, x); else showRecorded(x.id);
    if (window.innerWidth <= 1000) showPane("right");
  }

  // Open one question by id (from a link, from the per-question table, or as the first screen).
  async function openExample(exId, planner) {
    const ex = state.exById[exId]; if (!ex) return;
    if (planner && $$("option", $("#planner")).some((o) => o.value === planner)) $("#planner").value = planner;
    if (ex.corpus !== state.corpus) { state.corpus = ex.corpus; state.set = ex.set; await loadDocs({ open: false }); }
    if (state.set !== "all" && state.set !== ex.set) { state.set = ex.set; renderSetSel(); renderDocList(); }
    if (!state.doc || state.doc.id !== ex.doc_id) await selectDoc(ex.doc_id, { auto: true, open: false });
    if (!state.doc) return;
    if (state.mode === "recorded") showRecorded(ex.id); else { $("#question").value = ex.question; state.tableId = ex.table_id; renderExamples(); }
  }

  // ---------- asking ----------
  // ---------- conversation (live mode): /v1/chat keeps the session; the page only shows the transcript ----------
  function resetChat() { state.chat = { session: null, turns: [] }; renderTranscript(); }
  function renderTranscript() {
    $("#transcript").innerHTML = state.chat.turns.map((t) => `<li><span class="who">질문</span> <span class="said">${esc(t.message)}</span><br><span class="who">답</span> ${esc(t.text)}${t.notes && t.notes.length ? `<br><span class="who">기억</span> <span class="muted">${esc(t.notes.join(" "))}</span>` : ""}</li>`).join("");
    const box = $("#transcript"); box.scrollTop = box.scrollHeight;
  }
  async function chatTurn(question, tableId) {
    const user = $("#chatuser").value.trim();
    const body = { message: question, corpus: state.corpus, planner: $("#planner").value, session_id: state.chat.session || undefined, user_id: user || undefined };
    if (!state.chat.session || tableId) { body.doc_id = state.doc.id; body.table_id = tableId || state.tableId || undefined; }   // later turns rely on the session's table
    const r = await fetchJSON("v1/chat", { method: "POST", body: JSON.stringify(body) }, 90000);
    state.chat.session = r.session_id;
    state.chat.turns.push({ message: question, text: r.text, notes: r.memory.notes });
    renderTranscript();
    return r;
  }
  function renderChatOnly(r) {
    const box = $("#result"); box.hidden = false; clearEvidence();
    box.innerHTML = `<div class="card"><div class="card-head"><span>기억 <span class="badge badge-mode">${esc(r.intent)}</span></span><span class="badge badge-rec">대화 ${r.turn + 1}번째 턴</span></div><div class="card-body"><div class="answer hold">${esc(r.text)}</div></div></div>`;
  }

  function clearResult() { state.shown = null; $("#result").hidden = true; $("#result").innerHTML = ""; $("#resultempty").hidden = false; $("#status").hidden = true; $("#errorbar").hidden = true; clearEvidence(); }
  function showError(msg, retry) {
    const bar = $("#errorbar"); bar.hidden = false;
    bar.innerHTML = `<span>${esc(msg)}</span>${retry ? '<button type="button" class="btn" id="retrybtn">다시 시도</button>' : ""}`;
    if (retry) $("#retrybtn").addEventListener("click", retry);
  }
  function setStatus(text, spinning) {
    const s = $("#status"); s.hidden = false; s.innerHTML = `${spinning ? '<span class="spin" aria-hidden="true"></span>' : ""}<span>${esc(text)}</span>`;
  }

  async function ask(question, tableId, ex) {
    if (!question || state.busy || state.mode !== "live" || !state.doc) return;
    state.busy = true; $("#askbtn").disabled = true; $("#errorbar").hidden = true; $("#result").hidden = true; $("#resultempty").hidden = true; clearEvidence();
    const body = { question, corpus: state.corpus, doc_id: state.doc.id, table_id: tableId || state.tableId || undefined, planner: $("#planner").value };
    const known = ex || state.examples.find((x) => x.doc_id === state.doc.id && x.question === question) || null;   // a prepared question: its gold answer is shown
    const t0 = performance.now();
    state.timer = setInterval(() => setStatus(`실행 중 · ${fmtMs(performance.now() - t0)} · 검색 → 제안 → 도구 → 검증`, true), 250);
    setStatus("작업을 제출했습니다…", true);
    try {
      if ($("#chatmode").checked) {
        const r = await chatTurn(question, tableId);
        clearInterval(state.timer);
        setStatus(`완료 · 대화 ${r.turn + 1}번째 턴 · ${fmtMs(performance.now() - t0)}`, false);
        if (r.result) renderResult(r.result, { kind: "live", chat: r }); else renderChatOnly(r);
        $("#question").value = "";
        return;
      }
      let job = await fetchJSON("v1/ask?wait=1", { method: "POST", body: JSON.stringify(body) }, 90000);
      while (job.status === "queued" || job.status === "running") {
        await new Promise((r) => setTimeout(r, 400));
        job = await fetchJSON(`v1/jobs/${job.id}`, {}, 8000);
      }
      clearInterval(state.timer);
      if (job.status !== "done") { setStatus(`작업 ${job.id} · ${job.status}`, false); showError(`작업이 ${job.status === "timeout" ? "시간 초과" : "실패"}했습니다: ${job.error || ""}`, () => ask(question, tableId, ex)); return; }
      setStatus(`완료 · ${fmtMs(job.elapsed_ms)} · 작업 ${job.id}`, false);
      state.shown = known ? known.id : null; renderExamples();
      renderResult(job.result, { kind: "live", ex: known });
    } catch (e) {
      clearInterval(state.timer);
      setStatus("오류", false);
      showError(e.status === 429 ? "대기열이 가득 찼습니다. 잠시 후 다시 시도하세요." : e.status === 422 ? "입력이 잘못되었습니다: " + e.message : "요청 실패: " + e.message, () => ask(question, tableId, ex));
    } finally { state.busy = false; $("#askbtn").disabled = state.mode !== "live"; }
  }

  function showRecorded(exId) {
    const ex = state.exById[exId]; const hit = recordedRun(exId);
    state.shown = exId; renderExamples();
    if (ex) $("#question").value = ex.question;
    if (!hit) { $("#result").hidden = true; $("#resultempty").hidden = false; clearEvidence(); setStatus("선택한 플래너로 저장된 결과가 이 질문에는 없습니다. 플래너를 \"자동\"으로 바꿔 보세요.", false); return; }
    const { run, key, set } = hit, src = set.source;
    $("#errorbar").hidden = true; $("#resultempty").hidden = true; $("#status").hidden = true;
    renderResult(run.result, { kind: "recorded", at: state.recorded.generated_at, commit: state.recorded.commit, planner: key, set, run, ex,
      source: src ? { generated: src.generated[ex.set], where: src.where, ms: run.engine_ms } : null });
    $("#liveprop").value = (run.result.planner && run.result.planner.raw_output) || "";      // the proposal the visitor may change and verify here
    if (parseHash().view === "workbench") { try { history.replaceState(null, "", `#workbench/${encodeURIComponent(exId)}/${$("#planner").value}`); } catch (e) { /* sandboxed frames may refuse history changes */ } }
  }

  // ---------- "run it here" (static demo): the repository's verifier, tools and heuristic planner in this browser ----------
  async function initLive() {
    if (state.mode !== "recorded" || !window.TTLive) return;
    const m = await window.TTLive.available(); if (!m) return;        // this build carries no runtime (for example the single-file page)
    $("#livebox").hidden = false;
    $("#livesize").textContent = `약 ${m.download_mb} MB를 내려받습니다`;
    $("#liveload").addEventListener("click", async () => {
      $("#liveload").disabled = true;
      try {
        const t0 = performance.now();
        await window.TTLive.load((t) => { $("#livestep").textContent = t; });
        $("#liveintro").hidden = true; $("#liveform").hidden = false;
        $("#question").disabled = false; $("#question").placeholder = "질문 (영어 화학 문서에서는 직접 써도 됩니다)";
        setStatus(`실행 환경을 불러왔습니다 · ${fmtMs(performance.now() - t0)} · Python ${m.pyodide} (WebAssembly)`, false);
      } catch (e) { $("#liveload").disabled = false; $("#livestep").textContent = ""; showError("실행 환경을 불러오지 못했습니다: " + e.message); }
    });
    $("#liveverify").addEventListener("click", () => runHere($("#liveprop").value.trim() || "op: abstain ; cells: - ; answer: -"));
    $("#liveheur").addEventListener("click", () => runHere(null));
  }
  function runHere(proposal) {
    const question = $("#question").value.trim();
    if (!state.doc || !question || !window.TTLive.ready()) return;
    const ex = state.examples.find((x) => x.doc_id === state.doc.id && x.question === question) || null;      // a stored question: its gold is known
    const tableId = (ex && ex.table_id) || state.tableId;
    // the passage a stored question was recorded with (the one its run names), else the document's first
    const hit = ex ? recordedRun(ex.id) : null;
    const first = hit && hit.run.result.trace.find((s) => s.step === "retrieve");
    const passageId = first && first.output ? first.output.context_passage : null;
    $("#errorbar").hidden = true;
    let res;
    try { res = window.TTLive.run(state.doc, tableId, question, proposal, passageId, $("#liveentity").checked, ex ? ex.gold : null); }
    catch (e) { showError("실행 중 오류: " + String(e.message || e).split("\n").slice(-2).join(" ")); return; }
    if (res.error === "missing_tokens") {
      showError("한국어는 기록해 둔 질문과 표의 낱말로만 실행할 수 있습니다(형태소 분석기를 이 페이지에 실을 수 없습니다). 질문은 그대로 두고 제안만 바꿔 보거나, 영어 화학 문서에서 질문을 직접 써 보세요.");
      return;
    }
    window.__ttLast = res;                                   // read by the screen checks, which compare it with the same call on a server
    $("#resultempty").hidden = true;
    setStatus(`이 브라우저에서 실행 · ${fmtMs(res.browser_ms)} · ${res.status === "answered" ? "완료" : "보류"}`, false);
    renderResult(res, { kind: "browser", ex, run: { mark: res.mark, values: res.values }, settings: res.settings });
  }

  // ---------- result rendering ----------
  // What the model itself proposed: the first proposal in the trace (a later one would be the fallback planner's).
  function firstProposal(res) {
    const s = (res.trace || []).find((x) => x.step === "propose" && x.output && x.output.parsed);
    return s ? s.output.parsed : null;
  }
  const cellIds = (cells) => (cells || []).map((c) => `r${c.row}c${c.col}`);

  function renderResult(res, meta) {
    const box = $("#result"); box.hidden = false;
    const ex = meta.ex || null, run = meta.run || null;
    const modeBadge = meta.kind === "live" ? '<span class="badge badge-live">실시간 실행</span>'
      : meta.kind === "browser" ? '<span class="badge badge-live">실시간 실행 · 이 브라우저</span>'
      : `<span class="badge badge-rec" title="commit ${esc(meta.commit)}">저장된 실행 결과 · ${esc(meta.at)}</span>`;
    const plannerBadge = res.planner ? `<span class="badge badge-mode">${res.planner.mode === "neural" ? "모델 " + esc(res.planner.model_id || "") : res.planner.mode === "visitor" ? "방문자가 넣은 제안" : "휴리스틱"}${res.trace && res.trace.some((s) => s.input && s.input.fallback) ? " → 휴리스틱 보완" : ""}</span>` : "";
    const checksAll = (res.verdict && res.verdict.checks) || [];
    const failed = checksAll.filter((c) => !c.passed);
    let head, bodyHtml;
    if (res.status === "answered") {
      // An answer whose evidence the verifier had to repair is not the same as one that passed as proposed.
      const fixed = checksAll.some((c) => c.name === "evidence_repaired" || c.name === "column_repaired");
      head = fixed ? '<span class="badge badge-fix" title="모델이 인용한 셀에 답이 없어 검증기가 근거를 고쳤습니다">완료 · 근거를 고쳐 답함</span>' : '<span class="badge badge-ok">완료 · 검증 통과</span>';
      bodyHtml = `<div class="answer">${esc(res.answer)}</div>`;
    } else if (res.status === "abstained") {
      head = '<span class="badge badge-hold">답변 보류</span>';
      const reason = res.verdict && res.verdict.reason;
      const prop = firstProposal(res);
      // which check stopped the answer: the first failed one; none failed when the model itself proposed to withhold
      const why = failed.length ? `<div class="holdwhy"><b>걸린 검사</b> ${esc(CHECKS[failed[0].name] || failed[0].name)}<br><span class="d">${esc(failed[0].detail)}</span></div>`
        : prop && prop.op === "abstain" ? '<div class="holdwhy"><b>모델이 스스로 보류를 제안했습니다.</b></div>' : "";
      bodyHtml = `<div class="answer hold">답변을 보류했습니다</div><div class="reason">${esc(REASONS[reason] || reason || "")}</div>${why}`;
    } else {
      head = '<span class="badge badge-err">오류</span>';
      bodyHtml = `<div class="answer hold">${esc(res.error || "실행 오류")}</div>`;
    }
    const gold = ex ? `<p class="goldline"><b>정답</b> <span class="goldval">${esc(goldText(ex))}</span>${run ? " " + markHtml(run.mark, true) : ""}${ex.review && ex.review.verdict !== "ok" ? `<br><span class="flag">검수: 고쳐야 함</span> <span class="muted">${esc(ex.review.comment)}</span>` : ""}</p>` : "";
    const evidence = renderEvidence(res, run, ex);
    const calc = res.calculation ? renderCalc(res.calculation) : "";
    const ordered = [...failed, ...checksAll.filter((c) => c.passed)];        // what failed comes first
    const checks = ordered.length ? `<ul class="checks">${ordered.map((c) => `<li><span class="${c.passed ? "ok" : "ng"}">${c.passed ? "✓" : "✗"}</span><span><b>${esc(CHECKS[c.name] || c.name)}</b><br><span class="d">${esc(c.detail)}</span></span></li>`).join("")}</ul>` : '<p class="muted">검사 없음</p>';
    const trace = (res.trace || []).map((s) => `<li><details><summary><b>${esc(s.step)}</b>${s.tool ? ` <span class="muted">${esc(s.tool)}</span>` : ""}${s.status !== "ok" ? ` <span class="badge badge-err">${esc(s.status)}</span>` : ""}<span class="ms">${fmtMs(s.ms || 0)}</span></summary><pre>${esc(JSON.stringify({ input: s.input, output: s.output }, null, 1))}</pre></details></li>`).join("");
    box.innerHTML = `
      <div class="card"><div class="card-head"><span>답변 ${modeBadge} ${plannerBadge}</span>${head}</div><div class="card-body">${bodyHtml}${gold}
        ${meta.kind === "live" ? `<p class="muted qline">질문: ${esc(res.question)} · 표 ${esc(res.table_id || "-")} · ${fmtMs(res.elapsed_ms || 0)}</p>` : ""}
        ${meta.chat && (meta.chat.memory.notes.length || meta.chat.question !== meta.chat.message) ? `<p class="memline"><b>기억에서 채운 것</b> ${esc(meta.chat.memory.notes.join(" "))}<br>파이프라인에 보낸 질문: ${esc(meta.chat.question)}</p>` : ""}
        ${meta.source ? `<p class="muted provenance">모델 출력은 ${esc(meta.source.generated)}에 ${esc(meta.source.where)}에서 받아 저장한 것입니다${meta.source.ms ? `(그때의 응답 시간 ${fmtMs(meta.source.ms)})` : ""}. 검증·근거·실행 추적은 그 출력을 같은 파이프라인에 다시 넣은 결과입니다.</p>`
          : meta.kind === "recorded" ? `<p class="muted provenance">모델이 아닌 휴리스틱 기준선입니다. ${esc(meta.at)}에 이 저장소의 파이프라인으로 실행해 기록했습니다.</p>`
          : meta.kind === "browser" ? `<p class="muted provenance">지금 이 브라우저에서 저장소의 검증기와 도구를 실행한 결과입니다. 모델은 실행하지 않았습니다. ${res.planner.mode === "visitor" ? "제안은 위 칸에 적힌 것입니다." : "제안은 휴리스틱 플래너가 냈습니다."} 설정: 주어 검사 ${meta.settings && meta.settings.entity_check ? "켬" : "끔"}, 근거 복구 켬, 다시 시도 없음, 표 전체.</p>` : ""}
        ${run && run.rows_shown ? `<p class="muted provenance unseennote">이 표는 ${run.rows_shown[1]}행인데, 평가 때 입력 길이 한도 때문에 플래너에는 ${run.rows_shown[0]}행만 보여 줬습니다(${run.rows_list ? "질문과 겹치는 행을 골라서" : "앞에서부터"}). 표에서 흐린 행은 플래너가 보지 못한 행입니다.</p>` : ""}</div></div>
      ${renderCompare(ex, meta)}
      <div class="card"><div class="card-head"><span>근거</span><span>${res.evidence_cells.length}개 셀 · ${res.evidence_spans.length}개 문장</span></div><div class="card-body">${evidence}</div></div>
      ${calc ? `<div class="card"><div class="card-head"><span>계산</span><span>제한 계산기(사칙연산, 단위 검사)</span></div><div class="card-body calc">${calc}</div></div>` : ""}
      <div class="card"><div class="card-head"><span>모델의 제안과 검증 결과</span><span>${checksAll.length ? checksAll.filter((c) => c.passed).length + "/" + checksAll.length + " 통과" : ""}</span></div><div class="card-body">${renderProposal(res)}${checks}</div></div>
      <div class="card"><div class="card-head"><span>실행 추적</span><span>LangGraph 노드 · 도구 호출</span></div><div class="card-body"><ul class="trace">${trace}</ul>
        ${res.planner && res.planner.raw_output ? `<details class="rawbox"><summary class="muted">플래너 원문 출력</summary><div class="raw">${esc(res.planner.raw_output)}</div></details>` : ""}</div></div>`;
    $$(".evbtn", box).forEach((b) => b.addEventListener("click", () => focusEvidence(b.dataset.target, b.dataset.kind)));
    $$(".cmp button[data-planner]", box).forEach((b) => b.addEventListener("click", () => { $("#planner").value = b.dataset.planner; renderExamples(); showRecorded(ex.id); }));
    highlightEvidence(res, ex);
    markUnseenRows(run, res);
  }

  // Rows of a long table the planner was not shown (the evaluation cut the table to its input budget).
  function markUnseenRows(run, res) {
    if (!run || !run.rows_shown || !res.table_id) return;
    const seen = run.rows_list ? new Set(run.rows_list) : null;
    $$(`#t-${CSS.escape(res.table_id)} tbody tr`).forEach((tr, i) => tr.classList.toggle("is-unseen", seen ? !seen.has(i) : i >= run.rows_shown[0]));
  }

  // The same question under every stored planner: what each answered and whether it was right.
  function renderCompare(ex, meta) {
    if (!ex || meta.kind !== "recorded" || !state.recorded) return "";
    const rows = plannerKeys().map((k) => { const run = state.runs[k][ex.id]; if (!run) return "";
      const r = run.result;
      const ans = r.status === "answered" ? esc(cut(r.answer, 28)) : `<span class="muted">보류 · ${esc(REASONS[r.verdict && r.verdict.reason] || "")}</span>`;
      return `<tr class="${k === meta.planner ? "is-current" : ""}"><td><button type="button" class="linkbtn" data-planner="${esc(k)}" title="${esc(state.recorded.planners[k].model_id || "휴리스틱 기준선")}">${esc(plannerShort(k))}</button></td><td class="ans">${ans}</td><td class="mk">${markHtml(run.mark)}</td></tr>`; }).join("");
    return `<div class="card"><div class="card-head"><span>같은 질문, 다른 플래너</span><span>정답 ${esc(cut(goldText(ex), 24))}</span></div><div class="card-body"><table class="cmp"><tbody>${rows}</tbody></table>
      <p class="muted cmpnote">이름을 누르면 그 플래너의 근거와 검증을 봅니다. 문항 전체는 <a href="#matrix">문항별 결과</a>에 있습니다.</p></div></div>`;
  }

  // What the model proposed next to what the verifier let through. A difference is the verifier at work.
  function renderProposal(res) {
    const p = firstProposal(res); if (!p) return "";
    const pc = p.cells.map((c) => `r${c.row}c${c.col}`), vc = cellIds(res.evidence_cells);
    const same = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
    const pa = p.op === "abstain" ? "(보류 제안)" : (p.answer ?? ""), va = res.status === "answered" ? res.answer : "(보류)";
    const dc = !same(pc, vc) && res.status === "answered", da = String(pa) !== String(va) && res.status === "answered" && p.op !== "abstain";
    return `<table class="pv"><thead><tr><th></th><th>모델의 제안</th><th>검증 뒤</th></tr></thead><tbody>
      <tr><th>연산</th><td>${esc(OPS[p.op] || p.op)}</td><td>${res.status === "answered" ? "통과" : "보류"}</td></tr>
      <tr class="${dc ? "is-diff" : ""}"><th>셀</th><td>${esc(pc.join(", ") || "-")}</td><td>${esc(vc.join(", ") || "-")}</td></tr>
      <tr class="${da ? "is-diff" : ""}"><th>답</th><td>${esc(pa)}</td><td>${esc(va)}</td></tr></tbody></table>
      ${dc || da ? '<p class="muted pvnote">색이 든 줄은 검증기가 모델의 제안을 바꾼 곳입니다. 계산은 모델의 숫자가 아니라 도구가 다시 계산한 값을 씁니다.</p>' : ""}`;
  }

  function renderEvidence(res, run, ex) {
    const items = [];
    (res.evidence_cells || []).forEach((c, i) => {
      const td = findCell(c); const h = td ? td.dataset.header : ""; const u = td ? td.dataset.unit : ""; const v = td ? td.dataset.text : "";
      // how the number parser read the cell (stored results only): value, unit, and whether the unit came from the cell or the column header
      const val = run && run.values && run.values[i] && run.values[i].value !== null ? run.values[i] : null;
      const read = val ? `<br><span class="val">숫자로 읽은 값 <b>${esc(fmtNum(val.value))}</b>${val.unit ? ` · 단위 ${esc(val.unit)} <span class="muted">(${val.unit_from === "cell" ? "셀에서" : "열 머리에서"})</span>` : " · 단위 없음"}</span>` : "";
      items.push(`<li><button type="button" class="evbtn" data-kind="cell" data-target="${esc(c.table_id)}|r${c.row}c${c.col}" aria-label="근거 ${i + 1} 셀로 이동">${i + 1} · r${c.row}c${c.col}</button><span class="evtext"><b>${esc(v)}</b>${u ? ` <span class="muted">${esc(u)}</span>` : ""}<br><span class="h">${esc(h)} · 표 ${esc(c.table_id)}</span>${read}</span></li>`);
    });
    (res.evidence_spans || []).forEach((s) => {
      items.push(`<li><button type="button" class="evbtn" data-kind="span" data-target="${esc(s.passage_id)}" aria-label="근거 문장으로 이동">문장</button><span class="evtext">“${esc(s.text)}”<br><span class="h">문단 ${esc(s.passage_id)} · 위치 ${s.start}–${s.end}</span></span></li>`);
    });
    const list = items.length ? `<ul class="evlist">${items.join("")}</ul>` : '<p class="muted">근거가 제시되지 않았습니다(보류).</p>';
    return list + renderCited(res) + renderGoldCells(res, ex) + renderLegend(res, ex);
  }

  // Cells the model itself cited that did not become evidence: the verifier repaired the evidence, replaced the
  // proposal with the fallback planner's, or withheld the answer. Read from the first proposal in the trace.
  function citedOnly(res) {
    const first = firstProposal(res);
    const cells = (first && first.cells) || [];
    const ev = new Set((res.evidence_cells || []).map((c) => `${c.table_id}|${c.row}|${c.col}`));
    return cells.filter((c) => !ev.has(`${c.table_id}|${c.row}|${c.col}`));
  }
  function renderCited(res) {
    const cited = citedOnly(res); if (!cited.length) return "";
    const repaired = res.verdict && (res.verdict.checks || []).some((c) => c.name === "evidence_repaired" || c.name === "column_repaired");
    const why = repaired ? "이 셀에는 답이 없어 검증기가 근거를 위의 셀로 고쳤습니다."
      : res.status === "answered" ? "이 제안은 검증을 통과하지 못했고, 보완 제안의 셀이 근거가 됐습니다."
      : "검증을 통과하지 못해 근거로 쓰지 않았습니다.";
    const btns = cited.map((c) => {
      const td = findCell(c); const v = td ? td.dataset.text : "";
      return `<button type="button" class="evbtn evbtn-cited" data-kind="cell" data-target="${esc(c.table_id)}|r${c.row}c${c.col}" aria-label="모델이 인용한 셀로 이동">r${c.row}c${c.col}</button>${v ? ` <span class="citedval">${esc(v)}</span>` : ""}`;
    }).join(" ");
    return `<div class="citednote"><b>모델이 인용한 셀</b> ${btns}<br><span class="h">${why}</span></div>`;
  }
  // The gold answer's cells, shown only where they are not the evidence cells (a wrong or withheld answer, or a right answer on other cells).
  function goldOnly(res, ex) {
    if (!ex || !ex.table_id) return [];
    const ev = new Set(cellIds(res.evidence_cells));
    return (ex.gold.cells || []).filter((id) => !ev.has(id));
  }
  function renderGoldCells(res, ex) {
    const gold = goldOnly(res, ex); if (!gold.length) return "";
    return `<div class="citednote"><b>정답의 근거 셀</b> ${gold.map((id) => `<button type="button" class="evbtn evbtn-gold" data-kind="cell" data-target="${esc(ex.table_id)}|${esc(id)}" aria-label="정답의 근거 셀로 이동">${esc(id)}</button>`).join(" ")}<br><span class="h">평가 문항에 적힌 정답 셀입니다. 위의 근거 셀과 다릅니다.</span></div>`;
  }
  function renderLegend(res, ex) {
    const parts = [];
    if ((res.evidence_cells || []).length) parts.push('<span class="lg lg-ev">1</span> 검증기가 확인한 근거 셀');
    if (citedOnly(res).length) parts.push('<span class="lg lg-cited">모델</span> 모델이 인용했지만 근거가 되지 못한 셀');
    if (goldOnly(res, ex).length) parts.push('<span class="lg lg-gold">정답</span> 정답의 근거 셀');
    return parts.length > 1 ? `<p class="legend"><b>표 위의 표시</b> ${parts.join(" · ")}</p>` : "";
  }

  function renderCalc(c) {
    return `<div class="expr">${esc(c.op)}: ${esc(c.expression)} = <b>${esc(c.formatted)}</b></div>
      <table><thead><tr><th>셀</th><th>원문</th><th>값</th><th>단위</th></tr></thead><tbody>${c.inputs.map((i) => `<tr><td>r${i.cell.row}c${i.cell.col}</td><td>${esc(i.raw)}</td><td>${i.value}</td><td>${esc(i.unit || "-")}</td></tr>`).join("")}</tbody></table>`;
  }

  function findCell(c) { return document.querySelector(`#t-${CSS.escape(c.table_id)} td[data-rc="r${c.row}c${c.col}"]`); }
  function clearEvidence() {
    $$("tr.is-unseen").forEach((tr) => tr.classList.toggle("is-unseen", false));
    $$("td.is-evidence").forEach((td) => { td.classList.remove("is-evidence", "is-focus"); const n = $(".evn", td); if (n) n.remove(); });
    $$("td.is-cited").forEach((td) => { td.classList.remove("is-cited", "is-focus"); const n = $(".citedn", td); if (n) n.remove(); });
    $$("td.is-gold").forEach((td) => { td.classList.remove("is-gold", "is-focus"); const n = $(".goldn", td); if (n) n.remove(); });
    $$(".passage.is-evidence").forEach((p) => { p.classList.remove("is-evidence"); const t = $(".ptext", p); if (t) t.textContent = t.textContent; });
  }
  function highlightEvidence(res, ex) {
    clearEvidence();
    (res.evidence_cells || []).forEach((c, i) => { const td = findCell(c); if (td) { td.classList.add("is-evidence"); td.insertAdjacentHTML("beforeend", `<span class="evn">${i + 1}</span>`); } });
    citedOnly(res).forEach((c) => { const td = findCell(c); if (td) { td.classList.add("is-cited"); td.insertAdjacentHTML("beforeend", '<span class="citedn" title="모델이 인용했지만 근거가 되지 못한 셀">모델</span>'); } });
    goldOnly(res, ex).forEach((id) => { const td = document.querySelector(`#t-${CSS.escape(ex.table_id)} td[data-rc="${id}"]`); if (td && !td.classList.contains("is-cited")) { td.classList.add("is-gold"); td.insertAdjacentHTML("beforeend", '<span class="goldn" title="정답의 근거 셀">정답</span>'); } });
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

  // ---------- per-question results: every question of a set against every stored planner ----------
  async function renderMatrix() {
    const box = $("#matrix");
    try { await loadRecorded(); } catch (e) { box.innerHTML = '<p class="muted">저장된 실행 결과(data/recorded/index.json)가 없어 문항별 결과를 보여 줄 수 없습니다.</p>'; return; }
    const r = state.recorded, sets = state.sets.filter((s) => s.corpus === state.corpus);
    const legend = Object.keys(MARKS).map((m) => `${markHtml(m)} ${esc(markTitle(m))}`).join(" · ");
    const parts = sets.map((s) => {
      const exs = state.examples.filter((x) => x.set === s.key);
      const keys = plannerKeys().filter((k) => r.planners[k].totals[s.key]);
      const cats = Object.keys(CATS).filter((c) => exs.some((x) => x.category === c));
      const byCat = `<table class="res mx"><thead><tr><th>플래너</th>${cats.map((c) => `<th>${esc(CATS[c])} <span class="muted">${exs.filter((x) => x.category === c).length}</span></th>`).join("")}<th>합계</th></tr></thead><tbody>${keys.map((k) => { const t = r.planners[k].totals[s.key];
        return `<tr><th title="${esc(r.planners[k].model_id || "휴리스틱 기준선")}">${esc(plannerShort(k))}</th>${cats.map((c) => { const xs = exs.filter((x) => x.category === c); return `<td class="num">${xs.filter((x) => ["correct", "hold_ok"].includes(state.runs[k][x.id].mark)).length}/${xs.length}</td>`; }).join("")}<td class="num"><b>${t.right}/${t.n}</b></td></tr>`; }).join("")}</tbody></table>`;
      const rows = exs.map((x, i) => `<tr><td class="num">${i + 1}</td><td>${esc(CATS[x.category] || x.category)}</td><td class="q">${esc(x.question)}${x.review && x.review.verdict !== "ok" ? ' <span class="flag" title="' + esc(x.review.comment) + '">검수: 고쳐야 함</span>' : ""}</td><td class="g">${esc(cut(goldText(x), 26))}</td>${keys.map((k) => { const run = state.runs[k][x.id];
        return `<td class="mk"><a href="#workbench/${encodeURIComponent(x.id)}/${esc(k)}" title="${esc(plannerShort(k))}: ${esc(run.result.status === "answered" ? run.result.answer : "보류")}">${markHtml(run.mark)}</a></td>`; }).join("")}</tr>`).join("");
      return `<section><h3>${esc(s.title)} <span class="pill">${s.author === "owner" ? "소유자 작성" : "AI 도구 작성"}</span></h3><p>${esc(s.note)}</p>
        <h4>유형별로 맞은 수</h4><div class="tablescroll">${byCat}</div>
        <h4>문항마다</h4><div class="tablescroll"><table class="res mx"><thead><tr><th>#</th><th>유형</th><th>질문</th><th>정답</th>${keys.map((k) => `<th title="${esc(r.planners[k].model_id || "휴리스틱 기준선")}">${esc(plannerShort(k))}<br><span class="muted">${r.planners[k].totals[s.key].right}/${r.planners[k].totals[s.key].n}</span></th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div></section>`; }).join("");
    const notes = plannerKeys().map((k) => `<li><b>${esc(plannerShort(k))}</b> ${esc(r.planners[k].model_id || "")}. ${esc(r.planners[k].note)}${r.planners[k].source ? ` 출력을 받은 곳: ${esc(r.planners[k].source.where)}.` : ""}</li>`).join("");
    box.innerHTML = `<h2>문항별 결과 <span class="muted sub">기록 ${esc(r.generated_at)} · commit ${esc(r.commit)}</span></h2>
      <p>평가 문항을 하나도 빼지 않고 플래너마다의 결과를 정답과 견줬습니다. 표시를 누르면 그 문항의 근거와 검증을 워크벤치에서 봅니다. 위쪽의 코퍼스 단추로 한국어 표와 영어 화학 문서를 바꿉니다.</p>
      <p class="legend"><b>표시</b> ${legend}. 앞의 ✓와 ✗는 시스템이 옳게 행동했는지이고, 뒤의 말은 무엇을 했는지입니다.</p>
      <p class="muted">${esc(r.settings.note)}</p>${parts}
      <section><h3>플래너</h3><ul class="plist">${notes}</ul></section>`;
  }

  // ---------- research + about ----------
  let researchLoaded = false;
  async function loadResearch() {
    if (researchLoaded) return;
    const box = $("#research");
    try {
      const data = await fetchJSON("data/research.json", {}, 10000);
      box.innerHTML = renderResearch(data); researchLoaded = true;
      if (window.TTCharts) window.TTCharts.bind(box);
      // "세부 기록 보기": open the group that holds the section and scroll to it
      $$("a[data-more]", box).forEach((a) => a.addEventListener("click", (e) => {
        const sec = $$("section[data-title]", box).find((s) => s.dataset.title.startsWith(a.dataset.more)); if (!sec) return;
        e.preventDefault();
        sec.closest("details").open = true; sec.scrollIntoView({ block: "start", behavior: "smooth" }); sec.classList.add("is-target");
        setTimeout(() => sec.classList.toggle("is-target", false), 2500);
      }));
    } catch (e) { box.innerHTML = `<p class="muted">연구 결과 파일(data/research.json)을 아직 만들지 않았습니다: ${esc(e.message)}</p>`; }
  }
  function renderResearch(d) {
    const pill = (s) => s === "done" ? '<span class="pill done">실행·측정 완료</span>' : s === "prep" ? '<span class="pill prep">구현 후 미실행</span>' : s === "fail" ? '<span class="pill fail">실행했으나 실패/미달</span>' : s === "none" ? '<span class="pill">미구현</span>' : "";
    const cond = (c) => c && Object.keys(c).length ? `<div class="condbox"><dl>${Object.entries(c).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</dd>`).join("")}</dl></div>` : "";
    const table = (cols, rows) => `<div class="tablescroll"><table class="res"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((v, i) => `<td class="${typeof v === "number" || /^[\d.,%\s−-]+$/.test(String(v)) ? "num" : ""}">${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    const section = (s) => `<section data-title="${esc(s.title)}"><h3>${esc(s.title)} ${pill(s.status)}</h3>${s.description ? `<p>${esc(s.description)}</p>` : ""}${cond(s.conditions)}${s.columns ? table(s.columns, s.rows || []) : ""}${(s.notes || []).length ? `<ul>${s.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}${s.artifact ? `<p class="muted">산출물: <code>${esc(s.artifact)}</code></p>` : ""}</section>`;
    const sections = d.sections || [];
    // The top layer: a few conclusions, each with one small chart, then what went against expectations.
    const top = (d.highlights || []).length && window.TTCharts ? `<div class="hl-grid">${d.highlights.map((h) => window.TTCharts.card(h)).join("")}</div>` : "";
    const odd = (d.unexpected || []).length ? `<section class="hl-odd"><h3>기대와 달랐던 결과</h3><ul>${d.unexpected.map((u) => `<li>${esc(u.text)} <a href="#research" data-more="${esc(u.more)}">세부 기록</a></li>`).join("")}</ul></section>` : "";
    // Below it every experiment keeps its conditions, sample sizes and artifact paths, folded by topic.
    const groups = (d.groups || []).length ? d.groups : [{ name: "모든 실험", sections: sections.length }];
    const detail = groups.map((g) => { const own = sections.filter((s) => !s.group || s.group === g.name);
      return `<details class="grp"><summary><b>${esc(g.name)}</b> <span class="muted">실험 ${own.length}건</span><span class="grp-titles muted">${esc(own.map((s) => s.title.split(" — ")[0].split(" (")[0]).join(" · "))}</span></summary>${own.map(section).join("")}</details>`; }).join("");
    return `<h2>연구 결과 <span class="muted sub">생성 ${esc(d.generated_at)} · commit ${esc(d.commit)}</span></h2>
      <p class="muted">아래 여섯 가지가 이 프로젝트에서 잰 것의 요약입니다. 그림의 값은 모두 저장소의 결과 파일에서 읽은 것이고, 그림마다 "표로 보기"에 같은 값이 있습니다.</p>
      ${top}${odd}
      <h2 id="research-detail">실험별 세부 기록 <span class="muted sub">실험 ${sections.length}건 · 조건, 표본 수, 산출물 경로</span></h2>
      <p class="muted">${esc(d.summary || "")}</p>
      ${detail}`;
  }
  async function loadGraph() {
    const pre = $("#graphsrc"); if (pre.textContent) return;
    try { const g = state.mode === "live" ? (await fetchJSON("v1/graph", {}, 5000)).mermaid : (await fetchJSON("data/graph.json", {}, 5000)).mermaid; pre.textContent = g; }
    catch (e) { pre.textContent = "graph TD; retrieve --> propose --> verify; verify -->|retry| propose_fallback --> verify; verify -->|done| finalize"; }
  }

  init();
})();
