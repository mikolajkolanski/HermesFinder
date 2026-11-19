# Hermes Finder: browser extension for Firefox, Chromium and Opera

The browser extension of Hermes Finder, Manifest V3: Firefox 128+, Chromium/Chrome/Brave/Edge 121+ and Opera 109+. The code is shared; only the manifests differ, and `build.sh` generates them.

- **On an article page** it highlights sentences that are climate claims you can check against data (e.g. "temperature in Poland has risen by 2°C since 1990").
- **Clicking a highlight** opens a summary in the corner of the page: 1–6 key charts (3 by default) with one key number under each. Hover over a chart (or use the arrow keys) to read the value for any year; **Expand** shows one chart on most of the screen with full axes and a table of values. A new claim replaces the old one.
- **Legends are filters:** click a series name to hide or show it (the axis rescales to the visible series). Trend lines are dashed on the chart and in the legend, and can be hidden too.
- **More** (left of the × in the panel header) opens the full analysis in a new tab: the Hermes Finder page with the claim already searched (`/?q=…`, in the extension’s language). The article tab stays as it was. "All charts in the full analysis" under the summary does the same.
- **The toolbar icon** (or **Alt+Shift+T**) opens a popup with a field for your own claim, the summary, and the list of claims found on the current page. Clicking a claim from the list closes the popup and opens the corner panel on the page (one view at a time). **More** opens the full analysis in a new tab. The popup only mentions the server when it does not respond. The icon shows the number of claims.
- **The right-click menu** offers **"Analyze with Hermes Finder"** on selected text (and in Firefox "Analyze the link text with Hermes Finder" on a link). It opens the same corner panel as a highlight. If the page was open before the extension was installed or reloaded, the extension injects its script first; only pages closed to extensions (about:, add-on stores) fall back to a new tab.
- **13 languages:** English, Polish, German, French, Spanish, Italian, Portuguese, Dutch, Czech, Swedish, Ukrainian, Japanese and Chinese. "Automatic" picks the browser language if it is one of them, otherwise the language of your country (from the system time zone or the browser region), otherwise English. Content from the server (card titles, series names) stays in English.
- **Settings** (about:addons → Hermes Finder → Options): language, server address, language model, automatic scanning, sensitivity, highlight limit and style, excluded sites, number of charts in the summary and panel position.

The extension computes nothing itself. It sends the claim to the Hermes Finder server (`POST /api/analyze`), by default **https://hermesfinder.us**, which returns data from NASA, Copernicus, NOAA and other institutions. Only the claim (and the article title as context) is sent; claim detection runs locally and the rest of the page text is never sent anywhere. Parts of a claim without data are listed under the charts ("No data for this part of the claim"), and a claim with no data at all shows "No data available".

## Installation

The extension works out of the box with the public server `https://hermesfinder.us`. To use your own server instead, start it (`./start.sh` in the project directory, `http://127.0.0.1:8000`) and enter its address in the extension settings. Installations that still had the old local default (`http://127.0.0.1:8000`) are switched to `https://hermesfinder.us` once, on the first start of version 2.2.

Build the packages:

```bash
extension/build.sh
#  dist/hermes-finder-<version>.xpi            Firefox
#  dist/chromium/                              Chromium: "Load unpacked"
#  dist/hermes-finder-<version>-chromium.zip   Chromium as a package
#  dist/opera/                                 Opera: "Load unpacked"
#  dist/hermes-finder-<version>-opera.zip      Opera as a package (addons.opera.com)
```

### Opera

1. Open `opera://extensions` and turn on "Developer mode".
2. Click "Load unpacked" and pick `dist/opera/`.

### Chromium / Chrome / Brave / Edge

1. Open `chrome://extensions` and turn on "Developer mode".
2. Click "Load unpacked" and pick `dist/chromium/` (not `extension/`: that has the Firefox manifest).

The installation is permanent and site access is granted on install. After a rebuild, click "Reload" on the extension.

### Firefox: quick, until the browser closes

1. Open `about:debugging#/runtime/this-firefox`.
2. Click "Load Temporary Add-on…" and pick `dist/hermes-finder-<version>.xpi` (or `extension/manifest.json`).

Site access is granted right away.

### Firefox: permanently

Regular Firefox only installs add-ons signed by Mozilla permanently. Two options:

- **Signing (free, does not publish the add-on):**
  1. Create an account on addons.mozilla.org.
  2. Generate API keys at https://addons.mozilla.org/developers/addon/api/key/.
  3. Run (it builds the package and signs exactly its contents):
     ```bash
     AMO_JWT_ISSUER=YOUR_KEY AMO_JWT_SECRET=YOUR_SECRET extension/sign-firefox.sh
     ```
     Each signing needs a new `version` in `manifest.json`.
  4. Install the signed file from `dist/signed/` via about:addons → gear icon → "Install Add-on From File…".
- **Firefox Developer Edition, Nightly or ESR:** set `xpinstall.signatures.required = false` in `about:config` and install the unsigned `.xpi` from a file.

The add-on ID stayed `teza-w-danych@climate-verifier.local` (the project's earlier name), so updating from older versions keeps your settings.

## How claims are detected

Locally, offline, about 0.1 ms per paragraph (`shared/claims.js`), in any language. The vocabulary covers EN, PL, DE, FR, ES, IT, PT and NL, and numbers with units are recognised regardless of language.

1. The extension finds the article body (`article`, `main` or the block with the most paragraph text). It skips menus, page headers, footers, forms and code.
2. It splits paragraphs into sentences, aware of abbreviations ("w 2020 r.", "40 st. C", "z.B.", "prof."). Non-breaking spaces (`&nbsp;`) from news sites are normalised.
3. A sentence must state something about a **measured quantity**: temperature, sea level, sea ice, CO₂ and other gases, emissions, precipitation, or temperature on Mars or a planet. It scores points for:
   - a value with a unit,
   - a period ("since 1990", "per decade", "in 2025"),
   - a change or a record,
   - a place.
4. Penalties go to forecasts ("will", "by 2050", future years), explanations of causes, attribution ("CO₂ is responsible for 42% of warming"), definitions, chart descriptions, questions, single weather readings and the distant past. Ads, newsletters and "read also" boxes are rejected.
5. The best claims are highlighted: first one from each topic (temperature, sea, ice, gases…), then the rest by score. Up to 6 highlights by default, more in long articles.

**Tested on 19 real articles in 6 languages.** Sources: wp.pl, RMF24, OKO.press, Spider's Web, National Geographic, naukaoklimacie.pl, SmogLab, Teraz Środowisko, Demagog, Carbon Brief, Inside Climate News, Space.com, Klimareporter, Greenreport, Futura, Climática, Newtral. Result: 36 of 38 claims marked by hand as required, 0 forbidden fragments (forecasts, ads, politicians' quotes, author notes), 5.4 highlights per article on average.

## Look and panel

- **Highlight:** a dotted underline in a colour matched to the page text and a small dot at the end of the claim, with a light background on hover. The style comes from the manifest (`content/page.css`), so it also works on news sites with a strict CSP.
- **Corner panel:** an extension page in a frame (`panel/`). The site's CSS and CSP do not apply to it, and its height follows the content. Each new claim gets a fresh frame, so an old answer never shows under a new claim.
- **Requests:** the panel and the popup call the server directly (results cached for 30 minutes), so a long analysis does not break when the browser suspends the background script.
- **Context:** the article title is sent with the claim (the `context` field). The server uses it **only** to fill in a missing place: "Desde los 60, la temperatura ha subido 0,3 ºC" in an article about Spain gets data for Spain. A claim about the world stays global.

## Files

```
extension/
├── manifest.json          # Manifest V3 for Firefox (background.scripts, menus)
├── build.sh               # dist/: Firefox .xpi + Chromium variant (service worker, contextMenus)
├── background.js          # icon badge, context menu
├── content/content.js     # article scan, highlights, panel frame (incl. the expanded view)
├── content/page.css       # highlight style (injected by the browser, CSP-proof)
├── panel/                 # corner panel (extension document in an iframe)
├── popup/                 # popup from the toolbar icon
├── options/               # settings
├── shared/api.js          # server requests + 30-minute cache, opening the panel in a tab
├── shared/claims.js       # claim detection
├── shared/render.js       # key charts, SVG charts, hover values, legend filters, expanded chart view
├── shared/settings.js     # default settings
├── shared/langdetect.js   # language by setting / browser / country (same file as frontend/langdetect.js)
├── shared/i18n.js         # interface texts in 13 languages
├── _locales/              # extension description in the browser's add-on list
├── tests/i18n.test.js     # node extension/tests/i18n.test.js (not packaged)
└── icons/                 # Hermes Finder icon (hermes-finder.svg + PNGs)
```
