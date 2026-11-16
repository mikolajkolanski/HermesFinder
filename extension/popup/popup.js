/* Okno rozszerzenia: wlasne zapytanie + tezy wykryte na aktywnej karcie.
   "Wiecej" otwiera pelna analize (zwykle wyszukiwanie) w nowej karcie. */
"use strict";

(async function () {
  const api = CV.api;
  const $ = (id) => document.getElementById(id);
  const esc = CV.render.esc;
  const settings = await CV.loadSettings();     // ustawia tez jezyk (CV.t)
  const t = CV.t;
  HFLang.applyDom(document, t);

  // style skrotu wspolne z panelem na stronie
  const st = document.createElement("style");
  st.textContent = CV.render.css.replace(":host, .cv-root { all: initial; }", "");
  document.head.appendChild(st);
  $("stripes").innerHTML = CV.render.stripesHtml();

  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  const pageOk = !!(tab && /^https?:/.test(tab.url || ""));
  CV.canMaximize = true;   // link "wszystkie wykresy" -> nowa karta

  let pageContext = "";
  let runId = 0;              // tylko odpowiedz na OSTATNIE zapytanie trafia na ekran

  /** Pelna analiza (zwykle wyszukiwanie) w nowej karcie; okno rozszerzenia sie zamyka. */
  async function openFull(thesis) {
    await CV.openFull(settings, thesis);
    window.close();
  }
  function moreButton() {
    return `<p class="cv-full"><button type="button" class="cv-max" data-more title="${esc(t("moreTitle"))}">${esc(t("more"))}</button></p>`;
  }
  function bindMore(thesis) {
    const b = $("result").querySelector("[data-more]");
    if (b) b.addEventListener("click", () => openFull(thesis));
  }

  async function run(thesis, context = "") {
    thesis = String(thesis || "").replace(/\s+/g, " ").trim();
    if (thesis.length < 4) {
      $("q").focus();
      return;
    }
    $("q").value = thesis;
    const my = ++runId;
    document.body.classList.remove("cv-wide");
    document.querySelectorAll(".cv-zoom").forEach((z) => z.remove());
    $("result").innerHTML = `
      <div class="cv-bar" aria-hidden="true"></div>
      <p class="cv-loading">${esc(t("loading"))}</p>${moreButton()}`;
    bindMore(thesis);
    let res;
    try {
      res = await CV.analyze(thesis, context);
    } catch (e) {
      res = { ok: false, error: t("errFetch", { e: e.message || e }) };
    }
    if (my !== runId) return;   // w miedzyczasie wybrano inna teze
    if (!res || !res.ok) {
      $("result").innerHTML = `<p class="cv-error">${esc(res ? res.error : t("errNoResponse"))}</p>${moreButton()}`;
      bindMore(thesis);
      return;
    }
    CV.render.mountSummary($("result"), res.data, {
      maxCharts: Number(settings.maxCharts) || 2,
      // okno rozszerzenia mozna poszerzyc do ~800 px (limit przegladarki)
      onZoom: (on) => document.body.classList.toggle("cv-wide", on),
      onMaximize: () => openFull(thesis),
    });
    $("result").insertAdjacentHTML("beforeend", moreButton());
    bindMore(thesis);
    try { await api.storage.session?.set({ lastThesis: thesis }); } catch (e) { /* brak storage.session */ }
  }

  $("askForm").addEventListener("submit", (e) => { e.preventDefault(); run($("q").value); });
  $("q").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); run($("q").value); }
  });
  $("openOptions").addEventListener("click", () => api.runtime.openOptionsPage());

  /* tezy z aktywnej karty */
  function showClaims(list) {
    const ol = $("claimList");
    ol.innerHTML = "";
    $("pageClaims").classList.toggle("hidden", !list.length);
    $("noClaims").classList.toggle("hidden", !!list.length);
    for (const c of list) {
      const li = document.createElement("li");
      li.innerHTML = `<button type="button" class="claim">${esc(c.text)}</button>`;
      // teza ze strony: okno rozszerzenia sie zamyka, wynik pokazuje panel na stronie
      // (jeden widok naraz, nie okno + panel)
      li.querySelector("button").addEventListener("click", async () => {
        try {
          await api.tabs.sendMessage(tab.id, { type: "show-claim", id: c.id });
          window.close();
        } catch (e) {
          run(c.text, pageContext);    // strona nie odpowiada - wynik w oknie
        }
      });
      ol.appendChild(li);
    }
  }

  async function rescan() {
    try {
      const r = await api.tabs.sendMessage(tab.id, { type: "rescan" });
      showClaims((r && r.claims) || []);
    } catch (e) { /* strona bez skryptu */ }
  }
  $("rescan").addEventListener("click", rescan);
  $("rescan2").addEventListener("click", rescan);

  if (pageOk) {
    try {
      const r = await api.tabs.sendMessage(tab.id, { type: "get-claims" });
      pageContext = (r && r.context) || "";
      showClaims((r && r.claims) || []);
    } catch (e) {
      $("noClaims").classList.add("hidden");
    }
  }

  // ostatnia teza z tej sesji (wygoda)
  try {
    const s = await api.storage.session?.get("lastThesis");
    if (s && s.lastThesis && !$("q").value) $("q").value = s.lastThesis;
  } catch (e) { /* brak storage.session */ }

  $("q").focus();
  /* stan serwera: komunikat tylko, gdy serwer nie odpowiada */
  const h = await CV.health();
  $("status").textContent = h && h.ok ? "" : t("noServer", { url: settings.backendUrl });
})();
