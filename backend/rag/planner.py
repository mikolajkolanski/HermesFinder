"""Planner fallback (bez LLM): ekstrakcja parametrow z tezy regexami.

Zwraca plan w formacie v2 rozumianym przez pipeline:
  {"regions": [...], "global_scope", "time", "periods", "months",
   "metric_hints", "chart_hint", "heatmap_hint", "source"}

Gdy dostepny jest LLM (rag/llm.py), jego plan ma priorytet - ten modul jest
deterministycznym zabezpieczeniem (dziala bez klucza API).
"""
from __future__ import annotations

import re
from typing import Any

import config
from regions import (
    extract_regions_all,
    is_global_mentioned,
    region_by_id,
    region_dict,
)

# slowa-liczebniki PL (dla "ostatnie dwadziescia lat" itp.)
NUMBER_WORDS = {
    "trzy": 3, "cztery": 4, "piec": 5, "szesc": 6, "siedem": 7, "osiem": 8,
    "dziewiec": 9, "dziesiec": 10, "dwanascie": 12, "pietnascie": 15,
    "dwadziescia": 20, "trzydziesci": 30, "czterdziesci": 40,
    "piecdziesiat": 50, "sto": 100,
}

# pory roku: wzorce z granica slowa ("w latach 2000-2010" != lato!)
SEASON_PATTERNS = [
    (r"zim(?:a|y|i|ie|e|owych|owym|owe|o)\b", [12, 1, 2], "winter (Dec–Feb)"),
    (r"lat(?:em)\b|\blecie\b|\blato\b|(?:^|\s)letn[a-z]*\b",
     [6, 7, 8], "summer (Jun–Aug)"),
    (r"wiosen[a-z]*\b|wiosn[a-z]*\b", [3, 4, 5], "spring (Mar–May)"),
    (r"jesien[a-z]*\b", [9, 10, 11], "autumn (Sep–Nov)"),
]

MONTH_NAMES = {
    "stycznia": 1, "styczniu": 1, "styczen": 1,
    "lutego": 2, "lutym": 2, "luty": 2,
    "marca": 3, "marcu": 3, "marzec": 3,
    "kwietnia": 4, "kwietniu": 4, "kwiecien": 4,
    "maja": 5, "maju": 5, "maj": 5,
    "czerwca": 6, "czerwcu": 6, "czerwiec": 6,
    "lipca": 7, "lipcu": 7, "lipiec": 7,
    "sierpnia": 8, "sierpniu": 8, "sierpien": 8,
    "wrzesnia": 9, "wrzesniu": 9, "wrzesien": 9,
    "pazdziernika": 10, "pazdzierniku": 10, "pazdziernik": 10,
    "listopada": 11, "listopadzie": 11, "listopad": 11,
    "grudnia": 12, "grudniu": 12, "grudzien": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

MONTH_LABELS = ["", "January", "February", "March", "April", "May",
                "June", "July", "August", "September", "October",
                "November", "December"]


def _current_year() -> int:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).year


def _to_int(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    from regions import _norm
    return NUMBER_WORDS.get(_norm(word))


# ------------------------------------------------------------------ regiony ---
def extract_regions(text: str) -> list[dict[str, Any]]:
    """Wszystkie regiony z tezy (fallback: tez wieloregionalnych)."""
    regions = extract_regions_all(text, limit=4)
    if regions:
        return regions
    return []


# -------------------------------------------------------------------- czas ----
def extract_time(text: str) -> dict[str, Any]:
    """Glowne okno czasowe (gdy teza nie definiuje wielu okresow)."""
    from regions import _norm
    n = _norm(text.lower())
    cur = _current_year()

    m = re.search(r"(\d{4})\s*(?:-|–|do|az do|a|:)\s*(\d{4})", n)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 1800 <= a <= cur and 1800 <= b <= cur + 1 and a < b:
            return {"mode": "explicit", "start": a, "end": b,
                    "matched": f"{a}-{b}"}

    # skrot dekady z mediow: "od lat 70." / "od lat 90." (po obejsciu YYYY-YYYY,
    # wiec "w latach 2000-2010" nie uruchomi tej reguly)
    m = re.search(r"lat\s+(\d{2})\b", n)
    if m:
        v = int(m.group(1))
        year = 2000 + v if v < 30 else 1900 + v
        if 1900 <= year <= cur:
            return {"mode": "from_year", "start": year, "end": cur,
                    "matched": f"od lat {v}."}

    # "od rewolucji przemysłowej" / "era przedprzemysłowa" = start GISTEMP
    if re.search(r"rewolucj[a-z]*\s+przemyslow|przedprzemyslow", n):
        return {"mode": "from_year", "start": config.MIN_YEAR, "end": cur,
                "matched": "od rewolucji przemysłowej"}

    if re.search(r"od\s+poczatku\s+pomiar", n):
        return {"mode": "from_year", "start": config.MIN_YEAR, "end": cur,
                "matched": "od początku pomiarów"}

    m = re.search(r"(?:od|po|since|od roku|po roku|seit|depuis|desde|dal|dalla|sinds)\s+(?:roku\s+|l'|el\s+)?(\d{4})", n)
    if m:
        a = int(m.group(1))
        if 1800 <= a <= cur:
            return {"mode": "from_year", "start": a, "end": cur,
                    "matched": f"od {a}"}

    m = re.search(r"(?:przed|before)\s+(?:rokiem\s+)?(\d{4})", n)
    if m:
        b = int(m.group(1))
        if 1800 <= b <= cur:
            return {"mode": "until_year", "start": config.MIN_YEAR, "end": b,
                    "matched": f"przed {b}"}

    m = re.search(
        r"(?:ostatni(?:ch|e|)?|w ciagu|przez|za)?\s*(\d{1,3}|[a-z]+)\s*"
        r"(?:dekad(?:y|ach|a)?|decades?)", n)
    if m:
        v = _to_int(m.group(1))
        if v:
            start = cur - v * 10 + 1
            return {"mode": "last_n_years", "n": v * 10, "start": start,
                    "end": cur, "matched": f"ostatnie {v} dekady"}

    m = re.search(
        r"(?:ostatni(?:ch|e|)?|w ciagu|przez|za|w przeciagu|toward)?\s*"
        r"(\d{1,3}|[a-z]+)\s*(?:latach|lat|lata|years?|lecie)", n)
    if m:
        v = _to_int(m.group(1))
        if v and 2 <= v <= 150:
            return {"mode": "last_n_years", "n": v, "start": cur - v + 1,
                    "end": cur, "matched": f"ostatnie {v} lat"}

    if re.search(r"(xxi|21)\s*wiek", n):
        return {"mode": "explicit", "start": 2001, "end": cur, "matched": "XXI wiek"}
    if re.search(r"(xx|20)\s*wiek", n):
        return {"mode": "explicit", "start": 1901, "end": 2000, "matched": "XX wiek"}

    m = re.search(r"(?:w|roku|in|im|en|nel|em)\s+(?:roku\s+|jahr\s+)?(\d{4})(?!\d)", n)
    if m:
        a = int(m.group(1))
        if 1800 <= a <= cur:
            # jeden rok w tezie ("w 2024 r. bylo rekordowo") - pokazujemy go na tle
            # trendu: okno konczace sie na tym roku, nie pojedynczy punkt
            return {"mode": "year_in_context", "start": a - config.DEFAULT_YEARS_BACK + 1,
                    "end": a, "matched": str(a)}

    return {"mode": "last_n_years", "n": config.DEFAULT_YEARS_BACK,
            "start": cur - config.DEFAULT_YEARS_BACK + 1, "end": cur,
            "matched": None, "default": True}


def extract_periods(text: str) -> list[dict[str, int]]:
    """Wszystkie jawne zakresy YYYY-YYYY (porownanie okresow)."""
    from regions import _norm
    n = _norm(text.lower())
    cur = _current_year()
    out: list[dict[str, int]] = []
    seen: set[tuple[int, int]] = set()
    for m in re.finditer(r"(\d{4})\s*(?:-|–|do|az do|a|:)\s*(\d{4})", n):
        a, b = int(m.group(1)), int(m.group(2))
        if 1800 <= a < b <= cur + 1 and (a, b) not in seen:
            seen.add((a, b))
            out.append({"start": a, "end": b})
        if len(out) >= 4:
            break
    return out


def extract_months(text: str) -> dict[str, Any] | None:
    """Filtr miesieczny/pory roku, np. 'latem', 'w lipcu', 'zimowych miesiecy'.

    Konkretny miesiac wygrywa z pora roku ("cieply marzec: wiosna..." -> marzec).
    Wzorce z granica slowa: "w latach 2000-2010" NIE uruchamia filtra lata.
    """
    from regions import _norm
    n = _norm(text.lower())
    for name, num in sorted(MONTH_NAMES.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"(?:^|\s)(?:w|we|in)?\s*{re.escape(name)}\b", n):
            return {"months": [num], "label": MONTH_LABELS[num]}
    for pattern, months, label in SEASON_PATTERNS:
        if re.search(pattern, n):
            return {"months": months, "label": label}
    return None


def extract_metric_hints(text: str) -> list[str]:
    """Wskazowki co do metryki (kategorie zbiorow) dla retrievera."""
    from regions import _norm
    n = _norm(text.lower())
    hints: list[str] = []
    rules = [
        (r"maksymal|upal|rekord.*ciepla|fala upal", ["heat", "extreme"]),
        (r"minimalna|mroz|przymrozk|fala chlod", ["cold", "frost"]),
        (r"temperat|ocieplen|ciepl|chlod|grzan", ["temperature", "warming"]),
        (r"opad|deszcz|susza|susz|powodzi|snieg", ["precipitation", "rain"]),
        (r"wilgotnosc|wilgotnosci", ["humidity"]),
        (r"wiatr|wichur", ["wind"]),
        (r"naslonecznien|slonc|promieniowan|fotowoltaik|zachmurz", ["radiation", "sunlight"]),
        (r"co2|dwutlenk|emisj|cieplarnian", ["co2", "greenhouse"]),
        (r"poziom.*morza|morza|ocean", ["sea level"]),
        (r"lod|arktyk|topnien|biegun|grenlandi", ["sea ice", "arctic"]),
        (r"global|swiat|planet|ziemi", ["global temperature"]),
        (r"mars|marsj|wenus|merkur|jowisz|saturn|neptun|pluton|uklad slonecz|"
         r"planet", ["mars", "planets"]),
        (r"metan|ch4", ["methane", "greenhouse"]),
        (r"podtlenek|n2o", ["n2o", "greenhouse"]),
        (r"plam.*slonecz|aktywnosc slonc|cykl slonecz|sunspot|solar activit|solar cycle",
         ["sunspots", "solar activity"]),
        (r"oze|odnawialn", ["renewables", "energy"]),
        (r"antarkty|antarktyd", ["sea ice", "antarctic"]),
    ]
    for pattern, cats in rules:
        if re.search(pattern, n):
            hints.extend(cats)
    return sorted(set(hints))


# ------------------------------------------------------------ cialo niebieskie --
BODY_RULES = [
    ("mercury", r"\bmerkur"), ("venus", r"\bwenus|\bvenus"),
    ("moon", r"ksiezyc|\bmoon\b|\bluna\b"), ("mars", r"\bmars|\bmartian"),
    ("jupiter", r"\bjowisz|\bjupiter"), ("saturn", r"\bsaturn"),
    ("uranus", r"\buran(?:ie|a|em|ow|u)?\b|\buranus"),
    ("neptune", r"\bneptun"), ("pluto", r"\bpluton|\bpluto\b"),
]


def extract_bodies(text: str) -> list[str]:
    """Ciala Ukladu Slonecznego wymienione w tezie (id jak w planets.BODIES)."""
    from regions import _norm
    n = _norm(text.lower())
    found = [bid for bid, pat in BODY_RULES if re.search(pat, n)]
    # 'Ziemia' liczymy jako cialo tylko w towarzystwie innej planety
    if found and re.search(r"\bziemi|\bearth", n) and "earth" not in found:
        found.append("earth")
    return found


# ------------------------------------------------------------- typ wykresu ----
HEATMAP_RE = re.compile(
    r"mapa|heatmap|cieplna|rozkład|przestrzen|obszar|siatk", re.IGNORECASE)
DIFF_RE = re.compile(r"różnic|roznic|różnicy|vs\.?|versus|odwrotno", re.IGNORECASE)
COMPARE_RE = re.compile(r"porówn|porown|w porównaniu|w stosunku do|natomiast", re.IGNORECASE)


def infer_chart_hint(text: str, regions: list[dict[str, Any]],
                     periods: list[dict[str, int]],
                     global_scope: bool) -> tuple[str, bool]:
    """(chart_type, heatmap_rownej_karcie) wg regul fallbacku."""
    n = text.lower()
    multi = len(regions) >= 2
    multi_periods = len(periods) >= 2

    if multi_periods:
        # okresy przebijaja: karta okresow obsluguje 1..N regionow
        return "period_compare", False
    if multi and DIFF_RE.search(n):
        return "difference", False
    if multi and COMPARE_RE.search(n):
        return "multi_line", False
    if multi:
        return "multi_line", False
    if HEATMAP_RE.search(n) and regions and regions[0].get("type") == "bbox":
        # "temperatura polski na przestrzeni 20 lat" -> line + heatmapa
        return "line", True
    return "line", False


# ------------------------------------------------------ lata z opcji ---
EARLIEST_YEAR = 1850   # najstarsze serie (HadCRUT5, Berkeley) zaczynaja sie w 1850 r.


def user_window(options: dict[str, Any] | None) -> tuple[int, int] | None:
    """Zakres lat z opcji uzytkownika (start_year / end_year) albo None.

    Wystarczy jeden rok: brakujacy poczatek = EARLIEST_YEAR, koniec = biezacy rok.
    Zakres niepoprawny (odwrocony, poza 1850..biezacy rok) -> None; API odrzuca
    taki zakres wczesniej (main.py), to tylko zabezpieczenie."""
    options = options or {}
    s, e = options.get("start_year"), options.get("end_year")
    if s is None and e is None:
        return None
    try:
        s = int(s) if s is not None else EARLIEST_YEAR
        e = int(e) if e is not None else _current_year()
    except (TypeError, ValueError):
        return None
    if not (EARLIEST_YEAR <= s <= e <= _current_year()):
        return None
    return s, e


def clip_periods(periods: list[dict[str, Any]],
                 window: tuple[int, int]) -> list[dict[str, Any]]:
    """Okresy z tezy przyciete do zakresu uzytkownika; < 2 okresow -> brak
    (karta okresow podzieli wtedy sam zakres na poczatek i koniec)."""
    out = []
    for p in periods or []:
        a, b = max(int(p["start"]), window[0]), min(int(p["end"]), window[1])
        if b - a >= 2:
            out.append({**p, "start": a, "end": b,
                        "label": p.get("label") if (a, b) == (p["start"], p["end"])
                        else f"{a}–{b}"})
    return out if len(out) >= 2 else []


# -------------------------------------------------------------- glowny plan ---
def build_fallback_plan(thesis: str,
                        options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministyczny plan (bez LLM) w formacie v2."""
    options = options or {}
    regions = extract_regions(thesis)
    context = str(options.get("context") or "")[:300]
    if not regions and context and not is_global_mentioned(thesis):
        # "hierzulande", "w naszym kraju", "en la peninsula" - miejsce z tytulu artykulu
        # (teza o swiecie/globie zostaje globalna mimo kraju w tytule)
        regions = extract_regions(context)[:1]
    time = extract_time(thesis)
    periods = extract_periods(thesis)
    months = extract_months(thesis)
    global_scope = not regions and is_global_mentioned(thesis)

    # opcje uzytkownika nadpisuja automat (wystarczy jeden z dwoch lat)
    uw = user_window(options)
    if uw:
        time = {"mode": "explicit", "start": uw[0], "end": uw[1],
                "matched": "z opcji uzytkownika", "default": False}
        periods = clip_periods(periods, uw)
    if options.get("region_id"):
        reg = region_by_id(options["region_id"])
        if reg:
            regions = [region_dict(reg)]

    # porownanie okresow: glowne okno = obwiednia okresow
    if len(periods) >= 2:
        time = {"mode": "explicit",
                "start": min(p["start"] for p in periods),
                "end": max(p["end"] for p in periods),
                "matched": "porównanie okresów", "default": False}

    chart_hint, heatmap_extra = infer_chart_hint(
        thesis, regions, periods, global_scope)

    return {
        "regions": regions,
        "global_scope": global_scope,
        "time": time,
        "periods": periods,
        "months": months,
        "metric_hints": extract_metric_hints(thesis),
        "bodies": extract_bodies(thesis),
        "all_planets": bool(re.search(r"planet|uklad slonecz", __import__("regions")._norm(thesis.lower()))),
        "chart_hint": chart_hint,
        "heatmap_extra": heatmap_extra,
        "source": "rules",
    }


# kompatybilnosc ze starymi testami
def build_plan(thesis: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return build_fallback_plan(thesis, options)
