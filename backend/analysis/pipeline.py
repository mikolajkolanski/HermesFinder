"""Pipeline v2: plan (LLM lub fallback) -> executor kart -> odpowiedz API.

Gwarancja zaufania: LLM wplywa wylacznie na DOBOR zbiorow/parametrow.
Wszystkie liczby na kartach pochodza wylacznie z API NASA + scipy.
Kazda karta = jeden wykres; typy: line, multi_line, difference,
period_compare, period_bands, bars, heatmap.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

import config
from analysis import stats as st
from nasa import power as nasa_power
from nasa import vitals
from rag import llm as llm_mod
from rag.catalog import get_dataset, load_catalog
from rag.planner import build_fallback_plan, clip_periods, user_window
from rag.retriever import retrieve
from sources import registry

FIRST_LAST_WINDOW = 5
MIN_POINTS = 5


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _current_year() -> int:
    return dt.date.today().year


# -------------------------------------------------------------- okno czasu ---
def _clamp_window(dataset: dict[str, Any], start: int, end: int,
                  strict: bool = False) -> tuple[int, int]:
    """Okno zapytania przyciete do pokrycia zbioru.

    strict=True: zakres podal uzytkownik w opcjach - nigdy nie wychodzimy poza
    niego (bez przesuwania na najnowsze dostepne lata)."""
    cov_start = int(dataset["coverage"]["start"])
    cov_end = dataset["coverage"].get("end") or _current_year()
    last_full = (_current_year() - 1 if cov_end >= _current_year() else int(cov_end))
    w0, w1 = max(start, cov_start), min(end, last_full)
    if strict:
        return w0, w1
    if w1 - w0 < MIN_POINTS - 1 and end > last_full:
        # zadane okno wychodzi poza koniec zbioru (np. mareograf do 1999 r.,
        # teza o ostatnich 25 latach): najnowsze dostepne okno tej samej dlugosci
        span = max(end - start, MIN_POINTS * 2)
        w0, w1 = max(cov_start, last_full - span), last_full
    return w0, w1


# ----------------------------------------------------------------- serie -----
def _series_for(ds: dict[str, Any], region: dict[str, Any] | None,
                window: tuple[int, int], months: list[int] | None,
                force: bool) -> dict[str, Any]:
    """Srednie roczne dla zbioru (+regionu) w oknie; zwraca punkty i notke."""
    conn = ds["connector"]
    params = ds.get("connector_params", {})
    months_ignored = False

    if conn == "power":
        param = params["parameters"][0]
        raw = nasa_power.annual_series(param, window[0], window[1],
                                       region, months, force=force)
        method_note = nasa_power.region_note(region, {
            "method": raw["method"], "n_points": raw.get("n_points") or 0,
            "points_used": raw.get("points_used")})
        rows = raw["annual"]
    elif conn == "gistemp":
        raw = vitals.gistemp(params.get("zone", "global"), force=force)
        if months:
            by_year: dict[int, list[float]] = {}
            for row in raw["monthly"]:
                if row["month"] in months:
                    by_year.setdefault(row["year"], []).append(row["value"])
            rows = [{"year": y, "value": round(sum(v) / len(v), 3)}
                    for y, v in sorted(by_year.items())]
            method_note = (f"anomalies averaged over months: "
                           f"{', '.join(vitals.MONTH_NAME.get(m, str(m)) for m in months)}")
        else:
            rows = raw["annual"]
            method_note = "annual anomalies vs the 1951–1980 mean"
    elif conn == "co2":
        rows = vitals.co2(force=force)["annual"]
        method_note = "Mauna Loa (Hawaii) measurements, annual means"
    elif conn == "sea_level":
        rows = vitals.sea_level(force=force)["annual"]
        method_note = ("satellite altimetry; values relative to the "
                       "1993 level")
    elif conn == "arctic_ice":
        pole = params.get("pole", "north")
        if months:
            # NSIDC publikuje plik dla kazdego miesiaca - srednia z wybranych
            by_year: dict[int, list[float]] = {}
            for mo in sorted(set(months)):
                for r in vitals.arctic_ice(pole, mo, force=force)["annual"]:
                    by_year.setdefault(r["year"], []).append(r["value"])
            rows = [{"year": y, "value": round(sum(v) / len(v), 3)}
                    for y, v in sorted(by_year.items()) if len(v) == len(set(months))]
            method_note = ("mean sea ice extent in: " +
                           ", ".join(vitals.MONTH_NAME.get(m, str(m)) for m in sorted(set(months))))
        else:
            month = params.get("month", 9)
            rows = vitals.arctic_ice(pole, month, force=force)["annual"]
            method_note = (f"sea ice extent in "
                           f"{vitals.MONTH_NAME.get(month, month)}")
    elif conn in registry.EXTERNAL_CONNECTORS:
        ext = registry.full_series(ds, region, months, force=force)
        rows, method_note = ext["rows"], ext["method_note"]
        months_ignored = ext["months_ignored"]
    else:
        raise ValueError(f"Unknown connector: {conn}")

    points = [{"year": r["year"], "value": float(r["value"])}
              for r in rows
              if window[0] <= r["year"] <= window[1]
              and r.get("value") is not None]
    return {"points": points, "method_note": method_note,
            "months_ignored": months_ignored}


def _regional_note(ds: dict[str, Any], regions: list[dict[str, Any]]) -> str | None:
    if regions and not ds.get("supports_regions"):
        return ("the claim is about a region, but this dataset is global: "
                "treat it as context, not a local measurement")
    return None


# ----------------------------------------------------------------- fakty -----
def _series_stats(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    years = [p["year"] for p in points]
    values = [p["value"] for p in points]
    ols = st.ols(years, values)
    if not ols:
        return None
    return {
        "n": ols["n"],
        "slope_per_decade": round(ols["slope_per_decade"], 4),
        "total_change": round(ols["total_change"], 4),
        "r2": round(ols["r2"], 4),
        "p_value": ols["p_value"],
    }


def _trend_points(points: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    years = [p["year"] for p in points]
    values = [p["value"] for p in points]
    ols = st.ols(years, values)
    if not ols:
        return None
    return st.trend_line(years, ols["slope_per_year"], ols["intercept"])


def _first_last_fact(points: list[dict[str, Any]], unit: str) -> str | None:
    if len(points) < FIRST_LAST_WINDOW * 2:
        return None
    years = [p["year"] for p in points]
    values = [p["value"] for p in points]
    first = sum(values[:FIRST_LAST_WINDOW]) / FIRST_LAST_WINDOW
    last = sum(values[-FIRST_LAST_WINDOW:]) / FIRST_LAST_WINDOW
    diff = last - first
    sign = "+" if diff >= 0 else ""
    return (f"mean of the first {FIRST_LAST_WINDOW} years "
            f"({years[0]}–{years[FIRST_LAST_WINDOW-1]}): {st._fmt(first)} {unit}; "
            f"last {FIRST_LAST_WINDOW} years "
            f"({years[-FIRST_LAST_WINDOW]}–{years[-1]}): {st._fmt(last)} {unit}; "
            f"difference: {sign}{st._fmt(diff)} {unit}")


def _min_max_fact(points: list[dict[str, Any]], unit: str) -> str:
    values = [p["value"] for p in points]
    years = [p["year"] for p in points]
    vmin, vmax = min(values), max(values)
    return (f"range: minimum {st._fmt(vmin)} {unit} ({years[values.index(vmin)]}), "
            f"maximum {st._fmt(vmax)} {unit} ({years[values.index(vmax)]})")


def _ols_fact(label: str, points: list[dict[str, Any]], unit: str) -> str | None:
    stats = _series_stats(points)
    if not stats:
        return None
    sign = "+" if stats["slope_per_decade"] >= 0 else ""
    return (f"{label}: trend {sign}{st._fmt(stats['slope_per_decade'])} "
            f"{unit} per decade; R² = {st._fmt(stats['r2'])}; {st.fmt_p(stats['p_value'])}; "
            f"n = {stats['n']}")


# -------------------------------------------------------------- napisy -------
def _months_label(months: list[int] | None) -> str | None:
    """Etykieta filtru miesiecy: pora roku albo lista miesiecy (po angielsku)."""
    if not months:
        return None
    if set(months) == {12, 1, 2}:
        return "winter (Dec–Feb)"
    if months == [6, 7, 8]:
        return "summer (Jun–Aug)"
    if months == [3, 4, 5]:
        return "spring (Mar–May)"
    if months == [9, 10, 11]:
        return "autumn (Sep–Nov)"
    from rag.planner import MONTH_LABELS
    return "months: " + ", ".join(MONTH_LABELS[m] for m in sorted(months))


def _caption(ds: dict[str, Any], regions: list[dict[str, Any]],
             window: tuple[int, int] | None, periods: list[dict[str, int]],
             months: list[int] | None, method_note: str | None) -> str:
    parts: list[str] = []
    if regions:
        parts.append(" + ".join(r["name"] for r in regions))
    if periods and len(periods) >= 2:
        parts.append(" and ".join(f"{p['start']}–{p['end']}" for p in periods))
    elif window:
        parts.append(f"{window[0]}–{window[1]}")
    months_label = _months_label(months)
    if months_label:
        parts.append(months_label)
    if method_note:
        parts.append(method_note)
    parts.append(ds["source"]["name"])
    return "; ".join(parts)


def _fallback_title(ds: dict[str, Any], regions: list[dict[str, Any]],
                    months: list[int] | None,
                    multi: bool) -> str:
    title = ds["title"]
    bits = []
    if regions and ds.get("supports_regions"):
        bits.append(" + ".join(r["name"] for r in regions))
    elif multi:
        bits.append("regional comparison")
    months_label = _months_label(months)
    if months_label:
        bits.append(months_label)
    return f"{title}: {', '.join(bits)}" if bits else title


# ------------------------------------------------------------- executor ------
def execute_query(q: dict[str, Any], force: bool) -> list[dict[str, Any]]:
    """Jedno zapytanie planu -> 1-2 karty (heatmapa doklada karte line)."""
    from analysis import compare
    ds = get_dataset(q["dataset_id"])
    if not ds:
        return []
    chart = q["chart_type"]

    # --- porownanie zrodel / planety / Mars: karty z modulu compare ---
    if chart == "compare_sources":
        card = compare.compare_sources_card(q, force)
        if card:
            return [card]
        chart = "line"  # za malo zbiorow -> zwykla karta pierwszego zbioru
    if chart == "planet_bars" or ds.get("series_kind") == "planet_metric":
        card = compare.planet_bars_card(q, force)
        return [card] if card else []
    if ds.get("series_kind") == "seasonal_ls":
        return [compare.seasonal_single_card(q["dataset_id"], ds, q, force)]

    regions = q["regions"] if ds.get("supports_regions") else []
    months = q.get("months")
    unit = ds["unit"]
    cards: list[dict[str, Any]] = []

    if chart in ("period_compare", "period_bands", "bars"):
        periods_raw = q.get("periods") or []
        if periods_raw:
            # obwiednia okresow zamiast surowego okna z planu
            q_start = min(p["start"] for p in periods_raw)
            q_end = max(p["end"] for p in periods_raw)
        else:
            q_start, q_end = q["start_year"], q["end_year"]
        window = _clamp_window(ds, q_start, q_end, bool(q.get("user_window")))
        periods = [p for p in q.get("periods", [])
                   if p["end"] >= window[0] and p["start"] <= window[1]]
        if len(periods) < 2:
            periods = [{"start": window[0],
                        "end": min(window[1], window[0] + 9)},
                       {"start": max(window[0], window[1] - 9),
                        "end": window[1]}]
        # 1..N regionow na karcie okresow (None = global/wartosc roczna);
        # period_bands zostaje tylko dla pojedynczej serii
        region_list: list[dict[str, Any] | None] = (regions[:4] if regions
                                                    else [None])
        if chart == "period_bands" and len(region_list) > 1:
            chart = "period_compare"
        series_by_region: list[tuple[Any, dict[str, Any]]] = []
        method_note = None
        for reg in region_list:
            s = _series_for(ds, reg, window, months, force)
            method_note = method_note or s["method_note"]
            if len(s["points"]) >= MIN_POINTS:
                series_by_region.append((reg, s))
        if not series_by_region:
            return [_error_card(ds, q["dataset_id"], regions, window,
                                f"no data for {window[0]}–{window[1]}")]
        period_cards = []
        for p in periods:
            entries = []
            for reg, s in series_by_region:
                pts = [x for x in s["points"]
                       if p["start"] <= x["year"] <= p["end"]]
                if len(pts) < MIN_POINTS // 2:
                    continue
                mean = sum(x["value"] for x in pts) / len(pts)
                trend_pts = _trend_points(pts)
                entries.append({
                    "label": reg["name"] if reg else "annual value",
                    "points": pts,
                    "mean": round(mean, 3),
                    "trend": ({"label": f"trend {p['start']}–{p['end']}",
                               "points": trend_pts} if trend_pts else None),
                    "stats": _series_stats(pts),
                })
            if entries:
                period_cards.append({
                    "label": f"{p['start']}–{p['end']}",
                    "start": p["start"], "end": p["end"],
                    "series": entries,
                })
        if len(period_cards) < 2:
            return []
        base = {
            "title": q.get("title") or _fallback_title(ds, regions, months, False),
            "unit": unit, "dataset_id": q["dataset_id"], "source": ds["source"],
            "caption": _caption(ds, regions, None,
                                periods, months, method_note),
            "note": q.get("note"),
        }
        if chart == "period_compare":
            cards.append({**base, "id": _card_id("pcmp"), "type": "period_compare",
                          "periods": period_cards,
                          "facts": _period_facts(period_cards, unit)})
        elif chart == "bars":
            cards.append({**base, "id": _card_id("bars"), "type": "bars",
                          "values": [{"label": f"{pc['label']}, {e['label']}",
                                      "value": e["mean"]}
                                     for pc in period_cards for e in pc["series"]],
                          "facts": _period_facts(period_cards, unit)})
        else:  # period_bands (pojedyncza seria)
            reg0, s0 = series_by_region[0]
            pts_all = s0["points"]
            trend_all = _trend_points(pts_all)
            cards.append({**base, "id": _card_id("pbnd"), "type": "period_bands",
                          "series": [{"label": reg0["name"] if reg0 else "annual value",
                                      "points": pts_all}],
                          "trends": ([{"label": reg0["name"] if reg0 else "trend",
                                       "points": trend_all}] if trend_all else []),
                          "bands": [{"label": pc["label"], "start": pc["start"],
                                     "end": pc["end"]} for pc in period_cards],
                          "stats": [_stat_entry(reg0["name"] if reg0 else "period",
                                                pts_all, unit)],
                          "facts": _period_facts(period_cards, unit)})
        return cards

    # --- karty szeregowe (line / multi_line / difference / heatmap) ---
    window = _clamp_window(ds, q["start_year"], q["end_year"],
                           bool(q.get("user_window")))
    if chart == "difference":
        if len(regions) < 2:
            chart = "line"
        else:
            a = _series_for(ds, regions[0], window, months, force)
            b = _series_for(ds, regions[1], window, months, force)
            ya = {p["year"]: p["value"] for p in a["points"]}
            yb = {p["year"]: p["value"] for p in b["points"]}
            common = sorted(set(ya) & set(yb))
            if len(common) < MIN_POINTS:
                return [_error_card(ds, q["dataset_id"], regions, window,
                                    "too few years with data for both regions")]
            diff = [{"year": y, "value": round(ya[y] - yb[y], 4)} for y in common]
            label = f"{regions[0]['name']} − {regions[1]['name']}"
            card = {
                "id": _card_id("diff"), "type": "difference",
                "title": q.get("title") or f"Difference {label}: {ds['title']}",
                "unit": unit, "dataset_id": q["dataset_id"], "source": ds["source"],
                "caption": _caption(ds, regions[:2], window, [], months,
                                    a["method_note"]),
                "note": q.get("note"),
                "series": [{"label": label, "points": diff}],
                "trends": ([{"label": f"trend ({label})",
                             "points": _trend_points(diff)}]
                           if _trend_points(diff) else []),
                "stats": [_stat_entry(label, diff, unit)],
                "facts": _series_facts(label, diff, unit, diff=True),
                "notes": _notes_for(ds, a["method_note"], regions),
            }
            cards.append(card)
            return cards

    if chart == "multi_line" and len(regions) < 2:
        chart = "line"

    if chart == "heatmap" and (not regions
                               or regions[0].get("type") != "bbox"):
        chart = "line"

    if chart == "multi_line" and regions:
        return [_multi_line_card(ds, regions, window, months, q, force)]

    if chart == "heatmap":
        return _heatmap_cards(ds, regions[0], window, months, q, force)

    # zwykły line (1 region lub global)
    region = regions[0] if regions else None
    try:
        s = _series_for(ds, region, window, months, force)
    except registry.Unsupported as exc:
        return [_error_card(ds, q["dataset_id"], regions, window, str(exc))]
    if len(s["points"]) < MIN_POINTS:
        return [_error_card(ds, q["dataset_id"], regions, window,
                            f"too little data in {window[0]}–{window[1]} "
                            f"(available years: {ds['coverage']['start']} to usually "
                            f"last year)")]
    label = region["name"] if region else "annual value"
    trend = _trend_points(s["points"])
    card = {
        "id": _card_id("line"), "type": "line",
        "title": q.get("title") or _fallback_title(ds, [region] if region else [],
                                                   months, False),
        "unit": unit, "dataset_id": q["dataset_id"], "source": ds["source"],
        "caption": _caption(ds, [region] if region else [], window, [],
                            months, s["method_note"]),
        "note": q.get("note"),
        "series": [{"label": label, "points": s["points"]}],
        "trends": ([{"label": f"trend ({label})",
                     "points": trend}] if trend else []),
        "stats": [_stat_entry(label, s["points"], unit)],
        "facts": _series_facts(label, s["points"], unit),
        "notes": _notes_for(ds, s["method_note"], [region] if region else []),
    }
    cards.append(card)
    return cards



def _card_id(prefix: str) -> str:
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _stat_entry(label: str, points: list[dict[str, Any]], unit: str) -> dict[str, Any]:
    stats = _series_stats(points) or {}
    return {"label": label, "unit": unit, **stats}


def _series_facts(label: str, points: list[dict[str, Any]], unit: str,
                  diff: bool = False) -> list[str]:
    facts: list[str] = []
    if diff:
        values = [p["value"] for p in points]
        mean = sum(values) / len(values)
        facts.append(f"mean difference {label}: "
                     f"{'+' if mean >= 0 else ''}{st._fmt(mean)} {unit}")
    ols_fact = _ols_fact(label, points, unit)
    if ols_fact:
        facts.append(ols_fact)
    fl = _first_last_fact(points, unit)
    if fl:
        facts.append(fl)
    facts.append(_min_max_fact(points, unit))
    stats = _series_stats(points)
    if stats:
        facts.append(st.describe_trend(stats).capitalize() + ".")
    return facts


def _period_facts(period_cards: list[dict[str, Any]], unit: str) -> list[str]:
    """Fakty dla kart okresowych: srednia per okres (per region) + roznice."""
    facts: list[str] = []
    labels = [e["label"] for e in period_cards[0]["series"]]
    for label in labels:
        means = {}
        for pc in period_cards:
            for e in pc["series"]:
                if e["label"] == label:
                    means[pc["label"]] = e["mean"]
        if len(means) < 2:
            continue
        parts = [f"{k}: {st._fmt(v)} {unit}" for k, v in means.items()]
        keys = list(means.keys())
        d = means[keys[-1]] - means[keys[0]]
        parts.append(f"difference {keys[-1]} vs {keys[0]}: "
                     f"{'+' if d >= 0 else ''}{st._fmt(d)} {unit}")
        facts.append(f"{label} — " + "; ".join(parts))
    return facts


def _notes_for(ds: dict[str, Any], method_note: str,
               regions: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    if method_note:
        notes.append(method_note)
    reg_note = _regional_note(ds, regions)
    if reg_note:
        notes.append(reg_note)
    notes.append(f"dataset coverage: from {ds['coverage']['start']}")
    return notes


def _error_card(ds: dict[str, Any], ds_id: str, regions: list[dict[str, Any]],
                window: tuple[int, int], message: str) -> dict[str, Any]:
    return {
        "id": _card_id("err"), "type": "line",
        "title": _fallback_title(ds, regions, None, False),
        "unit": ds["unit"], "dataset_id": ds_id, "source": ds["source"],
        "caption": _caption(ds, regions, window, [], None, None),
        "error": message,
        "series": [], "trends": [], "stats": [], "facts": [], "notes": [],
    }


def _multi_line_card(ds: dict[str, Any], regions: list[dict[str, Any]],
                     window: tuple[int, int], months: list[int] | None,
                     q: dict[str, Any], force: bool) -> dict[str, Any]:
    series, stats, trends, facts, notes = [], [], [], [], []
    method_note = None
    for reg in regions:
        try:
            s = _series_for(ds, reg, window, months, force)
        except registry.Unsupported:
            continue
        method_note = method_note or s["method_note"]
        if len(s["points"]) < MIN_POINTS:
            continue
        series.append({"label": reg["name"], "points": s["points"]})
        trends.append({"label": f"trend ({reg['name']})",
                       "points": _trend_points(s["points"])})
        stats.append(_stat_entry(reg["name"], s["points"], ds["unit"]))
        facts.extend(_series_facts(reg["name"], s["points"], ds["unit"]))
    if not series:
        return _error_card(ds, q["dataset_id"], regions, window, "no data for the selected regions")
    return {
        "id": _card_id("multi"), "type": "multi_line",
        "title": q.get("title") or _fallback_title(ds, regions, months, True),
        "unit": ds["unit"], "dataset_id": q["dataset_id"], "source": ds["source"],
        "caption": _caption(ds, regions, window, [], months, method_note),
        "note": q.get("note"),
        "series": series,
        "trends": [t for t in trends if t["points"]],
        "stats": stats, "facts": facts,
        "notes": _notes_for(ds, method_note or "", regions),
    }


def _heatmap_cards(ds: dict[str, Any], region: dict[str, Any],
                   window: tuple[int, int], months: list[int] | None,
                   q: dict[str, Any], force: bool) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    try:
        grid = nasa_power.fetch_regional_grid(
            ds["connector_params"]["parameters"][0],
            window[0], window[1], region["bbox"], months, force=force)
    except Exception as exc:  # noqa: BLE001 - heatmapa nie zabija karty line
        grid = None
        heat_err = str(exc)
    if grid and grid["years"] and len(grid["years"]) >= 3:
        # karta line ze sredniej obszarowej z tej samej siatki (pomijana, gdy plan
        # ma juz osobna karte tego tematu i regionu - "nie wiecej")
        pts = [{"year": r["year"], "value": r["value"]} for r in grid["annual"]
               if window[0] <= r["year"] <= window[1]]
        if len(pts) >= MIN_POINTS and not q.get("heatmap_only"):
            trend = _trend_points(pts)
            cards.append({
                "id": _card_id("line"), "type": "line",
                "title": q.get("title") or _fallback_title(ds, [region], months, False),
                "unit": ds["unit"], "dataset_id": q["dataset_id"],
                "source": ds["source"],
                "caption": _caption(ds, [region], window, [], months,
                                    f"area mean of the POWER grid "
                                    f"({grid['n_points']} points)"),
                "note": q.get("note"),
                "series": [{"label": region["name"], "points": pts}],
                "trends": ([{"label": f"trend ({region['name']})",
                             "points": trend}] if trend else []),
                "stats": [_stat_entry(region["name"], pts, ds["unit"])],
                "facts": _series_facts(region["name"], pts, ds["unit"]),
                "notes": _notes_for(ds, grid["method"], [region]),
            })
        cards.append({
            "id": _card_id("heat"), "type": "heatmap",
            "title": f"Heat map: {region['name']}",
            "unit": ds["unit"], "dataset_id": q["dataset_id"],
            "source": ds["source"],
            "caption": _caption(ds, [region], window, [], months,
                                f"POWER grid of {grid['n_points']} points, "
                                f"pick the year with the slider"),
            "note": "move the slider to see the spatial pattern in a given year",
            "grid": {"lats": grid["lats"], "lons": grid["lons"],
                     "years": grid["years"], "values": grid["values"]},
            "bbox": grid.get("bbox_used"),
            "stats": [], "facts": _heatmap_facts(grid, ds["unit"]), "notes": [],
        })
        return cards
    # heatmapa niedostepna -> zwykla karta line
    s = _series_for(ds, region, window, months, force)
    if len(s["points"]) < MIN_POINTS:
        err = _error_card(ds, q["dataset_id"], [region], window,
                          f"heat map unavailable: {heat_err if not grid else 'too few years'}")
        return [err]
    trend = _trend_points(s["points"])
    return [{
        "id": _card_id("line"), "type": "line",
        "title": q.get("title") or _fallback_title(ds, [region], months, False),
        "unit": ds["unit"], "dataset_id": q["dataset_id"], "source": ds["source"],
        "caption": _caption(ds, [region], window, [], months, s["method_note"]),
        "note": q.get("note"),
        "series": [{"label": region["name"], "points": s["points"]}],
        "trends": ([{"label": f"trend ({region['name']})",
                     "points": trend}] if trend else []),
        "stats": [_stat_entry(region["name"], s["points"], ds["unit"])],
        "facts": _series_facts(region["name"], s["points"], ds["unit"]),
        "notes": _notes_for(ds, s["method_note"], [region]),
    }]


def _heatmap_facts(grid: dict[str, Any], unit: str) -> list[str]:
    last_year = str(grid["years"][-1])
    cells = [(float(k.split("|")[0]), float(k.split("|")[1]), v[last_year])
             for k, v in grid["values"].items() if last_year in v]
    if not cells:
        return []
    vmin = min(cells, key=lambda c: c[2])
    vmax = max(cells, key=lambda c: c[2])
    return [
        f"pattern in {last_year}: warmest grid cell "
        f"{vmax[0]:.1f}°N {vmax[1]:.1f}°E ({st._fmt(vmax[2])} {unit}), "
        f"coldest {vmin[0]:.1f}°N {vmin[1]:.1f}°E "
        f"({st._fmt(vmin[2])} {unit})",
        f"difference between grid cells in {last_year}: "
        f"{st._fmt(vmax[2] - vmin[2])} {unit}",
    ]


# ------------------------------------------------- fallback -> queries -------
BALTIC_REGIONS = {"poland", "baltic", "pomorskie", "zachodniopomorskie",
                  "gdansk", "szczecin", "sweden", "lithuania", "latvia",
                  "estonia", "finland", "germany", "denmark"}


TOPIC_FAMILY = {**llm_mod.TOPIC_FAMILY, "nh_temperature": "temp"}


def _compare_ids(ds: dict[str, Any], regions: list[dict[str, Any]]) -> list[str]:
    """Zbiory tego samego tematu od roznych dostawcow (dla karty porownawczej)."""
    from analysis.compare import MAX_SOURCES
    cat = load_catalog()
    topic = ds.get("topic") or ""
    if topic == "regional_temperature" and not regions:
        topic = "global_temperature"
    if topic == "tide_gauge_sea_level":
        rids = {r["id"] for r in regions}
        return (llm_mod.TIDE_BALTIC if rids & BALTIC_REGIONS else llm_mod.TIDE_DEFAULT)[:4]
    ids = [i for i, d in cat.items() if d.get("topic") == topic]
    if not regions:  # zrodla wymagajace regionu nic nie pokaza bez niego
        ids = [i for i in ids
               if cat[i].get("region_scope") not in ("any", "country", "eu")]
    return ids[:MAX_SOURCES]


def _space_queries(thesis: str, fallback: dict[str, Any],
                   picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Zapytania o Marsa / planety: sezonowa pogoda Marsa + porownanie planet."""
    from regions import _norm
    n = _norm(thesis.lower())
    cat = load_catalog()
    bodies = fallback.get("bodies") or []
    w = fallback["time"]
    base = {"regions": [], "start_year": int(w["start"]),
            "end_year": int(w["end"]), "months": None, "periods": [],
            "title": None, "note": None}
    queries: list[dict[str, Any]] = []
    top = cat[picks[0]["id"]]
    metric = "mean_temp"
    for pat, m in [(r"grawitac|przyciagan|gravity", "gravity"),
                   (r"odleglos|od slonca|distance", "distance_sun"),
                   (r"\bdob[ay]|dlugosc dnia|day length", "day_length"),
                   (r"srednic|rozmiar|wielkosc|najwieksz|najmniejsz", "diameter"),
                   (r"obieg|orbit", "orbital_period")]:
        if re.search(pat, n):
            metric = m
            break
    if metric == "mean_temp" and re.search(r"cisnien|pressure", n) and \
            ("mars" not in bodies or fallback.get("all_planets")):
        metric = "surface_pressure"
    mars_only = ("mars" in bodies and len([b for b in bodies if b != "earth"]) == 1) \
        or (not bodies and top.get("body") == "mars" and not fallback.get("all_planets"))
    wants_mars = mars_only and metric == "mean_temp"

    if wants_mars:
        if "cisnien" in n or "pressure" in n:
            vars_ = ["pressure"]
        elif "grunt" in n or "ground" in n:
            vars_ = ["max_gts_temp", "min_gts_temp"]
        else:
            vars_ = ["max_temp", "min_temp"]
        for v in vars_:
            ids = [i for i in (f"mars_rems_{v}", f"mars_mcd_{v}") if i in cat]
            if len(ids) >= 2:
                queries.append({**base, "dataset_id": ids[0], "dataset_ids": ids,
                                "chart_type": "compare_sources"})
            elif ids:
                queries.append({**base, "dataset_id": ids[0], "chart_type": "line"})
        body_ids = ["mars"] + [b for b in bodies if b != "mars"]
        if "earth" not in body_ids:
            body_ids.append("earth")
        queries.append({**base, "dataset_id": ("planet_surface_pressure"
                                               if vars_ == ["pressure"]
                                               else "planet_mean_temp"),
                        "chart_type": "planet_bars", "body_ids": body_ids})
    else:
        ds_id = f"planet_{metric}"
        body_ids = [] if fallback.get("all_planets") or not bodies else bodies
        if bodies and "earth" not in body_ids and len(body_ids) == 1:
            body_ids = body_ids + ["earth"]
        queries.append({**base, "dataset_id": ds_id, "chart_type": "planet_bars",
                        "body_ids": body_ids})
    return queries[:config.MAX_CARDS]


def _fallback_queries(thesis: str, fallback: dict[str, Any],
                      options: dict[str, Any]) -> list[dict[str, Any]]:
    """Konwertuje deterministyczny plan na queries (bez LLM)."""
    top_k = int(options.get("top_k") or 2)
    # ranking calego katalogu (61 zbiorow), potem straznik tematow wybiera te,
    # o ktorych teza mowi - premia za region nie wypycha np. poziomu morza
    picks = retrieve(thesis, fallback, top_k=len(load_catalog()))
    if not picks:
        return []
    folded = llm_mod._fold(thesis)
    cat_ = load_catalog()
    supported = [p for p in picks
                 if llm_mod._topic_supported(cat_[p["id"]].get("topic") or "", folded)]
    picks = supported or picks[:1]
    regions = fallback["regions"]
    months_raw = fallback.get("months")
    months = months_raw["months"] if months_raw else None
    window = fallback["time"]
    periods = fallback.get("periods") or []
    chart_hint = fallback.get("chart_hint", "line")
    queries: list[dict[str, Any]] = []

    primary = picks[0]["id"]
    ds = get_dataset(primary)
    if not ds:
        return []
    if fallback.get("bodies") or (ds.get("body") in ("mars", "solar_system")
                                  and re.search(llm_mod.PLANET_WORDS, folded)):
        return _space_queries(thesis, fallback, picks)

    def base_query(ds_item: dict[str, Any], ds_id: str, chart: str,
                   regs: list[dict[str, Any]], w: dict[str, Any]) -> dict[str, Any]:
        return {
            "dataset_id": ds_id,
            "regions": regs if ds_item.get("supports_regions") else [],
            "start_year": int(w["start"]), "end_year": int(w["end"]),
            "months": months, "chart_type": chart,
            "periods": periods,
            "title": None, "note": None,
        }

    if chart_hint in ("multi_line", "difference") and len(regions) >= 2 \
            and ds.get("supports_regions"):
        queries.append(base_query(ds, primary, chart_hint, regions, window))
        extra = [p for p in picks[1:2] if p["id"] != primary]
        for pick in extra:
            d2 = get_dataset(pick["id"])
            if d2 and d2.get("supports_regions"):
                queries.append(base_query(d2, pick["id"], "multi_line", regions, window))
            else:
                queries.append(base_query(d2, pick["id"], "line", regions, window))
    elif chart_hint in ("period_compare", "period_bands", "bars") and len(periods) >= 2:
        # karta okresow obsluguje 1..N regionow; bez regionu bierzemy pierwszy
        # zbior globalny z rankingu (np. Berkeley regionalny nie ma serii "swiat")
        def needs_region(d: dict[str, Any]) -> bool:
            return d.get("region_scope") in ("country", "eu") or d.get("connector") == "open_meteo"

        p_ds, p_id = ds, primary
        if not regions and needs_region(ds):
            for pick in picks:
                d2 = get_dataset(pick["id"])
                if d2 and not needs_region(d2):
                    p_ds, p_id = d2, pick["id"]
                    break
        queries.append(base_query(p_ds, p_id, chart_hint,
                                  regions if p_ds.get("supports_regions") else [],
                                  window))
    else:
        # porownanie ZRODEL: ten sam temat od roznych organizacji; potem kolejne
        # tematy z rankingu (max 2 karty porownawcze) + opcjonalnie heatmapa
        regs = regions if ds.get("supports_regions") else []
        seen_topics: set[str] = set()
        seen_families: set[str] = set()
        for pick in picks[:6]:
            d2 = get_dataset(pick["id"])
            if not d2 or len(queries) >= 2:
                break
            topic = d2.get("topic") or pick["id"]
            family = TOPIC_FAMILY.get(topic, topic)
            # "nie wiecej": drugi temat tylko z innej rodziny (Tmax obok temperatury
            # sredniej to ta sama wielkosc - nie dublujemy)
            if topic in seen_topics or family in seen_families:
                continue
            seen_topics.add(topic)
            seen_families.add(family)
            regs2 = regions if d2.get("supports_regions") or \
                d2.get("topic", "").startswith("regional") else []
            ids = _compare_ids(d2, regs2)
            if len(ids) >= 2:
                q = base_query(d2, ids[0], "compare_sources", regs2, window)
                q["regions"] = regs2[:1]
                q["dataset_ids"] = ids
                queries.append(q)
            else:
                queries.append(base_query(d2, pick["id"], "line",
                                          regs2 if d2.get("supports_regions") else [],
                                          window))
        bbox_regs = [r for r in regs if r.get("type") == "bbox"]
        if fallback.get("heatmap_extra") and bbox_regs:
            hm_ds = next((p["id"] for p in picks
                          if get_dataset(p["id"]).get("connector") == "power"), None)
            if hm_ds:
                queries.append(base_query(get_dataset(hm_ds), hm_ds, "heatmap",
                                          bbox_regs, window))
    return queries[:config.MAX_CARDS]


def _sources_summary(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Organizacje, z ktorych pochodza dane w calej odpowiedzi."""
    orgs: dict[str, dict[str, Any]] = {}
    for c in cards:
        if c.get("error"):
            continue
        entries = c.get("providers") or []
        if not entries:
            ds = get_dataset(c.get("dataset_id", "")) or {}
            prov = ds.get("provider") or {}
            if prov:
                entries = [{"org": prov.get("org"), "org_type": prov.get("type"),
                            "country": prov.get("country"),
                            "source_name": (c.get("source") or {}).get("name")}]
        for e in entries:
            org = e.get("org")
            if not org:
                continue
            o = orgs.setdefault(org, {"org": org, "type": e.get("org_type"),
                                      "country": e.get("country"),
                                      "datasets": []})
            name = e.get("source_name")
            if name and name not in o["datasets"]:
                o["datasets"].append(name)
    return list(orgs.values())


def _apply_user_window(q: dict[str, Any], window: tuple[int, int]) -> dict[str, Any]:
    """Zapytanie z oknem lat uzytkownika (okresy przyciete do okna)."""
    return {**q, "start_year": window[0], "end_year": window[1],
            "periods": clip_periods(q.get("periods") or [], window),
            "user_window": True}


def _trim_card_years(card: dict[str, Any], window: tuple[int, int]) -> None:
    """Zabezpieczenie: punkty roczne karty tylko z okna uzytkownika."""
    if card.get("x_kind") == "ls":
        return
    inside = lambda pts: [p for p in pts if window[0] <= p.get("year", window[0]) <= window[1]]  # noqa: E731
    for key in ("series", "trends"):
        for s in card.get(key) or []:
            if isinstance(s, dict) and isinstance(s.get("points"), list):
                s["points"] = inside(s["points"])
    for p in card.get("periods") or []:
        if isinstance(p.get("points"), list):
            p["points"] = inside(p["points"])
        for s in p.get("series") or []:
            if isinstance(s.get("points"), list):
                s["points"] = inside(s["points"])
            if isinstance(s.get("trend"), dict) and isinstance(s["trend"].get("points"), list):
                s["trend"]["points"] = inside(s["trend"]["points"])
    grid = card.get("grid")
    if isinstance(grid, dict) and isinstance(grid.get("years"), list):
        grid["years"] = [y for y in grid["years"] if window[0] <= y <= window[1]]


# -------------------------------------------------------------- glowny flow ---
def analyze(thesis: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    force = bool(options.get("force_refresh"))

    fallback = build_fallback_plan(thesis, options)
    queries: list[dict[str, Any]] = []
    summary: str | None = None
    planner_info: dict[str, Any] = {"used": False, "provider": None,
                                    "model": None}

    info = llm_mod.llm_info()
    if info["available"] and not options.get("disable_llm"):
        plan = llm_mod.plan_with_llm(thesis, fallback, options.get("context"))
        if plan and plan.get("queries"):
            queries = plan["queries"]
            summary = plan.get("summary")
            planner_info = {"used": True, "provider": info["provider"],
                            "model": llm_mod.last_model_used() or info["model"],
                            "summary": summary,
                            "non_english_dropped": len(llm_mod.NON_ENGLISH_DROPPED)}

    if not queries:
        queries = _fallback_queries(thesis, fallback, options)
        queries = llm_mod.normalize_queries(queries, thesis, load_catalog(),
                                            fallback.get("regions") or [])
        planner_info["fallback_used"] = True
        if info["available"] and not options.get("disable_llm"):
            planner_info["llm_error"] = llm_mod.LAST_ERROR

    # zakres lat z opcji obowiazuje KAZDE zapytanie (takze plan od LLM)
    uw = user_window(options)
    if uw:
        queries = [_apply_user_window(q, uw) for q in queries]
        planner_info["user_window"] = list(uw)

    cards: list[dict[str, Any]] = []
    for q in queries:
        if len(cards) >= config.MAX_CARDS:
            break
        try:
            new_cards = execute_query(q, force)
            ds_q = get_dataset(q.get("dataset_id", "")) or {}
            for c in new_cards:
                # metadane karty: temat danych, regiony, miesiace (dla klientow i testow)
                c.setdefault("topic", ds_q.get("topic"))
                c.setdefault("region_ids", [r["id"] for r in (q.get("regions") or [])])
                c.setdefault("months", q.get("months"))
                c.setdefault("body_ids", q.get("body_ids") or [])
            cards.extend(new_cards)
        except Exception as exc:  # noqa: BLE001 - blad jednej karty nie zabija reszty
            cards.append({
                "id": _card_id("err"), "type": "line", "title": "Card error",
                "unit": "", "dataset_id": str(q.get("dataset_id", "")),
                "source": (get_dataset(str(q.get("dataset_id", ""))) or {}).get("source", {}),
                "caption": "", "error": f"could not prepare this card: {exc}",
                "series": [], "trends": [], "stats": [], "facts": [], "notes": [],
            })
        cards = cards[:config.MAX_CARDS]

    if uw:
        shown: list[int] = []
        for c in cards:
            _trim_card_years(c, uw)
            if c.get("x_kind") != "ls":
                shown += [p["year"] for s in c.get("series") or [] for p in s.get("points") or []]
                shown += [p["year"] for per in c.get("periods") or []
                          for s in per.get("series") or [] for p in s.get("points") or []]
        # lata faktycznie na wykresach (filtr 2005-, a dane do 2025 -> 2005-2025)
        planner_info["years_shown"] = [min(shown), max(shown)] if shown else None

    # stabilne id canvasow: card-0, card-1...
    for i, c in enumerate(cards):
        c["idx"] = i

    return {
        "thesis": thesis,
        "summary": summary,
        "cards": cards,
        "sources": _sources_summary(cards),
        "planner": planner_info,
        "disclaimer": config.DISCLAIMER,
        "generated_at": _now_iso(),
    }
