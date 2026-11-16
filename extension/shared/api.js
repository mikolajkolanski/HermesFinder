/* Zapytania do serwera Hermes Finder - wykonywane BEZPOSREDNIO z panelu
   i okna rozszerzenia (strony rozszerzenia maja uprawnienia hosta).

   Dlaczego nie przez skrypt tla: w Manifest V3 przegladarka usypia tlo po ~30 s
   bezczynnosci, takze w trakcie dlugiego zapytania (LLM + pobieranie danych),
   co zrywalo kanal wiadomosci ("Rozszerzenie zostalo przeladowane").
   Wyniki sa zapamietywane w storage.session (wspolne dla panelu i okna). */
"use strict";

var CV = globalThis.CV || (globalThis.CV = {});

(function () {
  const CACHE_MS = 30 * 60 * 1000;
  const TIMEOUT_MS = 150 * 1000;

  function base(url) {
    return String(url || CV.DEFAULTS.backendUrl).replace(/\/+$/, "");
  }

  async function cacheKey(parts) {
    const data = new TextEncoder().encode(parts.join("\u0001"));
    const hash = await crypto.subtle.digest("SHA-1", data);
    return "cv:" + Array.from(new Uint8Array(hash)).map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  async function cacheGet(key) {
    try {
      const got = await CV.api.storage.session.get(key);
      const hit = got && got[key];
      if (hit && Date.now() - hit.at < CACHE_MS) return hit.data;
    } catch (e) { /* storage.session niedostepne - bez pamieci */ }
    return null;
  }

  async function cacheSet(key, data) {
    try {
      await CV.api.storage.session.set({ [key]: { at: Date.now(), data } });
    } catch (e) { /* przekroczony limit lub brak storage.session - pomijamy */ }
  }

  /** Analiza tezy -> {ok, data} albo {ok:false, error} (komunikat dla uzytkownika). */
  CV.analyze = async function analyze(thesis, context) {
    const settings = await CV.loadSettings();
    thesis = String(thesis || "").slice(0, 600);
    context = String(context || "").slice(0, 300);
    const key = await cacheKey([base(settings.backendUrl), String(settings.useLlm), thesis, context]);
    const cached = await cacheGet(key);
    if (cached) return { ok: true, data: cached, cached: true };

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      const resp = await fetch(`${base(settings.backendUrl)}/api/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thesis, options: { disable_llm: !settings.useLlm, context: context || null } }),
        signal: ctrl.signal,
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        const detail = Array.isArray(body.detail) ? CV.t("errLength") : body.detail;
        return { ok: false, error: CV.t("errServer", { status: resp.status, detail: detail ? ": " + detail : "" }) };
      }
      const data = await resp.json();
      await cacheSet(key, data);
      return { ok: true, data };
    } catch (err) {
      if (err.name === "AbortError") {
        return { ok: false, error: CV.t("errTimeout") };
      }
      return {
        ok: false,
        error: CV.t("errConnect", { url: base(settings.backendUrl) }),
      };
    } finally {
      clearTimeout(timer);
    }
  };

  /** Panel w rogu strony na karcie tabId (msg: {type:"open-panel", thesis, max}).
      Karta bez skryptu (otwarta przed instalacja/przeladowaniem rozszerzenia):
      wstrzykuje skrypty z manifestu i probuje jeszcze raz. false = strona
      niedostepna dla rozszerzen (about:, sklep z dodatkami). */
  CV.openInPage = async function openInPage(tabId, msg) {
    try {
      await CV.api.tabs.sendMessage(tabId, msg);
      return true;
    } catch (e) { /* brak odbiorcy */ }
    try {
      const cs = CV.api.runtime.getManifest().content_scripts[0];
      await CV.api.scripting.insertCSS({ target: { tabId }, files: cs.css || [] });
      await CV.api.scripting.executeScript({ target: { tabId }, files: cs.js });
      await CV.api.tabs.sendMessage(tabId, msg);
      return true;
    } catch (e) {
      return false;
    }
  };

  /** Stan aplikacji -> {ok, data} / {ok:false, error}. */
  CV.health = async function health() {
    const settings = await CV.loadSettings();
    try {
      const resp = await fetch(`${base(settings.backendUrl)}/api/health`, { signal: AbortSignal.timeout(8000) });
      return { ok: resp.ok, data: await resp.json() };
    } catch (err) {
      return { ok: false, error: String(err.message || err) };
    }
  };
})();
