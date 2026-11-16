/* Ustawienia rozszerzenia: wartosci domyslne + odczyt/zapis (storage.sync). */
"use strict";

var CV = globalThis.CV || (globalThis.CV = {});
// Firefox: `browser`; Chromium: `chrome` (w MV3 tez zwraca Promise)
CV.api = globalThis.browser ?? globalThis.chrome;

CV.DEFAULTS = {
  backendUrl: "http://127.0.0.1:8000",
  autoScan: true,           // skanuj artykuly automatycznie po wejsciu na strone
  articlesOnly: true,       // tylko strony, ktore wygladaja na artykul
  sensitivity: "medium",    // low | medium | high
  maxHighlights: 6,         // ile tez zaznaczyc na jednej stronie (najlepsze wg punktacji)
  highlightStyle: "underline", // underline | background | none
  maxCharts: 2,             // ile wykresow w skrocie (1-3)
  useLlm: true,             // dobor danych przez model jezykowy w backendzie
  panelPosition: "bottom-right", // bottom-right | bottom-left | top-right
  excludedSites: "",        // hosty, jeden w linii
  language: "auto",         // auto (kraj/przegladarka, inaczej angielski) albo kod: en, pl, de...
};

// prog punktowy zdania wg czulosci (wiekszy = mniej zaznaczen)
CV.THRESHOLDS = { low: 8, medium: 6, high: 4.5 };

CV.loadSettings = async function loadSettings() {
  try {
    const got = await CV.api.storage.sync.get(CV.DEFAULTS);
    const s = { ...CV.DEFAULTS, ...got };
    if (CV.initI18n) CV.initI18n(s.language);
    return s;
  } catch (e) {
    return { ...CV.DEFAULTS };
  }
};

CV.saveSettings = function saveSettings(values) {
  return CV.api.storage.sync.set(values);
};

/** Strona glowna z teza (zwykle wyszukiwanie); jezyk jak w rozszerzeniu, jesli wybrany recznie. */
CV.fullUrl = function fullUrl(backendUrl, thesis, lang) {
  const l = lang && lang !== "auto" ? `&lang=${encodeURIComponent(lang)}` : "";
  return `${String(backendUrl).replace(/\/+$/, "")}/?q=${encodeURIComponent(thesis)}${l}`;
};

/** Pelna analiza w nowej karcie (obok biezacej). */
CV.openFull = async function openFull(settings, thesis) {
  const url = CV.fullUrl(settings.backendUrl, thesis, settings.language);
  try {
    const [cur] = await CV.api.tabs.query({ active: true, currentWindow: true });
    await CV.api.tabs.create(cur ? { url, index: cur.index + 1, openerTabId: cur.id } : { url });
  } catch (e) {
    window.open(url, "_blank", "noopener");
  }
};

CV.isExcluded = function isExcluded(settings, host) {
  return String(settings.excludedSites || "")
    .split(/\s+/).map((h) => h.trim().toLowerCase()).filter(Boolean)
    .some((h) => host === h || host.endsWith("." + h));
};
