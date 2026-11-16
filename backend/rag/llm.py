"""LLM-first planner: wybor dostawcy (Gemini / OpenAI / OpenRouter).

LLM dostaje teze, katalog zbiorow, liste regionow i dozwolone typy wykresow,
a zwraca JSON-owy plan kart. Plan jest SCISLE WALIDOWANY: nieznane zbiory,
regiony, lata czy typy wykresow sa odrzucane - model nigdy nie moze wstrzyknac
arbitralnych parametrow ani liczb. Bez klucza API pipeline korzysta z
deterministycznego fallbacku (TF-IDF + reguly).

Priorytet: LLM_PROVIDER (gemini|openai|openrouter) -> pierwszy dostepny klucz.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

import config
from rag.catalog import load_catalog
from regions import region_by_id, regions_for_llm

CHART_TYPES = ["line", "multi_line", "difference", "period_compare",
               "period_bands", "bars", "heatmap", "compare_sources",
               "planet_bars"]
MAX_COMPARE_SOURCES = 7

SYSTEM_PROMPT = """You are a query planner for Earth and planetary climate data in Hermes Finder, \
an app that shows people the data behind a claim. The user gives a claim or a question (often \
informal, taken from a news article; it may also be about Mars or other planets). Your job is to \
plan 1-4 data cards that let the user judge the claim THEMSELVES. You NEVER judge whether the \
claim is true and you NEVER produce data values - only query parameters (you pick datasets).

OUTPUT LANGUAGE: every text you write ("summary", "title", "note") MUST be in English, whatever \
the language of the claim or of the article context (Polish, German, French, Spanish, Italian...). \
Do not copy or quote the claim in its original language. Write place names in English \
(Poland, Baltic Sea, Warsaw, Gdansk, Mediterranean Sea).

The catalog holds datasets from MANY organisations: agencies (NASA, NOAA, JMA, Met Office, \
Eurostat), Copernicus/ECMWF/ESA, universities (Univ. of Hawaii, Univ. of Maine), non-profits \
(Berkeley Earth, Our World in Data, Ember) and companies (Open-Meteo). Datasets with the same \
"topic" describe THE SAME quantity from different sources. MAIN RULE: when a topic has several \
datasets in the catalog, show them together in ONE comparison card so the user can see where the \
organisations agree or differ.

Reply ONLY with a JSON object (no markdown):
{
  "summary": "1-2 sentences in English: what data was prepared (no verdict on the claim)",
  "queries": [
    {
      "dataset_id": "catalog id (for compare_sources: the first of dataset_ids)",
      "dataset_ids": ["id1", "id2", ...] | [],
      "body_ids": ["mars", "earth", ...] | [],
      "region_ids": ["region id from the list"] | [],
      "start_year": int,
      "end_year": int,
      "months": [1-12] | [],
      "chart_type": "compare_sources" | "line" | "multi_line" | "difference" | "period_compare" | "period_bands" | "bars" | "heatmap" | "planet_bars",
      "periods": [{"start": int, "end": int}] | [],
      "title": "short title in English",
      "note": "1 sentence in English: what this card shows"
    }
  ]
}

MOST IMPORTANT RULE - MINIMALISM ("no more, no less"):
- Each card shows a quantity NAMED in the claim, for a place NAMED in the claim. One quantity in \
one place = ONE card (usually compare_sources). One card is usually enough.
- Do NOT add cards "for context" or "for comparison" when the claim does not ask for it: no \
global temperature for a claim about a country, no CO2 for a claim about temperature or \
emissions, no oceans, ice, tide gauges, maps or period comparisons the claim does not ask for.
- Add a second (third) card ONLY when the claim itself sets two things side by side: "Europe is \
warming faster than the world" / "the fastest in the world" / "szybciej niż średnia globalna" / \
"the Arctic is warming faster than the rest of the planet" -> region + global_temperature; \
"temperature has risen and winters are milder" -> whole year + winter (months [12,1,2]); \
"CO2 and methane" -> co2 + methane; "Wroclaw and Gdansk" -> one multi_line card with two regions.
- Do not make two cards for the same quantity and place (source comparison + periods + map): \
pick one. heatmap only when the claim talks about a map or spatial distribution.
- A season or months in the claim -> months (winter [12,1,2], summer [6,7,8], January and \
February [1,2]).
- "hot days", "maximum temperature" -> topic regional_tmax; "frost", "minimum" -> regional_tmin.
- The claim may be in any language (EN, PL, DE, FR, ES, IT...); understand it, but answer in English.
- If the claim gives no place ("hierzulande", "w naszym kraju", "la península", "u nas", \
"in our country"), take the place from the "source_context" field (the article title). Do NOT \
treat the context as a separate claim.

SELECTION RULES:
- "compare_sources" (PREFERRED): dataset_ids = 2-7 datasets with THE SAME topic (take them from \
the "topics" map), e.g. global_temperature -> gistemp_global, noaa_global_temp, hadcrut5, \
berkeley_global, jma_global, era5_global_temp. Pick different providers; no duplicates. For \
regional topics (regional_temperature, regional_precipitation) give ONE region in region_ids; \
datasets that do not support the region are skipped automatically. For global datasets \
region_ids = [].
- Topics: global_temperature (global anomalies), regional_temperature (region/country), \
ocean_temperature, sea_level, tide_gauge_sea_level (tide gauges: pick 2-4 relevant ones), co2, \
regional_precipitation, emissions (CO2/GHG of a country or the world), mars_max_temp, \
mars_min_temp, mars_pressure (NASA Curiosity observations vs the ESA/CNES MCD model).
- MARS / planets: a question about temperature on Mars -> compare_sources for mars_max_temp \
(mars_rems_max_temp + mars_mcd_max_temp) and mars_min_temp (mars_rems_min_temp + \
mars_mcd_min_temp), plus planet_bars with dataset_id "planet_mean_temp" and body_ids \
["mars","earth"]. Mars data is seasonal (Ls axis), so start_year/end_year do not matter (give the \
last 25 years). Other planets/metrics: planet_bars with dataset_id planet_* (mean_temp, gravity, \
distance_sun, day_length, surface_pressure, orbital_period, diameter) and body_ids from: \
mercury, venus, earth, moon, mars, jupiter, saturn, uranus, neptune, pluto (empty = all).
- chart_type "line": one series (1 region or global) - only when the topic has one dataset.
- "multi_line": the same dataset for 2-4 regions (e.g. Poland and Germany).
- "difference": the difference between two regions (a claim about a gap between areas).
- "period_compare": compares 2-4 periods (periods), can be combined with 1-4 regions.
- "period_bands": one chart with highlighted period bands (one series).
- "bars": bars - mean per period (periods).
- "heatmap": heat map of an area - ONLY POWER datasets (connector power) and a bbox region; as a \
SEPARATE query next to the comparison/line card.
- For seasons/months (months) some datasets have no monthly data - they will be skipped; do not \
try to work around this.
- Period: if the claim gives no years, use the last 25 years. Do not go past the current year.
- WATER / ocean temperature worldwide -> ocean_temperature. A specific sea (Baltic, \
Mediterranean, "mari italiani", "Ostsee") -> regional_temperature with that sea's region (air \
temperature over the sea; say so in the title), NOT the global ocean_temperature.
- At most 4 queries; do not repeat identical cards.
- summary, title and note: English, concise, no verdict on the claim."""


# ------------------------------------------------------------------ provider --
def llm_info() -> dict[str, Any]:
    """Aktywny dostawca LLM (lub None, gdy brak klucza -> fallback)."""
    pref = config.LLM_PROVIDER
    candidates = [
        ("gemini", config.GEMINI_API_KEY, config.GEMINI_MODEL),
        ("openai", config.OPENAI_API_KEY, config.OPENAI_MODEL),
        ("openrouter", config.OPENROUTER_API_KEY, config.OPENROUTER_MODEL),
    ]
    if pref:
        candidates = [c for c in candidates if c[0] == pref]
    for name, key, model in candidates:
        if key:
            return {"provider": name, "model": model, "available": True}
    return {"provider": None, "model": None, "available": False}


LAST_MODEL_USED: str | None = None
LAST_ERROR: str | None = None


def last_model_used() -> str | None:
    return LAST_MODEL_USED


def _call_gemini(prompt: str) -> str:
    """Gemini (Google AI Studio): klucz w naglowku, ponowienia przy 429/5xx
    i lancuch modeli zapasowych (modele preview bywaja przeciazone)."""
    global LAST_MODEL_USED
    import time
    models = [config.GEMINI_MODEL] + [m for m in config.GEMINI_FALLBACK_MODELS
                                      if m != config.GEMINI_MODEL]
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1,
                             "responseMimeType": "application/json"},
    }
    last_err: Exception | None = None
    deadline = time.monotonic() + config.LLM_TOTAL_BUDGET
    for model in models:
        remaining = deadline - time.monotonic()
        if remaining < 3:
            break
        try:
            resp = httpx.post(
                f"{config.GEMINI_BASE_URL}/models/{model}:generateContent",
                headers={"x-goog-api-key": config.GEMINI_API_KEY},
                json=body, timeout=min(config.LLM_TIMEOUT, remaining))
        except httpx.TransportError as exc:  # timeout / siec -> nastepny model
            last_err = RuntimeError(f"{model}: {type(exc).__name__}")
            continue
        if resp.status_code in (404, 429, 500, 502, 503, 504):
            # przeciazony lub niedostepny -> od razu kolejny model z listy
            last_err = RuntimeError(f"{model}: HTTP {resp.status_code}")
            continue
        resp.raise_for_status()
        parts = resp.json()["candidates"][0]["content"]["parts"]
        LAST_MODEL_USED = model
        return "".join(p.get("text", "") for p in parts)
    raise last_err or RuntimeError("Gemini niedostepny")


def _call_openai(base_url: str, api_key: str, model: str, prompt: str) -> str:
    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=config.LLM_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


# ------------------------------------------------------------------- prompt ---
def _build_prompt(thesis: str, fallback_plan: dict[str, Any],
                  context: str | None = None) -> str:
    catalog = load_catalog()
    cur = _current_year()
    ds_list = [
        {
            "id": ds_id,
            "title": ds["title"],
            "unit": ds["unit"],
            "regional": ds["supports_regions"],
            "connector": ds["connector"],
            "coverage_start": ds["coverage"]["start"],
            "topic": ds.get("topic"),
            "provider": (ds.get("provider") or {}).get("org"),
            "provider_type": (ds.get("provider") or {}).get("type"),
            "body": ds.get("body", "earth"),
            "data_type": ds.get("data_type"),
        }
        for ds_id, ds in catalog.items()
    ]
    topics: dict[str, list[str]] = {}
    for ds_id, ds in catalog.items():
        topics.setdefault(ds.get("topic") or ds_id, []).append(ds_id)
    topics = {t: ids for t, ids in topics.items() if len(ids) >= 2}
    payload = {
        "claim": thesis,
        "current_year": cur,
        "dataset_catalog": ds_list,
        "topics": topics,
        "regions": regions_for_llm(),
        "chart_types": CHART_TYPES,
        "rule_based_draft_plan": fallback_plan,
        "source_context": (context or "")[:300] or None,
        "output_language": "English",
    }
    return json.dumps(payload, ensure_ascii=False)


def _current_year() -> int:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).year


# ------------------------------------------------------------ jezyk tekstow --
# Teksty z LLM (summary/title/note) musza byc po angielsku. Gdy model mimo
# polecenia odpowie w jezyku tezy, tekst jest odrzucany i karta dostaje
# angielski tytul z backendu. Nazwy miejsc (Gdańsk, Kraków) nie przeszkadzaja,
# bo liczymy slowa funkcyjne, a nie znaki diakrytyczne.
_FOREIGN_WORDS = set("""
w we z ze na się jest są oraz dla od że przez po przy jak ale lub czy nie tylko także też
roku lat latach latami średnia średnie średniej temperatura temperatury wzrost wzrosła poziom
morza morze opady emisje dane danych zbiorów źródeł porównanie porównania okres okresy okresów
zima zimy lato polska polski polsce świat świata świecie globalna globalnej powietrza wody
pokazuje przedstawia przygotowano wykres karta karty między
der die das und ist sind mit von für den dem des eine einer ein auf im zum zur über seit
nicht auch wird wurde durchschnittliche jahr jahren jahre welt deutschland vergleich daten
le la les des du et est sont avec pour dans une sur au aux par depuis moyenne année années
monde données comparaison niveau mer
el los las del y es son con para por una al desde entre sobre año años mundo datos media
il gli della delle dei degli con per nel nella anno anni dati mondo
""".split())
_ENGLISH_WORDS = set("""
the of and in on for to from with by at is are was were this that these shows show showing
since between per across over data average mean annual temperature level sea compared vs
""".split())


def _is_english(text: str) -> bool:
    words = re.findall(r"[^\W\d_]+", text.lower())
    if not words:
        return True
    foreign = sum(w in _FOREIGN_WORDS for w in words)
    english = sum(w in _ENGLISH_WORDS for w in words)
    if foreign == 0:
        return True
    return foreign < 2 and english > foreign


def _english_or_none(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()[:limit]
    if not text:
        return None
    if not _is_english(text):
        NON_ENGLISH_DROPPED.append(text)
        return None
    return text


NON_ENGLISH_DROPPED: list[str] = []


# -------------------------------------------------------------- walidacja ----
def _valid_years(s: Any, e: Any) -> tuple[int, int] | None:
    try:
        s, e = int(s), int(e)
    except (TypeError, ValueError):
        return None
    cur = _current_year()
    if not (1800 <= s < e <= cur + 1):
        return None
    return s, e


def _valid_months(raw: Any) -> list[int] | None:
    if not isinstance(raw, list) or not raw:
        return None
    months = sorted({int(m) for m in raw if isinstance(m, (int, float))
                     and 1 <= int(m) <= 12})
    return months or None


def _valid_regions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rid in raw:
        if not isinstance(rid, str) or rid in seen:
            continue
        reg = region_by_id(rid)
        if reg:
            seen.add(rid)
            from regions import region_dict
            out.append(region_dict(reg))
        if len(out) >= 4:
            break
    return out


def _valid_periods(raw: Any) -> list[dict[str, int]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, int]] = []
    for p in raw[:4]:
        if isinstance(p, dict):
            years = _valid_years(p.get("start"), p.get("end"))
            if years:
                out.append({"start": years[0], "end": years[1]})
    return out


BODY_IDS = ["mercury", "venus", "earth", "moon", "mars", "jupiter", "saturn",
            "uranus", "neptune", "pluto"]


def _valid_bodies(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for b in raw:
        if isinstance(b, str) and b in BODY_IDS and b not in out:
            out.append(b)
    return out


def _valid_dataset_ids(raw: Any, catalog: dict[str, Any]) -> list[str]:
    """Id zbiorow z katalogu o tym samym topic co pierwszy (bez duplikatow)."""
    if not isinstance(raw, list):
        return []
    ids: list[str] = []
    topic = None
    for i in raw:
        if not isinstance(i, str) or i not in catalog or i in ids:
            continue
        t = catalog[i].get("topic")
        if topic is None:
            topic = t
        if t != topic:
            continue
        ids.append(i)
        if len(ids) >= MAX_COMPARE_SOURCES:
            break
    return ids


def validate_plan(raw: Any, thesis: str = "",
                  rule_regions: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Waliduje odpowiedz LLM -> {summary, queries[]} albo None.

    Walidacja PRZED limitem kart, by bledne wpisy na poczatku nie wycinaly
    poprawnych na koncu. Model wybiera TYLKO zbiory/regiony/lata/typy - kazde
    id jest sprawdzane wzgledem katalogu i slownika regionow.
    """
    if not isinstance(raw, dict):
        return None
    catalog = load_catalog()
    queries: list[dict[str, Any]] = []
    cur = _current_year()
    for q in raw.get("queries", []):
        if len(queries) >= config.MAX_CARDS:
            break
        if not isinstance(q, dict):
            continue
        chart = str(q.get("chart_type", "line"))
        if chart not in CHART_TYPES:
            chart = "line"

        ds_id = str(q.get("dataset_id", ""))
        dataset_ids = _valid_dataset_ids(q.get("dataset_ids"), catalog)
        if chart == "compare_sources":
            if ds_id in catalog and ds_id not in dataset_ids:
                # id glowne dolaczamy tylko, gdy ten sam topic
                dataset_ids = _valid_dataset_ids([ds_id] + dataset_ids, catalog)
            if len(dataset_ids) >= 2:
                ds_id = dataset_ids[0]
            else:
                chart = "line"
                ds_id = dataset_ids[0] if dataset_ids else ds_id
        ds = catalog.get(ds_id)
        if not ds:
            continue
        kind = ds.get("series_kind", "annual")
        if kind == "planet_metric":
            chart = "planet_bars"
        elif chart == "planet_bars":
            continue  # planet_bars tylko dla zbiorow planet_*

        years = _valid_years(q.get("start_year"), q.get("end_year"))
        if not years and kind in ("planet_metric", "seasonal_ls"):
            years = (cur - 25, cur - 1)  # lata nie maja znaczenia (dane sezonowe/wzorcowe)
        if not years:
            continue

        regions = _valid_regions(q.get("region_ids"))
        if chart == "compare_sources":
            regions = regions[:1]
            if not any(catalog[i].get("supports_regions") for i in dataset_ids):
                regions = []
        elif not ds.get("supports_regions"):
            regions = []  # zbior globalny: region z LLM nie ma znaczenia
        periods = _valid_periods(q.get("periods"))
        # heatmapa wymaga zbioru POWER + regionu bbox
        if chart == "heatmap" and (ds["connector"] != "power"
                                   or not regions
                                   or regions[0].get("type") != "bbox"):
            chart = "multi_line" if len(regions) > 1 else "line"
        # difference/multi_line wymaga >=2 regionow i zbioru regionalnego
        if chart in ("difference", "multi_line"):
            if len(regions) < 2 or not ds.get("supports_regions"):
                chart = "line"
        if chart in ("period_compare", "period_bands", "bars") and len(periods) < 2:
            chart = "line"
        queries.append({
            "dataset_id": ds_id,
            "dataset_ids": dataset_ids if chart == "compare_sources" else [],
            "body_ids": _valid_bodies(q.get("body_ids")),
            "regions": regions,
            "start_year": years[0],
            "end_year": years[1],
            "months": _valid_months(q.get("months")),
            "chart_type": chart,
            "periods": periods,
            "title": _english_or_none(q.get("title"), 140),
            "note": _english_or_none(q.get("note"), 300),
        })
    queries = normalize_queries(queries, thesis, catalog, rule_regions or [])
    if not queries:
        return None
    return {
        "summary": _english_or_none(raw.get("summary"), 400),
        "queries": queries[:config.MAX_CARDS],
    }


# zbiory z danymi miesiecznymi (filtr pory roku ma sens)
MONTHLY_CONNECTORS = {"power", "gistemp", "era5_pulse", "berkeley_region",
                      "open_meteo", "arctic_ice"}
HEATMAP_WORDS = re.compile(r"map|heatmap|cieplna|rozklad|rozkład|przestrzen|obszar"
                           r"|regionach|regiony kraju|spatial|karte|carte|mappa",
                           re.IGNORECASE)


# ta sama wielkosc w roznych wariantach - jedna karta (Tmax obok sredniej to dubel)
TOPIC_FAMILY = {"regional_temperature": "temp", "regional_tmax": "temp", "regional_tmin": "temp",
                "sea_level": "sea", "tide_gauge_sea_level": "sea",
                "emissions": "emis", "emissions_per_capita": "emis"}
TIDE_BALTIC = ["psmsl_64", "psmsl_2", "psmsl_78"]
TIDE_DEFAULT = ["psmsl_1", "psmsl_202", "psmsl_12", "psmsl_155"]


def topic_members(topic: str, catalog: dict[str, Any], with_region: bool,
                  thesis_folded: str = "") -> list[str]:
    """Wszystkie zbiory tematu (rozne organizacje) - do karty porownawczej."""
    if topic == "tide_gauge_sea_level":
        baltic = re.search(r"baltyk|baltyc|baltic|ostsee|baltique|baltico|gdansk|swinouj|polsk|polsc|szwec|sztokholm", thesis_folded)
        return [i for i in (TIDE_BALTIC if baltic else TIDE_DEFAULT) if i in catalog]
    ids = [i for i, d in catalog.items() if d.get("topic") == topic]
    if not with_region:
        ids = [i for i in ids if catalog[i].get("region_scope") not in ("any", "country", "eu")]
    return ids[:MAX_COMPARE_SOURCES]


# slowa tezy, ktore uzasadniaja dana karte (PL, EN, DE, FR, ES, IT; bez diakrytykow)
TOPIC_WORDS = {
    "global_temperature": r"global|swiat|swiec|world|welt|mond|mundo|planet|ziemi|earth|erde|terre|tierr|terra|przedindustr|pre-?industri|vorindustri|preindustri|paryski|paris|1[,.]5",
    # stezenie (nie emisje): wymaga slow o stezeniu / atmosferze
    "co2": r"ppm|stezen|koncentrac|concentrat|konzentr|mauna|keeling",
    "methane": r"metan|methan|ch4|ppb",
    "n2o": r"n2o|podtlen|nitrous|lachgas|protoxyde|oxido nitroso|protossido",
    "emissions": r"emisj|emission|emisi|ausstoss|uitstoot|spalan|kopalin|fossil|tonn|\bton",
    "emissions_per_capita": r"emisj|emission|emisi|mieszkan|capita|kopf|habitant|habitante|abitante",
    "renewables": r"oze|odnawial|renewab|erneuerbar|renouvelab|renovab|rinnovabil|wiatr|wind|solar|slonecz",
    "sea_level": r"poziom\w* (morz|ocean|baltyk|wod)|sea[- ]level|meeresspiegel|niveau|nivel|livello|zeespiegel|mareograf|tide",
    "tide_gauge_sea_level": r"baltyk|baltyc|baltic|ostsee|mareograf|tide gauge|gdansk|swinouj|wybrzez|\bport(u|ach|s)?\b",
    "ocean_temperature": r"ocean|sea surface|sst|meerestemp|temperatura (wody|morz)|water temp",
    # lod + konkretny biegun ("antarktyda" zawiera "arkty" - stad (?<!ant))
    "arctic_sea_ice": r"^(?=.*(lod|ice|eis|glace|hielo|ghiacc))(?=.*((?<!ant)arkty|(?<!ant)arctic|(?<!ant)arktis|(?<!ant)arctique|(?<!ant)artico|biegun\w* polnocn|north pole))",
    "antarctic_sea_ice": r"^(?=.*(lod|ice|eis|glace|hielo|ghiacc))(?=.*(antarkty|antarctic|antarktis|antarctique|antartid|antartic|biegun\w* poludn|south pole))",
    "regional_precipitation": r"opad|deszcz|susz|rain|precip|drought|niederschlag|regen|durre|pluie|secheres|lluvi|sequi|piogg|siccit",
    "regional_tmax": r"upal|tmax|maksym|maxim|hitze|heiss|chaleur|canicul|calor|caldo|heat|30 ?°",
    "regional_tmin": r"mroz|minim|frost|tmin|\bgel|helad|gelo|zim",
    "regional_temperature": r"temperat|ociepl|cieplej|cieplo|warm|chaud|calient|calid|cald|grad|°|stopn|degre|grado|nagrzew|ogrzew|zim|lato|winter|summer|hiver|invierno|inverno|ete\b|verano|estate",
    "solar_activity": r"slonc|sun|sonne|soleil|sol\b|plam",
    "regional_wind": r"wiatr|wichur|wind|vent|viento|vento",
    "regional_humidity": r"wilgot|humid|feucht|humed|umid",
    "regional_radiation": r"naslonecz|promieniow|slonc|radiat|strahl|rayonn|radiac|irradi|fotowolt|solar",
    "nh_temperature": r"polkul|hemisph|nordhalb|hemisfer",
}
for _t in ("mars_max_temp", "mars_min_temp", "mars_pressure", "mars_max_gts_temp", "mars_min_gts_temp"):
    TOPIC_WORDS[_t] = r"mars|martian|marsjan|curiosity|gale"


def _fold(text: str) -> str:
    import unicodedata
    t = text.lower().replace("ł", "l").replace("ß", "ss").replace("₂", "2").replace("º", "°")
    return "".join(ch for ch in unicodedata.normalize("NFD", t) if unicodedata.category(ch) != "Mn")


PLANET_WORDS = r"planet|\bmars|marsjan|martian|wenus|venus|jowisz|jupiter|merkur|mercury|saturn|\buran|neptun|pluton|pluto|ksiezyc|\bmoon|\blune|\bmond\b|uklad\w* slonecz|solar system|sonnensystem|systeme solaire|sistema solar"


def _topic_supported(topic: str, thesis_folded: str) -> bool:
    if topic.startswith("planet_"):
        return bool(re.search(PLANET_WORDS, thesis_folded))
    if topic == "co2" and re.search(r"\bco2\b|dwutlen|carbon dioxide|kohlendioxid|dioxyde de carbone|dioxido de carbono|anidride carbonica", thesis_folded) \
            and not re.search(r"emisj|emission|emisi|spalan|kopalin|fossil|ausstoss|uitstoot|tonn|\bton", thesis_folded):
        return True   # samo "CO2" bez slow o emisjach = stezenie w atmosferze
    pat = TOPIC_WORDS.get(topic)
    return True if pat is None else bool(re.search(pat, thesis_folded))


# "temperatura wzrosla od 1990, a zimy sa coraz lagodniejsze" = rok + pora roku
SEASON_SPLIT = re.compile(
    r"(wzrosl|wzrost|rosnie|ociepl|cieplej|increas|rose|risen|warmer|gestiegen|augment|hausse|aumenta|subid|cresc)"
    r".{3,}(,| a | i | and | und | et | y | e | oraz )\s*.{0,40}"
    r"(zim|lat[ao]|wiosn|jesien|winter|summer|spring|autumn|sommer|fruhling|herbst|hiver|ete|printemps|automne|invierno|verano|primavera|otono|inverno|estate|autunno)")

SEA_REGIONS = {"baltic", "mediterranean", "atlantic", "pacific", "indian_ocean", "arctic_ocean"}
MARS_AVG = re.compile(r"sredni|average|\bmean\b|durchschnitt|moyenne|\bmedia\b|promedio|ziemi|earth|erde|terre|tierra|\bterra\b|planet")
SEA_WORDS = re.compile(r"\bmorz|\bmorsk|\bsea\b|\bmeer|\bmer\b|\bmar(e|i)?\b|\bwod(a|y)\b|\bwater|\bwasser|\beau\b|\bagua|\bacqua")


def normalize_queries(queries: list[dict[str, Any]], thesis: str,
                      catalog: dict[str, Any],
                      rule_regions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Deterministyczne poprawki planu LLM: 'nie wiecej, nie mniej'.

    * temat z kilkoma zrodlami -> karta porownawcza z KOMPLETEM zrodel,
    * filtr miesiecy tylko dla zbiorow z danymi miesiecznymi,
    * heatmapa tylko, gdy teza mowi o rozkladzie przestrzennym / mapie,
    * jedna karta na (temat, regiony, miesiace) - bez duplikatow,
    * karta tylko dla tematu, o ktorym teza mowi (TOPIC_WORDS).
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    wants_map = bool(HEATMAP_WORDS.search(thesis or ""))
    folded = _fold(thesis or "")
    # strażnik tematów: karta tylko dla wielkości, o której teza mówi
    # (nigdy nie zostawiamy pustego planu - wtedy zostaje pierwsza karta)
    if thesis:
        kept = [q for q in queries
                if _topic_supported((catalog.get(q["dataset_id"]) or {}).get("topic") or "", folded)]
        queries = kept or queries[:1]
    rule_regions = rule_regions or []
    sea_rule = next((r for r in rule_regions if r["id"] in SEA_REGIONS), None)
    is_mars = bool(re.search(r"\bmars|martian|marsjan|curiosity", folded))
    for q in queries:
        ds0 = catalog.get(q["dataset_id"]) or {}
        # poziom morza + Baltyk -> mareografy baltyckie (jedyne dane dla Baltyku)
        if ds0.get("topic") == "sea_level" and re.search(r"baltyk|baltyc|baltic|ostsee|baltique|baltico", folded):
            q.update(chart_type="compare_sources", dataset_id="psmsl_64", regions=[rule_regions[0]] if rule_regions else [])
        # konkretne morze w tezie -> region morza, nie lad ("mari italiani" != Wlochy)
        if sea_rule and SEA_WORDS.search(folded) and ds0.get("supports_regions") \
                and q["regions"] and [r["id"] for r in q["regions"]] != [sea_rule["id"]]:
            q["regions"] = [sea_rule]
            if q["chart_type"] in ("multi_line", "difference"):
                q["chart_type"] = "line"
    if is_mars:
        has_avg = bool(MARS_AVG.search(folded))
        # karta planet tylko przy sredniej / porownaniu z Ziemia; pomiar lazika bez niej
        queries = [q for q in queries if has_avg or
                   (catalog.get(q["dataset_id"]) or {}).get("series_kind") != "planet_metric"
                   or len(queries) == 1]
        if has_avg and not any(q["dataset_id"] == "planet_mean_temp" for q in queries) \
                and re.search(r"temperat|°|grad|degr|stopn", folded):
            base = queries[0] if queries else {}
            queries.append({**base, "dataset_id": "planet_mean_temp", "dataset_ids": [],
                            "chart_type": "planet_bars", "body_ids": ["mars", "earth"],
                            "regions": [], "months": None, "periods": [],
                            "title": None, "note": None})
    for q in queries:
        ds = catalog.get(q["dataset_id"]) or {}
        topic = ds.get("topic") or q["dataset_id"]
        chart = q["chart_type"]
        if chart == "heatmap" and not wants_map:
            continue
        if q["months"] and ds.get("connector") not in MONTHLY_CONNECTORS \
                and chart != "compare_sources":
            q["months"] = None
        members = topic_members(topic, catalog, bool(q["regions"]), folded)
        # wykresy jednego zbioru (kilka regionow, okresy, mapa) - NASA POWER: bez
        # limitow zapytan, siatka dla dowolnego obszaru
        if chart in ("multi_line", "difference", "period_compare", "period_bands", "bars", "heatmap") \
                and ds.get("connector") != "power":
            power = next((i for i in members if catalog[i].get("connector") == "power"), None)
            if power:
                q["dataset_id"] = power
        if chart in ("compare_sources", "line") and len(members) >= 2 \
                and ds.get("series_kind", "annual") != "planet_metric" \
                and len(q["regions"]) <= 1:
            q["chart_type"] = "compare_sources"
            q["dataset_ids"] = members
            q["dataset_id"] = members[0]
        key = (TOPIC_FAMILY.get(topic, topic), tuple(sorted(r["id"] for r in q["regions"])),
               tuple(sorted(q["months"] or [])),
               tuple(q.get("body_ids") or []) if ds.get("series_kind") == "planet_metric" else (),
               "map" if chart == "heatmap" else "")
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    for q in out:
        if q["chart_type"] == "heatmap" and any(
                o is not q and o["chart_type"] != "heatmap" and o["regions"] == q["regions"]
                for o in out):
            q["heatmap_only"] = True
    # region zestawiony ze swiatem ("najszybciej na swiecie", "szybciej niz reszta
    # planety") -> brakujaca karta globalna
    has_regional = any(((catalog.get(q["dataset_id"]) or {}).get("topic") == "regional_temperature"
                        and q["regions"]) or
                       (catalog.get(q["dataset_id"]) or {}).get("topic") == "nh_temperature" for q in out)
    has_global = any((catalog.get(q["dataset_id"]) or {}).get("topic") == "global_temperature" for q in out)
    if has_regional and not has_global and re.search(
            r"(swiec|swiat|world|welt|monde|mundo|mondo|planet|global)", folded) and re.search(
            r"(szybciej|wolniej|najszybciej|bardziej niz|faster|slower|fastest|schneller|plus vite|mas rapido|piu veloce|"
            r"porown|compar|vergleich|niz (reszta|srednia)|than the|als der|que la|che la|rispetto|reszta)", folded):
        base = next((q for q in out if q["regions"]), out[0])
        gids = topic_members("global_temperature", catalog, False)
        out.append({**base, "dataset_id": gids[0], "dataset_ids": gids, "regions": [],
                    "chart_type": "compare_sources", "months": None, "title": None, "note": None})
    # teza nazywa CO2 (stezenie) obok innej wielkosci ("wraz ze wzrostem CO2 rosnie
    # temperatura") -> karta CO2, jesli model ja pominal
    topics_out = {(catalog.get(q["dataset_id"]) or {}).get("topic") for q in out}
    if out and "co2" not in topics_out and "emissions" not in topics_out and _topic_supported("co2", folded):
        cids = topic_members("co2", catalog, False)
        out.append({**out[0], "dataset_id": cids[0], "dataset_ids": cids, "regions": [],
                    "chart_type": "compare_sources", "months": None, "title": None, "note": None})
    # teza o calym roku i o porze roku -> brakujaca karta roczna
    if SEASON_SPLIT.search(folded):
        for q in list(out):
            ds = catalog.get(q["dataset_id"]) or {}
            if q["months"] and not any(
                    (catalog.get(o["dataset_id"]) or {}).get("topic") == ds.get("topic")
                    and not o["months"] for o in out):
                out.insert(out.index(q), {**q, "months": None, "title": None, "note": None})
                break
    return out


# ------------------------------------------------------------ publiczny API ---
def plan_with_llm(thesis: str,
                  fallback_plan: dict[str, Any],
                  context: str | None = None) -> dict[str, Any] | None:
    """Plan kart z LLM (zwwalidowany) albo None przy jakimkolwiek problemie."""
    global LAST_ERROR
    LAST_ERROR = None
    NON_ENGLISH_DROPPED.clear()
    info = llm_info()
    if not info["available"]:
        return None
    prompt = _build_prompt(thesis, fallback_plan, context)
    try:
        if info["provider"] == "gemini":
            raw_text = _call_gemini(prompt)
        elif info["provider"] == "openai":
            raw_text = _call_openai(config.OPENAI_BASE_URL,
                                    config.OPENAI_API_KEY, info["model"], prompt)
        else:
            raw_text = _call_openai(config.OPENROUTER_BASE_URL,
                                    config.OPENROUTER_API_KEY,
                                    info["model"], prompt)
        plan = validate_plan(_extract_json(raw_text), thesis,
                             fallback_plan.get("regions") or [])
        if plan is None:
            LAST_ERROR = "the LLM returned a plan that failed validation"
        return plan
    except Exception as exc:  # noqa: BLE001 - LLM zawodny: fallback
        LAST_ERROR = f"{type(exc).__name__}: {str(exc)[:160]}"
        return None
