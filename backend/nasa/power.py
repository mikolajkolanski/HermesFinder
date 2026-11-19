"""Konektor NASA POWER - miesieczne szeregi czasowe dla punktu lub bbox-a.

Endpointy:
  point:    /api/temporal/monthly/point?parameters=T2M&latitude=..&longitude=..
            &start=2000&end=2024&format=JSON  (start/end w formacie ROK)
  regional: /api/temporal/monthly/regional?latitude-min=..&latitude-max=..
            &longitude-min=..&longitude-max=..  (siatka punktow 0.5° x 0.625°)

Ograniczenia endpointu regionalnego (zrodlo bledu 422):
  * kazda os bbox-a musi miec CO NAJMNIEJ 2° (Slowacja: 47.7-49.6 = 1.9° -> 422),
  * i NAJWYZEJ 10° - wieksze obszary (Francja, Ukraina, Europa) sa dzielone na
    kafle <= 10° x 10°, pobierane rownolegle i sklejane (komorki na stykach kafli
    sa deduplikowane),
  * rok koncowy, ktorego POWER jeszcze nie opublikowal, tez daje 422 - wtedy
    ponawiamy zapytanie z rokiem wczesniejszym.

Wartosci -999/-998 = brak danych. Klucz "YYYY13" = srednia roczna POWER (pomijana).
Zwracamy ustandaryzowany slownik:
  {"monthly": [{"year": int, "month": int, "value": float}...],
   "annual": [{"year": int, "value": float}...],   # srednie roczne z 12 miesiecy
   "method": "area_mean"|"point"|"sampled_points",
   "n_points": int, "points_used": [[lat, lon], ...] (dla sampled)}
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import math
from typing import Any

import httpx

import config
from nasa.cache import get_or_fetch

POWER_API = "https://power.larc.nasa.gov/api/temporal/monthly"
MIN_SPAN = 2.0          # minimalny zakres osi w zapytaniu regionalnym
MAX_SPAN = 10.0         # maksymalny zakres osi w zapytaniu regionalnym
LAT_STEP, LON_STEP = 0.5, 0.625
MAX_TILES_MEAN = 12     # srednia obszarowa z kafli (wiecej -> probka punktow)
MAX_TILES_GRID = 40     # mapa cieplna: Europa = 20 kafli, Chiny = 28
TILE_WORKERS = 6
MAX_GRID_CELLS = 9000   # wiecej komorek -> usrednianie blokami (lzejsza odpowiedz)
MISSING = (-999.0, -998.0)


class AreaTooLarge(ValueError):
    """Obszar wymaga zbyt wielu zapytan regionalnych POWER."""


def _http_get(url: str) -> dict[str, Any]:
    resp = httpx.get(url, timeout=config.HTTP_TIMEOUT,
                     headers={"User-Agent": config.USER_AGENT},
                     follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def _last_year() -> int:
    return dt.date.today().year


# ----------------------------------------------------------- geometria bbox --
def _lon_span(lon_min: float, lon_max: float) -> float:
    """Rozpietosc dlugosci z obsluga antymerydianu (np. Pacyfik 130..-70)."""
    if lon_max >= lon_min:
        return lon_max - lon_min
    return (180.0 - lon_min) + (lon_max + 180.0)


def _widen(lo: float, hi: float, lo_lim: float, hi_lim: float,
           span: float = MIN_SPAN) -> tuple[float, float]:
    """Rozszerza przedzial do co najmniej `span` stopni (wokol srodka, w granicach)."""
    if hi - lo >= span:
        return lo, hi
    mid = (lo + hi) / 2
    lo, hi = mid - span / 2, mid + span / 2
    if lo < lo_lim:
        lo, hi = lo_lim, lo_lim + span
    if hi > hi_lim:
        lo, hi = hi_lim - span, hi_lim
    return round(lo, 4), round(hi, 4)


def _split(lo: float, hi: float, max_span: float = MAX_SPAN) -> list[tuple[float, float]]:
    n = max(1, math.ceil((hi - lo) / max_span - 1e-9))
    step = (hi - lo) / n
    return [(round(lo + i * step, 4), round(lo + (i + 1) * step, 4)) for i in range(n)]


def tiles_for(bbox: list[float]) -> list[list[float]]:
    """Kafle zapytan regionalnych (kazda os 2..10°) pokrywajace bbox.

    Bbox przez antymerydian (lon_max < lon_min) jest dzielony na dwie czesci.
    """
    lat_min, lat_max, lon_min, lon_max = bbox
    lat_min, lat_max = max(-90.0, min(lat_min, lat_max)), min(90.0, max(lat_min, lat_max))
    lon_parts = [(lon_min, lon_max)] if lon_max >= lon_min else [(lon_min, 180.0), (-180.0, lon_max)]
    out: list[list[float]] = []
    for la0, la1 in _split(*_widen(lat_min, lat_max, -90.0, 90.0)):
        la0, la1 = _widen(la0, la1, -90.0, 90.0)
        for part in lon_parts:
            for lo0, lo1 in _split(*_widen(part[0], part[1], -180.0, 180.0)):
                lo0, lo1 = _widen(lo0, lo1, -180.0, 180.0)
                out.append([la0, la1, lo0, lo1])
    return out


def _grid_estimate(bbox: list[float]) -> int:
    lat_min, lat_max, lon_min, lon_max = bbox
    n_lat = int(abs(lat_max - lat_min) / LAT_STEP) + 1
    n_lon = int(abs(_lon_span(lon_min, lon_max)) / LON_STEP) + 1
    return n_lat * n_lon


def _sample_points(bbox: list[float], n: int) -> list[tuple[float, float]]:
    """Rownomierna probka n punktow z bbox (srodki komorek, bez brzegow).

    Obsluguje bboxy przez antymerydian (lon_max < lon_min).
    """
    lat_min, lat_max, lon_min, lon_max = bbox
    side = max(1, math.isqrt(n))
    pts: list[tuple[float, float]] = []
    total_span = _lon_span(lon_min, lon_max)
    wraps = lon_max < lon_min
    for i in range(side):
        lat = lat_min + (lat_max - lat_min) * (i + 0.5) / side
        for j in range(side):
            d = total_span * (j + 0.5) / side
            if wraps and d > 180.0 - lon_min:
                lon = -180.0 + (d - (180.0 - lon_min))
            else:
                lon = lon_min + d
            pts.append((round(lat, 3), round(lon, 3)))
    return pts


def _in_bbox(lat: float, lon: float, bbox: list[float]) -> bool:
    lat_min, lat_max, lon_min, lon_max = bbox
    if not (lat_min - 1e-6 <= lat <= lat_max + 1e-6):
        return False
    if lon_max >= lon_min:
        return lon_min - 1e-6 <= lon <= lon_max + 1e-6
    return lon >= lon_min - 1e-6 or lon <= lon_max + 1e-6


# --------------------------------------------------------------- pobieranie --
def _with_year_retry(build_url, start: int, end: int) -> dict[str, Any]:
    """GET z ponowieniem dla 422 przy roku koncowym, ktorego POWER jeszcze nie ma."""
    try:
        return _http_get(build_url(start, end))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 422 and end >= _last_year() - 1 and end - 1 > start:
            return _http_get(build_url(start, end - 1))
        raise


def _point_values(parameter: str, lat: float, lon: float, start: int, end: int) -> dict[str, float]:
    data = _with_year_retry(
        lambda s, e: (f"{POWER_API}/point?parameters={parameter}&community=AG"
                      f"&latitude={lat}&longitude={lon}&start={s}&end={e}&format=JSON"),
        start, end)
    values = data["properties"]["parameter"][parameter]
    return {k: v for k, v in values.items() if v not in MISSING}


def _fetch_tile(parameter: str, tile: list[float], start: int, end: int,
                force: bool = False) -> dict[str, dict[str, float]]:
    """Jeden kafel regionalny -> {"lat|lon": {"YYYYMM": wartosc}} (cache per kafel)."""
    la0, la1, lo0, lo1 = tile

    def fetch() -> dict[str, dict[str, float]]:
        data = _with_year_retry(
            lambda s, e: (f"{POWER_API}/regional?parameters={parameter}&community=AG"
                          f"&latitude-min={la0}&latitude-max={la1}"
                          f"&longitude-min={lo0}&longitude-max={lo1}"
                          f"&start={s}&end={e}&format=JSON"),
            start, end)
        cells: dict[str, dict[str, float]] = {}
        for feat in data.get("features", []):
            lon, lat = feat["geometry"]["coordinates"][0], feat["geometry"]["coordinates"][1]
            vals = feat["properties"]["parameter"].get(parameter, {})
            cells[f"{round(lat, 3)}|{round(lon, 3)}"] = {
                k: v for k, v in vals.items()
                if len(k) == 6 and k[4:6] != "13" and v not in MISSING}
        return cells

    key = f"powertile:{parameter}:{la0}:{la1}:{lo0}:{lo1}:{start}-{end}"
    return get_or_fetch(key, fetch, force=force)


def fetch_cells(parameter: str, start: int, end: int, bbox: list[float],
                max_tiles: int = MAX_TILES_GRID, force: bool = False
                ) -> dict[str, dict[str, float]]:
    """Wszystkie komorki siatki POWER w bbox (kafle rownolegle, bez duplikatow)."""
    start = max(start, config.POWER_START_YEAR)
    tiles = tiles_for(bbox)
    if len(tiles) > max_tiles:
        raise AreaTooLarge(f"the area needs {len(tiles)} NASA POWER requests "
                           f"(limit {max_tiles}); pick a smaller area")
    cells: dict[str, dict[str, float]] = {}
    outside: dict[str, dict[str, float]] = {}
    errors: list[Exception] = []
    with cf.ThreadPoolExecutor(min(TILE_WORKERS, len(tiles))) as ex:
        futs = [ex.submit(_fetch_tile, parameter, t, start, end, force) for t in tiles]
        for f in futs:
            try:
                part = f.result()
            except Exception as exc:  # noqa: BLE001 - brakujacy kafel = luka
                errors.append(exc)
                continue
            for k, v in part.items():
                lat, lon = (float(x) for x in k.split("|"))
                (cells if _in_bbox(lat, lon, bbox) else outside).setdefault(k, v)
    if not cells and errors:
        raise errors[0]
    # bardzo maly obszar (np. miasto jako bbox) - zadna komorka nie lezy w srodku:
    # zostaja komorki z poszerzonego zapytania
    return cells or outside


def _region_slug(region: dict[str, Any] | None) -> str:
    if not region:
        return "global"
    if region.get("type") == "bbox":
        return f"{region['id']}-bbox-{'-'.join(str(x) for x in region['bbox'])}"
    return f"{region['id']}-point"


def fetch_monthly(parameter: str, start: int, end: int,
                  region: dict[str, Any] | None = None,
                  force: bool = False) -> dict[str, Any]:
    """Pobiera miesieczny szereg (bbox=area mean / punkt) z cache."""
    key = f"power2:{parameter}:{_region_slug(region)}:{start}-{end}"
    return get_or_fetch(
        key,
        lambda: _fetch_live(parameter, start, end, region, force),
        force=force,
    )


def _sampled(parameter: str, pts: list[tuple[float, float]], start: int, end: int,
             monthly: dict[tuple[int, int], list[float]]) -> list[tuple[float, float]]:
    used: list[tuple[float, float]] = []

    def one(p: tuple[float, float]) -> tuple[tuple[float, float], dict[str, float] | None]:
        try:
            return p, _point_values(parameter, p[0], p[1], start, end)
        except Exception:  # noqa: BLE001 - punkt nieosiagalny = pomin
            return p, None

    with cf.ThreadPoolExecutor(min(TILE_WORKERS, max(1, len(pts)))) as ex:
        for p, vals in ex.map(one, pts):
            if vals:
                _accumulate(vals, monthly)
                used.append(p)
    return used


def _fetch_live(parameter: str, start: int, end: int,
                region: dict[str, Any] | None, force: bool = False) -> dict[str, Any]:
    start = max(start, config.POWER_START_YEAR)
    monthly: dict[tuple[int, int], list[float]] = {}
    weights: dict[tuple[int, int], list[float]] = {}

    if region and region.get("type") == "point":
        lat, lon = region["point"]
        _accumulate(_point_values(parameter, lat, lon, start, end), monthly)
        method, n_pts, pts_used = "point", 1, [[lat, lon]]

    elif region and region.get("type") == "bbox":
        bbox = region["bbox"]
        if len(tiles_for(bbox)) <= MAX_TILES_MEAN:
            cells = fetch_cells(parameter, start, end, bbox, MAX_TILES_MEAN, force)
            for k, vals in cells.items():
                w = max(0.05, math.cos(math.radians(float(k.split("|")[0]))))
                _accumulate(vals, monthly, weights, w)
            method, n_pts, pts_used = "area_mean", len(cells), None
        else:
            pts = _sample_points(bbox, config.POWER_SAMPLE_POINTS)
            used = _sampled(parameter, pts, start, end, monthly)
            method, n_pts = "sampled_points", len(used) or len(pts)
            pts_used = [list(p) for p in (used or pts)]
    else:
        # brak regionu = srednia z probki punktow na swiecie
        pts = _sample_points([-55, 60, -160, 160], 12)
        used = _sampled(parameter, pts, start, end, monthly)
        method, n_pts = "sampled_points", len(used) or len(pts)
        pts_used = [list(p) for p in (used or pts)]

    monthly_list = []
    for (y, m), vals in sorted(monthly.items()):
        ws = weights.get((y, m))
        mean = (sum(v * w for v, w in zip(vals, ws)) / sum(ws)) if ws else sum(vals) / len(vals)
        monthly_list.append({"year": y, "month": m, "value": round(mean, 4)})
    annual = _annual_from_monthly(monthly_list)
    return {
        "monthly": monthly_list,
        "annual": annual,
        "method": method,
        "n_points": n_pts,
        "points_used": pts_used,
        "parameter": parameter,
    }


def _accumulate(values: dict[str, float],
                monthly: dict[tuple[int, int], list[float]],
                weights: dict[tuple[int, int], list[float]] | None = None,
                w: float = 1.0) -> None:
    """Dopisuje serie punktu do akumulatora obszaru (YYYYMM -> wartosci)."""
    for key, val in values.items():
        if len(key) == 6 and key[4:6] != "13" and val not in MISSING:
            y, m = int(key[:4]), int(key[4:6])
            monthly.setdefault((y, m), []).append(val)
            if weights is not None:
                weights.setdefault((y, m), []).append(w)


def _annual_from_monthly(monthly_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Srednia roczna = srednia z 12 miesiecy (z 11+ tez przyjmujemy)."""
    by_year: dict[int, list[float]] = {}
    for row in monthly_list:
        by_year.setdefault(row["year"], []).append(row["value"])
    return [{"year": y, "value": round(sum(vs) / len(vs), 4),
             "n_months": len(vs)}
            for y, vs in sorted(by_year.items()) if len(vs) >= 11]


def annual_series(parameter: str, start: int, end: int,
                  region: dict[str, Any] | None = None,
                  months: list[int] | None = None,
                  force: bool = False) -> dict[str, Any]:
    """Srednie roczne (opcjonalnie tylko wybrane miesiace, np. zima DJF).

    Zima (XII-I-II) dla roku Y = grudzien Y-1 + styczen Y + luty Y.
    """
    raw = fetch_monthly(parameter, start, end, region, force)
    monthly = raw["monthly"]
    if months is None:
        annual = raw["annual"]
    else:
        by_year: dict[int, dict[int, float]] = {}
        for row in monthly:
            by_year.setdefault(row["year"], {})[row["month"]] = row["value"]
        annual = []
        if set(months) == {12, 1, 2}:  # meteorologiczna zima
            for y in range(start + 1, end + 1):
                vals = [by_year.get(y - 1, {}).get(12),
                        by_year.get(y, {}).get(1), by_year.get(y, {}).get(2)]
                vals = [v for v in vals if v is not None]
                if len(vals) == 3:
                    annual.append({"year": y,
                                   "value": round(sum(vals) / 3, 4),
                                   "n_months": 3})
        else:
            for y, mm in by_year.items():
                vals = [mm[m] for m in months if m in mm]
                if len(vals) >= max(1, len(months) - 1):
                    annual.append({"year": y,
                                   "value": round(sum(vals) / len(vals), 4),
                                   "n_months": len(vals)})
        annual.sort(key=lambda r: r["year"])
    return {**raw, "annual": annual}


# ------------------------------------------------------------- mapa cieplna --
def _cell_year_value(vals: dict[str, float], year: int,
                     months: list[int] | None) -> float | None:
    if months and set(months) == {12, 1, 2}:
        keys = [f"{year - 1}12", f"{year}01", f"{year}02"]
        need = 3
    elif months:
        keys = [f"{year}{m:02d}" for m in sorted(set(months))]
        need = max(1, len(keys) - 1)
    else:
        keys = [f"{year}{m:02d}" for m in range(1, 13)]
        need = 11
    got = [vals[k] for k in keys if k in vals]
    return round(sum(got) / len(got), 3) if len(got) >= need else None


def fetch_regional_grid(parameter: str, start: int, end: int,
                        bbox: list[float], months: list[int] | None = None,
                        force: bool = False) -> dict[str, Any]:
    """Siatka punktow (lat x lon) ze srednimi rocznymi per punkt - mapa cieplna.

    Dowolny bbox do MAX_TILES_GRID kafli 10° x 10° (Europa, USA, Chiny...).
    Zwraca kompaktowe klatki: frames[i] = wartosci roku years[i] wierszami
    (lats malejaco, lons rosnaco; None = brak danych) oraz srednia obszarowa.
    """
    cells = fetch_cells(parameter, start, end, bbox, MAX_TILES_GRID, force)
    first = max(start, config.POWER_START_YEAR)
    lats = sorted({float(k.split("|")[0]) for k in cells}, reverse=True)
    lons_raw = sorted({float(k.split("|")[1]) for k in cells})
    wraps = bbox[3] < bbox[2]
    # antymerydian: dlugosci po wschodniej stronie zaczynaja os (130..180, -180..-70)
    lons = ([x for x in lons_raw if x >= bbox[2]] + [x for x in lons_raw if x < bbox[2]]) if wraps else lons_raw
    years_all = list(range(first + (1 if months and set(months) == {12, 1, 2} else 0), end + 1))

    values: dict[tuple[int, int], dict[int, float]] = {}
    ri = {lat: i for i, lat in enumerate(lats)}
    ci = {lon: i for i, lon in enumerate(lons)}
    for k, vals in cells.items():
        lat, lon = (float(x) for x in k.split("|"))
        per_year = {}
        for y in years_all:
            v = _cell_year_value(vals, y, months)
            if v is not None:
                per_year[y] = v
        if per_year:
            values[(ri[lat], ci[lon])] = per_year

    n_cells = len(values)
    years = [y for y in years_all
             if sum(1 for c in values.values() if y in c) >= max(3, int(0.6 * n_cells))]

    # srednia obszarowa (waga cos(lat)) z tych samych komorek
    annual = []
    for y in years:
        num = den = 0.0
        for (r, _c), c in values.items():
            if y in c:
                w = max(0.05, math.cos(math.radians(lats[r])))
                num += c[y] * w
                den += w
        if den:
            annual.append({"year": y, "value": round(num / den, 4)})

    # zbyt gesta siatka -> bloki k x k (srednia), zeby odpowiedz byla lekka
    factor = 1
    while math.ceil(len(lats) / factor) * math.ceil(len(lons) / factor) > MAX_GRID_CELLS:
        factor += 1
    out_lats = [round(sum(lats[i:i + factor]) / len(lats[i:i + factor]), 3)
                for i in range(0, len(lats), factor)]
    out_lons = [round(sum(lons[j:j + factor]) / len(lons[j:j + factor]), 3)
                for j in range(0, len(lons), factor)]
    frames: list[list[float | None]] = []
    for y in years:
        frame: list[float | None] = []
        for i in range(0, len(lats), factor):
            for j in range(0, len(lons), factor):
                vs = [values[(a, b)][y] for a in range(i, min(i + factor, len(lats)))
                      for b in range(j, min(j + factor, len(lons)))
                      if (a, b) in values and y in values[(a, b)]]
                frame.append(round(sum(vs) / len(vs), 3) if vs else None)
        frames.append(frame)

    return {
        "lats": out_lats, "lons": out_lons, "years": years, "frames": frames,
        "annual": annual, "method": "area_mean", "n_points": n_cells,
        "step": [LAT_STEP * factor, LON_STEP * factor],
        "bbox_used": [min(lats), max(lats), bbox[2], bbox[3]] if lats else bbox,
        "parameter": parameter,
    }


def region_note(region: dict[str, Any] | None, raw: dict[str, Any]) -> str:
    """Opis sposobu uśrednienia obszarowego (do sekcji notatek)."""
    if not region:
        return ("mean of 12 evenly spaced grid points around the world "
                "(NASA POWER reanalysis)")
    method = raw.get("method")
    if method == "point":
        return f"grid point: {region['name']} ({region['point'][0]}°N, {region['point'][1]}°E)"
    if method == "area_mean":
        return (f"area mean of the NASA POWER grid over {region['name']} "
                f"({raw['n_points']} grid points)")
    if method == "sampled_points":
        pts = raw.get("points_used") or []
        return (f"mean of {len(pts)} evenly spaced grid points "
                f"over {region['name']}")
    return region["name"]
