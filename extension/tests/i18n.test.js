/* Testy tlumaczen i wyboru jezyka: node extension/tests/i18n.test.js
   - kazdy wiersz slownika ma 13 tekstow, a w kazdym te same {zmienne} co po angielsku,
   - frontend/langdetect.js == extension/shared/langdetect.js,
   - wybor jezyka: ustawienie > jezyk przegladarki > kraj (strefa/region) > angielski. */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const root = path.join(__dirname, "..", "..");
const ext = (p) => path.join(root, "extension", p);
let failures = 0;
function check(name, fn) {
  try { fn(); console.log("ok   " + name); } catch (e) { failures++; console.log("FAIL " + name + "\n     " + e.message); }
}

const HF = require(ext("shared/langdetect.js"));
const vars = (s) => [...String(s).matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");

function checkDict(name, dict) {
  check(`${name}: 13 jezykow i te same zmienne`, () => {
    const bad = [];
    for (const [k, row] of Object.entries(dict)) {
      if (!Array.isArray(row) || row.length !== HF.LANGS.length) { bad.push(`${k}: ${row && row.length}`); continue; }
      row.forEach((txt, i) => {
        if (!txt || typeof txt !== "string") bad.push(`${k}[${HF.LANGS[i]}] pusty`);
        else if (vars(txt) !== vars(row[0])) bad.push(`${k}[${HF.LANGS[i]}] {${vars(txt)}} != {${vars(row[0])}}`);
      });
    }
    assert.deepStrictEqual(bad, []);
  });
}

// slownik rozszerzenia
const ctx = { globalThis: null, HFLang: HF };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(ext("shared/i18n.js"), "utf8"), ctx);
checkDict("rozszerzenie", ctx.CV.I18N);

// slownik strony (const I18N w skrypcie)
const fctx = { HFLang: HF, URLSearchParams, location: { search: "" }, localStorage: { getItem: () => null, setItem() {} }, document: {} };
vm.createContext(fctx);
vm.runInContext(fs.readFileSync(path.join(root, "frontend/i18n.js"), "utf8") + "\nthis.__I18N = I18N;", fctx);
checkDict("strona", fctx.__I18N);

check("klucze uzyte w kodzie istnieja w slownikach", () => {
  const missing = [];
  const scan = (files, dict, re) => {
    for (const f of files) {
      const src = fs.readFileSync(f, "utf8");
      for (const m of src.matchAll(re)) if (!(m[1] in dict)) missing.push(`${path.basename(f)}: ${m[1]}`);
    }
  };
  const extFiles = ["shared/render.js", "shared/api.js", "panel/panel.js", "popup/popup.js", "options/options.js",
    "content/content.js", "background.js"].map(ext);
  scan(extFiles, ctx.CV.I18N, /\b(?:CV\.)?t\("(\w+)"[,)]/g);
  const htmlExt = ["popup/popup.html", "options/options.html"].map(ext);
  scan(htmlExt, ctx.CV.I18N, /data-i18n(?:-ph|-title|-aria)?="(\w+)"/g);
  scan([path.join(root, "frontend/app.js")], fctx.__I18N, /\bt\("(\w+)"[,)]/g);
  scan([path.join(root, "frontend/index.html")], fctx.__I18N, /data-i18n(?:-ph|-title|-aria)?="(\w+)"/g);
  assert.deepStrictEqual(missing, []);
});

check("langdetect.js identyczny w rozszerzeniu i na stronie", () => {
  assert.strictEqual(fs.readFileSync(ext("shared/langdetect.js"), "utf8"),
    fs.readFileSync(path.join(root, "frontend/langdetect.js"), "utf8"));
});

check("wybor jezyka", () => {
  const d = (pref, languages, timeZone) => HF.detect(pref, { languages, timeZone }).lang;
  assert.strictEqual(d("de", ["pl-PL"], "Europe/Warsaw"), "de");             // ustawienie
  assert.strictEqual(d("auto", ["pl-PL", "en"], "America/New_York"), "pl");   // jezyk przegladarki
  assert.strictEqual(d("auto", ["en-US"], "Europe/Warsaw"), "pl");            // kraj ze strefy
  assert.strictEqual(d("auto", ["en-US"], "Europe/Prague"), "cs");
  assert.strictEqual(d("auto", ["en-US"], "America/Argentina/Cordoba"), "es");
  assert.strictEqual(d("auto", ["en-US"], "America/Sao_Paulo"), "pt");
  assert.strictEqual(d("auto", ["en-US"], "Asia/Tokyo"), "ja");
  assert.strictEqual(d("auto", ["en-US"], "Europe/Kyiv"), "uk");
  assert.strictEqual(d("auto", ["fr-CH"], "Europe/Zurich"), "fr");           // kraj wielojezyczny
  assert.strictEqual(d("auto", ["en-GB"], "Europe/Zurich"), "de");
  assert.strictEqual(d("auto", ["en-MX"], "UTC"), "es");                      // kraj z regionu jezyka
  assert.strictEqual(d("auto", ["en-US"], "America/Chicago"), "en");         // brak dopasowania
  assert.strictEqual(d("auto", ["ko-KR"], "Asia/Seoul"), "en");              // jezyk spoza listy
  assert.strictEqual(d("auto", ["zh-Hant-TW"], "Asia/Taipei"), "zh");
  assert.strictEqual(d("xx", [], undefined), "en");
});

if (failures) { console.log(`\n${failures} FAILED`); process.exit(1); }
console.log("\nall i18n tests passed");
