/* Hermes Finder — mapa cieplna v3
   Leaflet (podklad: mapa CARTO albo satelita Esri) + warstwa danych na canvasie:
   - siatka NASA POWER interpolowana dwuliniowo, rysowana w odwzorowaniu Mercatora
     (wiersze siatki trafiaja dokladnie w swoje szerokosci, takze dla Europy),
   - plynny suwak: wartosci miedzy latami sa interpolowane (rok 2014.4 = 60% 2014
     + 40% 2015), animacja "Odtworz" z wyborem tempa,
   - tryby: wartosci / odchylenie od sredniej okresu / zmiana od pierwszego roku,
   - maska "tylko wybrany obszar" po granicach krajow (world-atlas, Natural Earth),
     obrysy wybranych krajow, granice panstw na wierzchu,
   - podpowiedz z wartoscia w punkcie kursora, wykres sredniej obszarowej pod suwakiem.
   Bez Leaflet (np. blad sieci) mapa rysuje sie na zwyklym canvasie bez podkladu. */
"use strict";

(function () {
  const ATLAS_URL = "vendor/countries-50m.json";
  const BASES = {
    map: {
      url: "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
      labels: "https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png",
      attr: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener">CARTO</a>',
    },
    satellite: {
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      labels: "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
      attr: "Esri World Imagery (Esri, Maxar, Earthstar Geographics)",
    },
  };
  // skale kolorow (od niskich do wysokich wartosci)
  const SCALES = {
    thermal: ["#313695", "#4575b4", "#74add1", "#abd9e9", "#e0f3f8", "#ffffbf", "#fee090", "#fdae61", "#f46d43", "#d73027", "#a50026"],
    diverging: ["#2166ac", "#4393c3", "#92c5de", "#d1e5f0", "#f7f7f7", "#fddbc7", "#f4a582", "#d6604d", "#b2182b"],
    wet: ["#fff7d6", "#edf8b1", "#c7e9b4", "#7fcdbb", "#41b6c4", "#1d91c0", "#225ea8", "#253494", "#081d58"],
    viridis: ["#440154", "#482878", "#3e4989", "#31688e", "#26828e", "#1f9e89", "#35b779", "#6ece58", "#b5de2b", "#fde725"],
  };
  const MAX_PIXELS = 360000;

  let atlasPromise = null;
  function loadAtlas() {
    if (!atlasPromise) {
      atlasPromise = fetch(ATLAS_URL)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("atlas " + r.status))))
        .then((topo) => (typeof topojson !== "undefined"
          ? { countries: topojson.feature(topo, topo.objects.countries).features,
              borders: topojson.mesh(topo, topo.objects.countries, (a, b) => a !== b) }
          : null))
        .catch(() => null);
    }
    return atlasPromise;
  }

  /* ---------------------------------------------------------- kolory */
  function hexToRgb(h) {
    const n = parseInt(h.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function makeLut(stops) {
    const rgb = stops.map(hexToRgb);
    const lut = new Uint8ClampedArray(256 * 3);
    for (let i = 0; i < 256; i++) {
      const x = (i / 255) * (rgb.length - 1);
      const k = Math.min(rgb.length - 2, Math.floor(x));
      const u = x - k;
      for (let c = 0; c < 3; c++) lut[i * 3 + c] = Math.round(rgb[k][c] + (rgb[k + 1][c] - rgb[k][c]) * u);
    }
    return lut;
  }
  function scaleFor(unit, mode) {
    if (mode !== "values") return "diverging";
    const u = String(unit || "");
    if (u.includes("°C")) return "thermal";
    if (/mm/.test(u)) return "wet";
    return "viridis";
  }
  function gradientCss(name) {
    return `linear-gradient(90deg, ${SCALES[name].join(",")})`;
  }

  /* ---------------------------------------------------------- dane */
  function prepare(card) {
    const g = card.grid;
    const lats = g.lats, lons = g.lons, years = g.years;
    const nLat = lats.length, nLon = lons.length, n = nLat * nLon;
    const frames = (g.frames || []).map((f) => {
      const a = new Float32Array(n);
      for (let i = 0; i < n; i++) a[i] = f[i] === null || f[i] === undefined ? NaN : f[i];
      return a;
    });
    // srednia kazdej komorki z calego okresu (tryb odchylenia)
    const mean = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      let s = 0, c = 0;
      for (const f of frames) if (!Number.isNaN(f[i])) { s += f[i]; c++; }
      mean[i] = c ? s / c : NaN;
    }
    const wraps = card.bbox && card.bbox[3] < card.bbox[2];
    const lonsU = wraps ? lons.map((x) => (x < lons[0] ? x + 360 : x)) : lons.slice();
    const step = g.step || [Math.abs(lats[0] - lats[1] || 0.5), Math.abs(lonsU[1] - lonsU[0] || 0.625)];
    const latTop = lats[0] + step[0] / 2, latBot = lats[nLat - 1] - step[0] / 2;
    const lonL = lonsU[0] - step[1] / 2, lonR = lonsU[nLon - 1] + step[1] / 2;
    return { lats, lons: lonsU, years, frames, mean, nLat, nLon, step, latTop, latBot, lonL, lonR, wraps };
  }

  function valueRange(D, mode) {
    const vals = [];
    const first = D.frames[0];
    for (const f of D.frames) {
      for (let i = 0; i < f.length; i += Math.max(1, Math.floor(f.length / 4000))) {
        const v = f[i];
        if (Number.isNaN(v)) continue;
        if (mode === "values") vals.push(v);
        else if (mode === "anomaly") { if (!Number.isNaN(D.mean[i])) vals.push(v - D.mean[i]); }
        else if (!Number.isNaN(first[i])) vals.push(v - first[i]);
      }
    }
    if (!vals.length) return [0, 1];
    vals.sort((a, b) => a - b);
    const q = (p) => vals[Math.min(vals.length - 1, Math.max(0, Math.round(p * (vals.length - 1))))];
    let lo = q(0.02), hi = q(0.98);
    if (mode !== "values") { const m = Math.max(Math.abs(lo), Math.abs(hi)) || 1; lo = -m; hi = m; }
    if (hi - lo < 1e-9) { lo -= 0.5; hi += 0.5; }
    return [lo, hi];
  }

  /* ---------------------------------------------------------- odwzorowanie */
  const mercY = (lat) => {
    const s = Math.sin((Math.max(-85, Math.min(85, lat)) * Math.PI) / 180);
    return Math.log((1 + s) / (1 - s)) / 2;
  };
  const invMercY = (y) => (Math.atan(Math.sinh(y)) * 180) / Math.PI;

  /** Siatka probkowania: dla kazdego piksela indeksy i wagi 4 sasiednich komorek. */
  function sampler(D) {
    const yTop = mercY(Math.min(85, D.latTop)), yBot = mercY(Math.max(-85, D.latBot));
    const lonSpan = D.lonR - D.lonL;
    const aspect = (lonSpan * Math.PI / 180) / Math.max(1e-6, yTop - yBot);
    let W = Math.round(Math.sqrt(MAX_PIXELS * aspect));
    W = Math.max(64, Math.min(1400, W, D.nLon * 24));
    let H = Math.max(64, Math.min(1400, Math.round(W / aspect)));
    const N = W * H;
    const i0 = new Int32Array(N), wy = new Float32Array(N), j0 = new Int32Array(N), wx = new Float32Array(N);
    const latStep = D.nLat > 1 ? (D.lats[0] - D.lats[D.nLat - 1]) / (D.nLat - 1) : 1;
    const lonStep = D.nLon > 1 ? (D.lons[D.nLon - 1] - D.lons[0]) / (D.nLon - 1) : 1;
    const rowLat = new Float32Array(H);
    for (let y = 0; y < H; y++) rowLat[y] = invMercY(yTop - ((y + 0.5) / H) * (yTop - yBot));
    for (let y = 0; y < H; y++) {
      const fi = Math.max(0, Math.min(D.nLat - 1, (D.lats[0] - rowLat[y]) / latStep));
      const ii = Math.min(D.nLat - 2, Math.floor(fi));
      for (let x = 0; x < W; x++) {
        const lon = D.lonL + ((x + 0.5) / W) * lonSpan;
        const fj = Math.max(0, Math.min(D.nLon - 1, (lon - D.lons[0]) / lonStep));
        const jj = Math.min(D.nLon - 2, Math.floor(fj));
        const k = y * W + x;
        i0[k] = Math.max(0, ii); wy[k] = D.nLat > 1 ? fi - Math.max(0, ii) : 0;
        j0[k] = Math.max(0, jj); wx[k] = D.nLon > 1 ? fj - Math.max(0, jj) : 0;
      }
    }
    return { W, H, i0, j0, wx, wy, yTop, yBot };
  }

  /** Wartosc w ulamkowym roku t (0..years-1) w komorce idx; NaN gdy brak. */
  function cellValue(D, t, idx, mode) {
    const a = Math.floor(t), b = Math.min(D.frames.length - 1, a + 1), u = t - a;
    const va = D.frames[a][idx], vb = D.frames[b][idx];
    let v;
    if (Number.isNaN(va)) v = vb; else if (Number.isNaN(vb)) v = va; else v = va + (vb - va) * u;
    if (Number.isNaN(v)) return NaN;
    if (mode === "anomaly") return v - D.mean[idx];
    if (mode === "change") return v - D.frames[0][idx];
    return v;
  }

  function frameField(D, t, mode) {
    const n = D.nLat * D.nLon;
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) out[i] = cellValue(D, t, i, mode);
    return out;
  }

  function bilinear(field, D, i, j, wy, wx) {
    const n = D.nLon;
    const i1 = Math.min(D.nLat - 1, i + 1), j1 = Math.min(n - 1, j + 1);
    const a = field[i * n + j], b = field[i * n + j1], c = field[i1 * n + j], d = field[i1 * n + j1];
    const w = [(1 - wy) * (1 - wx), (1 - wy) * wx, wy * (1 - wx), wy * wx];
    const v = [a, b, c, d];
    let s = 0, ws = 0;
    for (let k = 0; k < 4; k++) if (!Number.isNaN(v[k])) { s += v[k] * w[k]; ws += w[k]; }
    return ws > 0.25 ? s / ws : NaN;
  }

  function render(ctx, img, S, D, field, range, lut, mask) {
    const px = img.data;
    const lo = range[0], span = range[1] - range[0];
    for (let k = 0, N = S.W * S.H; k < N; k++) {
      const v = bilinear(field, D, S.i0[k], S.j0[k], S.wy[k], S.wx[k]);
      const o = k * 4;
      if (Number.isNaN(v)) { px[o + 3] = 0; continue; }
      const ci = Math.max(0, Math.min(255, Math.round(((v - lo) / span) * 255))) * 3;
      px[o] = lut[ci]; px[o + 1] = lut[ci + 1]; px[o + 2] = lut[ci + 2];
      px[o + 3] = mask ? mask[k] : 255;
    }
    ctx.putImageData(img, 0, 0);
  }

  /** Maska (alfa 0..255) z wielokatow krajow w tym samym ukladzie pikseli co dane. */
  function buildMask(S, D, features) {
    const c = document.createElement("canvas");
    c.width = S.W; c.height = S.H;
    const g = c.getContext("2d");
    const lonSpan = D.lonR - D.lonL;
    const X = (lon) => {
      let l = lon;
      if (D.wraps && l < D.lonL - 180) l += 360;
      return ((l - D.lonL) / lonSpan) * S.W;
    };
    const Y = (lat) => ((S.yTop - mercY(lat)) / (S.yTop - S.yBot)) * S.H;
    g.fillStyle = "#000";
    g.beginPath();
    for (const f of features) {
      const geom = f.geometry;
      if (!geom) continue;
      const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.type === "MultiPolygon" ? geom.coordinates : [];
      for (const poly of polys) for (const ring of poly) {
        ring.forEach(([lon, lat], i) => (i ? g.lineTo(X(lon), Y(lat)) : g.moveTo(X(lon), Y(lat))));
        g.closePath();
      }
    }
    g.fill("evenodd");
    const a = g.getImageData(0, 0, S.W, S.H).data;
    const m = new Uint8ClampedArray(S.W * S.H);
    let any = 0;
    for (let k = 0; k < m.length; k++) { m[k] = a[k * 4 + 3]; any |= m[k]; }
    return any ? m : null;
  }

  /* ---------------------------------------------------------- HTML */
  function html(card, t, esc) {
    const years = (card.grid && card.grid.years) || [];
    const last = Math.max(0, years.length - 1);
    const id = card.idx;
    const hasMask = (card.regions || []).some((r) => r.iso_n && r.iso_n.length);
    return `
    <div class="hm" id="hm-${id}">
      <div class="hm-toolbar">
        <div class="hm-seg" role="group" aria-label="${esc(t("heatValues"))}">
          <button type="button" data-mode="values" class="on">${esc(t("heatValues"))}</button>
          <button type="button" data-mode="anomaly">${esc(t("heatAnomaly"))}</button>
          <button type="button" data-mode="change">${esc(t("heatChange", { y: years[0] ?? "" }))}</button>
        </div>
        <div class="hm-seg" role="group" aria-label="${esc(t("heatBaseMap"))}">
          <button type="button" data-base="map" class="on">${esc(t("heatBaseMap"))}</button>
          <button type="button" data-base="satellite">${esc(t("heatSatellite"))}</button>
        </div>
        ${hasMask ? `<label class="hm-check"><input type="checkbox" data-mask checked /> ${esc(t("heatMask"))}</label>` : ""}
        <button type="button" class="hm-icon" data-expand aria-pressed="false">${esc(t("heatExpand"))}</button>
      </div>
      <div class="hm-map" id="hmmap-${id}" role="img" aria-label="${esc(card.title || "")}"></div>
      <div class="hm-legend">
        <span class="hm-lmin" id="hmlo-${id}"></span>
        <div class="hm-lbar" id="hmbar-${id}"><div class="hm-lmark" id="hmmark-${id}" hidden></div></div>
        <span class="hm-lmax" id="hmhi-${id}"></span>
      </div>
      <div class="hm-player">
        <button type="button" class="hm-play" id="hmplay-${id}" aria-label="${esc(t("heatPlay"))}" title="${esc(t("heatPlay"))}">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path class="i-play" d="M4 2.5v11l9-5.5z"/><path class="i-pause" d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z"/></svg>
        </button>
        <div class="hm-track">
          <canvas class="hm-spark" id="hmspark-${id}" aria-hidden="true"></canvas>
          <input id="hmsl-${id}" class="hm-slider" type="range" min="0" max="${last}" step="0.01" value="${last}"
                 aria-label="${esc(t("tipYear", { y: "" }))}" aria-valuetext="${years[last] ?? ""}" />
          <div class="hm-ticks"><span>${years[0] ?? ""}</span><span>${years[last] ?? ""}</span></div>
        </div>
        <output class="hm-year" id="hmyr-${id}">${years[last] ?? "—"}</output>
        <label class="hm-speed">${esc(t("heatSpeed"))}
          <select id="hmspd-${id}"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select>
        </label>
      </div>
      <p class="hm-tip" id="hmtip-${id}" aria-live="polite"></p>
      <p class="map-note">${esc(t("mapNote"))}</p>
    </div>`;
  }

  /* ---------------------------------------------------------- rysowanie */
  function draw(card, ctx) {
    const { t, nf, fmtN } = ctx;
    const root = document.getElementById(`hm-${card.idx}`);
    const mapEl = document.getElementById(`hmmap-${card.idx}`);
    if (!root || !mapEl || !card.grid || !(card.grid.years || []).length) return null;
    const D = prepare(card);
    const S = sampler(D);
    const canvas = document.createElement("canvas");
    canvas.width = S.W; canvas.height = S.H;
    canvas.className = "hm-data";
    const c2d = canvas.getContext("2d");
    const img = c2d.createImageData(S.W, S.H);
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const state = { t: D.years.length - 1, mode: "values", playing: false, speed: 1, mask: null, useMask: true };
    let range = valueRange(D, state.mode);
    let lut = makeLut(SCALES[scaleFor(card.unit, state.mode)]);
    let field = frameField(D, state.t, state.mode);

    const slider = document.getElementById(`hmsl-${card.idx}`);
    const yearOut = document.getElementById(`hmyr-${card.idx}`);
    const tip = document.getElementById(`hmtip-${card.idx}`);
    const playBtn = document.getElementById(`hmplay-${card.idx}`);
    const speedSel = document.getElementById(`hmspd-${card.idx}`);
    const lo = document.getElementById(`hmlo-${card.idx}`), hi = document.getElementById(`hmhi-${card.idx}`);
    const bar = document.getElementById(`hmbar-${card.idx}`), mark = document.getElementById(`hmmark-${card.idx}`);
    const unitTxt = (v) => {
      const sign = state.mode !== "values" && v > 0 ? "+" : "";
      return `${sign}${fmtN(v, Math.abs(range[1] - range[0]) >= 20 ? 0 : 1)} ${card.unit || ""}`.trim();
    };

    const legend = () => {
      bar.style.background = gradientCss(scaleFor(card.unit, state.mode));
      lo.textContent = unitTxt(range[0]);
      hi.textContent = unitTxt(range[1]);
    };
    const yearLabel = () => {
      const a = Math.floor(state.t), u = state.t - a;
      const y = D.years[Math.min(D.years.length - 1, Math.round(state.t))];
      yearOut.textContent = u > 0.04 && u < 0.96 ? `${D.years[a]}–${D.years[a + 1]}` : String(y);
      slider.setAttribute("aria-valuetext", String(y));
    };

    const paint = () => {
      field = frameField(D, state.t, state.mode);
      render(c2d, img, S, D, field, range, lut, state.useMask ? state.mask : null);
      yearLabel();
      spark();
    };

    /* ---- mapa Leaflet albo zwykly canvas ---- */
    let map = null, overlay = null, base = null, labels = null, bordersLayer = null, outlineLayer = null;
    const bounds = [[D.latBot, D.lonL], [D.latTop, D.lonR]];
    if (typeof L !== "undefined") {
      map = L.map(mapEl, { zoomSnap: 0.25, zoomDelta: 0.5, scrollWheelZoom: false, worldCopyJump: false,
                           attributionControl: true, minZoom: 1, maxZoom: 11 });
      map.createPane("labels"); map.getPane("labels").style.zIndex = 650; map.getPane("labels").style.pointerEvents = "none";
      map.createPane("borders"); map.getPane("borders").style.zIndex = 640; map.getPane("borders").style.pointerEvents = "none";
      const setBase = (name) => {
        if (base) map.removeLayer(base);
        if (labels) map.removeLayer(labels);
        const b = BASES[name];
        base = L.tileLayer(b.url, { attribution: b.attr, subdomains: "abcd", maxZoom: 19, crossOrigin: true }).addTo(map);
        labels = L.tileLayer(b.labels, { pane: "labels", subdomains: "abcd", maxZoom: 19, opacity: name === "map" ? 0.9 : 1 }).addTo(map);
        root.classList.toggle("hm-sat", name === "satellite");
      };
      setBase("map");
      const Overlay = L.ImageOverlay.extend({
        _initImage() {
          const el = (this._image = this._url);
          L.DomUtil.addClass(el, "leaflet-image-layer");
          if (this._zoomAnimated) L.DomUtil.addClass(el, "leaflet-zoom-animated");
          el.onselectstart = L.Util.falseFn;
          el.onmousemove = L.Util.falseFn;
        },
      });
      overlay = new Overlay(canvas, bounds, { opacity: 0.78, interactive: false }).addTo(map);
      map.fitBounds(bounds, { padding: [8, 8] });
      root.querySelectorAll("[data-base]").forEach((btn) => btn.addEventListener("click", () => {
        root.querySelectorAll("[data-base]").forEach((b) => b.classList.toggle("on", b === btn));
        setBase(btn.dataset.base);
      }));
      // kolko myszy dopiero po kliknieciu w mape (nie przejmuje przewijania strony)
      map.on("click focus", () => map.scrollWheelZoom.enable());
      map.on("mouseout blur", () => map.scrollWheelZoom.disable());
      map.on("mousemove", (ev) => showTip(ev.latlng.lat, ev.latlng.lng));
      map.on("mouseout", () => { tip.textContent = ""; mark.hidden = true; });
    } else {
      root.querySelectorAll("[data-base]").forEach((b) => (b.disabled = true));
      canvas.classList.add("hm-flat");
      mapEl.appendChild(canvas);
      canvas.addEventListener("mousemove", (ev) => {
        const r = canvas.getBoundingClientRect();
        const lon = D.lonL + ((ev.clientX - r.left) / r.width) * (D.lonR - D.lonL);
        const lat = invMercY(S.yTop - ((ev.clientY - r.top) / r.height) * (S.yTop - S.yBot));
        showTip(lat, lon);
      });
    }

    function sampleAt(lat, lon) {
      let l = lon;
      if (D.wraps && l < D.lonL) l += 360;
      if (lat > D.latTop || lat < D.latBot || l < D.lonL || l > D.lonR) return NaN;
      const latStep = D.nLat > 1 ? (D.lats[0] - D.lats[D.nLat - 1]) / (D.nLat - 1) : 1;
      const lonStep = D.nLon > 1 ? (D.lons[D.nLon - 1] - D.lons[0]) / (D.nLon - 1) : 1;
      const fi = Math.max(0, Math.min(D.nLat - 1, (D.lats[0] - lat) / latStep));
      const fj = Math.max(0, Math.min(D.nLon - 1, (l - D.lons[0]) / lonStep));
      const i = Math.max(0, Math.min(D.nLat - 2, Math.floor(fi))), j = Math.max(0, Math.min(D.nLon - 2, Math.floor(fj)));
      return bilinear(field, D, i, j, D.nLat > 1 ? fi - i : 0, D.nLon > 1 ? fj - j : 0);
    }
    function showTip(lat, lon) {
      const v = sampleAt(lat, lon);
      const where = `${Math.abs(lat).toFixed(1)}°${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(1)}°${lon >= 0 ? "E" : "W"}`;
      const y = D.years[Math.round(state.t)];
      if (Number.isNaN(v)) { tip.textContent = `${where} — ${t("noDataCell")}`; mark.hidden = true; return; }
      tip.textContent = `${where} · ${t("tipYear", { y })}: ${unitTxt(v)}`;
      mark.hidden = false;
      mark.style.left = `${Math.max(0, Math.min(100, ((v - range[0]) / (range[1] - range[0])) * 100))}%`;
    }

    /* ---- granice krajow i maska wybranego obszaru ---- */
    const isoWanted = new Set((card.regions || []).flatMap((r) => r.iso_n || []));
    loadAtlas().then((atlas) => {
      if (!atlas) return;
      // Kosowo nie ma kodu ISO w Natural Earth - dolaczamy je razem z Serbia (Europa)
      const chosen = atlas.countries.filter((f) => isoWanted.has(String(f.id)) ||
        (isoWanted.has("688") && f.properties && f.properties.name === "Kosovo"));
      if (chosen.length) {
        state.mask = buildMask(S, D, chosen);
        if (state.mask) paint();
      } else {
        const m = root.querySelector("[data-mask]");
        if (m) m.closest("label").hidden = true;
      }
      if (map) {
        bordersLayer = L.geoJSON(atlas.borders, { pane: "borders", interactive: false,
          style: { color: "#ffffff", weight: 0.8, opacity: 0.85 } }).addTo(map);
        if (chosen.length) {
          outlineLayer = L.geoJSON({ type: "FeatureCollection", features: chosen }, { pane: "borders", interactive: false,
            style: { color: "#17212b", weight: 1.6, opacity: 0.9, fill: false } }).addTo(map);
        }
      }
    });

    /* ---- sterowanie ---- */
    root.querySelectorAll("[data-mode]").forEach((btn) => btn.addEventListener("click", () => {
      root.querySelectorAll("[data-mode]").forEach((b) => b.classList.toggle("on", b === btn));
      state.mode = btn.dataset.mode;
      range = valueRange(D, state.mode);
      lut = makeLut(SCALES[scaleFor(card.unit, state.mode)]);
      legend();
      paint();
    }));
    const maskBox = root.querySelector("[data-mask]");
    if (maskBox) maskBox.addEventListener("change", () => { state.useMask = maskBox.checked; paint(); });
    const expand = root.querySelector("[data-expand]");
    expand.addEventListener("click", () => {
      const on = !root.classList.contains("hm-big");
      root.classList.toggle("hm-big", on);
      expand.setAttribute("aria-pressed", String(on));
      expand.textContent = on ? t("heatShrink") : t("heatExpand");
      if (map) setTimeout(() => { map.invalidateSize(); map.fitBounds(bounds, { padding: [8, 8] }); }, 60);
    });

    slider.addEventListener("input", () => {
      stop();
      state.t = parseFloat(slider.value);
      paint();
    });
    // po puszczeniu suwaka - przyciagniecie do pelnego roku (plynny powrot)
    slider.addEventListener("change", () => {
      const target = Math.round(state.t);
      if (reduce || Math.abs(target - state.t) < 0.01) { state.t = target; slider.value = target; paint(); return; }
      const from = state.t, t0 = performance.now();
      const step = (now) => {
        const u = Math.min(1, (now - t0) / 180);
        state.t = from + (target - from) * (1 - Math.pow(1 - u, 3));
        slider.value = state.t;
        paint();
        if (u < 1 && !state.playing) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
    speedSel.addEventListener("change", () => { state.speed = parseFloat(speedSel.value) || 1; });

    let raf = 0, lastTs = 0;
    function tick(ts) {
      if (!state.playing) return;
      const dt = lastTs ? (ts - lastTs) / 1000 : 0;
      lastTs = ts;
      // 1x = 1.5 roku na sekunde; przy ograniczonym ruchu skok co pelny rok
      if (reduce) state.t = Math.floor(state.t) + (dt > 0 ? 1 : 0);
      else state.t += dt * 1.5 * state.speed;
      if (state.t > D.years.length - 1) state.t = 0;
      slider.value = state.t;
      paint();
      raf = reduce ? setTimeout(() => requestAnimationFrame(tick), 700 / state.speed) : requestAnimationFrame(tick);
    }
    function start() {
      if (D.years.length < 2) return;
      if (state.t >= D.years.length - 1.001) state.t = 0;
      state.playing = true; lastTs = 0;
      playBtn.classList.add("playing");
      playBtn.setAttribute("aria-label", t("heatPause")); playBtn.title = t("heatPause");
      raf = requestAnimationFrame(tick);
    }
    function stop() {
      if (!state.playing) return;
      state.playing = false;
      cancelAnimationFrame(raf); clearTimeout(raf);
      playBtn.classList.remove("playing");
      playBtn.setAttribute("aria-label", t("heatPlay")); playBtn.title = t("heatPlay");
    }
    playBtn.addEventListener("click", () => (state.playing ? stop() : start()));

    /* ---- wykres sredniej obszarowej pod suwakiem ---- */
    const sparkEl = document.getElementById(`hmspark-${card.idx}`);
    const annual = new Map((card.annual || []).map((r) => [r.year, r.value]));
    function spark() {
      if (!sparkEl || !annual.size) return;
      const w = sparkEl.clientWidth || 300, h = sparkEl.clientHeight || 34, dpr = window.devicePixelRatio || 1;
      if (sparkEl.width !== Math.round(w * dpr)) { sparkEl.width = Math.round(w * dpr); sparkEl.height = Math.round(h * dpr); }
      const g = sparkEl.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const ys = D.years.map((y) => annual.get(y)).filter((v) => v !== undefined);
      if (ys.length < 2) return;
      const mn = Math.min(...ys), mx = Math.max(...ys), sp = mx - mn || 1;
      const X = (i) => 8 + (i / Math.max(1, D.years.length - 1)) * (w - 16);
      const Y = (v) => h - 4 - ((v - mn) / sp) * (h - 8);
      g.strokeStyle = "rgba(29,78,137,.75)"; g.lineWidth = 1.5; g.beginPath();
      let started = false;
      D.years.forEach((y, i) => {
        const v = annual.get(y);
        if (v === undefined) return;
        if (!started) { g.moveTo(X(i), Y(v)); started = true; } else g.lineTo(X(i), Y(v));
      });
      g.stroke();
      const a = Math.floor(state.t), b = Math.min(D.years.length - 1, a + 1);
      const va = annual.get(D.years[a]), vb = annual.get(D.years[b]);
      if (va !== undefined && vb !== undefined) {
        const v = va + (vb - va) * (state.t - a);
        g.fillStyle = "#d55e00"; g.beginPath(); g.arc(X(state.t), Y(v), 3.5, 0, Math.PI * 2); g.fill();
      }
    }
    if (sparkEl) sparkEl.title = t("heatAreaMean");

    legend();
    paint();
    // canvas w kontenerze o zmiennej szerokosci (przelaczenie ukladu strony)
    if (map && typeof ResizeObserver !== "undefined") {
      new ResizeObserver(() => { map.invalidateSize(); spark(); }).observe(mapEl);
    }
    return {
      destroy() { stop(); if (map) map.remove(); },
      // dla testow i dostepnosci
      _state: state, _sample: sampleAt,
    };
  }

  window.HFHeatmap = { html, draw, loadAtlas };
})();
