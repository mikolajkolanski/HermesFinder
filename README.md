We created this app on [NASA Space Apps Challange 2026](https://www.spaceappschallenge.org/). 
I know its vibe-coded but the idea is fully ours.

# Hermes Finder: check climate claims against data from many institutions

Authors: Jakub Krawiec, Mikołaj Kolański.

You enter a **claim about climate change** on Earth or another planet (even a loose one,
copied from an article), and the backend:

1. **Plans the query with a language model** (**Gemini / OpenAI / OpenRouter**). The model
   understands the claim and picks datasets, regions, periods and the **chart type**.
   Without an API key a deterministic fallback runs instead (TF-IDF over the catalog + rules).
2. **Fetches live data from ~60 datasets by ~20 organisations**: NASA, ESA/Copernicus
   (ECMWF ERA5, Mars Climate Database), NOAA, the Met Office, JMA, Eurostat, CSIRO, universities,
   non-profits (Berkeley Earth, Our World in Data, Ember) and companies (Open-Meteo), with a
   disk cache. **One topic from several sources goes on one comparison chart**, so you can see
   where the organisations agree or differ.
3. **Computes statistics deterministically** (OLS with scipy). The language model never
   produces numbers, only query parameters, and those are strictly validated.
4. **Shows a report of charts**: lines, regional comparisons, differences, period comparisons,
   bars and **heat maps with a year slider**. **No verdict**: it never says "true" or "false";
   the decision is yours.

## Chart types (picked by the language model or the fallback)

| Type | When | Result |
| --- | --- | --- |
| `line` | one series (a region or global) | line chart + OLS trend |
| `multi_line` | 2–12 places compared (countries, continents, the EU, the world) | all series on one chart + comparison facts (latest values, gap, ratio, how many years A > B) |
| `difference` | a claim about the **difference** between areas | one A − B series + trend |
| `period_compare` | periods compared (e.g. 1980–1990 vs 2000–2010), also for 1–4 regions | small charts side by side, shared Y axis |
| `period_bands` | periods within one window | one chart with highlighted bands |
| `bars` | means per period | bar chart |
| `region_bars` | who has more/less, rankings, 3+ places | one bar per place (latest year, or the mean of the last 5 years for weather) |
| `multi_series` | different quantities for one place (e.g. electricity from coal vs renewables) | all series on one chart, same unit |
| `heatmap` | spatial pattern (POWER grid, one or many regions, up to ~40° × 60°) | **interactive map** (Leaflet, CARTO map or Esri satellite), smoothly interpolated grid, fractional-year slider with animation, values / anomaly / change modes, mask to the selected countries' borders |
| `compare_sources` | one topic from many organisations (the default) | all series on one chart, common baseline for anomalies, table of organisations, spread between sources |
| `planet_bars` | planets compared (temperature, gravity, day length…) | bars from the NASA Planetary Fact Sheet |
| (Mars) | weather on Mars | X axis = Martian season (Ls), Curiosity observations vs the ESA/CNES model |

## Project layout

```
climate-verifier/
├── flake.nix                     # Nix package + dev shell + NixOS module (services.climate-verifier)
├── TEZY_MEDIA.md                 # 25 claims from Polish media + expected charts (test corpus)
├── demo/index.html               # fictional news article for demoing the extension
├── backend/                      # Python + FastAPI
│   ├── main.py                   # POST /api/analyze, GET /api/catalog, /api/health, CORS, frontend
│   ├── config.py                 # configuration (LLM, cache, limits)
│   ├── regions.py                # 80+ regions (countries, Polish cities and voivodeships, continents, seas)
│   ├── catalog/                  # datasets.json (NASA) + datasets_external.json, built by generate_catalog.py
│   ├── rag/
│   │   ├── llm.py                # LLM planner: Gemini/OpenAI/OpenRouter + plan validation
│   │   ├── planner.py            # fallback: regexes, regions (with Polish inflection), periods, seasons
│   │   ├── retriever.py          # TF-IDF fallback for picking datasets
│   │   ├── indexer.py            # TF-IDF index → data/index.json
│   │   └── textproc.py, catalog.py
│   ├── nasa/                     # POWER (point / area mean / grid), GISTEMP, CO₂, sea level, sea ice, cache
│   ├── sources/                  # other providers, registry, dataset verification
│   └── analysis/
│       ├── pipeline.py           # card executor (all chart types)
│       ├── compare.py            # comparison cards, Mars, planets
│       └── stats.py              # OLS and data descriptions (no verdict)
├── frontend/                     # vanilla JS + Chart.js
└── extension/                    # Hermes Finder browser extension (Firefox + Chromium)
```

## Running it

Requirements: **Python 3.10+** and an internet connection (data is fetched live).

```bash
./start.sh        # Linux / macOS  (creates backend/.venv)
start.bat         # Windows
# or by hand:
cd backend && pip install -r requirements.txt && uvicorn main:app --port 8000
```

App: **http://127.0.0.1:8000** (the backend serves the frontend).

Demo article for the extension: `cd demo && python3 -m http.server 9123 --bind 127.0.0.1`,
then open http://127.0.0.1:9123/.

## NixOS / Nix (flake)

The project includes `flake.nix`: an app package, a dev shell and a NixOS module.
The first run creates `flake.lock` (`nix flake lock`) and fetches nixpkgs-25.05. If the
project is in a git repository, the files must be added to git (`git add .`), otherwise the
flake copies an empty tree.

```bash
nix run                        # server at http://127.0.0.1:8000
nix build .#climate-verifier   # one-off build -> ./result/bin/climate-verifier
nix develop                    # dev shell (backend/ + Python with dependencies)

# LLM keys through the environment, not the configuration:
GEMINI_API_KEY=... nix run
```

The packaged server listens on `CV_HOST`/`CV_PORT` (default 127.0.0.1:8000) and keeps the
cache and the TF-IDF index in `~/.local/state/climate-verifier` (the Nix store is read-only;
override with `CV_CACHE_DIR`/`CV_INDEX_PATH`).

**Troubleshooting:** since v3.0.1 the backend checks at startup that its directories are
writable. If the default location (e.g. `data/` in `/nix/store`) cannot be written, it moves the
cache and index to `~/.local/state/climate-verifier` (or `/tmp`) and logs a `[config] …` line.
If you see `Errno 30 Read-only file system …/backend/data/cache`, your source tree has an
**old `backend/config.py`** (for example only `flake.nix` copied into an older checkout).
Update all sources and run again (`nix run` rebuilds automatically).

To run it as a NixOS service (LLM keys from a secrets file):

```nix
# in the system flake.nix:
inputs.climate-verifier.url = "path:./climate-verifier";
# in a module:
imports = [ inputs.climate-verifier.nixosModules.default ];
services.climate-verifier = {
  enable = true;
  port = 8000;
  environmentFile = "/run/secrets/climate-verifier.env"; # GEMINI_API_KEY=...
};
```

The service runs as a DynamicUser with the state directory `/var/lib/climate-verifier` and
hardening (ProtectSystem=strict, PrivateTmp).

## Language model configuration (planner)

You can also put the key in a `.env` file in the project directory (`start.sh` loads it; the
file is in `.gitignore`). The backend works **without a key** (TF-IDF fallback + rules). With a
key, a language model interprets the claims, which is recommended for loose claims from articles:

```bash
# Gemini (recommended, free tier in AI Studio):
export GEMINI_API_KEY=...          # or GOOGLE_API_KEY
export GEMINI_MODEL=gemini-3-flash-preview   # default
export GEMINI_FALLBACK_MODELS=gemini-3.5-flash-lite,gemini-3.1-flash-lite   # tried on 503/404/timeout

# OpenAI:
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-4o

# OpenRouter (any model in the OpenRouter catalog):
export OPENROUTER_API_KEY=...
export OPENROUTER_MODEL=google/gemini-2.5-flash

# force a provider (optional; by default the first available key wins):
export LLM_PROVIDER=gemini   # gemini | openai | openrouter
```

The model's answer is **strictly validated**: unknown datasets, regions or chart types and
years out of range are rejected; any model error falls back to the rules automatically.

## What the planner handles (examples)

Claims can be in English, Polish, German, French, Spanish or Italian. The interface of the
page and of the extension is available in 13 languages (English, Polish, German, French,
Spanish, Italian, Portuguese, Dutch, Czech, Swedish, Ukrainian, Japanese, Chinese), picked by
country and browser language with English as the fallback (a language picker overrides it).
Content generated by the server (card titles, notes, the summary) stays in English.

- "Poland has warmed by 3 degrees in 20 years" → air temperature for Poland from several
  sources + trend,
- "Temperature in Poland and Germany…" → `multi_line` (2 series, 2 trends),
- "…in the Baltic compared with the Pacific" → 2 sea series on one chart (air temperature over
  the sea surface, as the caption says),
- "Warming in 1980–1990 compared with 2000–2010" → `period_compare` (two small charts side by
  side, shared Y axis, means labelled),
- "Temperature in Poland and Germany: 1980–1990 and 2000–2010" → `period_compare` for **two
  regions at once**,
- "A map of temperature in Poland" → a heat map: Esri World Imagery with place labels,
  interpolated temperature from 192 POWER grid points and a year slider; hovering shows the
  value at a point.

## Datasets (multi-source comparisons)

Full list: `GET /api/catalog` (with organisation type and verification status).
Catalog: `backend/catalog/datasets.json` (NASA) + `datasets_external.json` (the rest).

| Topic | Sources on one chart |
| --- | --- |
| global temperature | NASA GISTEMP v4 · NOAA NOAAGlobalTemp · Met Office HadCRUT5 · Berkeley Earth (non-profit) · JMA (Japan) · Copernicus ERA5 (ECMWF/ESA/EU) |
| regional/country temperature | NASA POWER · ECMWF ERA5 and ERA5-Land (via Open-Meteo, a company) · Berkeley Earth (countries/continents, to 2020) · Copernicus ERA5 (via OWID, countries) |
| regional precipitation | NASA POWER · ERA5 · ERA5-Land (Open-Meteo) |
| ocean temperature | NOAA ERSST · NOAA OISST (Climate Reanalyzer, Univ. of Maine; to 2023) · Copernicus ERA5 SST (to 2023) |
| sea level | NASA altimetry · NOAA altimetry · CSIRO (1880–2013) · Univ. of Hawaii (tide gauges) |
| tide gauges | PSMSL: Gdańsk, Świnoujście, Stockholm, Brest, Newlyn, New York, Honolulu, Sydney |
| CO₂ | NOAA/NASA Mauna Loa · NOAA GML (global mean); CH₄ and N₂O separately (NOAA GML) |
| country/world emissions | Global Carbon Project (CO₂) · Climate Watch/WRI (all GHG) · Eurostat (EU); also CO₂ per capita and renewables share (Ember) |
| electricity and energy (countries, continents, EU, world) | Ember / Energy Institute via OWID: electricity from coal, gas, oil, nuclear, renewables, solar, wind, hydro, fossil, low-carbon (TWh) and their shares (%), total generation and demand, primary energy, energy per capita |
| detailed emissions | Global Carbon Project / Jones et al. via OWID: CO₂ from coal, oil, gas, cement and land use, methane, N₂O, consumption-based, cumulative, share of global, per GDP, GHG per capita, population |
| sea ice | NSIDC: Arctic (September) and Antarctic (September) |
| Sun | SILSO (Royal Observatory of Belgium): sunspots |
| Mars | NASA Curiosity REMS (CAB-INTA/JPL, observations 2012–now): max/min air temperature, ground temperature, pressure · Mars Climate Database (LMD/CNES/ESA, **model**) |
| planets | NASA NSSDCA Planetary Fact Sheet: mean temperature, gravity, distance from the Sun, day length, pressure, orbital period, diameter |

Anomalies use different baselines in their sources (1901–2000, 1951–1980, 1961–1990,
1991–2020). A comparison card subtracts from each series its own mean over a **common period**
(1991–2020 by default, 1993–2012 for sea level; if a source does not cover it, the longest
common run of years). That is the only transformation: a constant shift, which changes neither
the shape nor the trend. A source that does not support the region or the month filter is left
out, with the reason shown.

### Picking data: every part of the claim

The language model has full freedom over **how many cards and which chart types** a claim needs
(up to `CV_MAX_CARDS`, default 12): each sub-claim gets its own card ("Germany produces more
electricity from renewables than Poland, but less from coal" = two comparison cards), compared places
go on one chart, and a heat map can cover several countries or a whole continent. Validation still
checks every dataset, region and year against the catalog; the model never supplies numbers.

**Missing data is said out loud.** If part of a claim has no dataset (e.g. "CO₂ from cows"), the
model plans cards for the rest and returns `missing[]` with a message written for that claim, in the
UI language (`options.language`). If nothing fits (nonsense, an off-topic sentence), the response has
no cards and `no_data: true`, and the page shows "No data available" ("Brak dostępnych danych").
The rules-only planner does the same when no topic of the catalog is named in the claim.

The rules-only planner (no API key) is stricter (`normalize_queries(strict=True)`):
- **Cards only for quantities named in the claim:** the topic guard works in 6 languages. No
  "for context" cards.
- **One card per quantity, place and season:** duplicates and variants of the same quantity
  (e.g. Tmax next to the mean) are removed.
- **Maps only on request:** a heat map appears when the claim is about a spatial pattern.
- **Comparisons always use the full set of sources for the topic.**
- **Cards the claim needs are added:** a region compared with the world gets a global card,
  "rose…, and winters…" gets an annual and a winter card, and CO₂ next to another quantity gets
  its own card.
- **Unambiguous mappings:** Baltic sea level means Baltic tide gauges, and a named sea means the
  sea region, not land. A Curiosity rover reading means Curiosity data, and Mars' mean
  temperature means the planets card.
- **`options.context` (e.g. the article title):** only fills in a missing place. A claim about
  the world stays global.

Unit tests without network (mocked NASA POWER, data and model answers):

```bash
cd backend && python -m pytest tests -q
```

Regression test (26 claims from articles in 5 languages; extra cards from the model are warnings):

```bash
cd backend && python tests/eval_planner.py http://127.0.0.1:8000          # with the LLM
cd backend && python tests/eval_planner.py http://127.0.0.1:8000 --nollm  # rules only
```

Result: 26/26 in both modes.

### Dataset verification

```bash
cd backend && python -m sources.verify          # --force = skip the cache
```

For every dataset: availability, number of points, continuity, how up to date it is, finite
values within a physically plausible range. Across each topic: correlation and RMSE between
organisations after shifting to a common baseline. The result goes to
`data/verification_report.json` and `GET /api/verification`.

Not available without registration (checked and skipped): ESA CCI (NetCDF only, via CEDA),
Scripps CO₂ (changed addresses), JAXA, OSI SAF, World Bank CCKP (502), Solar System OpenData
(needs a key), NASA InSight API (DEMO_KEY limit).

## Browser extension

`extension/` holds the Hermes Finder extension for Firefox, Chromium and Opera (packages:
`extension/build.sh`). On article pages it highlights checkable climate claims; a click (or
"Analyze with Hermes Finder" in the right-click menu on selected text) shows a summary in the
corner of the page: 1–6 key charts with values on hover, legends that hide and show series, and
a **More** button that opens the full analysis (the normal search on this page) in a new tab.
By default the extension talks to the public server **https://hermesfinder.us** (a local server
can be set in its options). Installation and details: `extension/README.md`.

**Download from the page:** the "Install the browser extension" section (link in the page header,
`/#install`) offers packages for Firefox (`.xpi`), Chrome/Edge/Brave and Opera (`.zip`) with
step-by-step instructions; the visitor's browser is highlighted. The server builds the packages on
the fly from `extension/` (`backend/extension_pkg.py`, the same contents as `extension/build.sh`):

```
GET /api/extension                     # version + package links
GET /api/extension/firefox|chromium|opera
```

A Firefox package signed by Mozilla (`extension/sign-firefox.sh` → `dist/signed/*.xpi`, or the path
in `CV_FIREFOX_XPI`) is served instead of the unsigned one when it matches the current version; it
installs permanently with one click. Browser logos come from the `@browser-logos/*` packages on jsDelivr
(pinned versions); without access to the CDN the cards show coloured letter badges instead.

## API

```
GET  /api/health                       # status + active LLM provider
GET  /api/catalog                      # dataset catalog (providers, topics, verification status)
GET  /api/verification                 # dataset verification report
POST /api/analyze                      # {"thesis": "...", "options": {...}}
```

Response: `summary`, `cards[]` (type, title, series + trends, statistics, facts, a caption with
regions/periods/source; comparison cards also have `providers[]`, `skipped[]`, `baseline`),
`sources[]` (organisations used in the answer), `missing[]` (`{subject, message}`: parts of the
claim with no data), `no_data` (true when there is nothing to show), `planner` (which planner
decided, the model, any LLM error, `years_shown` when a year range was set). Options:
`start_year`/`end_year` (1850 to the current year, start ≤ end; anything else returns 422; the
range applies to every card, including plans from the language model), `force_refresh`,
`disable_llm`, `context`, `language` (UI language for the missing-data messages).

## Limitations

- POWER is a model reanalysis (MERRA-2/CERES), not station measurements.
- The OISST (Climate Reanalyzer) and ERA5 SST (Climate Pulse) files have not been updated since
  2024 and show years up to 2023; Berkeley Earth regional files end in 2020.
- Open-Meteo limits requests per minute: the first download for a region can take a moment
  (the backend retries after 429), then the data stays cached for 30 days.
- The MCD model (Mars) takes ~8 s per request; the backend fetches it in the background at
  startup (`CV_WARM_CACHE=0` turns that off) and caches it for a year.
- Mars data is for Gale crater (where the rover works), not the whole planet.
- NASA POWER's regional endpoint accepts 2–10° per axis: smaller areas are widened to 2°, larger
  ones are split into tiles and merged (a heat map can use up to 40 tiles, e.g. Europe = 20,
  China = 28). The data covers the bounding box; the map can mask it to the country borders
  (Natural Earth via world-atlas, bundled in `frontend/vendor/`).
- Base maps: CARTO (© OpenStreetMap contributors) or Esri World Imagery; without internet the map
  shows the data layer and borders on a plain background.
- Periods shorter than ~10 years give weak regression power.
- Chart.js, Leaflet, topojson-client and the country borders are bundled in `frontend/vendor/`.
