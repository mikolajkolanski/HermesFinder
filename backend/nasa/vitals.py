"""Konektory zbiorow globalnych NASA: GISTEMP, CO2, poziom morza, lod arktyczny.

Wszystkie zwracaja ustandaryzowany format:
  {"annual": [{"year": int, "value": float}...],
   "monthly": [...] (opcjonalnie),
   "extra": {...}}
"""
from __future__ import annotations

from typing import Any

import httpx

import config
from nasa.cache import get_or_fetch

GISTEMP_URLS = {
    "global": "https://data.giss.nasa.gov/gistemp/tabledata_v4/GLB.Ts+dSST.csv",
    "nh": "https://data.giss.nasa.gov/gistemp/tabledata_v4/NH.Ts+dSST.csv",
    "sh": "https://data.giss.nasa.gov/gistemp/tabledata_v4/SH.Ts+dSST.csv",
}
CO2_URL = "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_annmean_mlo.csv"
VITAL_SIGNS_BASE = ("https://assets.science.nasa.gov/content/dam/science/"
                    "microapps/vital-signs/data/charts")
NSIDC_BASE = "https://noaadata.apps.nsidc.org/NOAA/G02135"
MONTH_NAME = {1: "January", 2: "February", 3: "March", 4: "April", 5: "May",
              6: "June", 7: "July", 8: "August", 9: "September", 10: "October",
              11: "November", 12: "December"}


def _get_text(url: str) -> str:
    resp = httpx.get(url, timeout=config.HTTP_TIMEOUT,
                     headers={"User-Agent": config.USER_AGENT},
                     follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _get_json(url: str) -> Any:
    resp = httpx.get(url, timeout=config.HTTP_TIMEOUT,
                     headers={"User-Agent": config.USER_AGENT},
                     follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------- GISTEMP ----
def gistemp(zone: str = "global", force: bool = False) -> dict[str, Any]:
    """Anomalie GISTEMP v4: roczne (kolumna J-D) i miesieczne."""
    zone = zone if zone in GISTEMP_URLS else "global"
    url = GISTEMP_URLS[zone]

    def fetch() -> dict[str, Any]:
        text = _get_text(url)
        annual: list[dict[str, Any]] = []
        monthly: list[dict[str, Any]] = []
        for line in text.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if not parts or not parts[0].isdigit():
                continue
            year = int(parts[0])
            if len(parts) < 14:
                continue
            j_d = parts[13]  # kolumna J-D (srednia roczna); [12] to grudzien
            if j_d not in ("***", "****", ""):
                annual.append({"year": year, "value": float(j_d)})
            for i, val in enumerate(parts[1:13], start=1):
                if val not in ("***", "****", ""):
                    monthly.append({"year": year, "month": i,
                                    "value": float(val)})
        return {"annual": annual, "monthly": monthly,
                "source_url": url, "baseline": "1951-1980"}

    key = f"gistemp2:{zone}"
    return get_or_fetch(key, fetch, ttl_days=1, force=force)


# --------------------------------------------------------------------- CO2 ---
def co2(force: bool = False) -> dict[str, Any]:
    """Roczne srednie CO2 Mauna Loa (NOAA GML; serwowane przez NASA Vital Signs)."""

    def fetch() -> dict[str, Any]:
        text = _get_text(CO2_URL)
        annual = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "year")):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2 and parts[0].isdigit():
                annual.append({"year": int(parts[0]),
                               "value": float(parts[1])})
        return {"annual": annual, "monthly": [], "source_url": CO2_URL}

    return get_or_fetch("co2:mauna_loa", fetch, ttl_days=30, force=force)


# ------------------------------------------------------------- poziom morza --
def sea_level(force: bool = False) -> dict[str, Any]:
    """GMSL z NASA Vital Signs (satelitarna altymetria od 1993, mm wzgl. 1993)."""

    def fetch() -> dict[str, Any]:
        data = _get_json(f"{VITAL_SIGNS_BASE}/sea-level.json")
        items = data.get("items", [])
        by_year: dict[int, list[float]] = {}
        for it in items:
            cats = it.get("category_titles") or []
            if "SeaLevel" not in cats:
                continue
            y = it.get("year") or int(float(it["x"]))
            val = it.get("y")
            if val is None:
                continue
            by_year.setdefault(int(y), []).append(float(val))
        annual = [{"year": y, "value": round(sum(vs) / len(vs), 2),
                   "n_measurements": len(vs)}
                  for y, vs in sorted(by_year.items())]
        return {"annual": annual, "monthly": [], "source_url":
                f"{VITAL_SIGNS_BASE}/sea-level.json"}

    return get_or_fetch("sea_level:vital_signs", fetch, ttl_days=30,
                        force=force)


# ------------------------------------------------------------- lod arktyczny -
def arctic_ice(pole: str = "north", month: int = 9, force: bool = False) -> dict[str, Any]:
    """Zasieg lodu morskiego (Sea Ice Index, NSIDC/NASA DAAC), mln km^2."""
    pole = "south" if pole == "south" else "north"
    pfx = "S" if pole == "south" else "N"
    url = f"{NSIDC_BASE}/{pole}/monthly/data/{pfx}_{month:02d}_extent_v4.0.csv"

    def fetch() -> dict[str, Any]:
        text = _get_text(url)
        annual = []
        for line in text.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5 and parts[0].isdigit():
                try:
                    extent = float(parts[4])
                except ValueError:
                    continue
                if extent > 0:
                    annual.append({"year": int(parts[0]), "value": extent})
        return {"annual": annual, "monthly": [], "source_url": url,
                "month": month, "pole": pole}

    key = f"arctic_ice:{pole}:{month}"
    return get_or_fetch(key, fetch, ttl_days=30, force=force)
