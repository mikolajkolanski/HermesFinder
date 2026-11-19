/* Skrot wyniku analizy: wybor najwazniejszych kart + wykresy SVG.
   Wspolny dla panelu na stronie (ramka iframe) i okna rozszerzenia.
   - legenda = przelaczniki: klik ukrywa/pokazuje serie (i linie trendu),
   - "Wiecej" / "wszystkie wykresy": pelna analiza w nowej karcie (strona glowna). */
"use strict";

var CV = globalThis.CV || (globalThis.CV = {});

(function () {
  const COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#17212B", "#8C969C"];
  const TREND_GREY = "#5E6A71";
  const STRIPES = ["#08519c", "#2171b5", "#6baed6", "#c6dbef", "#fcbba1", "#fb6a4a", "#cb181d", "#67000d"];
  const MAX_SERIES = 7;
  const t = (k, v) => (CV.t ? CV.t(k, v) : k);

  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function num(v, dec) {
    return v.toLocaleString(CV.locale || "en-GB", { minimumFractionDigits: dec, maximumFractionDigits: dec });
  }
  function decFor(range) {
    return range >= 50 ? 0 : range >= 5 ? 1 : 2;
  }
  function signed(v, unit, dec = 2) {
    return `${v >= 0 ? "+" : "−"}${num(Math.abs(v), dec)}${unit ? " " + unit : ""}`;
  }
  function withUnit(text, unit) {
    return unit ? `${text} ${unit}` : text;
  }

  /* ------------------------------------------------ wybor kart do skrotu */
  function weight(card, i) {
    if (card.error) return -1;
    let w = 0;
    const n = (card.series || []).length;
    if (card.compare && n >= 2) w = 3 + Math.min(n, 6) * 0.1;
    else if (card.type === "bars" && String(card.dataset_id || "").startsWith("planet_")) w = 2.6;
    else if (["line", "multi_line", "difference", "period_compare", "period_bands"].includes(card.type)) w = 2;
    else if (card.type === "bars") w = 1.5;
    // heatmapa nie miesci sie w skrocie
    return w ? w - i * 0.35 : 0;
  }

  /** Najwazniejsze karty (max n), w kolejnosci z analizy, bez powtorzen tematu. */
  function pickCards(data, n) {
    const cards = (data.cards || []).map((c, i) => ({ c, i, w: weight(c, i) })).filter((x) => x.w > 0);
    cards.sort((a, b) => b.w - a.w);
    const seen = new Set();
    const out = [];
    for (const x of cards) {
      const key = x.c.topic || x.c.dataset_id || x.c.id;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(x);
      if (out.length >= n) break;
    }
    return out.sort((a, b) => a.i - b.i).map((x) => x.c);
  }

  /** Wszystkie karty, ktore umiemy narysowac (widok pelny). */
  function drawableCards(data) {
    return (data.cards || []).filter((c, i) => weight(c, i) > 0 || (c.type === "bars" && !c.error));
  }

  /* ------------------------------------------------ najwazniejsza liczba */
  function keyFact(card) {
    const unit = card.unit || "";
    if (card.type === "bars") {
      return (card.values || []).slice(0, 6).map((v) => `${v.label} ${withUnit(num(v.value, decFor(Math.abs(v.value))), unit)}`).join(", ");
    }
    if (card.type === "period_compare") {
      const p = card.periods || [];
      if (p.length < 2) return "";
      const first = p[0].series || [], last = p[p.length - 1].series || [];
      return last.map((e) => {
        const f = first.find((x) => x.label === e.label);
        return f ? `${e.label}: ${signed(e.mean - f.mean, unit)} (${p[0].label} → ${p[p.length - 1].label})` : "";
      }).filter(Boolean).join("; ");
    }
    if (card.x_kind === "ls") {
      return (card.series || []).map((s) => {
        const v = s.points.map((p) => p.value);
        const r = Math.max(...v) - Math.min(...v);
        return t("factFromTo", { label: s.label, a: num(Math.min(...v), decFor(r)), b: withUnit(num(Math.max(...v), decFor(r)), unit) });
      }).join("; ");
    }
    const stats = (card.stats || []).filter((s) => s && s.n);
    if (card.type === "difference" && card.series && card.series[0]) {
      const v = card.series[0].points.map((p) => p.value);
      return t("meanDiff", { v: signed(v.reduce((a, b) => a + b, 0) / v.length, unit) });
    }
    if (stats.length >= 2) {
      const sl = stats.map((s) => s.slope_per_decade);
      const lo = Math.min(...sl), hi = Math.max(...sl);
      const spread = seriesSpread(card.series || []);
      const parts = [
        card.compare ? t("factSources", { n: stats.length }) : t("factSeries", { n: stats.length }),
        Math.abs(hi - lo) < 0.005 ? t("trend1", { a: signed(lo, unit) }) : t("trend2", { a: signed(lo, unit), b: signed(hi, unit) }),
      ];
      if (card.compare && spread !== null) parts.push(t("spread", { d: withUnit(num(spread, 2), unit) }));
      return parts.join(". ");
    }
    if (stats.length === 1) {
      const s = stats[0];
      return [t("trend1", { a: signed(s.slope_per_decade, unit) }), t("change", { b: signed(s.total_change, unit) }),
        t("yearsN", { n: s.n })].join(". ");
    }
    return "";
  }

  function seriesSpread(series) {
    if (series.length < 2) return null;
    const maps = series.map((s) => new Map(s.points.map((p) => [p.year, p.value])));
    const common = [...maps[0].keys()].filter((y) => maps.every((m) => m.has(y)));
    if (!common.length) return null;
    const sp = common.map((y) => {
      const v = maps.map((m) => m.get(y));
      return Math.max(...v) - Math.min(...v);
    });
    return sp.reduce((a, b) => a + b, 0) / sp.length;
  }

  /* ------------------------------------------------ widocznosc serii (legenda) */
  // stan na obiekcie karty: wspolny dla malego wykresu i powiekszenia
  function hiddenSet(card) {
    if (!card.__hidden) Object.defineProperty(card, "__hidden", { value: new Set(), enumerable: false });
    return card.__hidden;
  }
  function allSeries(card) {
    return (card.series || []).map((s, i) => ({ s, i, color: COLORS[i % COLORS.length] }))
      .filter((x) => x.s.points && x.s.points.length).slice(0, MAX_SERIES);
  }
  /** Czy karta ma linie trendu do narysowania (niezaleznie od ukrycia). */
  function trendMode(card, big) {
    const tr = card.trends || [];
    const n = allSeries(card).length;
    if (card.x_kind === "ls" || !tr.length) return null;
    if (n === 1 && tr[0] && tr[0].points && tr[0].points.length >= 2) return "single";
    // duzy wykres: trend kazdej serii w jej kolorze (trend i = seria i)
    if (big && n > 1 && tr.length === (card.series || []).length) return "each";
    return null;
  }

  /* ------------------------------------------------ wykresy SVG */
  // maly wykres w skrocie: 320 x 148 jednostek; duzy: wymiary w px
  const SMALL = { w: 320, h: 148, big: false };

  function niceStep(span, n) {
    const raw = (span || 1) / n;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const f = raw / mag;
    return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag;
  }
  function stepTicks(lo, hi, step) {
    const out = [];
    for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + 1e-9; v += step) out.push(Number(v.toFixed(10)));
    return out;
  }
  function decForStep(step) {
    return step >= 1 ? 0 : Math.min(3, Math.ceil(-Math.log10(step) - 1e-9));
  }

  /** Skale wykresu liniowego - wspolne dla rysowania i podpowiedzi.
      Os X z wszystkich serii (stala przy ukrywaniu), os Y z widocznych. */
  function lineModel(card, size) {
    const all = allSeries(card);
    if (!all.length) return null;
    const hidden = hiddenSet(card);
    const items = all.filter((x) => !hidden.has(String(x.i)));
    const { w, h, big } = size;
    const PL = big ? 52 : 40, PR = big ? 14 : 8, PT = big ? 24 : 20, PB = big ? 28 : 20;
    const ls = card.x_kind === "ls";
    const xsAll = all.flatMap((x) => x.s.points.map((p) => p.year));
    const ys = (items.length ? items : all).flatMap((x) => x.s.points.map((p) => p.value));
    const x0 = ls ? 0 : Math.min(...xsAll), x1 = ls ? 360 : Math.max(...xsAll);
    const ymin = Math.min(...ys), ymax = Math.max(...ys);
    const pad = (ymax - ymin) * 0.08 || 0.5;
    const y0 = ymin - pad, y1 = ymax + pad;
    const sx = (x) => PL + ((x - x0) / (x1 - x0 || 1)) * (w - PL - PR);
    const sy = (y) => PT + (1 - (y - y0) / (y1 - y0 || 1)) * (h - PT - PB);
    const ix = (px) => x0 + ((px - PL) / (w - PL - PR)) * (x1 - x0 || 1);
    const xs = [...new Set(items.flatMap((x) => x.s.points.map((p) => p.year)))].sort((a, b) => a - b);
    const series = items.map((x) => x.s);
    return { all, items, series, w, h, big, PL, PR, PT, PB, ls, x0, x1, y0, y1, ymin, ymax, pad, sx, sy, ix, xs };
  }

  function xLabel(m, x) {
    return m.ls ? `Ls ${Math.round(x)}°` : String(Math.round(x));
  }

  function trendPaths(card, m) {
    const mode = trendMode(card, m.big);
    if (!mode || hiddenSet(card).has("trend")) return "";
    const tr = card.trends || [];
    const list = mode === "single"
      ? (m.items.length ? [{ pts: tr[0].points, color: TREND_GREY }] : [])
      : m.items.map((x) => (tr[x.i] && tr[x.i].points && tr[x.i].points.length >= 2 ? { pts: tr[x.i].points, color: x.color } : null)).filter(Boolean);
    return list.map(({ pts, color }) => {
      const a = pts[0], b = pts[pts.length - 1];
      return `<path d="M${m.sx(a.year).toFixed(1)},${m.sy(a.value).toFixed(1)}L${m.sx(b.year).toFixed(1)},${m.sy(b.value).toFixed(1)}" stroke="${color}" stroke-width="${m.big ? 1.5 : 1.2}" stroke-dasharray="6 4" fill="none" opacity="${mode === "each" ? 0.85 : 1}"/>`;
    }).join("");
  }

  function lineSvg(card, size = SMALL) {
    const m = lineModel(card, size);
    if (!m) return "";
    if (!m.items.length) return `<p class="cv-allhidden">${esc(t("allHidden"))}</p>`;
    const { w, h, big, PL, PR, PT, PB, sx, sy } = m;
    let g = "";
    let yt, dec;
    if (big) {
      const step = niceStep(m.y1 - m.y0, Math.max(3, Math.round((h - PT - PB) / 56)));
      yt = stepTicks(m.y0, m.y1, step);
      dec = decForStep(step);
    } else {
      // os: min / max (+ zero, jesli w zakresie i nie nachodzi na etykiety)
      dec = decFor(m.y1 - m.y0);
      yt = [m.ymin, m.ymax];
      const near = (m.y1 - m.y0) * 0.14;
      if (m.y0 < 0 && m.y1 > 0 && Math.abs(yt[0]) > near && Math.abs(yt[1]) > near) yt.push(0);
    }
    for (const tk of yt) {
      const y = sy(tk).toFixed(1);
      g += `<line x1="${PL}" x2="${w - PR}" y1="${y}" y2="${y}" class="${tk === 0 ? "cv-zero" : "cv-grid"}"/>`;
      g += `<text x="${PL - 6}" y="${(sy(tk) + 3.5).toFixed(1)}" class="cv-tick" text-anchor="end">${esc(num(tk, dec))}</text>`;
    }
    if (big) {
      const xt = m.ls ? [0, 90, 180, 270, 360]
        : stepTicks(m.x0, m.x1, Math.max(1, niceStep(m.x1 - m.x0, Math.max(3, Math.round((w - PL - PR) / 90)))));
      for (const tk of xt) {
        g += `<line x1="${sx(tk).toFixed(1)}" x2="${sx(tk).toFixed(1)}" y1="${h - PB}" y2="${h - PB + 4}" class="cv-axis"/>`;
        g += `<text x="${sx(tk).toFixed(1)}" y="${h - PB + 16}" class="cv-tick" text-anchor="middle">${esc(m.ls ? tk + "°" : String(tk))}</text>`;
      }
      g += `<line x1="${PL}" x2="${w - PR}" y1="${h - PB}" y2="${h - PB}" class="cv-axis"/>`;
    } else {
      const xl = m.ls ? ["0°", "360°"] : [String(Math.round(m.x0)), String(Math.round(m.x1))];
      g += `<text x="${PL}" y="${h - 5}" class="cv-tick">${xl[0]}</text>`;
      g += `<text x="${w - PR}" y="${h - 5}" class="cv-tick" text-anchor="end">${xl[1]}</text>`;
    }
    m.items.forEach(({ s, color }) => {
      const d = s.points.map((p, k) => `${k ? "L" : "M"}${sx(p.year).toFixed(1)},${sy(p.value).toFixed(1)}`).join("");
      g += `<path d="${d}" fill="none" stroke="${color}" stroke-width="${big ? 2 : 1.6}" stroke-linejoin="round"/>`;
    });
    g += trendPaths(card, m);
    const unit = card.unit ? `<text x="${PL}" y="${big ? 13 : 10}" class="cv-tick">${esc(card.unit)}</text>` : "";
    // warstwa podpowiedzi: pionowa linia + kropki (ustawiane w attachHover)
    const hov = `<g class="cv-hov" visibility="hidden"><line class="cv-cross" y1="${PT}" y2="${h - PB}"/></g>`;
    return `<svg viewBox="0 0 ${w} ${h}" class="cv-svg" role="img" tabindex="0" aria-label="${esc(card.title)}. ${esc(t("arrowAria"))}">${unit}${g}${hov}</svg>`;
  }

  /** Legenda = przelaczniki widocznosci; trend jako linia przerywana. */
  function legendHtml(card, size = SMALL) {
    const all = allSeries(card);
    const mode = trendMode(card, size.big);
    if (!(all.length > 1 || card.compare || mode)) return "";
    const hidden = hiddenSet(card);
    const item = (key, label, swatch) => {
      const on = !hidden.has(key);
      return `<li><button type="button" class="cv-lg${on ? "" : " cv-off"}" data-key="${esc(key)}" aria-pressed="${on}" title="${esc(t("legendToggle"))}">${swatch}<span class="cv-lg-t">${esc(label)}</span></button></li>`;
    };
    let html = all.map((x) => item(String(x.i), x.s.label, `<span class="cv-sw" style="background:${x.color}"></span>`)).join("");
    if (mode) {
      const c = mode === "single" ? TREND_GREY : "#3A4650";
      html += item("trend", t("trend"), `<span class="cv-sw cv-sw-dash" style="--c:${c}"></span>`);
    }
    return `<ul class="cv-legend">${html}</ul>`;
  }

  function barValues(card) {
    let values = card.values || [];
    if (card.type === "period_compare") {
      values = (card.periods || []).flatMap((p) => (p.series || []).map((e) => ({
        label: (p.series.length > 1 ? `${p.label}, ${e.label}` : p.label), value: e.mean })));
    }
    return values;
  }

  function barsSvg(card, size = SMALL) {
    const values = barValues(card).slice(0, size.big ? 40 : 10);
    if (!values.length) return "";
    const W = size.w;
    const rowH = size.big ? 24 : 18, h = values.length * rowH + 6;
    const lw = size.big ? Math.min(220, W * 0.32) : 104, maxCh = size.big ? 34 : 18;
    const vmax = Math.max(0, ...values.map((v) => v.value)), vmin = Math.min(0, ...values.map((v) => v.value));
    const span = vmax - vmin || 1;
    const sx = (v) => lw + ((v - vmin) / span) * (W - lw - (size.big ? 70 : 54));
    const dec = decFor(span);
    const unit = card.unit || "";
    // czerwien/blekit tylko dla temperatury (powyzej/ponizej zera)
    const warmCold = /°C/.test(unit);
    let g = `<line x1="${sx(0).toFixed(1)}" x2="${sx(0).toFixed(1)}" y1="0" y2="${h}" class="cv-axis"/>`;
    values.forEach((v, i) => {
      const y = i * rowH + 3;
      const a = sx(Math.min(0, v.value)), b = sx(Math.max(0, v.value));
      const lab = v.label.length > maxCh ? v.label.slice(0, maxCh - 1) + "…" : v.label;
      g += `<g class="cv-barrow" data-tip="${esc(`${v.label}: ${withUnit(num(v.value, dec), unit)}`)}">`;
      g += `<rect x="0" y="${y}" width="${W}" height="${rowH}" fill="transparent"/>`;
      g += `<text x="${lw - 6}" y="${y + rowH * 0.66}" class="cv-tick" text-anchor="end">${esc(lab)}</text>`;
      g += `<rect class="cv-bar-mark" x="${a.toFixed(1)}" y="${y + 2}" width="${Math.max(1, b - a).toFixed(1)}" height="${rowH - 6}" rx="2" fill="${warmCold ? (v.value >= 0 ? "#B2182B" : "#2166AC") : "#1D4E89"}"/>`;
      g += `<text x="${(b + 4).toFixed(1)}" y="${y + rowH * 0.66}" class="cv-tick cv-val">${esc(num(v.value, dec))}</text></g>`;
    });
    return `<svg viewBox="0 0 ${W} ${h}" class="cv-svg" role="img" aria-label="${esc(card.title)}">${g}</svg>`;
  }

  function isBars(card) {
    return card.type === "bars" || card.type === "period_compare";
  }
  function chartFor(card, size = SMALL) {
    return isBars(card) ? barsSvg(card, size) : lineSvg(card, size) + legendHtml(card, size);
  }

  /** Rysuje wykres w kontenerze i podpina podpowiedzi + przelaczniki legendy.
      onToggle() - wolane po zmianie widocznosci (np. odswiezenie drugiego widoku). */
  function drawPlot(plot, card, size, onToggle) {
    plot.innerHTML = chartFor(card, size);
    attachHover(plot, card, size);
    plot.querySelectorAll(".cv-lg").forEach((btn) => {
      btn.addEventListener("click", () => {
        const hidden = hiddenSet(card);
        const key = btn.dataset.key;
        if (hidden.has(key)) hidden.delete(key); else hidden.add(key);
        drawPlot(plot, card, size, onToggle);
        const again = plot.querySelector(`.cv-lg[data-key="${CSS.escape(key)}"]`);
        if (again) again.focus({ preventScroll: true });
        if (onToggle) onToggle();
      });
    });
  }

  /* ------------------------------------------------ podpowiedz (wartosci pod kursorem) */
  const SVGNS = "http://www.w3.org/2000/svg";

  function attachBarHover(plot) {
    const svg = plot.querySelector("svg");
    if (!svg) return;
    const doc = plot.ownerDocument;
    const tip = doc.createElement("div");
    tip.className = "cv-tip";
    tip.hidden = true;
    plot.appendChild(tip);
    svg.querySelectorAll(".cv-barrow").forEach((row) => {
      row.addEventListener("pointerenter", () => {
        tip.textContent = row.dataset.tip;
        tip.hidden = false;
        const r = svg.getBoundingClientRect(), rr = row.getBoundingClientRect();
        tip.style.left = "0px";
        tip.style.top = `${Math.round(rr.bottom - r.top + 2)}px`;
      });
      row.addEventListener("pointerleave", () => { tip.hidden = true; });
    });
  }

  function attachHover(plot, card, size) {
    if (isBars(card)) return attachBarHover(plot);
    const m = lineModel(card, size);
    const svg = plot.querySelector("svg");
    if (!m || !svg || !m.items.length) return;
    const doc = plot.ownerDocument;
    const hov = svg.querySelector(".cv-hov");
    const cross = hov.querySelector(".cv-cross");
    const tip = doc.createElement("div");
    tip.className = "cv-tip";
    tip.hidden = true;
    plot.appendChild(tip);
    const dots = m.items.map(({ color }) => {
      const c = doc.createElementNS(SVGNS, "circle");
      c.setAttribute("r", m.big ? "4.5" : "3.5");
      c.setAttribute("fill", color);
      c.setAttribute("class", "cv-dot");
      hov.appendChild(c);
      return c;
    });
    const unit = card.unit || "";
    const vdec = Math.max(decFor(m.ymax - m.ymin), 2);
    const tol = m.ls ? 12 : 0.5;
    let idx = m.xs.length - 1;

    function pointAt(s, x) {
      let best = null, bd = Infinity;
      for (const p of s.points) {
        const d = Math.abs(p.year - x);
        if (d < bd) { bd = d; best = p; }
      }
      return bd <= tol ? best : null;
    }

    function show(i) {
      idx = Math.max(0, Math.min(m.xs.length - 1, i));
      const x = m.xs[idx];
      const px = m.sx(x);
      cross.setAttribute("x1", px.toFixed(1));
      cross.setAttribute("x2", px.toFixed(1));
      hov.setAttribute("visibility", "visible");
      tip.textContent = "";
      const head = doc.createElement("div");
      head.className = "cv-tip-x";
      head.textContent = xLabel(m, x);
      tip.appendChild(head);
      m.items.forEach(({ s, color }, k) => {
        const p = pointAt(s, x);
        if (!p) { dots[k].setAttribute("visibility", "hidden"); return; }
        dots[k].setAttribute("visibility", "visible");
        dots[k].setAttribute("cx", m.sx(p.year).toFixed(1));
        dots[k].setAttribute("cy", m.sy(p.value).toFixed(1));
        const row = doc.createElement("div");
        row.className = "cv-tip-row";
        const key = doc.createElement("span");
        key.className = "cv-tip-key";
        key.style.background = color;
        const val = doc.createElement("strong");
        val.textContent = withUnit(num(p.value, vdec), unit);
        row.append(key, val);
        if (m.all.length > 1 || card.compare) {
          const lab = doc.createElement("span");
          lab.className = "cv-tip-lab";
          lab.textContent = s.label;
          row.appendChild(lab);
        }
        tip.appendChild(row);
      });
      tip.hidden = false;
      // pozycja w px elementu (SVG jest skalowany do szerokosci)
      const r = svg.getBoundingClientRect();
      const k = r.width / m.w;
      const left = px * k;
      const tw = tip.offsetWidth;
      tip.style.left = `${Math.round(left + 12 + tw > r.width ? Math.max(0, left - 12 - tw) : left + 12)}px`;
      tip.style.top = `${Math.round(m.PT * k)}px`;
    }
    function hide() {
      hov.setAttribute("visibility", "hidden");
      tip.hidden = true;
    }
    function nearestIndex(clientX) {
      const r = svg.getBoundingClientRect();
      const x = m.ix(((clientX - r.left) / r.width) * m.w);
      let best = 0, bd = Infinity;
      m.xs.forEach((v, i) => { const d = Math.abs(v - x); if (d < bd) { bd = d; best = i; } });
      return best;
    }
    svg.addEventListener("pointermove", (e) => show(nearestIndex(e.clientX)));
    svg.addEventListener("pointerdown", (e) => show(nearestIndex(e.clientX)));
    svg.addEventListener("pointerleave", () => { if (doc.activeElement !== svg) hide(); });
    svg.addEventListener("focus", () => show(idx));
    svg.addEventListener("blur", hide);
    svg.addEventListener("keydown", (e) => {
      const stepBig = Math.max(1, Math.round(m.xs.length / 10));
      const moves = { ArrowLeft: -1, ArrowRight: 1, PageDown: -stepBig, PageUp: stepBig };
      if (e.key in moves) { e.preventDefault(); show(idx + moves[e.key]); }
      else if (e.key === "Home") { e.preventDefault(); show(0); }
      else if (e.key === "End") { e.preventDefault(); show(m.xs.length - 1); }
    });
  }

  /* ------------------------------------------------ tabela wartosci */
  function tableHtml(card) {
    const unit = card.unit ? ` (${esc(card.unit)})` : "";
    if (isBars(card)) {
      const vals = barValues(card);
      const dec = decFor(Math.max(...vals.map((v) => Math.abs(v.value)), 0));
      return `<table class="cv-table"><thead><tr><th scope="col"></th><th scope="col">${esc(t("value"))}${unit}</th></tr></thead><tbody>` +
        vals.map((v) => `<tr><th scope="row">${esc(v.label)}</th><td>${esc(num(v.value, Math.max(dec, 1)))}</td></tr>`).join("") +
        "</tbody></table>";
    }
    const all = allSeries(card);
    if (!all.length) return "";
    const maps = all.map((x) => new Map(x.s.points.map((p) => [p.year, p.value])));
    const vals = all.flatMap((x) => x.s.points.map((p) => p.value));
    const dec = Math.max(decFor(Math.max(...vals) - Math.min(...vals)), 2);
    const ls = card.x_kind === "ls";
    const xs = [...new Set(all.flatMap((x) => x.s.points.map((p) => p.year)))].sort((a, b) => a - b);
    const head = `<tr><th scope="col">${ls ? "Ls" : esc(t("year"))}</th>${all.map((x) => `<th scope="col">${esc(x.s.label)}${unit}</th>`).join("")}</tr>`;
    const rows = [...xs].reverse().map((x) => `<tr><th scope="row">${esc(ls ? Math.round(x) + "°" : String(x))}</th>` +
      maps.map((mp) => `<td>${mp.has(x) ? esc(num(mp.get(x), dec)) : "–"}</td>`).join("") + "</tr>").join("");
    return `<table class="cv-table"><thead>${head}</thead><tbody>${rows}</tbody></table>`;
  }

  function hintFor(card) {
    if (isBars(card)) return "";
    const legend = allSeries(card).length > 1 || card.compare || trendMode(card, true);
    return t("hoverHint") + (legend ? " " + t("legendHint") : "");
  }

  /* ------------------------------------------------ powiekszenie jednego wykresu */
  /** Wykres na wiekszej czesci ekranu (warstwa w tym samym dokumencie).
      onZoom(true/false) pozwala gospodarzowi powiekszyc ramke / okno. */
  function openZoom(card, host, opts, opener, onClosed) {
    const doc = host.ownerDocument;
    const win = doc.defaultView;
    const root = host.closest(".cv-root") || doc.body;
    const box = doc.createElement("div");
    box.className = "cv-zoom";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", card.title || t("chart"));
    const fact = keyFact(card);
    box.innerHTML = `
      <div class="cv-zoom-head">
        <h3>${esc(card.title)}</h3>
        <button type="button" class="cv-zbtn cv-zclose">${esc(t("close"))} ×</button>
      </div>
      <div class="cv-zoom-body">
        <div class="cv-plot cv-plot-big"></div>
        ${fact ? `<p class="cv-key">${esc(fact)}</p>` : ""}
        <p class="cv-zhint">${esc(hintFor(card))}</p>
        <details class="cv-values"><summary>${esc(t("table"))}</summary>${tableHtml(card)}</details>
      </div>`;
    root.appendChild(box);
    const plot = box.querySelector(".cv-plot");

    function draw() {
      const wpx = Math.max(280, Math.floor(plot.clientWidth));
      const avail = box.clientHeight - box.querySelector(".cv-zoom-head").offsetHeight - 150;
      const hpx = Math.max(200, Math.min(Math.round(wpx * 0.5), avail));
      drawPlot(plot, card, { w: wpx, h: hpx, big: true });
    }
    let raf = 0;
    const onResize = () => { cancelAnimationFrame(raf); raf = win.requestAnimationFrame(draw); };
    function close() {
      win.removeEventListener("resize", onResize);
      win.removeEventListener("keydown", onKey, true);
      box.remove();
      if (opts.onZoom) opts.onZoom(false);
      if (onClosed) onClosed();
      if (opener) opener.focus({ preventScroll: true });
    }
    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); close(); }
    }
    box.querySelector(".cv-zclose").addEventListener("click", close);
    win.addEventListener("keydown", onKey, true);
    win.addEventListener("resize", onResize);
    if (opts.onZoom) opts.onZoom(true);
    // gospodarz moze zmienic rozmiar ramki - rysuj po nim (resize) i od razu
    draw();
    setTimeout(onResize, 120);
    box.querySelector(".cv-zclose").focus({ preventScroll: true });
    return close;
  }

  /* ------------------------------------------------ skrot (maly panel) */
  function renderSummary(data, { maxCharts = 2 } = {}) {
    const all = drawableCards(data);
    const picked = pickCards(data, maxCharts);
    let html = "";
    const missing = data.missing || [];
    if (!picked.length && !(data.cards || []).length) html += `<p class="cv-empty"><strong>${esc(t("empty"))}</strong></p>`;
    else if (!picked.length && (data.cards || []).some((c) => c.type === "heatmap" && !c.error)) html += `<p class="cv-empty">${esc(t("mapInFull"))}</p>`;
    else if (!picked.length) html += `<p class="cv-empty">${esc(t("empty"))}</p>`;
    picked.forEach((c, i) => {
      const fact = keyFact(c);
      html += `
        <section class="cv-card">
          <div class="cv-card-head">
            <h3>${esc(c.title)}</h3>
            <button type="button" class="cv-zbtn" data-zoom="${i}" title="${esc(t("expandTitle"))}">${esc(t("expand"))}</button>
          </div>
          <div class="cv-plot" data-plot="${i}"></div>
          ${fact ? `<p class="cv-key">${esc(fact)}</p>` : ""}
        </section>`;
    });
    for (const m of missing) {
      html += `<p class="cv-missing"><strong>${esc(m.message || !m.subject ? t("missingTitle") : t("noDataFor", { x: m.subject }))}</strong>${m.message ? `<br>${esc(m.message)}` : ""}</p>`;
    }
    const rest = all.length - picked.length;
    if (rest > 0 && CV.canMaximize) html += `<p class="cv-more"><button type="button" class="cv-linkbtn" data-maximize>${esc(t("moreCharts", { n: rest }))}</button></p>`;
    html += `<p class="cv-disc">${esc(t("disclaimer"))}</p>`;
    return html;
  }

  /** Wstawia skrot do kontenera i podpina podpowiedzi, legendy i powiekszanie.
      opts: maxCharts, onZoom(on), onMaximize() (przycisk "zobacz wszystkie"). */
  function mountSummary(container, data, opts = {}) {
    container.innerHTML = renderSummary(data, opts);
    const picked = pickCards(data, opts.maxCharts || 2);
    const redraw = [];
    container.querySelectorAll("[data-plot]").forEach((plot) => {
      const card = picked[Number(plot.dataset.plot)];
      if (!card) return;
      const fn = () => drawPlot(plot, card, SMALL);
      redraw[Number(plot.dataset.plot)] = fn;
      fn();
    });
    container.querySelectorAll("[data-zoom]").forEach((btn) => {
      const i = Number(btn.dataset.zoom);
      btn.addEventListener("click", () => openZoom(picked[i], container, opts, btn, redraw[i]));
    });
    const more = container.querySelector("[data-maximize]");
    if (more && opts.onMaximize) more.addEventListener("click", () => opts.onMaximize());
  }

  function stripesHtml() {
    return `<div class="cv-stripes" aria-hidden="true">${STRIPES.map((c) => `<span style="background:${c}"></span>`).join("")}</div>`;
  }

  /* Style panelu i okna rozszerzenia (te same tokeny co aplikacja) */
  const css = `
  :host, .cv-root { all: initial; }
  .cv-root, .cv-root * { box-sizing: border-box; }
  .cv-root {
    --paper: #f2f4f3; --panel: #ffffff; --ink: #17212b; --ink-2: #3a4650; --muted: #5e6a71;
    --rule: #d3dadc; --rule-soft: #e6eaeb; --accent: #1d4e89;
    font-family: "Schibsted Grotesk", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    font-size: 14px; line-height: 1.45; color: var(--ink); background: var(--panel);
  }
  .cv-stripes { display: flex; height: 6px; }
  .cv-stripes span { flex: 1; }
  .cv-head { display: flex; align-items: center; gap: 8px; padding: 10px 12px 8px 14px; }
  .cv-head h2 { margin: 0; font-size: 15px; font-weight: 600; flex: 1; }
  .cv-x { background: none; border: 0; cursor: pointer; color: var(--muted); font: inherit; font-size: 20px; line-height: 1; padding: 2px 4px; border-radius: 4px; }
  .cv-x:hover { color: var(--ink); background: var(--rule-soft); }
  .cv-max { display: inline-flex; align-items: center; gap: 6px; background: none; border: 1px solid var(--rule); border-radius: 4px;
    padding: 3px 8px; font: inherit; font-size: 12px; color: var(--accent); cursor: pointer; }
  .cv-max:hover { border-color: var(--accent); background: #f3f6fa; }
  .cv-max svg { display: block; width: 12px; height: 12px; }
  .cv-body { padding: 0 14px 14px; overflow-y: auto; }
  .cv-thesis { margin: 0 0 8px; font-size: 15px; font-weight: 500; }
  .cv-thesis::before { content: "“"; } .cv-thesis::after { content: "”"; }
  .cv-meta { margin: 0 0 10px; color: var(--muted); font-size: 12px; }
  .cv-card { border-top: 1px solid var(--rule); padding: 10px 0 6px; }
  .cv-card h3 { margin: 0 0 6px; font-size: 14px; font-weight: 600; }
  .cv-svg { display: block; width: 100%; height: auto; }
  .cv-grid { stroke: var(--rule-soft); stroke-width: 1; }
  .cv-axis { stroke: var(--rule); stroke-width: 1; }
  .cv-tick { fill: var(--muted); font-size: 10px; font-family: inherit; }
  .cv-legend { list-style: none; margin: 4px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 2px 6px; font-size: 11.5px; color: var(--ink-2); }
  .cv-lg { display: inline-flex; align-items: center; gap: 5px; background: none; border: 0; border-radius: 3px; padding: 2px 4px;
    margin: 0 0 0 -4px; font: inherit; color: inherit; cursor: pointer; text-align: left; }
  .cv-lg:hover { background: var(--rule-soft); }
  .cv-lg.cv-off { color: var(--muted); }
  .cv-lg.cv-off .cv-lg-t { text-decoration: line-through; }
  .cv-lg.cv-off .cv-sw { opacity: .3; }
  .cv-sw { display: inline-block; width: 16px; height: 3px; flex: 0 0 auto; }
  .cv-sw-dash { height: 2px; background: repeating-linear-gradient(90deg, var(--c) 0 5px, transparent 5px 8px) !important; }
  .cv-allhidden { margin: 0; padding: 22px 8px; text-align: center; color: var(--muted); font-size: 12.5px;
    border: 1px dashed var(--rule); border-radius: 4px; }
  .cv-key { margin: 6px 0 0; font-size: 13px; color: var(--ink-2); }
  .cv-more { margin: 8px 0 0; font-size: 12.5px; }
  .cv-linkbtn { background: none; border: 0; padding: 0; font: inherit; color: var(--accent); text-decoration: underline;
    text-underline-offset: 2px; cursor: pointer; text-align: left; }
  .cv-linkbtn:hover { text-decoration-thickness: 2px; }
  .cv-full { margin: 6px 0 0; font-size: 12.5px; }
  .cv-open { color: var(--accent); text-decoration: underline; text-underline-offset: 2px; }
  .cv-open:hover { text-decoration-thickness: 2px; }
  .cv-open:focus-visible, .cv-x:focus-visible, button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .cv-disc { margin: 8px 0 0; font-size: 11.5px; color: var(--muted); }
  .cv-empty, .cv-error { margin: 8px 0; }
  .cv-missing { margin: 10px 0 4px; padding: 8px 10px; border-left: 3px solid var(--muted); background: #f5f7f7; font-size: 13px; color: var(--ink-2); }
  .cv-missing strong { color: var(--ink); font-weight: 600; }
  .cv-error { color: #7a4b00; background: #fbf3e6; border-left: 3px solid #c98a1a; padding: 8px 10px; }
  .cv-loading { margin: 6px 0 4px; color: var(--ink-2); }
  .cv-bar { height: 4px; background: var(--rule-soft); position: relative; overflow: hidden; margin: 8px 0; }
  .cv-bar::after { content: ""; position: absolute; inset: 0 auto 0 0; width: 35%;
    background: linear-gradient(90deg, #2166ac, #f7f7f7, #b2182b); animation: cvload 1.4s ease-in-out infinite; }
  @keyframes cvload { from { transform: translateX(-100%); } to { transform: translateX(300%); } }
  @media (prefers-reduced-motion: reduce) { .cv-bar::after { animation: none; width: 100%; } }
  .cv-zero { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 2 3; }
  .cv-card-head { display: flex; align-items: baseline; gap: 8px; margin: 0 0 6px; }
  .cv-card-head h3 { margin: 0; flex: 1; }
  .cv-zbtn { flex: 0 0 auto; background: none; border: 1px solid var(--rule); border-radius: 4px; padding: 2px 8px;
    font: inherit; font-size: 12px; color: var(--accent); cursor: pointer; }
  .cv-zbtn:hover { border-color: var(--accent); background: #f3f6fa; }
  .cv-plot { position: relative; }
  .cv-plot svg { cursor: crosshair; touch-action: pan-y; }
  .cv-plot svg:focus { outline: none; }
  .cv-plot svg:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .cv-cross { stroke: var(--ink-2); stroke-width: 1; }
  .cv-dot { stroke: #ffffff; stroke-width: 2; }
  .cv-barrow:hover .cv-bar-mark { opacity: .7; }
  .cv-barrow:hover .cv-tick { fill: var(--ink); }
  .cv-tip { position: absolute; z-index: 2; pointer-events: none; min-width: 96px; max-width: 260px;
    background: #ffffff; border: 1px solid var(--rule); border-radius: 4px; padding: 6px 8px;
    box-shadow: 0 4px 14px rgba(23, 33, 43, .14); font-size: 12px; line-height: 1.35; color: var(--ink); }
  .cv-tip[hidden] { display: none; }
  .cv-tip-x { color: var(--muted); margin-bottom: 3px; }
  .cv-tip-row { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
  .cv-tip-key { display: inline-block; width: 12px; height: 2px; flex: 0 0 auto; }
  .cv-tip-row strong { font-weight: 600; font-variant-numeric: tabular-nums; }
  .cv-tip-lab { color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; }
  .cv-zoom { position: fixed; inset: 0; z-index: 10; background: var(--panel); display: flex; flex-direction: column; }
  .cv-zoom-head { display: flex; align-items: center; gap: 12px; padding: 12px 18px 10px; border-bottom: 1px solid var(--rule); }
  .cv-zoom-head h3 { margin: 0; flex: 1; font-size: 16px; font-weight: 600; }
  .cv-zoom-body { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 12px 18px 18px; }
  .cv-zoom .cv-tick { font-size: 11.5px; }
  .cv-zoom .cv-legend { font-size: 12.5px; margin-top: 6px; }
  .cv-zoom .cv-key { font-size: 14px; }
  .cv-zhint { margin: 6px 0 0; font-size: 12px; color: var(--muted); }
  .cv-zhint:empty { display: none; }
  .cv-values { margin-top: 10px; font-size: 13px; }
  .cv-values summary { cursor: pointer; color: var(--accent); font-weight: 500; }
  .cv-table { border-collapse: collapse; margin-top: 6px; font-size: 12.5px; font-variant-numeric: tabular-nums; }
  .cv-table th, .cv-table td { padding: 3px 12px 3px 0; border-bottom: 1px solid var(--rule-soft); text-align: right; }
  .cv-table th[scope="row"], .cv-table thead th:first-child { text-align: left; }
  .cv-table thead th { color: var(--ink-2); font-weight: 600; border-bottom: 1px solid var(--rule); vertical-align: bottom; }
  .cv-values .cv-table { display: block; max-height: 320px; overflow: auto; }
  `;

  CV.render = {
    renderSummary, mountSummary, openZoom, pickCards, drawableCards, keyFact, chartFor, drawPlot,
    tableHtml, legendHtml, stripesHtml, esc, css, COLORS,
  };
})();

if (typeof module !== "undefined") module.exports = CV.render;
