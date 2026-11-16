"""Konektory zbiorow GLOBALNYCH spoza NASA (agencje, uniwersytety, firmy).

Kazdy konektor zwraca {"annual": [{"year", "value"}...], "source_url": ...}.
Wartosci pochodza wylacznie z plikow/API dostawcow - nic nie jest generowane.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import zipfile
from typing import Any

from nasa.cache import get_or_fetch
from sources.http import annual_mean, get, get_json, get_text, to_float


def _cur_year() -> int:
    return dt.date.today().year


# ---------------------------------------------------------- NOAA (CAG) -------
def noaa_cag(region: str = "globe", element: str = "tavg",
             surface: str = "land_ocean", force: bool = False) -> dict[str, Any]:
    """NOAA NCEI Climate at a Glance: roczne odchylenia (baza 1901-2000)."""
    url = ("https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/"
           f"global/time-series/{region}/{element}/{surface}/12/12/"
           f"1850-{_cur_year()}/data.csv")

    def fetch() -> dict[str, Any]:
        annual = []
        for line in get_text(url).splitlines():
            parts = line.split(",")
            if len(parts) >= 2 and parts[0].strip().isdigit():
                v = to_float(parts[1])
                if v is not None and v > -90:
                    annual.append({"year": int(parts[0]), "value": v})
        return {"annual": annual, "source_url": url}

    return get_or_fetch(f"noaa_cag:{region}:{element}:{surface}", fetch,
                        ttl_days=3, force=force)


# ------------------------------------------------------ Met Office HadCRUT5 --
HADCRUT_VERSIONS = ["5.1.0.0", "5.0.2.0"]


def hadcrut5(force: bool = False) -> dict[str, Any]:
    """HadCRUT5 (Met Office Hadley Centre + UEA CRU), baza 1961-1990."""

    def fetch() -> dict[str, Any]:
        last_exc: Exception | None = None
        for ver in HADCRUT_VERSIONS:
            url = (f"https://www.metoffice.gov.uk/hadobs/hadcrut5/data/"
                   f"HadCRUT.{ver}/analysis/diagnostics/"
                   f"HadCRUT.{ver}.analysis.summary_series.global.annual.csv")
            try:
                text = get_text(url)
            except Exception as exc:  # noqa: BLE001 - sprobuj starsza wersje
                last_exc = exc
                continue
            annual = []
            for line in text.splitlines():
                parts = line.split(",")
                if len(parts) >= 2 and parts[0].strip().isdigit():
                    v = to_float(parts[1])
                    if v is not None:
                        annual.append({"year": int(parts[0]), "value": v})
            if annual:
                return {"annual": annual, "source_url": url, "version": ver}
        raise RuntimeError(f"HadCRUT5 unavailable: {last_exc}")

    return get_or_fetch("hadcrut5:global", fetch, ttl_days=3, force=force)


# --------------------------------------------------------- Berkeley Earth ----
BERKELEY_BASE = "https://berkeley-earth-temperature.s3.us-west-1.amazonaws.com"


def berkeley_global(force: bool = False) -> dict[str, Any]:
    """Berkeley Earth Land+Ocean, roczne anomalie (baza 1951-1980)."""
    url = f"{BERKELEY_BASE}/Global/Land_and_Ocean_summary.txt"

    def fetch() -> dict[str, Any]:
        annual = []
        for line in get_text(url).splitlines():
            if line.lstrip().startswith("%"):
                continue
            parts = line.split()
            if len(parts) >= 3 and parts[0].isdigit():
                v = to_float(parts[1])
                if v is not None:
                    annual.append({"year": int(parts[0]), "value": v})
        return {"annual": annual, "source_url": url}

    return get_or_fetch("berkeley:global", fetch, ttl_days=7, force=force)


def berkeley_region(slug: str, force: bool = False) -> dict[str, Any]:
    """Berkeley Earth: temperatura ladu dla kraju/kontynentu (anomalia roczna).

    Srednia roczna = srednia 12 miesiecznych anomalii (tylko pelne lata).
    """
    url = f"{BERKELEY_BASE}/Regional/TAVG/{slug}-TAVG-Trend.txt"

    def fetch() -> dict[str, Any]:
        annual, monthly = [], []
        for line in get_text(url).splitlines():
            if line.lstrip().startswith("%"):
                continue
            parts = line.split()
            if len(parts) < 5 or not parts[0].isdigit() or \
                    not parts[1].isdigit():
                continue
            m = to_float(parts[2])
            if m is not None:
                monthly.append({"year": int(parts[0]), "month": int(parts[1]),
                                "value": m})
        by_year: dict[int, list[float]] = {}
        for r in monthly:
            by_year.setdefault(r["year"], []).append(r["value"])
        annual = [{"year": y, "value": round(sum(v) / 12, 4)}
                  for y, v in sorted(by_year.items()) if len(v) == 12]
        if not annual:
            raise RuntimeError(f"Berkeley Earth: no data for '{slug}'")
        return {"annual": annual, "monthly": monthly, "source_url": url}

    return get_or_fetch(f"berkeley2:{slug}", fetch, ttl_days=7, force=force)


# ---------------------------------------------------------------- JMA --------
def jma_global(force: bool = False) -> dict[str, Any]:
    """Japonska Agencja Meteorologiczna: anomalie globalne (baza 1991-2020)."""
    url = "https://www.data.jma.go.jp/cpdinfo/temp/list/csv/an_wld.csv"

    def fetch() -> dict[str, Any]:
        raw = get(url).content.decode("shift_jis", errors="replace")
        annual = []
        for line in raw.splitlines():
            parts = line.split(",")
            if len(parts) >= 2 and parts[0].strip().isdigit():
                v = to_float(parts[1])
                if v is not None:
                    annual.append({"year": int(parts[0]), "value": v})
        return {"annual": annual, "source_url": url}

    return get_or_fetch("jma:global", fetch, ttl_days=7, force=force)


# --------------------------------------------- Copernicus Climate Pulse ------
PULSE_BASE = "https://sites.ecmwf.int/data/climatepulse/data/series"


def era5_pulse(var: str = "2t_global", force: bool = False) -> dict[str, Any]:
    """Copernicus C3S / ECMWF ERA5: dzienne anomalie (baza 1991-2020) -> roczne.

    var: '2t_global' (temperatura powietrza) albo 'sst_60S-60N'.
    Rok liczony tylko, gdy ma >= 360 dni.
    """
    url = f"{PULSE_BASE}/era5_daily_series_{var}.csv"

    def fetch() -> dict[str, Any]:
        rows: list[tuple[int, float]] = []
        absolute: list[tuple[int, float]] = []
        per_month: dict[tuple[int, int], list[float]] = {}
        idx_ano = idx_abs = None
        for line in get_text(url, timeout=180).splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split(",")
            if parts[0] == "date":
                idx_abs = 1
                idx_ano = next((i for i, p in enumerate(parts)
                                if p.startswith("ano")), None)
                continue
            if idx_ano is None or len(parts) <= idx_ano:
                continue
            y = int(parts[0][:4])
            a = to_float(parts[idx_ano])
            b = to_float(parts[idx_abs])
            if a is not None:
                rows.append((y, a))
                per_month.setdefault((y, int(parts[0][5:7])), []).append(a)
            if b is not None:
                absolute.append((y, b))
        monthly = [{"year": y, "month": m,
                    "value": round(sum(v) / len(v), 4)}
                   for (y, m), v in sorted(per_month.items()) if len(v) >= 25]
        return {"annual": annual_mean(rows, 360), "monthly": monthly,
                "annual_absolute": annual_mean(absolute, 360),
                "source_url": url}

    return get_or_fetch(f"era5_pulse:{var}", fetch, ttl_days=3, force=force)


# --------------------------------------- Climate Reanalyzer (Univ. Maine) ----
def oisst_world(force: bool = False) -> dict[str, Any]:
    """NOAA OISST v2.1 przez Climate Reanalyzer (Univ. of Maine): SST 60S-60N."""
    url = ("https://climatereanalyzer.org/clim/sst_daily/json/"
           "oisst2.1_world2_sst_day.json")

    def fetch() -> dict[str, Any]:
        rows: list[tuple[int, float]] = []
        for item in get_json(url, timeout=180):
            name = str(item.get("name", ""))
            if not name.isdigit():
                continue
            for v in item.get("data", []):
                if v is not None:
                    rows.append((int(name), float(v)))
        return {"annual": annual_mean(rows, 360), "source_url": url}

    return get_or_fetch("oisst:world", fetch, ttl_days=3, force=force)


# ------------------------------------------------------- stezenia gazow ------
GML_BASE = "https://gml.noaa.gov/webdata/ccgg/trends"


def noaa_gml_annual(gas: str = "co2", scope: str = "gl",
                    force: bool = False) -> dict[str, Any]:
    """NOAA GML: roczne srednie stezenie (gas: co2/ch4/n2o; scope: gl/mlo)."""
    url = f"{GML_BASE}/{gas}/{gas}_annmean_{scope}.csv"

    def fetch() -> dict[str, Any]:
        annual = []
        for line in get_text(url).splitlines():
            if line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) >= 2 and parts[0].strip().isdigit():
                v = to_float(parts[1])
                if v is not None:
                    annual.append({"year": int(parts[0]), "value": v})
        return {"annual": annual, "source_url": url}

    return get_or_fetch(f"gml:{gas}:{scope}", fetch, ttl_days=30, force=force)


# ----------------------------------------------------------- poziom morza ----
def noaa_star_sea_level(force: bool = False) -> dict[str, Any]:
    """NOAA Laboratory for Satellite Altimetry: GMSL (TOPEX..Sentinel-6), mm."""
    url = ("https://www.star.nesdis.noaa.gov/socd/lsa/SeaLevelRise/slr/"
           "slr_sla_gbl_free_all_66.csv")

    def fetch() -> dict[str, Any]:
        rows: list[tuple[int, float]] = []
        for line in get_text(url, timeout=180).splitlines():
            if line.startswith("#") or line.startswith("year"):
                continue
            parts = line.split(",")
            try:
                year = int(float(parts[0]))
            except ValueError:
                continue
            vals = [to_float(p) for p in parts[1:]]
            vals = [v for v in vals if v is not None]
            if vals:
                rows.append((year, sum(vals) / len(vals)))
        return {"annual": annual_mean(rows, 20), "source_url": url}

    return get_or_fetch("noaa_star:gmsl", fetch, ttl_days=14, force=force)


def csiro_sea_level(force: bool = False) -> dict[str, Any]:
    """CSIRO (Church & White 2011, aktualizacja): GMSL z mareografow, mm."""
    url = ("https://www.cmar.csiro.au/sealevel/downloads/"
           "church_white_gmsl_2011_up.zip")

    def fetch() -> dict[str, Any]:
        z = zipfile.ZipFile(io.BytesIO(get(url, timeout=180).content))
        name = next(n for n in z.namelist()
                    if n.endswith("CSIRO_Recons_gmsl_yr_2015.csv"))
        annual = []
        for line in z.read(name).decode("utf-8", errors="replace").splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2 and re.match(r"^\d{4}\.\d", parts[0]):
                v = to_float(parts[1])
                if v is not None:
                    annual.append({"year": int(float(parts[0])), "value": v})
        return {"annual": annual, "source_url": url, "file": name}

    return get_or_fetch("csiro:gmsl", fetch, ttl_days=60, force=force)


def owid_sea_level(column: str = "UHSLC", force: bool = False) -> dict[str, Any]:
    """Univ. of Hawaii Sea Level Center (UHSLC) / Church&White przez OWID."""
    url = "https://ourworldindata.org/grapher/sea-level.csv?csvType=full"

    def fetch() -> dict[str, Any]:
        import csv
        reader = csv.DictReader(io.StringIO(get_text(url)))
        rows: list[tuple[int, float]] = []
        for r in reader:
            if r.get("Entity") != "World":
                continue
            v = to_float(r.get(column, "") or "")
            q = r.get("Quarter", "")
            if v is not None and re.match(r"^\d{4}-Q\d$", q):
                rows.append((int(q[:4]), v))
        return {"annual": annual_mean(rows, 3), "source_url": url}

    return get_or_fetch(f"owid:sea_level:{column}", fetch, ttl_days=30,
                        force=force)


def psmsl_station(station_id: int, force: bool = False) -> dict[str, Any]:
    """PSMSL (UK National Oceanography Centre): roczne RLR mareografu, mm."""
    url = ("https://psmsl.org/data/obtaining/rlr.annual.data/"
           f"{int(station_id)}.rlrdata")

    def fetch() -> dict[str, Any]:
        annual = []
        for line in get_text(url).splitlines():
            parts = [p.strip() for p in line.split(";")]
            if len(parts) >= 2 and parts[0].isdigit():
                v = to_float(parts[1])
                if v is not None and v > -90000:
                    annual.append({"year": int(parts[0]), "value": v})
        return {"annual": annual, "source_url": url}

    return get_or_fetch(f"psmsl:{station_id}", fetch, ttl_days=30, force=force)


# --------------------------------------------------------------- Slonce ------
def silso_sunspots(force: bool = False) -> dict[str, Any]:
    """SILSO (Royal Observatory of Belgium): roczna liczba plam slonecznych."""
    url = "https://www.sidc.be/SILSO/DATA/SN_y_tot_V2.0.csv"

    def fetch() -> dict[str, Any]:
        annual = []
        for line in get_text(url).splitlines():
            parts = [p.strip() for p in line.split(";")]
            if len(parts) >= 2:
                try:
                    year = int(float(parts[0]))
                    v = float(parts[1])
                except ValueError:
                    continue
                if v >= 0:
                    annual.append({"year": year, "value": v})
        return {"annual": annual, "source_url": url}

    return get_or_fetch("silso:annual", fetch, ttl_days=30, force=force)


# ------------------------------------------------------- lod morski (S) ------
def nsidc_ice(pole: str = "north", month: int = 9,
              force: bool = False) -> dict[str, Any]:
    """NSIDC Sea Index (juz w nasa.vitals) - alias dla spojnosci."""
    from nasa import vitals
    return vitals.arctic_ice(pole, month, force=force)
