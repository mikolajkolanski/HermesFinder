#!/usr/bin/env bash
# Buduje rozszerzenie dla trzech przegladarek z jednego kodu:
#   dist/hermes-finder-<version>.xpi            Firefox (manifest.json bez zmian)
#   dist/chromium/                             Chromium/Chrome/Brave/Edge: "Zaladuj rozpakowane"
#   dist/hermes-finder-<version>-chromium.zip   to samo jako paczka (Chrome Web Store)
#   dist/opera/                                Opera: opera://extensions -> "Load unpacked"
#   dist/hermes-finder-<version>-opera.zip      to samo jako paczka (addons.opera.com)
# Roznice w manifescie Chromium/Opery: tlo jako service worker (nie background.scripts),
# uprawnienie contextMenus (nie menus), bez browser_specific_settings.
set -euo pipefail
cd "$(dirname "$0")"

FILES=(background.js content popup options panel shared icons _locales)
version=$(python3 -c 'import json; print(json.load(open("manifest.json"))["version"])')
mkdir -p ../dist
rm -f ../dist/hermes-finder-*.xpi ../dist/hermes-finder-*.zip

# ---- Firefox
xpi="../dist/hermes-finder-${version}.xpi"
zip -r -q -X "$xpi" manifest.json "${FILES[@]}" -x '*.DS_Store' '*~'
echo "Firefox:  $(realpath "$xpi")"

# ---- Chromium i Opera (ten sam silnik, manifest w wariancie Chromium)
build_chromium() {   # $1 = nazwa (chromium|opera)
  local name=$1 out=../dist/$1
  rm -rf "$out"
  mkdir -p "$out"
  cp -r "${FILES[@]}" "$out/"
  python3 - "$out/manifest.json" "$name" <<'PY'
import json, sys
m = json.load(open("manifest.json", encoding="utf-8"))
m["background"] = {"service_worker": "background.js"}   # skrypty laduje importScripts w background.js
m["permissions"] = ["contextMenus" if p == "menus" else p for p in m["permissions"]]
m.pop("browser_specific_settings", None)
# Opera 109+ (Chromium 123) i Chromium 121+: MV3, storage.session, scripting
m["minimum_chrome_version"] = "123" if sys.argv[2] == "opera" else "121"
json.dump(m, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
  local zipf="../dist/hermes-finder-${version}-${name}.zip"
  (cd "$out" && zip -r -q -X "../$(basename "$zipf")" .)
  echo "$(printf '%-9s' "${name^}:") $(realpath "$out")  (and $(realpath "$zipf"))"
}
build_chromium chromium
build_chromium opera
