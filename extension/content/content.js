/* Skrypt strony: skanuje artykul, zaznacza tezy, pokazuje skrot wyniku w rogu. */
"use strict";

(function () {
  if (window.__cvLoaded) return;
  window.__cvLoaded = true;

  const api = CV.api;
  const BLOCK_SEL = "p, li, h1, h2, h3, h4, blockquote, figcaption, dd";
  const SKIP_SEL = "nav, header, footer, aside, form, button, select, textarea, pre, code, script, style, noscript, [contenteditable], [aria-hidden='true'], .cv-claim";
  let settings = CV.DEFAULTS;
  let claims = [];          // [{id, text, score}]
  let panel = null;         // <iframe> z panelem
  let zoomed = false;       // powiekszony jeden wykres (ramka rozciagnieta)
  let lastHeight = 160;

  /* ------------------------------------------------ znalezienie tekstu */
  function articleRoot() {
    const cands = [...document.querySelectorAll("article, main, [role='main'], [itemprop='articleBody']")];
    if (!cands.length) return document.body;
    // najwieksza ilosc tekstu w akapitach
    let best = null, bestLen = 0;
    for (const c of cands) {
      const len = [...c.querySelectorAll("p")].reduce((a, p) => a + p.textContent.length, 0);
      if (len > bestLen) { best = c; bestLen = len; }
    }
    return best || document.body;
  }

  function looksLikeArticle(root) {
    if (document.querySelector("article")) return true;
    const ps = [...root.querySelectorAll("p")].filter((p) => p.textContent.trim().length > 80);
    return ps.reduce((a, p) => a + p.textContent.length, 0) > 1200 && ps.length >= 4;
  }

  function textBlocks(root) {
    const out = [];
    for (const el of root.querySelectorAll(BLOCK_SEL)) {
      if (out.length >= 500) break;
      if (el.closest(SKIP_SEL)) continue;
      if (el.querySelector(BLOCK_SEL)) continue;          // tylko bloki "liscie"
      const text = el.textContent;
      if (!text || text.trim().length < 40) continue;
      if (!el.offsetParent && getComputedStyle(el).position !== "fixed") continue; // niewidoczne
      out.push({ id: out.length, el, text });
    }
    return out;
  }

  /* ------------------------------------------------ zaznaczanie */
  function textNodesWithOffsets(el) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let pos = 0, n;
    while ((n = walker.nextNode())) {
      nodes.push({ node: n, start: pos, end: pos + n.data.length });
      pos += n.data.length;
    }
    return nodes;
  }

  /** Owija fragment [start, end) bloku w <mark class="cv-claim"> (takze ponad wieloma wezlami). */
  function wrapRange(el, start, end, claimId) {
    const marks = [];
    for (const { node, start: ns, end: ne } of textNodesWithOffsets(el)) {
      if (ne <= start || ns >= end) continue;
      if (node.parentElement && node.parentElement.closest(".cv-claim")) continue;
      const a = Math.max(start, ns) - ns;
      const b = Math.min(end, ne) - ns;
      if (b - a <= 0 || !node.data.slice(a, b).trim()) continue;
      const range = document.createRange();
      range.setStart(node, a);
      range.setEnd(node, b);
      const mark = document.createElement("mark");
      mark.className = `cv-claim cv-${settings.highlightStyle}`;
      mark.dataset.cvClaim = String(claimId);
      try {
        range.surroundContents(mark);
        marks.push(mark);
      } catch (e) { /* fragment przecina element - pomijamy */ }
    }
    if (marks.length) marks[marks.length - 1].classList.add("cv-end");
    if (marks[0]) {
      marks[0].tabIndex = 0;
      marks[0].setAttribute("role", "button");
      marks[0].setAttribute("aria-label", CV.t("markAria"));
    }
    return marks;
  }

  function clearHighlights() {
    for (const m of document.querySelectorAll("mark.cv-claim")) {
      const parent = m.parentNode;
      while (m.firstChild) parent.insertBefore(m.firstChild, m);
      parent.removeChild(m);
      parent.normalize();
    }
    claims = [];
  }

  function scan({ force = false } = {}) {
    clearHighlights();
    const root = articleRoot();
    if (!force && settings.articlesOnly && !looksLikeArticle(root)) {
      report();
      return claims;
    }
    const blocks = textBlocks(root);
    const found = CV.claims.findClaims(blocks.map((b) => ({ id: b.id, text: b.text })), {
      threshold: CV.THRESHOLDS[settings.sensitivity] ?? 6,
      max: Number(settings.maxHighlights) || 6,
    });
    // od konca bloku, zeby wczesniejsze pozycje pozostaly wazne
    found.sort((a, b) => a.blockId - b.blockId || b.start - a.start);
    found.forEach((f, i) => {
      const block = blocks[f.blockId];
      const id = i + 1;
      if (settings.highlightStyle !== "none") wrapRange(block.el, f.start, f.end, id);
      claims.push({ id, text: f.text, score: f.score });
    });
    claims.sort((a, b) => b.score - a.score);
    report();
    return claims;
  }

  function report() {
    try {
      api.runtime.sendMessage({ type: "claims-count", count: claims.length }).catch(() => {});
    } catch (e) { /* kontekst rozszerzenia niewazny */ }
  }

  /* ------------------------------------------------ panel w rogu */
  // Panel to strona rozszerzenia w ramce: CSS i CSP strony jej nie dotycza.
  // Pozycja i wymiary ramki ustawiane przez CSSOM (dozwolone przy kazdym CSP).
  const FRAME_STYLE = {
    position: "fixed", "z-index": "2147483646", width: "min(380px, calc(100vw - 32px))",
    height: "160px", "max-height": "calc(100vh - 32px)", border: "1px solid #c2cbce",
    "border-radius": "8px", background: "#ffffff", "box-shadow": "0 12px 32px rgba(23, 33, 43, 0.22)",
    margin: "0", padding: "0", display: "block", "color-scheme": "light", opacity: "1",
  };
  const POSITION = {
    "bottom-right": { right: "16px", bottom: "16px" },
    "bottom-left": { left: "16px", bottom: "16px" },
    "top-right": { right: "16px", top: "16px" },
  };

  function setStyles(el, styles) {
    for (const [k, v] of Object.entries(styles)) el.style.setProperty(k, v, "important");
  }

  // powiekszony jeden wykres: prawie caly ekran, wysrodkowany, najwyzej 1200 px
  // szerokosci; strona z artykulem zostaje pod spodem bez zmian
  const EXPANDED_STYLE = {
    // iframe nie rozciaga sie miedzy left/right - wymiary trzeba podac wprost
    top: "16px", left: "max(16px, calc((100vw - 1200px) / 2))",
    width: "min(1200px, calc(100vw - 32px))", height: "calc(100vh - 32px)", "max-height": "none",
  };

  function placePanel() {
    for (const k of ["top", "bottom", "left", "right", "width", "height", "max-height"]) panel.style.removeProperty(k);
    if (zoomed) {
      setStyles(panel, { ...FRAME_STYLE, ...EXPANDED_STYLE });
    } else {
      setStyles(panel, { ...FRAME_STYLE, ...(POSITION[settings.panelPosition] || POSITION["bottom-right"]) });
      panel.style.setProperty("height", `${lastHeight}px`, "important");
    }
  }

  function closePanel() {
    if (!panel) return;
    panel.remove();
    panel = null;
    zoomed = false;
    document.querySelectorAll("mark.cv-claim.cv-active").forEach((m) => m.classList.remove("cv-active"));
  }

  /** Kontekst rozszerzenia wazny? (po aktualizacji/przeladowaniu rozszerzenia
      stary skrypt w otwartej karcie traci polaczenie z przegladarka) */
  function extensionAlive() {
    try {
      return Boolean(api.runtime && api.runtime.id && api.runtime.getURL("panel/panel.html"));
    } catch (e) {
      return false;
    }
  }

  function showStaleNotice() {
    const box = document.createElement("div");
    box.setAttribute("role", "status");
    box.textContent = CV.t("staleNotice");
    const st = {
      position: "fixed", right: "16px", bottom: "16px", "z-index": "2147483646", "max-width": "340px",
      padding: "12px 14px", background: "#ffffff", color: "#17212b", border: "1px solid #c2cbce",
      "border-radius": "8px", "box-shadow": "0 12px 32px rgba(23,33,43,.22)",
      font: "14px/1.45 system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif",
    };
    for (const [k, v] of Object.entries(st)) box.style.setProperty(k, v, "important");
    document.documentElement.appendChild(box);
    setTimeout(() => box.remove(), 6000);
    // stare zaznaczenia nic juz nie robia - zdejmij je
    for (const m of document.querySelectorAll("mark.cv-claim")) {
      const p = m.parentNode;
      while (m.firstChild) p.insertBefore(m.firstChild, m);
      p.removeChild(m);
    }
  }

  function openPanel(thesis) {
    thesis = CV.claims.cleanThesis(thesis || "");
    if (thesis.length < 4) return;
    if (!extensionAlive()) {
      showStaleNotice();
      return;
    }
    // nowa teza = nowa ramka: sama zmiana #q w adresie nie przeladowalaby panelu
    // (zostawala stara teza), a stare zapytanie nie nadpisze nowego wyniku
    if (panel) panel.remove();
    zoomed = false;
    panel = document.createElement("iframe");
    panel.className = "cv-panel-frame";
    panel.title = "Hermes Finder";
    placePanel();
    document.documentElement.appendChild(panel);
    // kontekst = tytul artykulu: backend uzupelni z niego brakujace miejsce tezy
    // ("hierzulande", "w naszym kraju"), nigdy nie traktuje go jako osobnej tezy
    const h1 = document.querySelector("h1");
    const context = ((h1 && h1.textContent.trim()) || document.title || "").slice(0, 300);
    panel.src = api.runtime.getURL("panel/panel.html") + "#q=" + encodeURIComponent(thesis) +
      "&c=" + encodeURIComponent(context);
  }

  window.addEventListener("message", (e) => {
    if (!panel || e.source !== panel.contentWindow || !e.data || !e.data.cv) return;
    if (e.data.type === "close") closePanel();
    if (e.data.type === "height") {
      lastHeight = Math.max(120, Math.min(Number(e.data.height) || 160, window.innerHeight - 32));
      if (!zoomed) panel.style.setProperty("height", `${lastHeight}px`, "important");
    }
    if (e.data.type === "expand") {
      zoomed = !!e.data.on;
      placePanel();
    }
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && panel) closePanel(); });

  /* ------------------------------------------------ zdarzenia */
  document.addEventListener("click", (e) => {
    const m = e.target.closest && e.target.closest("mark.cv-claim");
    if (!m || settings.highlightStyle === "none") return;
    if (e.target.closest("a") && (e.ctrlKey || e.metaKey)) return; // pozwol otworzyc link
    e.preventDefault();
    e.stopPropagation();
    const c = claims.find((x) => String(x.id) === m.dataset.cvClaim);
    document.querySelectorAll("mark.cv-claim.cv-active").forEach((x) => x.classList.remove("cv-active"));
    document.querySelectorAll(`mark.cv-claim[data-cv-claim="${m.dataset.cvClaim}"]`).forEach((x) => x.classList.add("cv-active"));
    if (c) openPanel(c.text);
  }, true);

  document.addEventListener("keydown", (e) => {
    const m = e.target.closest && e.target.closest("mark.cv-claim");
    if (m && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      m.click();
    }
  });

  api.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === "get-claims") {
      const h1 = document.querySelector("h1");
      sendResponse({ claims, url: location.href,
                     context: ((h1 && h1.textContent.trim()) || document.title || "").slice(0, 300) });
    } else if (msg.type === "rescan") {
      sendResponse({ claims: scan({ force: true }) });
    } else if (msg.type === "open-panel") {
      openPanel(msg.thesis);
      sendResponse({ ok: true });
    } else if (msg.type === "show-claim") {
      const mark = document.querySelector(`mark.cv-claim[data-cv-claim="${msg.id}"]`);
      if (mark) mark.scrollIntoView({ behavior: "smooth", block: "center" });
      document.querySelectorAll("mark.cv-claim.cv-active").forEach((x) => x.classList.remove("cv-active"));
      document.querySelectorAll(`mark.cv-claim[data-cv-claim="${msg.id}"]`).forEach((x) => x.classList.add("cv-active"));
      const c = claims.find((x) => x.id === msg.id);
      if (c) openPanel(c.text);
      sendResponse({ ok: true });
    }
    return false;
  });

  /* ------------------------------------------------ start */
  CV.loadSettings().then((s) => {     // ustawia tez jezyk (CV.t)
    settings = s;
    if (CV.isExcluded(settings, location.hostname)) return;
    if (!settings.autoScan) return;
    const run = () => scan();
    // daj stronie chwile na doladowanie tresci artykulu
    if (document.readyState === "complete") setTimeout(run, 300);
    else window.addEventListener("load", () => setTimeout(run, 300), { once: true });
  });

  CV.api.storage.onChanged.addListener((changes, area) => {
    if (area !== "sync") return;
    for (const [k, v] of Object.entries(changes)) settings[k] = v.newValue;
  });
})();
