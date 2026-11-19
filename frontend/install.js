/* Hermes Finder — sekcja "Zainstaluj rozszerzenie": paczki z serwera (/api/extension),
   przycisk pobierania i kroki instalacji dla Firefoksa, Chromium (Chrome/Edge/Brave) i Opery.
   Przegladarka uzytkownika jest wyrozniona. */
"use strict";

(function () {
  const grid = document.getElementById("installGrid");
  if (!grid) return;
  let info = null;      // odpowiedz /api/extension (null = jeszcze nie wiadomo / brak)
  let failed = false;

  function detect() {
    const ua = navigator.userAgent || "";
    if (/Firefox\//.test(ua)) return "firefox";
    if (/OPR\/|Opera/.test(ua)) return "opera";
    if (/Chrome\/|Chromium\/|Edg\//.test(ua)) return "chromium";
    return null;
  }

  // logotypy przegladarek (SVG z pakietow @browser-logos): najpierw kopia w vendor/
  // (dziala zawsze, takze gdy CDN jest blokowany), potem CDN jsDelivr (wersje
  // przypiete), na koncu kolorowe kolko z litera
  const LOGO = (name, ver) => [`vendor/browser-logos/${name}.svg`,
    `https://cdn.jsdelivr.net/npm/@browser-logos/${name}@${ver}/${name}.svg`];
  const LOGOS = {
    firefox: { name: "Firefox", src: LOGO("firefox", "3.0.10"), mark: "F", color: "#e66000" },
    chrome: { name: "Chrome", src: LOGO("chrome", "2.0.0"), mark: "C", color: "#1a73e8" },
    edge: { name: "Edge", src: LOGO("edge", "2.0.7"), mark: "E", color: "#0c8484" },
    brave: { name: "Brave", src: LOGO("brave", "3.0.13"), mark: "B", color: "#fb542b" },
    opera: { name: "Opera", src: LOGO("opera", "1.1.11"), mark: "O", color: "#ff1b2d" },
  };
  const CARDS = [
    { id: "firefox", name: "Firefox", logos: ["firefox"] },
    { id: "chromium", name: "Chrome · Edge · Brave", logos: ["chrome", "edge", "brave"] },
    { id: "opera", name: "Opera", logos: ["opera"] },
  ];

  function logosHtml(ids) {
    return `<span class="install-logos${ids.length > 1 ? " stack" : ""}" aria-hidden="true">${ids.map((id, i) => {
      const l = LOGOS[id];
      return `<span class="install-logo" style="--c:${l.color};z-index:${ids.length - i}" title="${escapeAttr(l.name)}">
          <span class="install-mark">${l.mark}</span><img src="${escapeAttr(l.src[0])}" data-alt="${escapeAttr(l.src.slice(1).join(" "))}" alt="" width="32" height="32" decoding="async" referrerpolicy="no-referrer" /></span>`;
    }).join("")}</span>`;
  }

  function steps(key, vars) {
    // kroki w slowniku sa rozdzielone znakiem nowej linii; `kod` -> <code>
    return t(key, vars).split("\n").map((s) =>
      `<li>${escapeHtml(s).replace(/`([^`]+)`/g, "<code>$1</code>")}</li>`).join("");
  }

  function render() {
    const mine = detect();
    const pk = new Map(((info && info.packages) || []).map((p) => [p.browser, p]));
    grid.innerHTML = CARDS.map((c) => {
      const p = pk.get(c.id);
      const signed = c.id === "firefox" && p && p.signed;
      const stepKey = c.id === "firefox" ? (signed ? "stepsFirefoxSigned" : "stepsFirefox")
        : c.id === "opera" ? "stepsOpera" : "stepsChromium";
      const dlKey = c.id === "firefox" ? "dlFirefox" : c.id === "opera" ? "dlOpera" : "dlChromium";
      const meta = info && info.version
        ? [t("installVersion", { v: info.version }), p ? p.filename : ""].filter(Boolean).join(" · ") : "";
      const href = p ? p.url : "#";
      return `
        <article class="install-card${mine === c.id ? " mine" : ""}">
          ${mine === c.id ? `<span class="install-badge">${escapeHtml(t("installYour"))}</span>` : ""}
          <h3>${logosHtml(c.logos)}${escapeHtml(c.name)}</h3>
          ${meta ? `<p class="install-meta">${escapeHtml(meta)}</p>` : ""}
          <a class="install-dl" href="${escapeAttr(href)}" ${p ? `download="${escapeAttr(p.filename)}"` : 'aria-disabled="true"'}>${escapeHtml(t(dlKey))}</a>
          <ol>${steps(stepKey)}</ol>
          ${c.id === "firefox" && p && !signed ? `<p class="install-note">${escapeHtml(t("installUnsigned"))}</p>` : ""}
        </article>`;
    }).join("") + (failed ? `<p class="install-note" style="grid-column:1/-1">${escapeHtml(t("installUnavailable"))}</p>` : "");
    // logo zaladowane -> chowamy litere; blad (offline, CDN zablokowany) -> zostaje litera
    grid.querySelectorAll(".install-logo img").forEach((img) => {
      const next = (img.dataset.alt || "").split(" ").filter(Boolean);
      const ok = () => img.parentElement && img.parentElement.classList.add("loaded");
      const bad = () => {
        const src = next.shift();
        if (src) img.src = src; else img.remove();   // kolejne zrodlo albo litera
      };
      img.addEventListener("load", ok);
      img.addEventListener("error", bad);
      if (img.complete) (img.naturalWidth ? ok() : bad());
    });
  }

  render();
  fetch(`${API_BASE}/api/extension`)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((d) => { info = d; failed = !d.available; render(); })
    .catch(() => { failed = true; render(); });

  window.HFInstall = { render };
})();
