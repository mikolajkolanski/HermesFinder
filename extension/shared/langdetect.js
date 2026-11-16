/* Hermes Finder: wybor jezyka interfejsu (13 jezykow) po kraju uzytkownika.
   TEN SAM PLIK jest w extension/shared/ i frontend/ (test: tests/test_i18n.py).

   Kolejnosc:
   1. jezyk wybrany recznie w ustawieniach,
   2. jezyk przegladarki, jesli to jeden z 13 (poza angielskim),
   3. kraj: ze strefy czasowej systemu (Europe/Warsaw -> PL), potem z regionu
      w ustawieniach jezyka przegladarki (en-PL, es-MX) -> jezyk tego kraju,
   4. angielski.
   Nic nie jest wysylane do sieci: strefa czasowa i jezyki pochodza z przegladarki. */
"use strict";

(function (root) {
  const LANGS = ["en", "pl", "de", "fr", "es", "it", "pt", "nl", "cs", "sv", "uk", "ja", "zh"];
  const NAMES = {
    en: "English", pl: "Polski", de: "Deutsch", fr: "Français", es: "Español", it: "Italiano",
    pt: "Português", nl: "Nederlands", cs: "Čeština", sv: "Svenska", uk: "Українська",
    ja: "日本語", zh: "中文（简体）",
  };
  // format liczb i dat
  const LOCALES = {
    en: "en-GB", pl: "pl-PL", de: "de-DE", fr: "fr-FR", es: "es-ES", it: "it-IT", pt: "pt-PT",
    nl: "nl-NL", cs: "cs-CZ", sv: "sv-SE", uk: "uk-UA", ja: "ja-JP", zh: "zh-CN",
  };

  // kraj -> jezyk(i) urzedowy(e) sposrod 13; kraje anglojezyczne nie sa potrzebne
  // (brak dopasowania = angielski)
  const COUNTRY_LANG = {
    PL: "pl",
    DE: "de", AT: "de", LI: "de", CH: ["de", "fr", "it"], LU: ["fr", "de"], BE: ["nl", "fr", "de"],
    FR: "fr", MC: "fr", SN: "fr", CI: "fr", CM: "fr", ML: "fr", BF: "fr", NE: "fr", TG: "fr", BJ: "fr",
    GA: "fr", CG: "fr", CD: "fr", MG: "fr", HT: "fr", RE: "fr", GP: "fr", MQ: "fr", GF: "fr", NC: "fr", PF: "fr",
    ES: "es", MX: "es", AR: "es", CO: "es", PE: "es", CL: "es", VE: "es", EC: "es", BO: "es", PY: "es",
    UY: "es", GT: "es", SV: "es", HN: "es", NI: "es", CR: "es", PA: "es", CU: "es", DO: "es", PR: "es", GQ: "es",
    IT: "it", SM: "it", VA: "it",
    PT: "pt", BR: "pt", AO: "pt", MZ: "pt", CV: "pt", GW: "pt", ST: "pt", TL: "pt",
    NL: "nl", SR: "nl", AW: "nl", CW: "nl", SX: "nl",
    CZ: "cs",
    SE: "sv", AX: "sv", FI: ["sv"],          // Finlandia: szwedzki jest jezykiem urzedowym (fin. poza lista)
    UA: "uk",
    JP: "ja",
    CN: "zh", TW: "zh", HK: "zh", MO: "zh", SG: ["en", "zh"],
    CA: ["en", "fr"],
  };

  // strefa czasowa IANA -> kraj (tylko kraje z COUNTRY_LANG)
  const TZ_COUNTRY = {
    "Europe/Warsaw": "PL",
    "Europe/Berlin": "DE", "Europe/Busingen": "DE", "Europe/Vienna": "AT", "Europe/Vaduz": "LI",
    "Europe/Zurich": "CH", "Europe/Luxembourg": "LU", "Europe/Brussels": "BE",
    "Europe/Paris": "FR", "Europe/Monaco": "MC", "Africa/Dakar": "SN", "Africa/Douala": "CM",
    "Africa/Bamako": "ML", "Africa/Ouagadougou": "BF", "Africa/Niamey": "NE", "Africa/Lome": "TG",
    "Africa/Porto-Novo": "BJ", "Africa/Libreville": "GA", "Africa/Brazzaville": "CG",
    "Africa/Kinshasa": "CD", "Africa/Lubumbashi": "CD", "Indian/Antananarivo": "MG",
    "America/Port-au-Prince": "HT", "Indian/Reunion": "RE", "America/Guadeloupe": "GP",
    "America/Martinique": "MQ", "America/Cayenne": "GF", "Pacific/Noumea": "NC", "Pacific/Tahiti": "PF",
    "Europe/Madrid": "ES", "Atlantic/Canary": "ES", "Africa/Ceuta": "ES",
    "America/Mexico_City": "MX", "America/Cancun": "MX", "America/Merida": "MX", "America/Monterrey": "MX",
    "America/Matamoros": "MX", "America/Chihuahua": "MX", "America/Ciudad_Juarez": "MX",
    "America/Ojinaga": "MX", "America/Mazatlan": "MX", "America/Bahia_Banderas": "MX",
    "America/Hermosillo": "MX", "America/Tijuana": "MX",
    "America/Bogota": "CO", "America/Lima": "PE", "America/Santiago": "CL", "America/Punta_Arenas": "CL",
    "Pacific/Easter": "CL", "America/Caracas": "VE", "America/Guayaquil": "EC", "Pacific/Galapagos": "EC",
    "America/La_Paz": "BO", "America/Asuncion": "PY", "America/Montevideo": "UY",
    "America/Guatemala": "GT", "America/El_Salvador": "SV", "America/Tegucigalpa": "HN",
    "America/Managua": "NI", "America/Costa_Rica": "CR", "America/Panama": "PA", "America/Havana": "CU",
    "America/Santo_Domingo": "DO", "America/Puerto_Rico": "PR", "Africa/Malabo": "GQ",
    "Europe/Rome": "IT", "Europe/San_Marino": "SM", "Europe/Vatican": "VA",
    "Europe/Lisbon": "PT", "Atlantic/Madeira": "PT", "Atlantic/Azores": "PT",
    "America/Sao_Paulo": "BR", "America/Bahia": "BR", "America/Fortaleza": "BR", "America/Recife": "BR",
    "America/Belem": "BR", "America/Manaus": "BR", "America/Cuiaba": "BR", "America/Campo_Grande": "BR",
    "America/Porto_Velho": "BR", "America/Boa_Vista": "BR", "America/Rio_Branco": "BR",
    "America/Eirunepe": "BR", "America/Noronha": "BR", "America/Araguaina": "BR", "America/Maceio": "BR",
    "America/Santarem": "BR", "Africa/Luanda": "AO", "Africa/Maputo": "MZ", "Atlantic/Cape_Verde": "CV",
    "Africa/Bissau": "GW", "Africa/Sao_Tome": "ST", "Asia/Dili": "TL",
    "Europe/Amsterdam": "NL", "America/Paramaribo": "SR", "America/Aruba": "AW", "America/Curacao": "CW",
    "America/Lower_Princes": "SX",
    "Europe/Prague": "CZ",
    "Europe/Stockholm": "SE", "Europe/Mariehamn": "AX",
    "Europe/Kyiv": "UA", "Europe/Kiev": "UA", "Europe/Uzhgorod": "UA", "Europe/Zaporozhye": "UA",
    "Asia/Tokyo": "JP",
    "Asia/Shanghai": "CN", "Asia/Chongqing": "CN", "Asia/Chungking": "CN", "Asia/Harbin": "CN",
    "Asia/Urumqi": "CN", "PRC": "CN", "Asia/Taipei": "TW", "Asia/Hong_Kong": "HK", "Asia/Macau": "MO",
    "Asia/Singapore": "SG",
  };
  // Argentyna ma wiele stref: America/Argentina/*
  function tzCountry(tz) {
    if (!tz) return null;
    if (tz.startsWith("America/Argentina/") || tz === "America/Buenos_Aires") return "AR";
    return TZ_COUNTRY[tz] || null;
  }

  function browserLangs(nav) {
    const list = (nav && (nav.languages && nav.languages.length ? nav.languages : [nav.language])) || [];
    return list.filter(Boolean).map(String);
  }

  /**
   * Jezyk interfejsu.
   * pref: "auto" albo kod z LANGS (wybor uzytkownika).
   * env (testy): {languages: [...], timeZone: "Europe/Warsaw"}
   * Zwraca {lang, source, country}.
   */
  function detect(pref, env) {
    if (pref && pref !== "auto" && LANGS.includes(pref)) return { lang: pref, source: "setting", country: null };
    const nav = env || root.navigator || {};
    const tags = env ? env.languages || [] : browserLangs(nav);
    const primary = tags.map((t) => t.toLowerCase().split(/[-_]/)[0]);

    // 2. jasno wybrany jezyk przegladarki (inny niz angielski)
    const own = primary.find((l) => l !== "en" && LANGS.includes(l));
    if (own) return { lang: own, source: "browser", country: null };

    // 3. kraj: strefa czasowa, potem region z tagow jezyka
    const countries = [];
    let tz = env ? env.timeZone : null;
    if (!env) {
      try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) { tz = null; }
    }
    const fromTz = tzCountry(tz);
    if (fromTz) countries.push(fromTz);
    for (const t of tags) {
      const m = /^[a-z]{2,3}[-_](?:[a-z]{4}[-_])?([a-z]{2})\b/i.exec(t);
      if (m) countries.push(m[1].toUpperCase());
    }
    for (const c of countries) {
      const langs = COUNTRY_LANG[c];
      if (!langs) continue;
      const arr = [].concat(langs);
      return { lang: arr.find((l) => primary.includes(l)) || arr[0], source: "country", country: c };
    }
    // 4. angielski
    return { lang: "en", source: "fallback", country: countries[0] || null };
  }

  /** Szablon: "Sources: {n}" + {n: 3} -> "Sources: 3". */
  function fill(str, vars) {
    return vars ? String(str).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : String(str);
  }

  /** Slownik w formacie {klucz: [en, pl, de, ...]} (kolejnosc jak LANGS). */
  function makeTranslator(dict, lang) {
    const i = Math.max(0, LANGS.indexOf(lang));
    return function t(key, vars) {
      const row = dict[key];
      if (!row) return key;
      return fill(row[i] || row[0], vars);
    };
  }

  /** Teksty w HTML: data-i18n (tresc), data-i18n-ph / -title / -aria (atrybuty). */
  function applyDom(doc, t) {
    doc.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    doc.querySelectorAll("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
    doc.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
    doc.querySelectorAll("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nAria)); });
  }

  const api = { LANGS, NAMES, LOCALES, COUNTRY_LANG, detect, tzCountry, fill, makeTranslator, applyDom };
  root.HFLang = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
