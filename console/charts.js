/* Small charts for the 연구 결과 view. Plain HTML/SVG, no library.
   Each chart is one of five forms chosen by what the reader has to do with the numbers:
     bars      compare a magnitude across a few named rows (one hue; the one row the conclusion is about is accented)
     stack     how one whole splits, for two wholes on a shared scale (right / not answered / wrong: status colours with labels)
     dumbbell  before and after per row (one hue, two shades)
     meter     k out of n per named row
     line      two series over a shared x (legend, end labels, crosshair)
   Every value is also in a table under the chart ("표로 보기"); hover and keyboard focus show the same values. */
(function () {
  "use strict";
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (x, d = 1) => (100 * x).toFixed(d) + "%";
  const table = (cols, rows) => `<details class="viz-table"><summary>표로 보기</summary><div class="tablescroll"><table class="res"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((v, i) => `<td class="${i ? "num" : ""}">${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`;
  const mark = (cls, style, tip) => `<span class="${cls}" style="${style}" tabindex="0" data-tip="${esc(tip)}"></span>`;

  function bars(h) {
    const hasTicks = h.rows.some((r) => r.ticks && r.ticks.length);
    const span = (r) => (r.ticks && r.ticks.length ? `${pct(Math.min(...r.ticks))}~${pct(Math.max(...r.ticks))}` : "");
    const rows = h.rows.map((r) => {
      const w = 100 * r.value / h.max, far = 100 * Math.max(r.value, ...(r.ticks || [])) / h.max;
      const range = span(r) ? mark("vb-range", `left:${w}%;width:${far - w}%`, `${r.label} · ${h.tick_label}: ${span(r)}`) : "";
      return `<div class="vb-row"><div class="vb-label">${esc(r.label)}</div><div class="vb-plot"><div class="vb-track">
        ${mark("vb-bar" + (r.emphasis ? " is-em" : ""), `width:${w}%`, `${r.label}: ${r.text}`)}${range}<span class="vb-val" style="left:${far}%">${esc(r.text)}${span(r) ? ` <span class="vb-sub">· ${esc(span(r))}</span>` : ""}</span></div></div></div>`;
    }).join("");
    const legend = hasTicks ? `<p class="viz-legend"><span class="lgk lgk-range"></span>${esc(h.tick_label)}의 범위 (막대 끝의 가는 선과 뒤의 숫자)</p>` : "";
    return `<div class="viz vb">${legend}${rows}</div>` + table(["", "값"].concat(hasTicks ? [h.tick_label || "다른 실행"] : []),
      h.rows.map((r) => [r.label, r.text].concat(hasTicks ? [(r.ticks || []).map((t) => pct(t)).join(", ") || "-"] : [])));
  }

  function stack(h) {
    const names = h.bars[0].parts.map((p) => p);
    const legend = `<p class="viz-legend">${names.map((p) => `<span class="lgk lgk-${esc(p.role)}"></span>${esc(p.name)}`).join(" &nbsp; ")}</p>`;
    const rows = h.bars.map((b) => `<div class="vs-row"><div class="vs-label">${esc(b.label)}</div><div class="vs-bar">${b.parts.map((p) =>
      `<span class="vs-seg vs-${esc(p.role)}" style="flex:${p.value}" tabindex="0" data-tip="${esc(b.label + " · " + p.name + ": " + pct(p.value))}">${p.value >= 0.08 ? `<span>${pct(p.value)}</span>` : ""}</span>`).join("")}</div></div>`).join("");
    return `<div class="viz vs">${legend}${rows}</div>` + table([""].concat(names.map((p) => p.name)), h.bars.map((b) => [b.label].concat(b.parts.map((p) => pct(p.value)))));
  }

  function dumbbell(h) {
    const rows = h.rows.map((r) => {
      const a = 100 * r.before / h.max, b = 100 * r.after / h.max, lo = Math.min(a, b), hi = Math.max(a, b);
      return `<div class="vd-row"><div class="vd-label">${esc(r.label)}</div><div class="vd-plot"><div class="vd-track">
        <span class="vd-link" style="left:${lo}%;width:${hi - lo}%"></span>${mark("vd-dot vd-before", `left:${a}%`, `${r.label} · ${h.before_label}: ${pct(r.before)}`)}${mark("vd-dot vd-after", `left:${b}%`, `${r.label} · ${h.after_label}: ${pct(r.after)}`)}
        </div></div><div class="vd-val">${esc(r.text)}</div></div>`;
    }).join("");
    const legend = `<p class="viz-legend"><span class="lgk lgk-dot vd-before"></span>${esc(h.before_label)} &nbsp; <span class="lgk lgk-dot vd-after"></span>${esc(h.after_label)}</p>`;
    return `<div class="viz vd">${legend}${rows}</div>` + table(["", h.before_label, h.after_label], h.rows.map((r) => [r.label, pct(r.before), pct(r.after)]));
  }

  function meter(h) {
    const rows = h.rows.map((r) => `<div class="vm-row"><div class="vm-label">${esc(r.label)}</div><div class="vm-track">${mark("vm-fill", `width:${100 * r.value / r.of}%`, `${r.label}: ${r.text}`)}</div><div class="vm-val">${esc(r.text)}</div></div>`).join("");
    return `<div class="viz vm">${rows}</div>` + table(["", "맞은 수"], h.rows.map((r) => [r.label, r.text]));
  }

  function line(h) {
    const W = 400, H = 236, L = 40, R = 48, T = 10, B = 24, pw = W - L - R, ph = H - T - B;
    const x = (v) => L + pw * v / h.x_max, y = (v) => T + ph * (1 - v / h.y_max);
    const yt = [0, 0.05, 0.1, 0.15, 0.2].filter((v) => v <= h.y_max), xt = [0, 0.25, 0.5, 0.75, 1];
    const grid = yt.map((v) => `<line class="vl-grid" x1="${L}" x2="${L + pw}" y1="${y(v)}" y2="${y(v)}"/><text class="vl-tick" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${pct(v, 0)}</text>`).join("")
      + xt.map((v) => `<text class="vl-tick" x="${x(v)}" y="${T + ph + 16}" text-anchor="middle">${pct(v, 0)}</text>`).join("");
    const lines = h.series.map((s, i) => { const end = s.points[s.points.length - 1];
      return `<polyline class="vl-line vl-s${i + 1}" points="${s.points.map((p) => x(p[0]).toFixed(1) + "," + y(p[1]).toFixed(1)).join(" ")}"/>
        <circle class="vl-dot vl-s${i + 1}" cx="${x(end[0])}" cy="${y(end[1])}" r="4"/><text class="vl-end" x="${x(end[0]) + 8}" y="${y(end[1]) + 4}">${pct(end[1])}</text>`; }).join("");
    const legend = `<p class="viz-legend">${h.series.map((s, i) => `<span class="lgk lgk-line vl-s${i + 1}"></span>${esc(s.name)}`).join(" &nbsp; ")}</p>`;
    const n = Math.max(...h.series.map((s) => s.points.length));
    const rows = Array.from({ length: n }, (_, i) => [i === n - 1 ? "문턱 없음 (" + h.series.map((s) => pct(s.points[i][0])).join(" / ") + ")" : pct(h.series[0].points[i][0], 0)].concat(h.series.map((s) => pct(s.points[i][1]))));
    return `<div class="viz vl" data-line='${esc(JSON.stringify({ L, pw, x_max: h.x_max, W, series: h.series, x_label: h.x_label }))}'>${legend}
      <p class="viz-axes">세로: ${esc(h.y_label)} · 가로: ${esc(h.x_label)}</p>
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(h.y_label + " 대 " + h.x_label)}">${grid}
        <line class="vl-axis" x1="${L}" x2="${L + pw}" y1="${T + ph}" y2="${T + ph}"/><line class="vl-cross" x1="0" x2="0" y1="${T}" y2="${T + ph}" visibility="hidden"/>
        ${lines}
        <rect class="vl-hit" x="${L}" y="${T}" width="${pw}" height="${ph}" fill="transparent"/></svg></div>` + table([h.x_label].concat(h.series.map((s) => s.name)), rows);
  }

  const FORMS = { bars, stack, dumbbell, meter, line };
  function card(h) {
    const body = (FORMS[h.kind] || (() => ""))(h);
    return `<article class="hl" id="hl-${esc(h.id)}"><h3>${esc(h.title)}</h3>${body}<p class="hl-cap">${esc(h.caption)}</p>
      <p class="hl-more"><a href="#research" data-more="${esc(h.more)}">세부 기록 보기</a>${h.link ? ` · <a href="${esc(h.link.href)}">${esc(h.link.text)}</a>` : ""}</p></article>`;
  }

  // One tooltip for every mark: shown on hover and on keyboard focus, text set with textContent.
  function bind(root) {
    let tip = document.getElementById("viztip");
    if (!tip) { tip = document.createElement("div"); tip.id = "viztip"; tip.className = "viz-tip"; tip.hidden = true; document.body.appendChild(tip); }
    const show = (text, px, py) => { tip.textContent = text; tip.hidden = false;
      const w = tip.offsetWidth, vw = document.documentElement.clientWidth;
      tip.style.left = Math.max(4, Math.min(vw - w - 4, px - w / 2)) + window.scrollX + "px"; tip.style.top = py + window.scrollY - tip.offsetHeight - 10 + "px"; };
    const hide = () => { tip.hidden = true; };
    root.querySelectorAll("[data-tip]").forEach((el) => {
      const at = () => { const b = el.getBoundingClientRect(); show(el.dataset.tip, b.left + b.width / 2, b.top); };
      el.addEventListener("pointerenter", at); el.addEventListener("focus", at);
      el.addEventListener("pointerleave", hide); el.addEventListener("blur", hide);
    });
    // line chart: the crosshair snaps to the nearest coverage level and the tooltip lists every series there
    root.querySelectorAll(".vl").forEach((box) => {
      const cfg = JSON.parse(box.dataset.line), svg = box.querySelector("svg"), cross = box.querySelector(".vl-cross"), hit = box.querySelector(".vl-hit");
      const n = cfg.series[0].points.length;
      hit.addEventListener("pointermove", (e) => {
        const b = svg.getBoundingClientRect(), k = cfg.W / b.width, v = ((e.clientX - b.left) * k - cfg.L) / cfg.pw * cfg.x_max;
        let best = 0; for (let i = 1; i < n; i++) if (Math.abs(cfg.series[0].points[i][0] - v) < Math.abs(cfg.series[0].points[best][0] - v)) best = i;
        const px = cfg.L + cfg.pw * cfg.series[0].points[best][0] / cfg.x_max;
        cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.setAttribute("visibility", "visible");
        const head = best === n - 1 ? "문턱 없음" : cfg.x_label + " " + pct(cfg.series[0].points[best][0], 0);
        show(head + " · " + cfg.series.map((s) => pct(s.points[best][1]) + " " + s.name).join(" · "), b.left + px / k, e.clientY - 6);
      });
      hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hide(); });
    });
  }

  window.TTCharts = { card, bind };
})();
