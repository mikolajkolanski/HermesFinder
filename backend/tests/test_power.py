"""NASA POWER: zapytania regionalne zgodne z limitami API (2..10° na os).

Atrapa API odtwarza zachowanie POWER: 422 dla osi < 2° lub > 10°, siatka
0.5° x 0.625°, wartosc = funkcja polozenia i roku (latwo sprawdzic sklejanie).
Uruchom: cd backend && python -m pytest tests -q
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from nasa import power  # noqa: E402


def _value(lat: float, lon: float, year: int, month: int) -> float:
    return round(20 - 0.5 * lat + 0.01 * lon + 0.05 * (year - 2000) + math.sin(month), 3)


class FakePower:
    def __init__(self, last_year: int = 2025):
        self.calls: list[str] = []
        self.last_year = last_year

    def __call__(self, url: str):
        self.calls.append(url)
        q = dict(re.findall(r"([a-z-]+)=([^&]+)", url))
        start, end = int(q["start"]), int(q["end"])
        req = httpx.Request("GET", url)
        if end > self.last_year:
            raise httpx.HTTPStatusError("422", request=req, response=httpx.Response(422, request=req))
        if "/regional" in url:
            la0, la1 = float(q["latitude-min"]), float(q["latitude-max"])
            lo0, lo1 = float(q["longitude-min"]), float(q["longitude-max"])
            if not (2 <= la1 - la0 <= 10 and 2 <= lo1 - lo0 <= 10):
                raise httpx.HTTPStatusError("422", request=req, response=httpx.Response(422, request=req))
            feats = []
            lat = math.ceil(la0 / 0.5) * 0.5
            while lat <= la1 + 1e-9:
                lon = math.ceil(lo0 / 0.625) * 0.625
                while lon <= lo1 + 1e-9:
                    vals = {f"{y}{m:02d}": _value(lat, lon, y, m)
                            for y in range(start, end + 1) for m in range(1, 13)}
                    feats.append({"geometry": {"coordinates": [lon, lat]},
                                  "properties": {"parameter": {"T2M": vals}}})
                    lon += 0.625
                lat += 0.5
            return {"features": feats}
        lat, lon = float(q["latitude"]), float(q["longitude"])
        vals = {f"{y}{m:02d}": _value(lat, lon, y, m) for y in range(start, end + 1) for m in range(1, 13)}
        return {"properties": {"parameter": {"T2M": vals}}}


@pytest.fixture()
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    f = FakePower()
    monkeypatch.setattr(power, "_http_get", f)
    return f


def test_slovakia_narrow_bbox_no_422(fake):
    # bug z produkcji: Slowacja 47.7-49.6 (1.9°) -> 422
    reg = {"id": "slovakia", "name": "Slovakia", "type": "bbox", "bbox": [47.7, 49.6, 16.8, 22.6]}
    raw = power.annual_series("T2M", 2002, 2025, reg)
    assert raw["method"] == "area_mean"
    assert len(raw["annual"]) == 24
    assert all("latitude-min=47.65" in u for u in fake.calls)


def test_large_bbox_is_tiled_not_cropped(fake):
    # Ukraina ma 18° dlugosci: dawniej przycinano ja do wschodnich 10°
    grid = power.fetch_regional_grid("T2M", 2015, 2020, [44.3, 52.4, 22.1, 40.2])
    assert min(grid["lons"]) < 23 and max(grid["lons"]) > 39
    assert len([u for u in fake.calls if "/regional" in u]) == 2
    assert len(grid["frames"]) == len(grid["years"]) == 6
    assert len(grid["frames"][0]) == len(grid["lats"]) * len(grid["lons"])


def test_europe_heatmap_tiles_and_downsampling(fake, monkeypatch):
    monkeypatch.setattr(power, "MAX_GRID_CELLS", 1500)
    grid = power.fetch_regional_grid("T2M", 2019, 2020, [35.0, 71.0, -10.0, 40.0])
    assert len([u for u in fake.calls if "/regional" in u]) == 20
    assert len(grid["lats"]) * len(grid["lons"]) <= 1500
    assert grid["step"][0] > 0.5
    # cieplej na poludniu: pierwszy wiersz (polnoc) chlodniejszy od ostatniego
    row = len(grid["lons"])
    f = grid["frames"][-1]
    north = [v for v in f[:row] if v is not None]
    south = [v for v in f[-row:] if v is not None]
    assert sum(north) / len(north) < sum(south) / len(south)


def test_unpublished_end_year_retried(fake):
    fake.last_year = 2024  # POWER nie ma jeszcze 2025
    reg = {"id": "poland", "name": "Poland", "type": "bbox", "bbox": [49.0, 54.9, 14.1, 24.15]}
    raw = power.annual_series("T2M", 2002, power._last_year() - 1 if power._last_year() - 1 <= 2025 else 2025, reg)
    assert raw["annual"] and raw["annual"][-1]["year"] <= 2024


def test_too_large_area_for_heatmap(fake):
    with pytest.raises(power.AreaTooLarge):
        power.fetch_regional_grid("T2M", 2019, 2020, [-90, 90, -180, 180])


def test_antimeridian_tiles():
    tiles = power.tiles_for([-10, 5, 170, -170])
    assert all(2 <= t[1] - t[0] <= 10 and 2 <= t[3] - t[2] <= 10 for t in tiles)
    assert any(t[2] >= 170 for t in tiles) and any(t[3] <= -170 for t in tiles)
