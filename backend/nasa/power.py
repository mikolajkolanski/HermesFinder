"""Konektor NASA POWER - miesieczne szeregi czasowe dla punktu lub bbox-a.

Endpointy:
  point:    /api/temporal/monthly/point?parameters=T2M&latitude=..&longitude=..
            &start=2000&end=2024&format=JSON  (start/end w formacie ROK)
  regional: /api/temporal/monthly/regional?latitude-min=..&latitude-max=..
            &longitude-min=..&longitude-max=..  (siatka punktow)

Wartosci -999/-998 = brak danych. Klucz "YYYY13" = srednia roczna POWER.
Zwracamy ustandaryzowany slownik:
  {"monthly": [{"year": int, "month": int, "value": float}...],
   "annual": [{"year": int, "value": float}...],   # srednie roczne z 12 miesiecy
   "method": "area_mean"|"point"|"sampled_points"|"region_centroid",
   "n_points": int, "points_used": [[lat, lon], ...] (dla sampled)}
"""
from __future__ import annotations

import math
from typing import Any

import httpx

import config
from nasa.cache import get_or_fetch

POWER_API = "https://power.larc.nasa.gov/api/temporal/monthly"


def _http_get(url: str) -> dict[str, Any]:
    resp = httpx.get(url, timeout=config.HTTP_TIMEOUT,
                     headers={"User-Agent": config.USER_AGENT},
                     follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


def _clamp_bbox(bbox: list[float], max_span: float = 10.0) -> list[float]:
    """Endpoint regionalny POWER przyjmuje maks. 10 stopni na os - przytnij.
    Bboxy przez antymerydian (lon_max < lon_min) nie sa przycinane w dlugosci."""
    lat_min, lat_max, lon_min, lon_max = bbox
    if lat_max - lat_min > max_span:
        lat_min = max(lat_min, lat_max - max_span)
    if lon_max > lon_min and lon_max - lon_min > max_span:
        lon_min = max(lon_min, lon_max - max_span)
    return [lat_min, lat_max, lon_min, lon_max]


def _lon_span(lon_min: float, lon_max: float) -> float:
    """Rozpietosc dlugosci z obsluga antymerydianu (np. Pacyfik 130..-70)."""
    if lon_max >= lon_min:
        return lon_max - lon_min
    return (180.0 - lon_min) + (lon_max + 180.0)


def _grid_estimate(bbox: list[float]) -> int:
    lat_min, lat_max, lon_min, lon_max = bbox
    n_lat = int(abs(lat_max - lat_min) / 0.5) + 1
    n_lon = int(abs(_lon_span(lon_min, lon_max)) / 0.625) + 1
    return n_lat * n_lon


def _sample_points(bbox: list[float], n: int) -> list[tuple[float, float]]:
    """Rownomierna probka n punktow z bbox (kolo rosyjskie bez brzegow).

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


def _parse_point_json(data: dict[str, Any], param: str) -> dict[str, float]:
    values = data["properties"]["parameter"][param]
    return {k: v for k, v in values.items() if v not in (-999.0, -998.0, -999.0)}


def _region_slug(region: dict[str, Any] | None) -> str:
    if not region:
        return "global"
    return f"{region['id']}-{'bbox' if 'bbox' in region else 'point'}"


def fetch_monthly(parameter: str, start: int, end: int,
                  region: dict[str, Any] | None = None,
                  force: bool = False) -> dict[str, Any]:
    """Pobiera miesieczny szereg (bbox=area mean / punkt) z cache."""
    key = f"power:{parameter}:{_region_slug(region)}:{start}-{end}"
    return get_or_fetch(
        key,
        lambda: _fetch_live(parameter, start, end, region),
        force=force,
    )


def _fetch_live(parameter: str, start: int, end: int,
                region: dict[str, Any] | None) -> dict[str, Any]:
    start = max(start, config.POWER_START_YEAR)
    monthly: dict[tuple[int, int], list[float]] = {}

    if region and region.get("type") == "point":
        lat, lon = region["point"]
        data = _http_get(
            f"{POWER_API}/point?parameters={parameter}&community=AG"
            f"&latitude={lat}&longitude={lon}&start={start}&end={end}&format=JSON")
        _accumulate(_parse_point_json(data, parameter), monthly)
        method, n_pts, pts_used = "point", 1, [[lat, lon]]

    elif region and region.get("type") == "bbox":
        bbox = region["bbox"]
        if _grid_estimate(bbox) <= config.POWER_REGIONAL_MAX_POINTS:
            lat_min, lat_max, lon_min, lon_max = _clamp_bbox(bbox)
            data = _http_get(
                f"{POWER_API}/regional?parameters={parameter}&community=AG"
                f"&latitude-min={lat_min}&latitude-max={lat_max}"
                f"&longitude-min={lon_min}&longitude-max={lon_max}"
                f"&start={start}&end={end}&format=JSON")
            feats = data.get("features", [])
            for feat in feats:
                vals = feat["properties"]["parameter"][parameter]
                _accumulate({k: v for k, v in vals.items()
                             if v not in (-999.0, -998.0)}, monthly)
            method, n_pts = "area_mean", len(feats)
            pts_used = None
        else:
            pts = _sample_points(bbox, config.POWER_SAMPLE_POINTS)
            for lat, lon in pts:
                try:
                    data = _http_get(
                        f"{POWER_API}/point?parameters={parameter}&community=AG"
                        f"&latitude={lat}&longitude={lon}"
                        f"&start={start}&end={end}&format=JSON")
                    _accumulate(_parse_point_json(data, parameter), monthly)
                except Exception:  # noqa: BLE001 - punkt nieosiagalny = pomin
                    continue
            pts = pts or [(sum(bbox[0:2]) / 2, sum(bbox[2:4]) / 2)]
            method, n_pts = "sampled_points", len(pts)
            pts_used = [list(p) for p in pts]
    else:
        # brak regionu = srednia z probki punktow na swiecie
        pts = _sample_points([-55, 60, -160, 160], 12)
        for lat, lon in pts:
            try:
                data = _http_get(
                    f"{POWER_API}/point?parameters={parameter}&community=AG"
                    f"&latitude={lat}&longitude={lon}"
                    f"&start={start}&end={end}&format=JSON")
                _accumulate(_parse_point_json(data, parameter), monthly)
            except Exception:  # noqa: BLE001
                continue
        method, n_pts = "sampled_points", len(pts)
        pts_used = [list(p) for p in pts]

    monthly_list = [
        {"year": y, "month": m, "value": round(sum(vals) / len(vals), 4)}
        for (y, m), vals in sorted(monthly.items())
    ]
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
                monthly: dict[tuple[int, int], list[float]]) -> None:
    """Dopisuje serie punktu do akumulatora obszaru (YYYYMM -> wartosci)."""
    for key, val in values.items():
        if len(key) == 6 and key[4:6] != "13":
            y, m = int(key[:4]), int(key[4:6])
            monthly.setdefault((y, m), []).append(val)


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


def fetch_regional_grid(parameter: str, start: int, end: int,
                        bbox: list[float], months: list[int] | None = None,
                        force: bool = False) -> dict[str, Any]:
    """Siatka punktow (lat x lon) ze srednimi rocznymi per punkt - mapa cieplna.

    Uzywa endpointu regionalnego (1 zapytanie). Dostepne tylko dla bbox o
    gestosci <= POWER_REGIONAL_MAX_POINTS punktow (wieksze obszary = za duza
    odpowiedz API). Zwraca tez srednia obszarowa (annual) z tych samych danych.
    """
    lat_min, lat_max, lon_min, lon_max = _clamp_bbox(bbox)

    def fetch() -> dict[str, Any]:
        data = _http_get(
            f"{POWER_API}/regional?parameters={parameter}&community=AG"
            f"&latitude-min={lat_min}&latitude-max={lat_max}"
            f"&longitude-min={lon_min}&longitude-max={lon_max}"
            f"&start={start}&end={end}&format=JSON")
        return data

    key = (f"powergrid:{parameter}:{lat_min}-{lat_max}:{lon_min}-{lon_max}"
           f":{start}-{end}:m={'-'.join(map(str, months)) if months else 'all'}")
    raw = get_or_fetch(key, fetch, force=force)

    cells: dict[str, dict[int, list[float]]] = {}
    area: dict[int, list[float]] = {}
    for feat in raw.get("features", []):
        lon, lat = feat["geometry"]["coordinates"][0], feat["geometry"]["coordinates"][1]
        vals = feat["properties"]["parameter"].get(parameter, {})
        cell_key = f"{round(lat, 3)}|{round(lon, 3)}"
        for k, v in vals.items():
            if len(k) == 6 and k[4:6] != "13" and v not in (-999.0, -998.0):
                year = int(k[:4])
                cells.setdefault(cell_key, {}).setdefault(year, []).append(v)
                area.setdefault(year, []).append(v)

    lats = sorted({float(k.split("|")[0]) for k in cells}, reverse=True)
    lons = sorted({float(k.split("|")[1]) for k in cells})
    years_all = sorted(area.keys())
    n_cells = len(cells)
    min_months = max(2, len(months) - 1) if months else 11

    # wartosci per komorka per rok (srednia z 12 miesiecy lub z filtrowanych)
    grid: dict[str, dict[str, float]] = {}
    for cell_key, by_year in cells.items():
        for year, vs in by_year.items():
            if len(vs) >= min_months:
                grid.setdefault(cell_key, {})[str(year)] = round(
                    sum(vs) / len(vs), 3)

    years = [y for y in years_all
             if sum(1 for cell in grid.values() if str(y) in cell) >= max(3, n_cells // 3)]

    min_pts = max(3, int(0.8 * n_cells)) if n_cells else 0
    annual = [{"year": y, "value": round(sum(vs) / len(vs), 4),
               "n_points": len(vs)}
              for y, vs in sorted(area.items()) if len(vs) >= min_pts]

    return {
        "lats": lats, "lons": lons, "years": years,
        "values": grid, "annual": annual,
        "method": "area_mean", "n_points": len(cells),
        "bbox_used": [lat_min, lat_max, lon_min, lon_max],
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
