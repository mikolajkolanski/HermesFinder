/* Panel w rogu strony (dokument rozszerzenia w ramce iframe).
   Teza przychodzi w adresie (#q=...&c=...); kazda nowa teza = nowa ramka.
   Z karta strony rozmawia przez postMessage: wysokosc, powiekszenie wykresu,
   zamkniecie. "Wiecej" otwiera pelna analize (zwykle wyszukiwanie) w nowej karcie. */
"use strict";

(async function () {
  const esc = CV.render.esc;
  const $ = (id) => document.getElementById(id);
  const st = document.createElement("style");
  st.textContent = CV.render.css.replace(":host, .cv-root { all: initial; }", "");
  document.head.appendChild(st);
  $("stripes").innerHTML = CV.render.stripesHtml();

  const params = new URLSearchParams(location.hash.slice(1));
  const thesis = params.get("q") || "";
  const context = params.get("c") || "";
  const settings = await CV.loadSettings();      // ustawia tez jezyk (CV.t)
  const t = CV.t;
  CV.canMaximize = true;                        // link "wszystkie wykresy" -> nowa karta

  $("close").setAttribute("aria-label", t("panelClose"));
  $("close").title = t("panelClose");
  $("moreLabel").textContent = t("more");
  $("more").title = t("moreTitle");

  function post(msg) {
    // rodzic = karta ze strona; jego pochodzenia nie znamy z gory, wiadomosci
    // nie zawieraja danych prywatnych (tylko wysokosc / prosby o rozmiar)
    window.parent.postMessage({ cv: true, ...msg }, "*");
  }

  // wysokosc TRESCI (nie kontenera, ktory wypelnia cala ramke)
  function reportHeight() {
    const body = $("body");
    const last = body.lastElementChild;
    const content = last ? last.offsetTop + last.offsetHeight : 0;
    const pad = parseFloat(getComputedStyle(body).paddingBottom) || 0;
    const h = $("stripes").offsetHeight + document.querySelector(".cv-head").offsetHeight + content + pad + 2;
    post({ type: "height", height: Math.ceil(h) });
  }
  new MutationObserver(reportHeight).observe($("body"), { childList: true, subtree: true });
  window.addEventListener("load", reportHeight);

  const openFull = () => CV.openFull(settings, thesis);
  $("more").addEventListener("click", openFull);
  $("close").addEventListener("click", () => post({ type: "close" }));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !document.querySelector(".cv-zoom")) post({ type: "close" });
  });

  const head = `<p class="cv-thesis">${esc(thesis)}</p>`;
  $("body").innerHTML = `${head}<div class="cv-bar" aria-hidden="true"></div><p class="cv-loading">${esc(t("loading"))}</p>`;
  reportHeight();
  $("close").focus({ preventScroll: true });

  let res;
  try {
    // zapytanie prosto z panelu - nie zalezy od uspionego skryptu tla
    res = await CV.analyze(thesis, context);
  } catch (e) {
    res = { ok: false, error: t("errFetch", { e: e.message || e }) };
  }
  if (!res || !res.ok) {
    $("body").innerHTML = `${head}<p class="cv-error">${esc(res ? res.error : t("errNoResponse"))}</p>`;
  } else {
    $("body").innerHTML = `${head}<div id="summary"></div>`;
    CV.render.mountSummary($("summary"), res.data, {
      maxCharts: Number(settings.maxCharts) || 2,
      // powiekszony wykres: karta strony rozciaga ramke na wieksza czesc ekranu
      onZoom: (on) => post({ type: "expand", on }),
      onMaximize: openFull,
    });
  }
  reportHeight();
})();
