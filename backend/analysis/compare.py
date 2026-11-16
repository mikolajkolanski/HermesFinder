"""Karty porownawcze: ten sam temat z wielu organizacji/zrodel naraz.

Zasada projektu bez zmian: backend NIE ocenia tezy. Karta porownawcza tylko
zestawia serie od roznych dostawcow (agencje, uniwersytety, organizacje
non-profit, firmy) na wspolnym wykresie, a fakty opisuja liczby (trend,
rozstep miedzy zrodlami) - bez werdyktu.

Serie anomalii o roznych liniach odniesienia (np. 1951-1980 vs 1961-1990)
sa sprowadzane do WSPOLNEGO okresu bazowego: od kazdej odejmowana jest jej
wlasna srednia z tego okresu. To jedyna transformacja - przesuniecie o stala.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
from typing import Any

from analysis import stats as st
from rag.catalog import get_dataset
from sources import registry
from sources.regional import Unsupported

MIN_POINTS = 5
MAX_SOURCES = 7
# preferowana wspolna linia odniesienia wg tematu (lata wlacznie)
TOPIC_BASELINE = {"sea_level": (1993, 2012)}
DEFAULT_BASELINE = (1991, 2020)


def _pl():
    from analysis import pipeline  # import leniwy: pipeline importuje ten modul
    return pipeline


def label_for(ds: dict[str, Any]) -> str:
    return ds.get("short") or ds["provider"]["org"]


def _unique_labels(items: list[tuple[str, dict[str, Any]]]) -> dict[str, str]:
    seen: dict[str, int] = {}
    out: dict[str, str] = {}
    for ds_id, ds in items:
        base = label_for(ds)
        seen[base] = seen.get(base, 0) + 1
        out[ds_id] = base if seen[base] == 1 else f"{base} ({ds_id})"
    return out


def provider_entry(ds_id: str, ds: dict[str, Any], label: str,
                   note: str | None, baseline: str | None) -> dict[str, Any]:
    prov = ds.get("provider") or {}
    return {
        "label": label, "dataset_id": ds_id,
        "org": prov.get("org"), "org_type": prov.get("type"),
        "country": prov.get("country"),
        "source_name": ds["source"]["name"],
        "url": ds["source"].get("dataset_url") or ds["source"].get("url"),
        "kind": ds.get("kind"), "original_baseline": ds.get("baseline"),
        "data_type": ds.get("data_type"),
        "note": "; ".join(x for x in (note, ds.get("notes")) if x) or None,
    }


# -------------------------------------------------------- linia odniesienia --
def _run_of_years(years: set[int], max_len: int = 30,
                  min_len: int = 10) -> tuple[int, int] | None:
    """Ostatni spojny ciag lat (>= min_len) we wspolnym zbiorze, max max_len."""
    runs: list[list[int]] = []
    for y in sorted(years):
        if runs and y == runs[-1][-1] + 1:
            runs[-1].append(y)
        else:
            runs.append([y])
    for run in reversed(runs):
        if len(run) >= min_len:
            run = run[-max_len:]
            return run[0], run[-1]
    return None


def _covers(years: set[int], base: tuple[int, int]) -> bool:
    need = (base[1] - base[0] + 1) * 0.8
    return sum(1 for y in range(base[0], base[1] + 1) if y in years) >= need


def choose_baseline(year_sets: dict[str, set[int]],
                    preferred: tuple[int, int]
                    ) -> tuple[tuple[int, int] | None, dict[str, str]]:
    """Wspolny okres bazowy + zrodla odrzucone (powod). Najpierw preferowany."""
    dropped: dict[str, str] = {}
    cur = dict(year_sets)
    while len(cur) >= 2:
        if all(_covers(s, preferred) for s in cur.values()):
            return preferred, dropped
        common = set.intersection(*cur.values())
        run = _run_of_years(common)
        if run:
            return run, dropped
        worst = min(cur, key=lambda k: len(cur[k]))
        dropped[worst] = "series too short to set a common baseline"
        cur.pop(worst)
    return None, dropped


# ----------------------------------------------------------- karta glowna ----
def compare_sources_card(q: dict[str, Any], force: bool) -> dict[str, Any] | None:
    pl = _pl()
    items = [(i, get_dataset(i)) for i in q.get("dataset_ids", [])]
    items = [(i, d) for i, d in items if d][:MAX_SOURCES]
    if len(items) < 2:
        return None
    if all(d.get("series_kind") == "seasonal_ls" for _, d in items):
        return seasonal_compare_card(items, q, force)

    regions = q.get("regions") or []
    region = regions[0] if regions else None
    months = q.get("months")
    w0, w1 = int(q["start_year"]), int(q["end_year"])
    topic = items[0][1].get("topic")
    # mareografy: dlugie, czesto zakonczone dawno serie (Gdansk do 1999) -
    # pokazujemy zapis od 1950, inaczej czesc stacji nie mialaby danych w oknie
    if topic == "tide_gauge_sea_level" and not q.get("user_window"):
        w0 = min(w0, 1950)
    labels = _unique_labels(items)
    kinds = {d.get("kind", "absolute") for _, d in items}
    units = {d["unit"] for _, d in items}
    base_pref = TOPIC_BASELINE.get(topic, DEFAULT_BASELINE)
    # wspolna baza tylko dla anomalii/poziomow wzglednych; serie bezwzgledne
    # (emisje, CO2, opady) pokazujemy w oryginalnych wartosciach
    rebase = "anomaly" in kinds
    fetch_lo = min(w0, base_pref[0]) if rebase else w0
    fetch_hi = max(w1, base_pref[1]) if rebase else w1

    def load(item: tuple[str, dict[str, Any]]) -> dict[str, Any]:
        ds_id, ds = item
        try:
            r = pl._series_for(ds, region if ds.get("supports_regions") else None,
                               pl._clamp_window(ds, fetch_lo, fetch_hi), months,
                               force)
            if months and r.get("months_ignored"):
                return {"skip": "no monthly data, so it was left out "
                                "of the month/season filter"}
            return {"rows": r["points"], "note": r["method_note"]}
        except Unsupported as exc:
            return {"skip": str(exc)}
        except Exception as exc:  # noqa: BLE001 - zrodlo zawodzi, reszta dziala
            return {"skip": f"source unavailable ({type(exc).__name__}: "
                            f"{str(exc)[:90]})"}

    with cf.ThreadPoolExecutor(min(len(items), 6)) as ex:
        loaded = list(ex.map(load, items))

    skipped: list[dict[str, str]] = []
    good: dict[str, dict[str, Any]] = {}
    for (ds_id, ds), res in zip(items, loaded):
        if "skip" in res:
            skipped.append({"label": labels[ds_id], "reason": res["skip"]})
        elif len(res["rows"]) < MIN_POINTS:
            skipped.append({"label": labels[ds_id],
                            "reason": "too little data for this region or period"})
        else:
            good[ds_id] = res

    baseline: tuple[int, int] | None = None
    if len(good) == 1:
        # tylko jedno zrodlo zwrocilo dane - wspolna baza niepotrzebna, pokazujemy
        # je w oryginalnych wartosciach (pozostale sa wymienione jako pominiete)
        rebase = False
    if rebase and good:
        years = {i: {r["year"] for r in g["rows"]} for i, g in good.items()}
        baseline, dropped = choose_baseline(years, base_pref)
        for i, reason in dropped.items():
            skipped.append({"label": labels[i], "reason": reason})
            good.pop(i, None)
        if baseline is None:
            good = {}

    series, trends, stats, facts, providers = [], [], [], [], []
    by_label: dict[str, dict[int, float]] = {}
    ds_map = dict(items)
    for ds_id, g in good.items():
        ds = ds_map[ds_id]
        rows = g["rows"]
        offset = 0.0
        if rebase and baseline:
            off = registry.rebase_offset(rows, baseline)
            if off is None:
                skipped.append({"label": labels[ds_id],
                                "reason": "no data in the baseline period"})
                continue
            offset = off
        pts = [{"year": r["year"], "value": round(r["value"] - offset, 4)}
               for r in rows if w0 <= r["year"] <= w1]
        if len(pts) < MIN_POINTS:
            skipped.append({"label": labels[ds_id],
                            "reason": f"too little data in {w0}–{w1}"})
            continue
        lab = labels[ds_id]
        series.append({"label": lab, "points": pts, "dataset_id": ds_id})
        tp = pl._trend_points(pts)
        if tp:
            trends.append({"label": f"trend ({lab})", "points": tp})
        unit = _unit(ds, rebase)
        stats.append(pl._stat_entry(lab, pts, unit))
        by_label[lab] = {p["year"]: p["value"] for p in pts}
        providers.append(provider_entry(ds_id, ds, lab, g["note"],
                                        ds.get("baseline")))

    if not series:
        first = items[0][1]
        return pl._error_card(first, items[0][0], regions, (w0, w1),
                              "none of the sources returned data: " +
                              "; ".join(f"{s['label']} — {s['reason']}"
                                        for s in skipped))
    facts.extend(_spread_facts(by_label, _unit(items[0][1], rebase)))
    if len(series) > 2:
        trends = []  # >2 zrodel: linie trendu zaciemniaja wykres (trend jest w statystykach)

    unit = _unit(items[0][1], rebase)
    title = q.get("title") or _title(items[0][1], region, months)
    base_txt = (f"common baseline {baseline[0]}–{baseline[1]}"
                if rebase and baseline else None)
    notes = []
    if len(units) > 1:
        notes.append("The sources report different quantities or ranges (" + ", ".join(sorted(units)) +
                     "): compare the shape and the trend, not just the level.")
    if base_txt:
        notes.append(
            f"Series with different baselines were shifted to a common period, "
            f"{baseline[0]}–{baseline[1]} (each had its own mean for that period "
            f"subtracted). Only the level changes, not the shape or the trend.")
    for s in skipped:
        notes.append(f"skipped {s['label']}: {s['reason']}")
    first_ds = items[0][1]
    caption_parts = []
    if region:
        caption_parts.append(region["name"])
    # zakres lat faktycznie na wykresie (okno zapytania moze siegac biezacego,
    # niepelnego roku, ktorego zrodla jeszcze nie maja)
    yrs = [p["year"] for s in series for p in s["points"]]
    caption_parts.append(f"{min(yrs)}–{max(yrs)}" if yrs else f"{w0}–{w1}")
    ml = pl._months_label(months)
    if ml:
        caption_parts.append(ml)
    if base_txt:
        caption_parts.append(base_txt)
    caption_parts.append(f"sources ({len(series)}): " +
                         ", ".join(s["label"] for s in series))
    return {
        "id": pl._card_id("cmp"), "type": "multi_line", "compare": True,
        "title": title, "unit": unit, "dataset_id": items[0][0],
        "source": first_ds["source"],
        "caption": "; ".join(caption_parts), "note": q.get("note"),
        "series": series, "trends": trends, "stats": stats, "facts": facts,
        "notes": notes, "providers": providers, "skipped": skipped,
        "baseline": list(baseline) if baseline else None,
        "topic": topic,
    }


def _unit(ds: dict[str, Any], rebase: bool) -> str:
    """Jednostka bez dopisku o linii odniesienia (ta jest w podpisie karty)."""
    return ds["unit"].split(" (")[0]


def _title(ds: dict[str, Any], region: dict[str, Any] | None,
           months: list[int] | None) -> str:
    topic_titles = {
        "global_temperature": "Global surface temperature",
        "ocean_temperature": "Ocean surface temperature",
        "sea_level": "Global sea level",
        "tide_gauge_sea_level": "Sea level at tide gauges",
        "co2": "Atmospheric CO₂ concentration",
        "regional_temperature": "Air temperature",
        "regional_precipitation": "Precipitation",
        "emissions": "Greenhouse gas emissions",
    }
    title = topic_titles.get(ds.get("topic", ""), ds["title"])
    bits = []
    if region:
        bits.append(region["name"])
    ml = _pl()._months_label(months)
    if ml:
        bits.append(ml)
    return title + (": " + ", ".join(bits) if bits else "")


def _spread_facts(by_label: dict[str, dict[int, float]], unit: str) -> list[str]:
    """Opis rozstepu miedzy zrodlami (bez oceny, ktore ma racje)."""
    if len(by_label) < 2:
        return []
    labels = list(by_label)
    common = set.intersection(*(set(v) for v in by_label.values()))
    if not common:
        return []
    out = []
    last = max(common)
    vals = {lab: by_label[lab][last] for lab in labels}
    hi, lo = max(vals, key=vals.get), min(vals, key=vals.get)
    out.append(f"in {last} (last year common to all sources): " +
               "; ".join(f"{lab} {st._fmt(v)} {unit}" for lab, v in vals.items()) +
               f"; spread {st._fmt(vals[hi] - vals[lo])} {unit}")
    spreads = [max(by_label[l][y] for l in labels) - min(by_label[l][y] for l in labels)
               for y in common]
    out.append(f"mean spread between sources over {len(common)} common years: "
               f"{st._fmt(sum(spreads) / len(spreads))} {unit} "
               f"(max {st._fmt(max(spreads))} {unit})")
    return out


# ------------------------------------------------------------- Mars ----------
LS_LABEL = "Martian season, Ls (°)"
LS_NOTE = ("Ls 0° = start of northern spring, 90° = summer, "
           "180° = autumn, 270° = winter; a Martian year lasts 687 Earth days")


def seasonal_compare_card(items: list[tuple[str, dict[str, Any]]],
                          q: dict[str, Any], force: bool) -> dict[str, Any] | None:
    pl = _pl()
    labels = _unique_labels(items)
    series, providers, facts, skipped, notes = [], [], [], [], []
    for ds_id, ds in items:
        try:
            r = registry.seasonal_series(ds, force)
        except Unsupported as exc:
            skipped.append({"label": labels[ds_id], "reason": str(exc)})
            continue
        except Exception as exc:  # noqa: BLE001
            skipped.append({"label": labels[ds_id],
                            "reason": f"source unavailable ({str(exc)[:90]})"})
            continue
        if len(r["points"]) < MIN_POINTS:
            skipped.append({"label": labels[ds_id], "reason": "too little data"})
            continue
        lab = labels[ds_id]
        series.append({"label": lab, "points": r["points"], "dataset_id": ds_id})
        providers.append(provider_entry(ds_id, ds, lab, r["method_note"], None))
        vals = [p["value"] for p in r["points"]]
        lo = min(r["points"], key=lambda p: p["value"])
        hi = max(r["points"], key=lambda p: p["value"])
        unit = ds["unit"]
        facts.append(f"{lab}: mean {st._fmt(sum(vals) / len(vals))} {unit}; "
                     f"minimum {st._fmt(lo['value'])} {unit} (Ls≈{lo['year']:.0f}°), "
                     f"maximum {st._fmt(hi['value'])} {unit} (Ls≈{hi['year']:.0f}°)")
    if not series:
        first = items[0][1]
        return pl._error_card(first, items[0][0], [], (0, 0),
                              "no data: " + "; ".join(
                                  f"{s['label']} — {s['reason']}" for s in skipped))
    if len(series) >= 2:
        a, b = series[0], series[1]
        ya = {p["year"]: p["value"] for p in a["points"]}
        yb = {p["year"]: p["value"] for p in b["points"]}
        common = sorted(set(ya) & set(yb))
        if common:
            diffs = [yb[x] - ya[x] for x in common]
            unit = items[0][1]["unit"]
            facts.append(
                f"{b['label']} − {a['label']} over {len(common)} Ls bins: "
                f"mean {st._fmt(sum(diffs) / len(diffs))} {unit}; "
                f"largest absolute difference {st._fmt(max(abs(d) for d in diffs))} {unit}")
    notes.append(LS_NOTE)
    for it in items:
        if it[1].get("is_model"):
            notes.append(f"{labels[it[0]]}: output of a climate MODEL, not a measurement.")
    for s in skipped:
        notes.append(f"skipped {s['label']}: {s['reason']}")
    first = items[0][1]
    var_title = {"mars_max_temp": "Mars: daily maximum air temperature",
                 "mars_min_temp": "Mars: daily minimum air temperature",
                 "mars_pressure": "Mars: atmospheric pressure",
                 "mars_max_gts_temp": "Mars: daily maximum ground temperature",
                 "mars_min_gts_temp": "Mars: daily minimum ground temperature"
                 }.get(first.get("topic", ""), first["title"])
    return {
        "id": pl._card_id("mars"), "type": "multi_line", "compare": True,
        "title": q.get("title") or var_title,
        "unit": first["unit"], "dataset_id": items[0][0], "source": first["source"],
        "caption": "Gale crater (4.6°S, 137.4°E), by Martian season (Ls); sources: " +
                   ", ".join(s["label"] for s in series),
        "note": q.get("note"), "series": series, "trends": [], "stats": [],
        "facts": facts, "notes": notes, "providers": providers, "skipped": skipped,
        "x_label": LS_LABEL, "x_kind": "ls", "x_min": 0, "x_max": 360,
        "topic": first.get("topic"),
    }


def seasonal_single_card(ds_id: str, ds: dict[str, Any], q: dict[str, Any],
                         force: bool) -> dict[str, Any]:
    """Jeden zbior marsjanski: kazdy rok marsjanski jako osobna linia (REMS)."""
    pl = _pl()
    r = registry.seasonal_series(ds, force)
    series, facts = [], []
    per_year = r.get("per_year") or {}
    for my, pts in sorted(per_year.items()):
        series.append({"label": f"MY{my}", "points": pts})
    if not series:
        series = [{"label": label_for(ds), "points": r["points"]}]
    unit = ds["unit"]
    vals = [p["value"] for p in r["points"]]
    if vals:
        lo = min(r["points"], key=lambda p: p["value"])
        hi = max(r["points"], key=lambda p: p["value"])
        facts.append(f"climatology: mean {st._fmt(sum(vals) / len(vals))} {unit}; "
                     f"min {st._fmt(lo['value'])} {unit} (Ls≈{lo['year']:.0f}°), "
                     f"max {st._fmt(hi['value'])} {unit} (Ls≈{hi['year']:.0f}°)")
    if per_year:
        facts.append(f"full Martian years in the data: "
                     f"MY{min(per_year)}–MY{max(per_year)} ({len(per_year)} years)")
    return {
        "id": pl._card_id("mars"), "type": "multi_line",
        "title": q.get("title") or ds["title"], "unit": unit, "dataset_id": ds_id,
        "source": ds["source"], "caption": "Gale crater, by Martian season (Ls); " + r["method_note"],
        "note": q.get("note"), "series": series, "trends": [], "stats": [],
        "facts": facts, "notes": [LS_NOTE],
        "providers": [provider_entry(ds_id, ds, label_for(ds), r["method_note"], None)],
        "x_label": LS_LABEL, "x_kind": "ls", "x_min": 0, "x_max": 360,
    }


# ---------------------------------------------------------- planety ----------
def planet_bars_card(q: dict[str, Any], force: bool) -> dict[str, Any] | None:
    pl = _pl()
    ds = get_dataset(q["dataset_id"])
    if not ds or ds.get("series_kind") != "planet_metric":
        return None
    body_ids = q.get("body_ids") or None
    vals = registry.planet_values(ds, body_ids, force)
    if len(vals) < 2:
        return None
    unit = ds["unit"]
    facts = []
    hi = max(vals, key=lambda v: v["value"])
    lo = min(vals, key=lambda v: v["value"])
    facts.append(f"highest value: {hi['name']} ({st._fmt(hi['value'])} {unit}); "
                 f"lowest: {lo['name']} ({st._fmt(lo['value'])} {unit})")
    earth = next((v for v in vals if v["id"] == "earth"), None)
    if earth and earth["value"]:
        for v in vals:
            if v["id"] != "earth":
                facts.append(f"{v['name']}: {st._fmt(v['value'])} {unit} "
                             f"(Earth: {st._fmt(earth['value'])} {unit})")
    notes = ["Reference values from the NASA NSSDCA fact sheet "
             "(not a time series). For the gas giants the temperature is at "
             "the 1 bar level, not the surface."] if ds["connector_params"].get(
        "metric") == "mean_temp" else ["Reference values from the NASA NSSDCA "
                                       "fact sheet (not a time series)."]
    return {
        "id": pl._card_id("planet"), "type": "bars", "compare": False,
        "title": q.get("title") or ds["title"], "unit": unit,
        "dataset_id": q["dataset_id"], "source": ds["source"],
        "caption": "NASA Planetary Fact Sheet (NSSDCA)", "note": q.get("note"),
        "values": [{"label": v["name"], "value": v["value"]} for v in vals],
        "facts": facts, "notes": notes,
        "providers": [provider_entry(q["dataset_id"], ds, label_for(ds), None, None)],
    }
