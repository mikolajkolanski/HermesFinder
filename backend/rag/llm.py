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
               "planet_bars", "region_bars", "multi_series"]
MAX_COMPARE_SOURCES = 7
MAX_SERIES = 10

SYSTEM_PROMPT = """You are the data planner of Hermes Finder, an app that shows people the data behind \
a claim about climate, energy, emissions, weather, the oceans or other planets. The user gives a claim or \
a question (often informal, from a news article, in any language). You plan the data cards (charts) that \
let the user check EVERY part of the claim THEMSELVES. You NEVER judge whether the claim is true and you \
NEVER produce data values - you only pick datasets, places, years and chart types from the catalog; \
the numbers are fetched by the backend.

Reply ONLY with a JSON object (no markdown):
{
  "summary": "1-2 sentences in English: what data was prepared (no verdict)",
  "queries": [
    {
      "dataset_id": "catalog id",
      "dataset_ids": ["id1", "id2", ...] | [],          // compare_sources only
      "body_ids": ["mars", "earth", ...] | [],          // planet_bars only
      "region_ids": ["region id", ...] | [],            // [] = the world / global dataset
      "series": [{"dataset_id": "id", "region_id": "id" | null, "label": "short label"}] | [],  // multi_series only
      "start_year": int, "end_year": int,
      "months": [1-12] | [],
      "chart_type": "compare_sources" | "line" | "multi_line" | "region_bars" | "multi_series" | "difference" | "period_compare" | "period_bands" | "bars" | "heatmap" | "planet_bars",
      "periods": [{"start": int, "end": int}] | [],
      "title": "short title in English",
      "note": "1 sentence in English: what this card shows and how it relates to the claim"
    }
  ],
  "missing": [{"subject": "the part of the claim with no data", "message": "1-2 sentences"}],
  "no_data": false
}

HOW TO PLAN (most important):
1. Split the claim into ALL its sub-claims and quantities. Every quantity, place and comparison in the \
claim gets data. "Germany produces more electricity from renewables than Poland, but less from coal" = \
TWO cards: renewables electricity Germany vs Poland AND coal electricity Germany vs Poland. Never drop a \
part of the claim because another card already exists. Use as many cards as the claim needs (typically \
1-6; up to 10 for long claims). Do not add unrelated cards.
2. Comparing places (A vs B, "more than", "than", "vs", "compared with", "and its neighbours", a list of \
countries): put ALL compared places on ONE chart - chart_type "multi_line" with region_ids [A, B, ...] \
and ONE dataset that covers every place (country/continent/world data such as OWID emissions and \
electricity, or NASA POWER power_* for weather). Add a "region_bars" card (latest values side by side) \
when the claim is about who has more/less, a ranking, or 3+ places. Up to 12 regions per card. \
"Poland vs its 5 neighbours" -> Poland + 5 neighbour countries (see "neighbors" in the region list).
3. The world as one of the compared places: in multi_line/region_bars use the special region id "world" \
(only datasets with region_scope country_or_world support it; for temperature compare a region with \
global_temperature in a separate compare_sources card).
4. Different quantities for one place on one chart (e.g. electricity from coal vs from renewables in \
Poland): chart_type "multi_series" with "series" (same unit for all series).
5. One quantity for one place where several organisations publish it (topics map): "compare_sources" \
with all datasets of that topic (dataset_ids), e.g. global temperature from NASA, NOAA, Met Office, \
Berkeley, JMA, ERA5. Good for checking a single number or trend.
6. Heat maps ("heatmap"): spatial patterns, maps, "where", regional differences inside an area, or when a \
map clearly helps (e.g. warming across Europe). ONLY power_* datasets (NASA POWER grid). region_ids may \
list several regions (the map covers all of them, e.g. ["poland", "germany", "czechia"]), or a large area \
(europe, eu, usa, china...). Area limit about 40° x 60°. A heat map can be combined with other cards.
7. Periods ("in 1980-1990 vs 2000-2010"): period_compare (2-4 periods, 1-12 regions), period_bands, bars.
8. "difference": the A - B gap between two regions over time.
9. Seasons/months -> months (winter [12,1,2], summer [6,7,8]). "hot days"/"maximum" -> regional_tmax; \
"frost"/"minimum" -> regional_tmin.
10. Period: if the claim gives no years, use the last 25 years (energy/emissions: from 1990 or 2000). \
Never past the current year.
11. If the claim gives no place ("in our country", "hierzulande", "u nas"), take the place from \
"source_context" (the article title). Do NOT treat the context as a separate claim.
12. WATER / ocean temperature worldwide -> ocean_temperature. A specific sea (Baltic, Mediterranean) -> \
regional_temperature with that sea's region (air temperature over the sea; say so in the title).
13. MARS / planets: temperature on Mars -> compare_sources mars_max_temp (mars_rems_max_temp + \
mars_mcd_max_temp) and mars_min_temp, plus planet_bars "planet_mean_temp" with body_ids ["mars","earth"]. \
Other planet metrics: planet_bars with planet_* and body_ids from: mercury, venus, earth, moon, mars, \
jupiter, saturn, uranus, neptune, pluto (empty = all).

MISSING DATA (very important - be honest):
- When a part of the claim has NO matching dataset in the catalog (e.g. "CO2 from cows", "air pollution in \
Warsaw", "number of hurricanes", a country not in the region list), still plan cards for the parts that \
DO have data, and add an entry to "missing" for each part without data. The "message" is written in the \
language given in "message_language", is specific to the claim (name the missing quantity and place), \
for example (Polish): "Brak danych dla emisji CO₂ z hodowli krów — katalog nie zawiera emisji \
z rolnictwa ani z hodowli zwierząt." Do not invent a substitute dataset for the missing part.
- When NOTHING in the claim can be shown (nonsense, a topic outside climate/energy/emissions/weather/ \
ocean/planets, or no matching dataset at all): "queries": [], "no_data": true and one "missing" entry \
explaining briefly (in "message_language") that no data is available for this claim.
- Never use a dataset that does not measure what the claim talks about just to have a chart.

OUTPUT LANGUAGE: "summary", "title" and "note" MUST be in English whatever the language of the claim \
(place names in English: Poland, Baltic Sea, Gdansk). Only "missing[].message" uses "message_language".

DATA RULES:
- Datasets with the same "topic" measure the same quantity from different sources.
- Regional datasets (regional=true) need region_ids. Global datasets (regional=false) ignore regions.
- region_scope "country_or_world": countries, continents (europe, asia, africa, north_america, \
south_america, oceania), eu and "world". region_scope "any": any region or city (NASA POWER, Open-Meteo).
- Electricity by source (TWh) and its shares (%), energy use, emissions by fuel, methane, per capita and \
per GDP emissions are in the catalog (owid_*). Use them for energy/emission claims.
- For seasons some datasets have no monthly data - they will be skipped; do not work around this."""


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
                  context: str | None = None, language: str | None = None) -> str:
    catalog = load_catalog()
    cur = _current_year()
    ds_list = [
        {
            "id": ds_id,
            "title": ds["title"],
            "unit": ds["unit"],
            "regional": ds["supports_regions"],
            "connector": ds["connector"],
            "region_scope": ds.get("region_scope"),
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
        "message_language": _language_name(language) or "the language of the claim",
    }
    return json.dumps(payload, ensure_ascii=False)


LANGUAGE_NAMES = {"en": "English", "pl": "Polish", "de": "German", "fr": "French", "es": "Spanish",
                  "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "cs": "Czech", "sv": "Swedish",
                  "uk": "Ukrainian", "ja": "Japanese", "zh": "Chinese"}


def _language_name(code: str | None) -> str | None:
    if not code:
        return None
    return LANGUAGE_NAMES.get(str(code).lower().split("-")[0].split("_")[0])


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
        if len(out) >= config.MAX_REGIONS:
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


def _valid_missing(raw: Any) -> list[dict[str, str]]:
    """Czesci tezy bez danych: [{subject, message}] (tekst w jezyku uzytkownika)."""
    out: list[dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for m in raw[:6]:
        if isinstance(m, str):
            m = {"subject": "", "message": m}
        if not isinstance(m, dict):
            continue
        subject = str(m.get("subject") or "").strip()[:160]
        message = str(m.get("message") or "").strip()[:400]
        if subject or message:
            out.append({"subject": subject, "message": message})
    return out


def _power_twin(ds_id: str, catalog: dict[str, Any]) -> str | None:
    """Zbior NASA POWER tej samej rodziny tematu (mapa cieplna wymaga siatki POWER)."""
    ds = catalog.get(ds_id) or {}
    if ds.get("connector") == "power":
        return ds_id
    fam = TOPIC_FAMILY.get(ds.get("topic") or "", ds.get("topic"))
    topic = ds.get("topic")
    if topic in ("global_temperature", "nh_temperature"):
        topic, fam = "regional_temperature", "temp"
    for i, d in catalog.items():
        if d.get("connector") == "power" and d.get("topic") == topic:
            return i
    for i, d in catalog.items():
        if d.get("connector") == "power" and TOPIC_FAMILY.get(d.get("topic") or "") == fam:
            return i
    return None


def _covering_dataset(ds_id: str, ids: list[str], catalog: dict[str, Any]) -> str:
    """Do porownania wielu regionow: zbior tematu, ktory obsluguje dowolny region
    (POWER dla pogody, OWID dla danych krajowych), inaczej wskazany."""
    cands = [ds_id] + [i for i in ids if i != ds_id]
    for i in cands:
        if (catalog.get(i) or {}).get("connector") in ("power", "owid", "owid_csv"):
            return i
    topic = (catalog.get(ds_id) or {}).get("topic")
    for i, d in catalog.items():
        if d.get("topic") == topic and d.get("connector") in ("power", "owid", "owid_csv"):
            return i
    return ds_id


def _valid_series(raw: Any, catalog: dict[str, Any]) -> list[dict[str, Any]]:
    """multi_series: [{dataset_id, region|None, label}] - kazde id sprawdzone."""
    from regions import region_dict
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        ds_id = str(item.get("dataset_id") or "")
        ds = catalog.get(ds_id)
        if not ds or ds.get("series_kind", "annual") != "annual":
            continue
        rid = item.get("region_id")
        reg = region_by_id(rid) if isinstance(rid, str) and rid else None
        region = region_dict(reg) if reg and ds.get("supports_regions") else None
        key = (ds_id, region["id"] if region else "")
        if key in seen:
            continue
        seen.add(key)
        label = _english_or_none(item.get("label"), 60)
        out.append({"dataset_id": ds_id, "region": region, "label": label})
        if len(out) >= MAX_SERIES:
            break
    return out


def validate_plan(raw: Any, thesis: str = "",
                  rule_regions: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Waliduje odpowiedz LLM -> {summary, queries[], missing[], no_data} albo None.

    Walidacja PRZED limitem kart, by bledne wpisy na poczatku nie wycinaly
    poprawnych na koncu. Model wybiera TYLKO zbiory/regiony/lata/typy - kazde
    id jest sprawdzane wzgledem katalogu i slownika regionow. Model ma pelna
    swobode co do LICZBY kart i typow wykresow (do config.MAX_CARDS).
    """
    if not isinstance(raw, dict):
        return None
    catalog = load_catalog()
    queries: list[dict[str, Any]] = []
    cur = _current_year()
    raw_queries = raw.get("queries") if isinstance(raw.get("queries"), list) else []
    for q in raw_queries:
        if len(queries) >= config.MAX_CARDS * 2:
            break
        if not isinstance(q, dict):
            continue
        chart = str(q.get("chart_type", "line"))
        if chart not in CHART_TYPES:
            chart = "line"

        series = _valid_series(q.get("series"), catalog) if chart == "multi_series" else []
        ds_id = str(q.get("dataset_id", ""))
        if chart == "multi_series":
            if len(series) < 2:
                if series:
                    s0 = series[0]
                    ds_id = s0["dataset_id"]
                    q = {**q, "region_ids": [s0["region"]["id"]] if s0["region"] else []}
                chart = "line"
            else:
                ds_id = series[0]["dataset_id"]
        dataset_ids = _valid_dataset_ids(q.get("dataset_ids"), catalog)
        regions = _valid_regions(q.get("region_ids"))
        if chart == "compare_sources":
            if ds_id in catalog and ds_id not in dataset_ids:
                # id glowne dolaczamy tylko, gdy ten sam topic
                dataset_ids = _valid_dataset_ids([ds_id] + dataset_ids, catalog)
            if len(regions) >= 2:
                # kilka miejsc = porownanie miejsc na jednym wykresie (jeden zbior,
                # ktory obsluguje wszystkie regiony), nie porownanie zrodel
                ds_id = _covering_dataset(dataset_ids[0] if dataset_ids else ds_id,
                                          dataset_ids, catalog)
                chart = "multi_line"
            elif len(dataset_ids) >= 2:
                ds_id = dataset_ids[0]
            else:
                chart = "line"
                ds_id = dataset_ids[0] if dataset_ids else ds_id
        if chart == "heatmap":
            twin = _power_twin(ds_id, catalog)
            if twin:
                ds_id = twin
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
            years = (cur - config.DEFAULT_YEARS_BACK, cur)

        if chart == "compare_sources":
            regions = regions[:1]
            if not any(catalog[i].get("supports_regions") for i in dataset_ids):
                regions = []
        elif chart != "multi_series" and not ds.get("supports_regions"):
            regions = []  # zbior globalny: region z LLM nie ma znaczenia
        if ds.get("region_scope") not in ("country_or_world",) and chart != "multi_series":
            # "world" jako region tylko dla danych krajowych z wierszem World
            regions = [r for r in regions if r["id"] != "world"]
        periods = _valid_periods(q.get("periods"))
        if chart == "heatmap":
            regions = [r for r in regions if r.get("type") in ("bbox", "point")]
            if ds["connector"] != "power" or not regions:
                chart = "multi_line" if len(regions) > 1 else "line"
        # difference/multi_line/region_bars wymagaja >=2 regionow i zbioru regionalnego
        if chart in ("difference", "multi_line", "region_bars"):
            if len(regions) < 2 or not ds.get("supports_regions"):
                chart = "line"
        if chart in ("period_compare", "period_bands", "bars") and len(periods) < 2:
            chart = "line"
        if chart == "line" and len(regions) > 1:
            chart = "multi_line"
        queries.append({
            "dataset_id": ds_id,
            "dataset_ids": dataset_ids if chart == "compare_sources" else [],
            "body_ids": _valid_bodies(q.get("body_ids")),
            "regions": regions,
            "series": series if chart == "multi_series" else [],
            "start_year": years[0],
            "end_year": years[1],
            "months": _valid_months(q.get("months")),
            "chart_type": chart,
            "periods": periods,
            "title": _english_or_none(q.get("title"), 140),
            "note": _english_or_none(q.get("note"), 300),
        })
    queries = normalize_queries(queries, thesis, catalog, rule_regions or [], strict=False)
    missing = _valid_missing(raw.get("missing"))
    no_data = bool(raw.get("no_data")) and not queries
    if not queries and not missing and not no_data:
        return None
    return {
        "summary": _english_or_none(raw.get("summary"), 400),
        "queries": queries[:config.MAX_CARDS],
        "missing": missing,
        "no_data": no_data or not queries,
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
                "emissions": "emis", "emissions_per_capita": "emis",
                "renewables": "elec_renewables"}
for _k in ("total", "coal", "gas", "oil", "nuclear", "renewables", "solar", "wind", "hydro",
           "fossil", "low_carbon"):
    TOPIC_FAMILY[f"electricity_{_k}"] = f"elec_{_k}"
    TOPIC_FAMILY[f"share_elec_{_k}"] = f"elec_{_k}"
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
    "emissions": r"emisj|emission|emisi|\bemit|emituj|emitt|ausstoss|uitstoot|spalan|kopalin|fossil|tonn|\bton|produkc\w* co2|co2 produc|wytwarza\w* co2",
    "emissions_per_capita": r"emisj|emission|emisi|\bemit|emituj|mieszkan|capita|kopf|habitant|habitante|abitante",
    "renewables": r"oze|odnawial|renewab|erneuerbar|renouvelab|renovab|rinnovabil|wiatr|wind|solar|slonecz",
    "sea_level": r"poziom\w* (morz|ocean|baltyk|wod)|sea[- ]level|meeresspiegel|niveau|nivel|livello|zeespiegel|mareograf|tide",
    "tide_gauge_sea_level": r"mareograf|tide gauge|^(?=.*(poziom\w* (morz|baltyk|wod)|sea[- ]level|meeresspiegel|niveau de la mer|nivel del mar|livello del mare|wybrzez|zalew))(?=.*(baltyk|baltyc|baltic|ostsee|gdansk|swinouj|wybrzez|\bport(u|ach|s)?\b))",
    "ocean_temperature": r"ocean|sea surface|sst|meerestemp|temperatura (wody|morz)|water temp",
    # lod + konkretny biegun ("antarktyda" zawiera "arkty" - stad (?<!ant))
    "arctic_sea_ice": r"^(?=.*(lod|ice|eis|glace|hielo|ghiacc))(?=.*((?<!ant)arkty|(?<!ant)arctic|(?<!ant)arktis|(?<!ant)arctique|(?<!ant)artico|biegun\w* polnocn|north pole))",
    "antarctic_sea_ice": r"^(?=.*(lod|ice|eis|glace|hielo|ghiacc))(?=.*(antarkty|antarctic|antarktis|antarctique|antartid|antartic|biegun\w* poludn|south pole))",
    "regional_precipitation": r"opad|deszcz|susz|rain|precip|drought|niederschlag|regen|durre|pluie|secheres|lluvi|sequi|piogg|siccit",
    "regional_tmax": r"upal|tmax|maksym|maxim|hitze|heiss|chaleur|canicul|calor|caldo|heat|30 ?°",
    "regional_tmin": r"mroz|minim|frost|tmin|\bgel|helad|gelo|zim",
    "regional_temperature": r"temperat|ociepl|cieplej|cieplo|warm|chaud|calient|calid|cald|grad|°|stopn|degre|grado|nagrzew|ogrzew|zim|lato|winter|summer|hiver|invierno|inverno|ete\b|verano|estate|klimat|climat|clima|upal|goraco|zimno|chlod",
    "solar_activity": r"slonc|\bsun\b|\bsuns|sunspot|solar (activity|cycle)|sonne|soleil|\bsol\b|plam",
    "regional_wind": r"wiatr|wichur|wind|vent|viento|vento",
    "regional_humidity": r"wilgot|humid|feucht|humed|umid",
    "regional_radiation": r"naslonecz|promieniow|slonc|radiat|strahl|rayonn|radiac|irradi|fotowolt|solar",
    "nh_temperature": r"polkul|hemisph|nordhalb|hemisfer",
}
for _t in ("mars_max_temp", "mars_min_temp", "mars_pressure", "mars_max_gts_temp", "mars_min_gts_temp"):
    TOPIC_WORDS[_t] = r"mars|martian|marsjan|curiosity|gale"

# energia i emisje szczegolowe (pliki OWID): slowa o pradzie + o zrodle
_ELEC = r"prad|elektr|electric|strom|power|energi|\btwh|\bgwh"
_EMIS = r"emisj|emission|emisi|\bemit|emituj|ausstoss|co2|co₂|dwutlen"
_SHARE = r"udzia|share|anteil|\bpart\b|cuota|quota|procent|percent|%"
_SRC = {
    "coal": r"wegl|coal|kohle|charbon|carbon(?! dioxide)|carbone|lignit|brunat",
    "gas": r"\bgaz|\bgas\b|erdgas",
    "oil": r"\brop[aey]|\boil\b|\bol\b|petrol|erdol",
    "nuclear": r"atom|jadrow|nuclear|kernkraft|nucleai|nucleair",
    "renewables": r"\boze\b|odnawial|renewab|erneuerbar|renouvelab|renovab|rinnovabil",
    "solar": r"fotowolt|slonecz|solar|photovolt|\bpv\b",
    "wind": r"wiatr|wind|eolien|eolic",
    "hydro": r"wodn|hydro|wasserkraft",
    "fossil": r"kopaln|fossil|fosil",
    "low_carbon": r"niskoemis|low[- ]carbon|bezemisyj|zeroemis",
}


def _both(a: str, b: str) -> str:
    return rf"^(?=.*({a}))(?=.*({b}))"


TOPIC_WORDS["electricity_total"] = rf"(produkc|wytwarz|generat|erzeug)\w*.*({_ELEC})|({_ELEC}).*(produkc|generat)"
for _k, _pat in _SRC.items():
    TOPIC_WORDS[f"electricity_{_k}"] = _both(_ELEC, _pat)
    TOPIC_WORDS[f"share_elec_{_k}"] = rf"^(?=.*({_ELEC}))(?=.*({_pat}))(?=.*({_SHARE}))"
TOPIC_WORDS.update({
    "primary_energy": r"energi\w* pierwotn|primary energy|zuzyc\w* energi|energy consumption|energieverbrauch|consommation d.energie",
    "energy_per_capita": _both(r"energi|energy|energie", r"mieszk|capita|kopf|habitant|na osob"),
    "renewables_share_energy": _both(_SRC["renewables"], r"energi\w* pierwotn|primary energy|zuzyc\w* energi|energy consumption"),
    "coal_consumption": r"zuzyc\w* wegl|coal consumption|kohleverbrauch|spalan\w* wegl|burn\w* coal",
    "electricity_demand": r"zapotrzeb|zuzyc\w* (prad|energi\w* elektr)|electricity (demand|consumption)|stromverbrauch|power demand",
    "emissions_coal": _both(_EMIS, _SRC["coal"]),
    "emissions_oil": _both(_EMIS, _SRC["oil"]),
    "emissions_gas": _both(_EMIS, _SRC["gas"]),
    "emissions_cement": r"cement|zement|ciment",
    "emissions_land_use": r"wylesian|deforest|uzytkow\w* grunt|land[- ]use|abholz|deboise",
    "emissions_methane": _both(r"metan|methan|ch4", r"emisj|emission|emisi|\bemit|emituj|rolnic|hodowl|krow|bydl|agricult|livestock"),
    "emissions_n2o": r"n2o|podtlen|nitrous|lachgas|protoxyde",
    "emissions_consumption": r"konsumpc|consumption[- ]based|import\w* emisj|emisj\w* importow|handl\w* emisj",
    "emissions_cumulative": r"skumulowan|cumulative|kumuliert|cumul|historyczn\w* emisj|historical emission|od poczatku",
    "emissions_share_global": _both(_EMIS, r"udzia\w* w (swiatow|globaln)|share of (the )?global|% (swiatow|global)|procent (swiatow|global)|of world"),
    "emissions_per_gdp": _both(_EMIS, r"\bpkb|\bgdp|\bbip|\bpib|gospodark|economy"),
    "ghg_per_capita": _both(r"gaz\w* cieplarn|\bghg|greenhouse|treibhaus", r"mieszk|capita|kopf|habitant|na osob"),
    "population": r"ludnos|populac|population|bevolker|poblacion|popolazione|liczb\w* mieszk",
})


def _fold(text: str) -> str:
    import unicodedata
    t = text.lower().replace("ł", "l").replace("ß", "ss").replace("₂", "2").replace("º", "°")
    t = "".join(ch for ch in unicodedata.normalize("NFD", t) if unicodedata.category(ch) != "Mn")
    # "dwutlenek wegla" to CO2, nie wegiel (paliwo) - inaczej trafialby w tematy o weglu
    return re.sub(r"dwutlen\w*\s+wegl\w*", "dwutlenek co2", t)


PLANET_WORDS = r"planet|\bmars|marsjan|martian|wenus|venus|jowisz|jupiter|merkur|mercury|saturn|\buran|neptun|pluton|pluto|ksiezyc|\bmoon|\blune|\bmond\b|uklad\w* slonecz|solar system|sonnensystem|systeme solaire|sistema solar"


def topic_mentioned(topic: str, thesis_folded: str) -> bool:
    """Teza WPROST mowi o temacie (temat bez wzorca slow -> False)."""
    if topic.startswith("planet_"):
        return bool(re.search(PLANET_WORDS, thesis_folded))
    if topic not in TOPIC_WORDS and topic != "co2":
        return False
    return _topic_supported(topic, thesis_folded)


def _topic_supported(topic: str, thesis_folded: str) -> bool:
    if topic.startswith("planet_"):
        return bool(re.search(PLANET_WORDS, thesis_folded))
    if topic == "co2" and re.search(r"\bco2\b|dwutlen|carbon dioxide|kohlendioxid|dioxyde de carbone|dioxido de carbono|anidride carbonica", thesis_folded) \
            and not re.search(r"emisj|emission|emisi|\bemit|emituj|emitt|produkc|wytwarza|spalan|kopalin|fossil|ausstoss|uitstoot|tonn|\bton", thesis_folded):
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
                      rule_regions: list[dict[str, Any]] | None = None,
                      strict: bool = True) -> list[dict[str, Any]]:
    """Deterministyczne poprawki planu.

    * temat z kilkoma zrodlami -> karta porownawcza z KOMPLETEM zrodel,
    * filtr miesiecy tylko dla zbiorow z danymi miesiecznymi,
    * jedna karta na (temat, regiony, miesiace, rodzaj wykresu) - bez duplikatow,
    * strict=True (planer regulowy, bez modelu): karta tylko dla tematu, o ktorym
      teza mowi (TOPIC_WORDS), heatmapa tylko przy slowach o mapie / rozkladzie.
      Plan modelu jezykowego (strict=False) nie jest tak przycinany - model sam
      decyduje, ile kart i jakich wykresow potrzebuje teza.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    wants_map = bool(HEATMAP_WORDS.search(thesis or "")) or not strict
    folded = _fold(thesis or "")
    # strażnik tematów: karta tylko dla wielkości, o której teza mówi
    # (nigdy nie zostawiamy pustego planu - wtedy zostaje pierwsza karta)
    if thesis and strict:
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
                and len(q["regions"]) == 1 and q["regions"][0]["id"] != sea_rule["id"] \
                and q["regions"][0]["id"] not in SEA_REGIONS:
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
        if chart in ("multi_line", "difference", "period_compare", "period_bands", "bars", "heatmap",
                     "region_bars") \
                and ds.get("connector") != "power":
            power = next((i for i in members if catalog[i].get("connector") == "power"), None)
            if power:
                q["dataset_id"] = power
        if chart in ("compare_sources", "line") and len(members) >= 2 \
                and ds.get("series_kind", "annual") != "planet_metric" \
                and len(q["regions"]) <= 1 and not (q["regions"] and q["regions"][0]["id"] == "world"):
            q["chart_type"] = "compare_sources"
            q["dataset_ids"] = members
            q["dataset_id"] = members[0]
        group = {"heatmap": "map", "region_bars": "bars", "bars": "bars",
                 "period_compare": "periods", "period_bands": "periods",
                 "difference": "diff"}.get(chart, "")
        if chart == "multi_series":
            key = ("ms", tuple((x["dataset_id"], (x.get("region") or {}).get("id", ""))
                               for x in q.get("series") or []), tuple(sorted(q["months"] or [])))
        else:
            key = (TOPIC_FAMILY.get(topic, topic) if strict else topic,
                   tuple(sorted(r["id"] for r in q["regions"])),
                   tuple(sorted(q["months"] or [])),
                   tuple(q.get("body_ids") or []) if ds.get("series_kind") == "planet_metric" else (),
                   group)
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    for q in out:
        if q["chart_type"] == "heatmap" and (len(q["regions"]) > 1 or any(
                o is not q and o["chart_type"] != "heatmap"
                and {r["id"] for r in q["regions"]} <= {r["id"] for r in o["regions"]}
                for o in out)):
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
                  context: str | None = None,
                  language: str | None = None) -> dict[str, Any] | None:
    """Plan kart z LLM (zwalidowany) albo None przy jakimkolwiek problemie."""
    global LAST_ERROR
    LAST_ERROR = None
    NON_ENGLISH_DROPPED.clear()
    info = llm_info()
    if not info["available"]:
        return None
    prompt = _build_prompt(thesis, fallback_plan, context, language)
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
