"""Porownanie cial Ukladu Slonecznego: NASA NSSDCA Planetary Fact Sheet."""
from __future__ import annotations

import re
from html import unescape
from typing import Any

from nasa.cache import get_or_fetch
from sources.http import get_text

FACTSHEET_URL = "https://nssdc.gsfc.nasa.gov/planetary/factsheet/"

BODIES = [("mercury", "Mercury"), ("venus", "Venus"), ("earth", "Earth"),
          ("moon", "Moon"), ("mars", "Mars"), ("jupiter", "Jupiter"),
          ("saturn", "Saturn"), ("uranus", "Uranus"), ("neptune", "Neptune"),
          ("pluto", "Pluto")]

# klucz metryki -> (fragment etykiety w tabeli NASA, jednostka, opis PL)
METRICS: dict[str, tuple[str, str, str]] = {
    "mean_temp": ("Mean Temperature", "°C", "mean temperature (surface or 1 bar level)"),
    "gravity": ("Gravity", "m/s²", "gravitational acceleration"),
    "distance_sun": ("Distance from Sun", "million km", "mean distance from the Sun"),
    "day_length": ("Length of Day", "hours", "length of the solar day"),
    "surface_pressure": ("Surface Pressure", "bar", "surface pressure"),
    "diameter": ("Diameter", "km", "diameter"),
    "orbital_period": ("Orbital Period", "days", "orbital period"),
    "mass": ("Mass", "10²⁴ kg", "mass"),
}


def _parse_number(raw: str) -> float | None:
    raw = raw.replace(",", "").replace("*", "").strip()
    try:
        return float(raw)
    except ValueError:
        return None


def factsheet(force: bool = False) -> dict[str, Any]:
    """Parsuje tabele {metryka: {body_id: wartosc}} ze strony NASA."""

    def fetch() -> dict[str, Any]:
        html = get_text(FACTSHEET_URL)
        table: dict[str, dict[str, float]] = {}
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
            cells = [re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
            if len(cells) < 11:
                continue
            for key, (label, _unit, _desc) in METRICS.items():
                if key in table or not cells[0].startswith(label):
                    continue
                vals = {}
                for (bid, _name), raw in zip(BODIES, cells[1:11]):
                    v = _parse_number(raw)
                    if v is not None:
                        vals[bid] = v
                if vals:
                    table[key] = vals
        if "mean_temp" not in table:
            raise RuntimeError("NASA Fact Sheet: the table format has changed")
        return {"table": table, "source_url": FACTSHEET_URL}

    return get_or_fetch("planets:factsheet", fetch, ttl_days=60, force=force)


def metric_values(metric: str, body_ids: list[str] | None = None,
                  force: bool = False) -> list[dict[str, Any]]:
    data = factsheet(force)["table"].get(metric, {})
    names = dict(BODIES)
    ids = body_ids or [b for b, _ in BODIES]
    return [{"id": b, "name": names[b], "value": data[b]}
            for b in ids if b in data]
