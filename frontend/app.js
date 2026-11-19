/* Hermes Finder — frontend v3 (vanilla JS + Chart.js + Esri tiles) */
"use strict";

// frontend serwowany przez backend -> ten sam origin (dowolny port);
// otwarty z pliku (file://) -> domyslny adres backendu
const API_BASE = window.location.protocol.startsWith("http")
  ? window.location.origin
  : "http://127.0.0.1:8000";

const el = {
  thesisInput: document.getElementById("thesisInput"),
  charCount: document.getElementById("charCount"),
  clearBtn: document.getElementById("clearBtn"),
  chips: document.getElementById("chips"),
  analyzeBtn: document.getElementById("analyzeBtn"),
  submitHint: document.getElementById("submitHint"),
  loader: document.getElementById("loader"),
  loaderText: document.getElementById("loaderText"),
  connectionError: document.getElementById("connectionError"),
  retryBtn: document.getElementById("retryBtn"),
  results: document.getElementById("results"),
  summaryLine: document.getElementById("summaryLine"),
  startYear: document.getElementById("startYear"),
  endYear: document.getElementById("endYear"),
  disableLlm: document.getElementById("disableLlm"),
};

// Okabe-Ito: paleta odporna na daltonizm, standard w publikacjach naukowych
const SERIES_COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#17212B", "#8C969C"];
const TREND_GREY = "#5E6A71";
const AXIS = { tick: "#5E6A71", grid: "#E6EAEB", title: "#5E6A71" };
// etykiety typow instytucji i danych (klucze slownika: org_*, dt_*)
const orgTypeLabel = (k) => (k && I18N["org_" + k] ? t("org_" + k) : k || "");
const dataTypeLabel = (k) => (k && I18N["dt_" + k] ? t("dt_" + k) : k || "");
const charts = [];
let lastData = null;      // ostatni wynik - do ponownego narysowania po zmianie jezyka
let reqYears = null;      // lata z ustawien zapytania {start, end} (null = z tezy)

/* ============================ jezyk ============================ */
applyStaticTexts();
document.getElementById("noServerP").innerHTML =
  escapeHtml(t("noServerP", { url: "\u0001" })).replace("\u0001", `<code>${escapeHtml(API_BASE)}</code>`);
document.getElementById("langSelect").addEventListener("change", (ev) => {
  setLanguage(ev.target.value);
  document.getElementById("noServerP").innerHTML =
    escapeHtml(t("noServerP", { url: "\u0001" })).replace("\u0001", `<code>${escapeHtml(API_BASE)}</code>`);
  validateYears();
  if (lastData) { clearResults(); render(lastData); }
  drawStripes();
});

/* ============================ lata w ustawieniach zapytania ============================ */
/** Sprawdza pola "od roku" / "do roku"; blad na czerwono pod polami.
    Zwraca {ok, start, end} (puste pole = null). */
function validateYears() {
  const box = document.getElementById("yearError");
  const fields = [[el.startYear, "fromYear"], [el.endYear, "toYear"]];
  const out = { ok: true, start: null, end: null };
  const msgs = [];
  for (const [input, key] of fields) {
    input.removeAttribute("aria-invalid");
    const raw = input.value.trim();
    // pole liczbowe z tekstem, ktorego przegladarka nie umie przeczytac (np. "19e9")
    if (!raw && !(input.validity && input.validity.badInput)) continue;
    const v = Number(raw);
    if (!/^\d{4}$/.test(raw) || !Number.isInteger(v) || v < YEAR_MIN || v > YEAR_MAX) {
      input.setAttribute("aria-invalid", "true");
      msgs.push(t("errYearRange", { field: `“${t(key)}”`, min: YEAR_MIN, max: YEAR_MAX }));
      out.ok = false;
    } else if (key === "fromYear") out.start = v; else out.end = v;
  }
  if (out.ok && out.start !== null && out.end !== null && out.start > out.end) {
    el.startYear.setAttribute("aria-invalid", "true");
    el.endYear.setAttribute("aria-invalid", "true");
    msgs.push(t("errYearOrder", { from: `“${t("fromYear")}”`, to: `“${t("toYear")}”` }));
    out.ok = false;
  }
  box.textContent = msgs.join(" ");
  box.hidden = !msgs.length;
  return out;
}
el.startYear.max = el.endYear.max = String(YEAR_MAX);
for (const input of [el.startYear, el.endYear]) {
  input.addEventListener("input", validateYears);
  input.addEventListener("change", validateYears);
}

/* ============================ UI: input ============================ */

el.thesisInput.addEventListener("input", () => {
  el.charCount.textContent = `${el.thesisInput.value.length} / 600`;
});

el.clearBtn.addEventListener("click", () => {
  el.thesisInput.value = "";
  el.charCount.textContent = "0 / 600";
  el.thesisInput.focus();
});

el.chips.addEventListener("click", (ev) => {
  const btn = ev.target.closest(".chip");
  if (!btn) return;
  el.thesisInput.value = btn.textContent.trim();
  el.charCount.textContent = `${el.thesisInput.value.length} / 600`;
  el.thesisInput.focus();
});

el.thesisInput.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) {
    ev.preventDefault();
    analyze();
  }
});

el.analyzeBtn.addEventListener("click", analyze);
el.retryBtn.addEventListener("click", () => {
  el.connectionError.classList.add("hidden");
  analyze();
});

/* ============================ Analiza ============================ */

async function analyze() {
  const thesis = el.thesisInput.value.trim();
  if (thesis.length < 4) {
    shake(el.thesisInput);
    el.thesisInput.focus();
    return;
  }
  const years = validateYears();
  if (!years.ok) {
    // blad lat: otworz ustawienia zapytania i pokaz pole z bledem
    document.getElementById("advanced").open = true;
    const bad = document.querySelector("#advanced [aria-invalid='true']");
    if (bad) { shake(bad); bad.focus(); }
    return;
  }
  hide(el.connectionError);
  el.summaryLine.classList.add("hidden");
  clearResults();
  show(el.loader);
  setLoading(true);

  const options = {};
  if (years.start !== null) options.start_year = years.start;
  if (years.end !== null) options.end_year = years.end;
  reqYears = years.start !== null || years.end !== null ? { start: years.start, end: years.end } : null;
  if (el.disableLlm.checked) options.disable_llm = true;
  options.language = LANG; // komunikaty o brakujacych danych w jezyku interfejsu

  try {
    const resp = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ thesis, options }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      const detail = Array.isArray(body.detail)
        ? body.detail.map((d) => String(d.msg || "").replace(/^Value error, /, "")).join("; ")
        : body.detail;
      throw new Error(detail || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    render(data);
  } catch (err) {
    hide(el.loader);
    if (err instanceof TypeError) {
      show(el.connectionError);
    } else {
      clearResults();
      el.results.innerHTML = `
        <div class="card">
          <h2 class="card-title">${escapeHtml(t("analysisError"))}</h2>
          <div class="card-error">${escapeHtml(String(err.message || err))}</div>
        </div>`;
      show(el.results);
    }
  } finally {
    setLoading(false);
    hide(el.loader);
  }
}

function setLoading(state) {
  el.analyzeBtn.disabled = state;
  el.submitHint.textContent = state ? t("fetching") : t("orEnter");
}

function clearResults() {
  el.results.classList.add("hidden");
  charts.forEach((c) => c.destroy());
  charts.length = 0;
  heatmaps.forEach((h) => h.destroy());
  heatmaps.length = 0;
  el.results.innerHTML = "";
}

function render(data) {
  lastData = data;
  if (reqYears) data.cards.forEach((c) => clampCardYears(c, reqYears));
  const cards = data.cards || [];
  const sources = data.sources || [];
  const planner = data.planner || {};

  el.summaryLine.innerHTML = `
    <p class="report-quote">${escapeHtml(data.thesis || el.thesisInput.value.trim())}</p>
    ${data.summary ? `<p class="report-summary">${escapeHtml(data.summary)}</p>` : ""}
    ${yearsLine(planner) ? `<p class="report-planner">${escapeHtml(yearsLine(planner))}</p>` : ""}`;
  el.summaryLine.classList.remove("hidden");

  const missing = data.missing || [];
  if (!cards.length) {
    const msgs = missing.map((m) => m.message || t("noDataFor", { x: m.subject })).filter(Boolean);
    el.results.innerHTML = `
      <article class="card card-nodata span-3" role="status">
        <h2 class="card-title">${escapeHtml(t("noData"))}</h2>
        ${msgs.map((m) => `<p class="nodata-msg">${escapeHtml(m)}</p>`).join("")}
        <p class="card-note">${escapeHtml(t("noDataHint"))}</p>
      </article>`;
    show(el.results);
    return;
  }

  let html = "";
  for (const card of cards) html += cardHtml(card);
  html += missingHtml(missing);
  html += sourcesOverviewHtml(sources);
  html += `<p class="disclaimer">${escapeHtml(t("disclaimer"))}</p>`;
  el.results.innerHTML = html;
  show(el.results);

  for (const card of cards) {
    if (card.error) continue;
    try {
      if (card.type === "heatmap") drawHeatmap(card);
      else if (card.type === "period_compare") drawPeriodMiniCharts(card);
      else if (card.type === "bars") drawBars(card);
      else drawSeriesChart(card);
    } catch (err) {
      console.error("render card failed", card.id, err);
    }
  }
}

/** Lata z ustawien zapytania sa wymuszone: punkty spoza zakresu znikaja z karty
    (zabezpieczenie takze dla starszego serwera), os X = dokladnie wybrany zakres. */
function inYears(y, w) {
  return (w.start === null || y >= w.start) && (w.end === null || y <= w.end);
}
function clampCardYears(card, w) {
  if (card.x_kind === "ls") return;
  const cut = (pts) => (pts || []).filter((p) => inYears(p.year, w));
  for (const s of [...(card.series || []), ...(card.trends || [])]) s.points = cut(s.points);
  for (const p of card.periods || []) {
    if (p.points) p.points = cut(p.points);
    for (const s of p.series || []) {
      s.points = cut(s.points);
      if (s.trend && s.trend.points) s.trend.points = cut(s.trend.points);
    }
  }
  if (card.grid && card.grid.years) {
    const keep = card.grid.years.filter((y) => inYears(y, w));
    card.grid.years = keep;
  }
}

/** Jedyna informacja pod teza: lata wymuszone w ustawieniach zapytania
    (bez komunikatow o serwerze, modelu i liczbie instytucji). */
function yearsLine(planner) {
  const uw = planner.years_shown;
  if (Array.isArray(uw) && uw.length === 2) return t("yearsShown", { a: uw[0], b: uw[1] });
  if (reqYears) return t("yearsShown", { a: reqYears.start ?? YEAR_MIN, b: reqYears.end ?? YEAR_MAX });
  return "";
}

/* ============================ HTML kart ============================ */

/** Czesci tezy, dla ktorych w katalogu nie ma danych (komunikat od modelu). */
function missingHtml(missing) {
  if (!missing || !missing.length) return "";
  return missing.map((m) => `
    <article class="card card-missing span-3" role="note">
      <h2 class="card-title"><span class="missing-icon" aria-hidden="true">∅</span>${escapeHtml(m.message || !m.subject ? t("missingTitle") : t("noDataFor", { x: m.subject }))}</h2>
      ${m.message ? `<p class="nodata-msg">${escapeHtml(m.message)}</p>` : ""}
    </article>`).join("");
}

function spanClass(card) {
  if (card.compare) return "";
  if (["heatmap", "period_compare", "period_bands", "bars", "multi_line"].includes(card.type)) return "";
  if (card.type === "difference") return "span-3";
  return (card.series || []).length === 1 ? "span-3" : "";
}

function cardHtml(card) {
  const span = spanClass(card);
  const note = card.note ? `<p class="card-note">${escapeHtml(card.note)}</p>` : "";
  if (card.error) {
    return `
    <article class="card ${span}">
      <h2 class="card-title">${escapeHtml(card.title || "")}</h2>
      <p class="card-error">${escapeHtml(card.error)}</p>
      ${card.caption ? `<p class="caption">${escapeHtml(card.caption)}</p>` : ""}
    </article>`;
  }
  const facts = (card.facts || []).map((f) => `<li>${escapeHtml(f)}</li>`).join("");
  return `
    <article class="card ${span}">
      <h2 class="card-title">${escapeHtml(card.title || "")}</h2>
      ${note}
      ${innerHtml(card)}
      ${card.caption ? `<p class="caption">${escapeHtml(card.caption)}</p>` : ""}
      ${numbersHtml(card)}
      ${facts ? `<ul class="facts">${facts}</ul>` : ""}
      ${skippedHtml(card)}
      ${detailsHtml(card)}
    </article>`;
}

function innerHtml(card) {
  switch (card.type) {
    case "heatmap":
      return heatmapHtml(card);
    case "period_compare":
      return periodMiniHtml(card);
    case "bars":
      return `<div class="bar-chart-box"><canvas id="cv-${card.idx}" aria-label="${escapeAttr(card.title || "")}"></canvas></div>`;
    default:
      return `<div class="chart-box"><canvas id="cv-${card.idx}" aria-label="${escapeAttr(card.title || "")}"></canvas></div>`;
  }
}

function signed(v, unit) {
  return `${v >= 0 ? "+" : "−"}${fmt(Math.abs(v))}${unit ? " " + unit : ""}`;
}

/* liczby pod wykresem: tabela zrodel (porownania) albo wiersz statystyk */
function numbersHtml(card) {
  const unit = card.unit || "";
  if (card.providers && card.providers.length && card.type !== "bars") return sourcesTableHtml(card);

  const items = [];
  if (card.type === "period_compare") {
    const periods = card.periods || [];
    if (periods.length >= 2) {
      const first = periods[0].series || [], last = periods[periods.length - 1].series || [];
      for (const e of last) {
        const f = first.find((x) => x.label === e.label);
        if (f) items.push([`${e.label}, ${periods[0].label} → ${periods[periods.length - 1].label}`, signed(e.mean - f.mean, unit)]);
      }
    }
  } else if (card.type === "difference") {
    const pts = (card.series || []).flatMap((s) => s.points.map((p) => p.value));
    if (pts.length) items.push([t("meanDiff"), signed(pts.reduce((a, b) => a + b, 0) / pts.length, unit)]);
    pushStats(items, card.stats, unit);
  } else if (card.type === "bars" || card.type === "heatmap") {
    return "";
  } else if ((card.stats || []).length > 1) {
    return statsTableHtml(card);
  } else {
    pushStats(items, card.stats, unit);
  }
  if (!items.length) return "";
  return `<dl class="stat-row">${items.map(([k, v]) => `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`).join("")}</dl>`;
}

function pushStats(items, stats, unit) {
  const s = (stats || []).find((x) => x && x.n);
  if (!s) return;
  items.push([t("trendDecade"), signed(s.slope_per_decade, unit)]);
  items.push([t("changeTrend"), signed(s.total_change, unit)]);
  items.push([t("fitR2"), fmt(s.r2)]);
  items.push([t("signif"), fmtP(s.p_value)]);
  items.push([t("yearsData"), String(s.n)]);
}

function statsTableHtml(card) {
  const unit = card.unit || "";
  const rows = (card.stats || []).filter((s) => s && s.n).map((s, i) => `
      <tr>
        <td><span class="swatch" style="background:${SERIES_COLORS[i % SERIES_COLORS.length]}"></span><span class="series-name">${escapeHtml(s.label)}</span></td>
        <td class="num" data-label="${escapeAttr(t("trendDecade"))}">${escapeHtml(signed(s.slope_per_decade, unit))}</td>
        <td class="num" data-label="${escapeAttr(t("changePeriod"))}">${escapeHtml(signed(s.total_change, unit))}</td>
        <td data-label="R²">${fmt(s.r2)}</td><td data-label="p">${escapeHtml(fmtP(s.p_value))}</td><td data-label="${escapeAttr(t("years"))}">${s.n}</td>
      </tr>`).join("");
  return `<div class="sources-table-wrap"><table class="sources-table">
      <thead><tr><th>${escapeHtml(t("series"))}</th><th>${escapeHtml(t("trendDecade"))}</th><th>${escapeHtml(t("changePeriod"))}</th><th>R²</th><th>p</th><th>${escapeHtml(t("years"))}</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
}

function sourcesTableHtml(card) {
  const unit = card.unit || "";
  const statBy = new Map((card.stats || []).filter((s) => s && s.n).map((s) => [s.label, s]));
  const hasTrend = statBy.size > 0;
  const rows = (card.providers || []).map((p, i) => {
    const st = statBy.get(p.label);
    const kind = [orgTypeLabel(p.org_type), dataTypeLabel(p.data_type), p.country].filter(Boolean).join(", ");
    return `
      <tr>
        <td><span class="swatch" style="background:${SERIES_COLORS[i % SERIES_COLORS.length]}"></span><span class="series-name">${escapeHtml(p.label || "")}</span></td>
        <td data-label="${escapeAttr(t("institution"))}">${escapeHtml(p.org || "")}<span class="sub">${escapeHtml(kind)}</span></td>
        ${hasTrend ? `<td class="num" data-label="${escapeAttr(t("trendDecade"))}">${st ? escapeHtml(signed(st.slope_per_decade, unit)) : "—"}</td>` : ""}
        <td data-label="${escapeAttr(t("baseline"))}">${escapeHtml(p.original_baseline || "—")}</td>
        <td data-label="${escapeAttr(t("dataset"))}"><a href="${escapeAttr(p.url || "#")}" target="_blank" rel="noopener">${escapeHtml(p.source_name || t("dataWord"))}</a>${p.note ? `<span class="sub">${escapeHtml(p.note)}</span>` : ""}</td>
      </tr>`;
  }).join("");
  return `<div class="sources-table-wrap"><table class="sources-table">
      <thead><tr><th>${escapeHtml(t("series"))}</th><th>${escapeHtml(t("institution"))}</th>${hasTrend ? `<th>${escapeHtml(t("trendDecade"))}</th>` : ""}<th>${escapeHtml(t("baseline"))}</th><th>${escapeHtml(t("dataset"))}</th></tr></thead>
      <tbody>${rows}</tbody></table></div>`;
}

function skippedHtml(card) {
  const sk = card.skipped || [];
  if (!sk.length) return "";
  return `<div class="skipped"><b>${escapeHtml(t("notShown", { n: sk.length }))}</b>
    <ul>${sk.map((s) => `<li>${escapeHtml(s.label)}: ${escapeHtml(s.reason)}</li>`).join("")}</ul></div>`;
}

function detailsHtml(card) {
  const notes = (card.notes || []).filter((n) => !/^(skipped|pominięto) /.test(n))
    .map((n) => `<p>${escapeHtml(n)}</p>`).join("");
  const src = card.source || {};
  const srcLink = !(card.providers || []).length && src.name
    ? `<p class="src-link">${escapeHtml(t("datasetLink"))} <a href="${escapeAttr(src.dataset_url || src.url || "#")}" target="_blank" rel="noopener">${escapeHtml(src.name)}</a></p>`
    : "";
  if (!notes && !srcLink) return "";
  return `
    <details class="extra">
      <summary>${escapeHtml(t("method"))}</summary>
      <div class="notes">${notes}</div>
      ${srcLink}
    </details>`;
}

/* ============================ osie: lata + madre kroki Y ============================ */

function fmtN(v, dec) {
  return v.toLocaleString(LOCALE, {
    minimumFractionDigits: dec, maximumFractionDigits: dec,
  });
}

function niceStep(range, target = 6) {
  if (!(range > 0)) return 1;
  const raw = range / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (raw <= m * mag) return m * mag;
  }
  return 10 * mag;
}

function yTickOpts(min, max) {
  const step = niceStep(max - min || 1);
  const dec = step >= 1 ? 0 : step >= 0.1 ? 1 : step >= 0.01 ? 2 : 3;
  return {
    ticks: {
      // stepSize musi byc w ticks (Chart.js 4), inaczej os dobiera wlasny krok,
      // a etykiety z za mala liczba miejsc po przecinku sie dubluja
      stepSize: step,
      color: AXIS.tick, font: { size: 12 }, maxTicksLimit: 10,
      callback: (v) => fmtN(v, dec),
    },
    grid: { color: AXIS.grid },
  };
}

function yearTickOpts(years, forced) {
  const w = forced ? reqYears : null;
  return {
    type: "linear",
    min: w && w.start !== null ? w.start : Math.min(...years),
    max: w && w.end !== null ? w.end : Math.max(...years),
    grid: { color: AXIS.grid },
    ticks: {
      color: AXIS.tick, font: { size: 12 }, maxTicksLimit: 8,
      callback: (v) => String(Math.round(v)), // rok bez separatora tysiecy
    },
  };
}

function lineDataset(series, color, isTrend, label) {
  return {
    label: label || series.label,
    data: series.points.map((p) => ({ x: p.year, y: p.value })),
    borderColor: color,
    backgroundColor: "transparent",
    borderWidth: isTrend ? 1.6 : 1.8,
    borderDash: isTrend ? [6, 4] : [],
    pointRadius: 0,
    pointHoverRadius: 4,
    tension: 0.2,
    fill: false,
  };
}

/** Legenda: probka w ksztalcie linii, przerywana dla trendow (jak na wykresie).
    Klik w pozycje ukrywa/pokazuje serie (domyslne zachowanie Chart.js). */
function legendOpts(display, size) {
  return {
    display,
    labels: {
      // probka = odcinek linii (pointStyle "line") o stalej dlugosci; domyslne
      // generateLabels bierze styl PUNKTU (bez przerywania), stad wlasna funkcja
      color: "#3A4650", font: { size }, usePointStyle: true, pointStyle: "line",
      pointStyleWidth: 30, boxHeight: 10,
      generateLabels(chart) {
        return chart.data.datasets.map((ds, i) => ({
          text: ds.label,
          datasetIndex: i,
          hidden: !chart.isDatasetVisible(i),
          pointStyle: "line",
          rotation: 0,
          fillStyle: ds.borderColor,
          strokeStyle: ds.borderColor,
          lineWidth: 2.5,
          lineDash: ds.borderDash && ds.borderDash.length ? [5, 3] : [],
          lineCap: "butt",
          fontColor: chart.isDatasetVisible(i) ? "#3A4650" : "#9AA4A9",
        }));
      },
    },
  };
}

function chartTooltip(unit) {
  return {
    backgroundColor: "#17212B",
    titleColor: "#FFFFFF",
    bodyColor: "#D3DADC",
    borderColor: "#17212B",
    borderWidth: 1,
    padding: 8,
    callbacks: {
      title: (items) => t("tipYear", { y: Math.round(items[0].parsed.x) }),
      label: (item) => `${item.dataset.label}: ${nf().format(item.parsed.y)} ${unit}`,
    },
  };
}

/* ============================ wykresy szeregowe ============================ */

function dataRange(card) {
  let yMin = Infinity, yMax = -Infinity;
  const yrs = [];
  (card.series || []).forEach((s) =>
    s.points.forEach((p) => {
      yrs.push(p.year);
      yMin = Math.min(yMin, p.value);
      yMax = Math.max(yMax, p.value);
    })
  );
  return { yMin, yMax, years: yrs };
}

function drawSeriesChart(card) {
  const canvas = document.getElementById(`cv-${card.idx}`);
  if (!canvas || typeof Chart === "undefined") return;
  const { yMin, yMax, years } = dataRange(card);
  const pad = (yMax - yMin) * 0.08 || 0.5;
  const datasets = (card.series || []).map((s, i) =>
    lineDataset(s, SERIES_COLORS[i % SERIES_COLORS.length], false));
  const nSeries = (card.series || []).length;
  (card.trends || []).forEach((tr, i) => {
    if (tr && tr.points) {
      const c = nSeries > 1 ? SERIES_COLORS[i % SERIES_COLORS.length] : TREND_GREY;
      const own = nSeries > 1 && card.series[i] ? card.series[i].label : "";
      datasets.push(lineDataset(tr, c, true, own ? `${t("trend")} (${own})` : t("trend")));
    }
  });

  charts.push(
    new Chart(canvas.getContext("2d"), {
      type: "line",
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "nearest", intersect: false },
        scales: {
          x: card.x_kind === "ls" ? lsTickOpts(card) : yearTickOpts(years.length ? years : [0, 1], true),
          y: {
            ...yTickOpts(yMin - pad, yMax + pad),
            suggestedMin: yMin - pad,
            suggestedMax: yMax + pad,
            title: card.unit ? { display: true, text: card.unit, color: AXIS.tick, font: { size: 12 } } : undefined,
          },
        },
        plugins: {
          legend: legendOpts(datasets.length > 1, 12),
          tooltip: card.x_kind === "ls" ? lsTooltip(card.unit || "") : chartTooltip(card.unit || ""),
        },
      },
    })
  );
}

function lsTickOpts(card) {
  return {
    type: "linear", min: card.x_min ?? 0, max: card.x_max ?? 360,
    grid: { color: AXIS.grid },
    title: { display: true, text: card.x_label || "Ls (°)", color: AXIS.tick, font: { size: 12 } },
    ticks: { color: AXIS.tick, font: { size: 12 }, stepSize: 45, callback: (v) => `${Math.round(v)}°` },
  };
}

function lsTooltip(unit) {
  const tt = chartTooltip(unit);
  tt.callbacks.title = (items) => `Ls ≈ ${Math.round(items[0].parsed.x)}°`;
  return tt;
}

/* ============================ źródła: tabela + przegląd ============================ */

function sourcesOverviewHtml(sources) {
  if (!sources.length) return "";
  const items = sources.map((s) => `
      <li><span class="org">${escapeHtml(s.org)}</span>
        <span class="meta">${escapeHtml([orgTypeLabel(s.type), s.country].filter(Boolean).join(", "))}</span>
        <span class="meta">${escapeHtml((s.datasets || []).join("; "))}</span></li>`).join("");
  return `
    <section class="provenance">
      <h2>${escapeHtml(t("provenance"))}</h2>
      <ul class="provenance-list">${items}</ul>
    </section>`;
}

/* ============================ period mini-charts ============================ */

function periodSeriesList(p) {
  if (p.series && p.series.length) return p.series;
  const pts = p.points || [];
  const mean = pts.length
    ? pts.reduce((a, b) => a + b.value, 0) / pts.length : 0;
  return [{ label: t("annualValue"), points: pts, trend: p.trend, mean }];
}

function periodMiniHtml(card) {
  const periods = card.periods || [];
  return `<div class="mini-grid">${periods
    .map((p, i) => {
      const list = periodSeriesList(p);
      const means = list
        .map((s) => `${escapeHtml(s.label)}: ${fmt(s.mean)} ${escapeHtml(card.unit)}`)
        .join("; ");
      return `
      <div class="mini-chart">
        <div class="mini-head"><span class="mini-title">${escapeHtml(p.label)}</span></div>
        <div class="chart-box"><canvas id="cv-${card.idx}-${i}"></canvas></div>
        <div class="mini-caption">${escapeHtml(t("meanLabel"))} ${means}</div>
      </div>`;
    })
    .join("")}</div>`;
}

function drawPeriodMiniCharts(card) {
  if (typeof Chart === "undefined") return;
  const periods = card.periods || [];
  // wspolny zakres Y dla porownywalnosci (wszystkie serie, wszystkie okresy)
  let yMin = Infinity, yMax = -Infinity;
  periods.forEach((p) =>
    periodSeriesList(p).forEach((s) =>
      s.points.forEach((pt) => {
        yMin = Math.min(yMin, pt.value);
        yMax = Math.max(yMax, pt.value);
      })
    )
  );
  const pad = (yMax - yMin) * 0.08 || 1;
  yMin -= pad; yMax += pad;

  periods.forEach((p, i) => {
    const canvas = document.getElementById(`cv-${card.idx}-${i}`);
    if (!canvas) return;
    const list = periodSeriesList(p);
    const yrs = [];
    list.forEach((s) => s.points.forEach((pt) => yrs.push(pt.year)));
    const datasets = [];
    list.forEach((s, j) => {
      datasets.push(lineDataset(s, SERIES_COLORS[j % SERIES_COLORS.length], false));
      if (s.trend && s.trend.points) {
        datasets.push(lineDataset(s.trend, list.length > 1 ? SERIES_COLORS[j % SERIES_COLORS.length] : TREND_GREY, true,
          list.length > 1 ? `${t("trend")} (${s.label})` : t("trend")));
      }
    });
    charts.push(
      new Chart(canvas.getContext("2d"), {
        type: "line",
        data: { datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "nearest", intersect: false },
          scales: {
            x: yearTickOpts(yrs.length ? yrs : [0, 1]),
            y: {
              ...yTickOpts(yMin, yMax),
              min: yMin, max: yMax,
              title: card.unit ? { display: true, text: card.unit, color: AXIS.tick, font: { size: 12 } } : undefined,
            },
          },
          plugins: {
            legend: legendOpts(list.length > 1 || datasets.length > list.length, 11),
            tooltip: chartTooltip(card.unit || ""),
          },
        },
      })
    );
  });
}

/* ============================ wykres slupkowy ============================ */

function drawBars(card) {
  const canvas = document.getElementById(`cv-${card.idx}`);
  if (!canvas || typeof Chart === "undefined") return;
  const values = card.values || [];
  let vMin = Math.min(...values.map((v) => v.value));
  let vMax = Math.max(...values.map((v) => v.value));
  // slupki porownania miejsc zaczynaja sie od zera (dlugosc = wartosc)
  if (card.zero_based) { vMin = Math.min(0, vMin); vMax = Math.max(0, vMax); }
  const pad = card.zero_based ? (vMax - vMin) * 0.06 : (vMax - vMin) * 0.1 || 0.5;
  const lo = card.zero_based && vMin === 0 ? 0 : vMin - pad;
  const hi = card.zero_based && vMax === 0 ? 0 : vMax + pad;
  const horizontal = card.region_bars && values.length > 5;
  const colors = card.region_bars
    ? values.map((_, i) => SERIES_COLORS[i % SERIES_COLORS.length])
    : "rgba(29,78,137,0.78)";
  const valueAxis = {
    ...yTickOpts(lo, hi),
    suggestedMin: lo, suggestedMax: hi,
    ...(card.zero_based && vMin === 0 ? { min: 0 } : {}),
    title: card.unit ? { display: true, text: card.unit, color: AXIS.tick, font: { size: 12 } } : undefined,
  };
  const catAxis = { grid: { display: false }, ticks: { color: AXIS.tick, font: { size: 12 }, autoSkip: false } };
  const box = canvas.parentElement;
  if (horizontal && box) box.style.height = `${Math.max(240, values.length * 34 + 60)}px`;
  charts.push(
    new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: values.map((v) => v.label),
        datasets: [
          {
            label: card.region_bars ? (card.value_label || card.unit) : t("barMean", { unit: card.unit }),
            data: values.map((v) => v.value),
            backgroundColor: colors,
            borderColor: card.region_bars ? colors : SERIES_COLORS[0],
            borderWidth: card.region_bars ? 0 : 1.5,
            borderRadius: 4,
            maxBarThickness: 64,
          },
        ],
      },
      options: {
        indexAxis: horizontal ? "y" : "x",
        responsive: true,
        maintainAspectRatio: false,
        scales: horizontal ? { y: catAxis, x: valueAxis } : { x: catAxis, y: valueAxis },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#17212B",
            callbacks: { label: (item) => `${nf().format(horizontal ? item.parsed.x : item.parsed.y)} ${card.unit}` },
          },
        },
      },
    })
  );
}

/* ============================ heatmapa v3 (heatmap.js) ============================ */

const heatmaps = [];

function heatmapHtml(card) {
  return HFHeatmap.html(card, t, escapeHtml);
}

function drawHeatmap(card) {
  const h = HFHeatmap.draw(card, { t, nf, fmtN });
  if (h) heatmaps.push(h);
}

/* ============================ helpery ============================ */

function show(node) { node.classList.remove("hidden"); }
function hide(node) { node.classList.add("hidden"); }

// format liczb wg jezyka strony (przecinek dziesietny w pl/de/fr...)
const nfCache = new Map();
function nf() {
  if (!nfCache.has(LOCALE)) nfCache.set(LOCALE, new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 2 }));
  return nfCache.get(LOCALE);
}

function fmt(v) {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return nf().format(v);
}

function fmtP(p) {
  if (p === undefined || p === null) return "—";
  if (p < 0.001) return `< ${(0.001).toLocaleString(LOCALE)}`;
  return p.toLocaleString(LOCALE, { maximumFractionDigits: 3 });
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}
function escapeAttr(s) { return escapeHtml(s); }

function shake(node) {
  node.animate(
    [{ transform: "translateX(0)" }, { transform: "translateX(-6px)" },
     { transform: "translateX(6px)" }, { transform: "translateX(0)" }],
    { duration: 250, iterations: 1 }
  );
}

/* ============================ link do tezy: ?q=... ============================ */
(function autoRunFromUrl() {
  const q = new URLSearchParams(window.location.search).get("q");
  if (!q) return;
  el.thesisInput.value = q.slice(0, 600);
  el.charCount.textContent = `${el.thesisInput.value.length} / 600`;
  analyze();
})();

/* ============================ pasy ocieplenia (dane NASA GISTEMP) ============================ */
// paleta pasow Eda Hawkinsa (ColorBrewer RdBu, 8 odcieni chlodnych + 8 cieplych)
const STRIPE_COLORS = ["#08306b", "#08519c", "#2171b5", "#4292c6", "#6baed6", "#9ecae1", "#c6dbef", "#deebf7",
  "#fee0d2", "#fcbba1", "#fc9272", "#fb6a4a", "#ef3b2c", "#cb181d", "#a50f15", "#67000d"];

let stripesData = null;   // {years, values} z /api/stripes (po zmianie jezyka bez ponownego pobierania)

async function drawStripes() {
  const band = document.getElementById("stripesBand");
  const tip = document.getElementById("stripesTip");
  if (!band) return;
  try {
    if (!stripesData) {
      const resp = await fetch(`${API_BASE}/api/stripes`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const d = await resp.json();
      if (!d.values || !d.values.length) throw new Error("no data");
      stripesData = { years: d.years, values: d.values };
    }
    const { values: vals, years } = stripesData;
    // skala symetryczna wokol sredniej calego okresu (jak w oryginale Hawkinsa)
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    const lim = Math.max(...vals.map((v) => Math.abs(v - mean))) || 1;
    band.innerHTML = vals.map((v, i) => {
      const k = Math.max(0, Math.min(STRIPE_COLORS.length - 1,
        Math.floor((v - mean + lim) / (2 * lim) * STRIPE_COLORS.length)));
      return `<span style="background:${STRIPE_COLORS[k]}" data-i="${i}"></span>`;
    }).join("");
    if (!band.dataset.ready) {
      band.dataset.ready = "1";
      band.classList.add("reveal");
      band.tabIndex = 0;
      band.setAttribute("role", "img");
      // podpowiedz natychmiast pod kursorem (zamiast atrybutu title z opoznieniem)
      let cur = -1;
      const showAt = (i) => {
        const { years: ys, values: vs } = stripesData;
        cur = Math.max(0, Math.min(ys.length - 1, i));
        tip.textContent = t("stripeTip", { year: ys[cur], v: signed(vs[cur], "°C") });
        tip.hidden = false;
        const r = band.getBoundingClientRect();
        const x = ((cur + 0.5) / ys.length) * r.width;
        const w = tip.offsetWidth;
        tip.style.left = `${Math.round(Math.max(4, Math.min(r.width - w - 4, x - w / 2)))}px`;
        band.querySelectorAll(".on").forEach((n) => n.classList.remove("on"));
        const sp = band.children[cur];
        if (sp) sp.classList.add("on");
      };
      const hideTip = () => {
        tip.hidden = true;
        band.querySelectorAll(".on").forEach((n) => n.classList.remove("on"));
      };
      band.addEventListener("pointermove", (ev) => {
        const r = band.getBoundingClientRect();
        showAt(Math.floor(((ev.clientX - r.left) / r.width) * stripesData.years.length));
      });
      band.addEventListener("pointerdown", (ev) => {
        const r = band.getBoundingClientRect();
        showAt(Math.floor(((ev.clientX - r.left) / r.width) * stripesData.years.length));
      });
      band.addEventListener("pointerleave", () => { if (document.activeElement !== band) hideTip(); });
      band.addEventListener("focus", () => showAt(cur < 0 ? stripesData.years.length - 1 : cur));
      band.addEventListener("blur", hideTip);
      band.addEventListener("keydown", (ev) => {
        const moves = { ArrowLeft: -1, ArrowRight: 1, Home: -1e6, End: 1e6 };
        if (ev.key in moves) { ev.preventDefault(); showAt(cur + moves[ev.key]); }
      });
    }
    band.setAttribute("aria-label", t("stripesWhat"));
    document.getElementById("stripesFrom").textContent = years[0];
    document.getElementById("stripesTo").textContent = years[years.length - 1];
  } catch (err) {
    document.getElementById("stripes").classList.add("hidden");
  }
}

if (typeof Chart !== "undefined") {
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = AXIS.tick;
}
drawStripes();
