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

  const CARDS = [
    { id: "firefox", name: "Firefox", mark: "F", color: "#e66000" },
    { id: "chromium", name: "Chrome · Edge · Brave", mark: "C", color: "#1a73e8" },
    { id: "opera", name: "Opera", mark: "O", color: "#ff1b2d" },
  ];

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
          <h3><span class="install-mark" style="background:${c.color}" aria-hidden="true">${c.mark}</span>${escapeHtml(c.name)}</h3>
          ${meta ? `<p class="install-meta">${escapeHtml(meta)}</p>` : ""}
          <a class="install-dl" href="${escapeAttr(href)}" ${p ? `download="${escapeAttr(p.filename)}"` : 'aria-disabled="true"'}>${escapeHtml(t(dlKey))}</a>
          <ol>${steps(stepKey)}</ol>
          ${c.id === "firefox" && p && !signed ? `<p class="install-note">${escapeHtml(t("installUnsigned"))}</p>` : ""}
        </article>`;
    }).join("") + (failed ? `<p class="install-note" style="grid-column:1/-1">${escapeHtml(t("installUnavailable"))}</p>` : "");
  }

  render();
  fetch(`${API_BASE}/api/extension`)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((d) => { info = d; failed = !d.available; render(); })
    .catch(() => { failed = true; render(); });

  window.HFInstall = { render };
})();
