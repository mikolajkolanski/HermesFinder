/* Extension settings page. */
"use strict";

(async function () {
  const api = CV.api;
  const $ = (id) => document.getElementById(id);
  const FIELDS = Object.keys(CV.DEFAULTS);
  const STRIPES = ["#08519c", "#2171b5", "#6baed6", "#c6dbef", "#fcbba1", "#fb6a4a", "#cb181d", "#67000d"];
  $("stripes").innerHTML = STRIPES.map((c) => `<span style="background:${c}"></span>`).join("");

  /* jezyk: lista 13 jezykow + "automatycznie"; zmiana od razu tlumaczy strone */
  function applyLanguage(pref) {
    const t = CV.initI18n(pref);
    HFLang.applyDom(document, t);
    document.title = `Hermes Finder – ${t("settings")}`;
    const sel = $("language");
    const cur = sel.value || pref;
    sel.innerHTML = `<option value="auto">${t("optLangAuto")}</option>` +
      HFLang.LANGS.map((l) => `<option value="${l}">${HFLang.NAMES[l]}</option>`).join("");
    sel.value = cur;
    const auto = HFLang.detect("auto");
    $("langHelp").textContent = t("optLangHelp", { lang: HFLang.NAMES[auto.lang] + (auto.country ? ` (${auto.country})` : "") });
    return t;
  }
  let t = CV.t;

  function fill(s) {
    for (const k of FIELDS) {
      const el = $(k);
      if (!el) continue;
      if (el.type === "checkbox") el.checked = !!s[k];
      else el.value = s[k];
    }
  }

  function read() {
    const out = {};
    for (const k of FIELDS) {
      const el = $(k);
      if (!el) continue;
      if (el.type === "checkbox") out[k] = el.checked;
      else if (el.type === "number" || k === "maxCharts") out[k] = Math.max(1, Math.min(k === "maxCharts" ? 3 : 30, parseInt(el.value, 10) || CV.DEFAULTS[k]));
      else out[k] = el.value.trim();
    }
    out.backendUrl = (out.backendUrl || CV.DEFAULTS.backendUrl).replace(/\/+$/, "");
    return out;
  }

  function originPattern(url) {
    try {
      const u = new URL(url);
      return `${u.protocol}//${u.hostname}/*`;
    } catch (e) {
      return null;
    }
  }

  async function refreshPerm() {
    const all = await api.permissions.contains({ origins: ["<all_urls>"] });
    $("permState").textContent = all ? t("optPermOk") : t("optPermNo");
    $("grant").classList.toggle("hidden", all);
  }

  const initial = await CV.loadSettings();
  $("language").innerHTML = `<option value="${initial.language}"></option>`;
  $("language").value = initial.language;
  t = applyLanguage(initial.language);
  fill(initial);
  refreshPerm();
  $("language").addEventListener("change", () => {
    t = applyLanguage($("language").value);
    refreshPerm();
  });

  $("grant").addEventListener("click", async () => {
    await api.permissions.request({ origins: ["<all_urls>"] });
    refreshPerm();
  });

  $("test").addEventListener("click", async () => {
    const s = read();
    $("testResult").textContent = t("optTesting");
    const pat = originPattern(s.backendUrl);
    if (pat && !(await api.permissions.contains({ origins: [pat] }))) {
      await api.permissions.request({ origins: [pat] }).catch(() => false);
    }
    await CV.saveSettings({ backendUrl: s.backendUrl });
    const h = await CV.health();
    $("testResult").textContent = h && h.ok
      ? t("optConnected", { n: h.data.datasets, llm: h.data.llm && h.data.llm.available ? `${h.data.llm.provider} (${h.data.llm.model})` : t("optLlmOff") })
      : t("optNoConnect", { url: s.backendUrl });
  });

  $("form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const s = read();
    const pat = originPattern(s.backendUrl);
    if (pat && !(await api.permissions.contains({ origins: [pat] }))) {
      await api.permissions.request({ origins: [pat] }).catch(() => false);
    }
    await CV.saveSettings(s);
    $("saved").textContent = t("optSaved");
  });

  $("reset").addEventListener("click", async () => {
    await CV.saveSettings({ ...CV.DEFAULTS });
    fill(CV.DEFAULTS);
    t = applyLanguage(CV.DEFAULTS.language);
    $("saved").textContent = t("optDefaults");
  });
})();
