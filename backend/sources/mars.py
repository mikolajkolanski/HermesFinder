"""Mars: obserwacje Curiosity REMS (NASA/JPL + CAB-INTA, Hiszpania) oraz model
Mars Climate Database (LMD/CNES, Open University, IAA, ESA).

Dane sezonowe indeksowane dlugoscia heliocentryczna Ls (0-360 deg), bo rok
ziemski miesza pory roku marsjanskie (rok Marsa = 687 dni ziemskich).
"""
from __future__ import annotations

import concurrent.futures as cf
import re
import threading
from typing import Any

from nasa.cache import cached_at, get_or_fetch
from sources.http import get, get_json, to_float

REMS_URL = "https://mars.nasa.gov/rss/api/?feed=weather&category=msl&feedtype=json"
MCD_URL = "https://www-mars.lmd.jussieu.fr/mcd_python/cgi-bin/mcdcgi.py"
GALE = (-4.6, 137.4)          # krater Gale - miejsce pracy Curiosity
LS_BIN = 15                   # szerokosc przedzialu Ls (stopnie)
MCD_LS_STEP = 30              # krok Ls dla modelu MCD (srodki = co drugi przedzial REMS)
FIRST_MARS_YEAR = 31          # Curiosity ladowal w MY31 (sierpien 2012, Ls~150)

REMS_VARS = {
    "max_temp": ("°C", "daily maximum air temperature (REMS, ~1.5 m)"),
    "min_temp": ("°C", "daily minimum air temperature (REMS, ~1.5 m)"),
    "pressure": ("Pa", "atmospheric pressure (REMS)"),
    "max_gts_temp": ("°C", "daily maximum ground temperature (REMS GTS)"),
    "min_gts_temp": ("°C", "daily minimum ground temperature (REMS GTS)"),
}


def _rems_raw(force: bool = False) -> dict[str, Any]:
    """Wszystkie sole REMS jako lista rekordow z numerem roku marsjanskiego."""

    def fetch() -> dict[str, Any]:
        data = get_json(REMS_URL, timeout=180)
        sols = sorted(data["soles"], key=lambda s: int(s["sol"]))
        out = []
        my, prev_ls = FIRST_MARS_YEAR, None
        for s in sols:
            ls = to_float(str(s.get("ls", "")))
            if ls is None:
                continue
            if prev_ls is not None and prev_ls > 300 and ls < 60:
                my += 1
            prev_ls = ls
            rec = {"sol": int(s["sol"]), "date": s["terrestrial_date"],
                   "ls": ls, "my": my}
            for var in REMS_VARS:
                rec[var] = to_float(str(s.get(var, "")))
            out.append(rec)
        return {"sols": out, "source_url": REMS_URL}

    return get_or_fetch("mars:rems:raw", fetch, ttl_days=7, force=force)


def rems_mars_years(var: str, force: bool = False) -> dict[int, list[dict[str, Any]]]:
    """{rok_marsjanski: [{year: Ls_srodka_przedzialu, value}]} (tylko pelne lata)."""
    raw = _rems_raw(force)["sols"]
    by_my: dict[int, list[dict[str, Any]]] = {}
    for r in raw:
        by_my.setdefault(r["my"], []).append(r)
    result: dict[int, list[dict[str, Any]]] = {}
    for my, recs in by_my.items():
        bins: dict[int, list[float]] = {}
        for r in recs:
            v = r.get(var)
            if v is None:
                continue
            b = int(r["ls"] // LS_BIN)
            bins.setdefault(b, []).append(v)
        n_bins = 360 // LS_BIN
        # pelny rok: dane w >= 85% przedzialow Ls
        if len(bins) < 0.85 * n_bins:
            continue
        result[my] = [{"year": b * LS_BIN + LS_BIN / 2,
                       "value": round(sum(v) / len(v), 3)}
                      for b, v in sorted(bins.items())]
    return result


def rems_climatology(var: str, force: bool = False) -> dict[str, Any]:
    """Srednia po pelnych latach marsjanskich dla kazdego przedzialu Ls."""
    years = rems_mars_years(var, force)
    acc: dict[float, list[float]] = {}
    for pts in years.values():
        for p in pts:
            acc.setdefault(p["year"], []).append(p["value"])
    pts = [{"year": ls, "value": round(sum(v) / len(v), 3)}
           for ls, v in sorted(acc.items())]
    return {"points": pts, "mars_years": sorted(years),
            "per_year": years, "source_url": REMS_URL}


def rems_year_means(var: str, force: bool = False) -> list[dict[str, Any]]:
    """Srednie roczne (rok marsjanski) - tylko pelne lata."""
    years = rems_mars_years(var, force)
    return [{"year": my, "value": round(sum(p["value"] for p in pts) / len(pts), 3)}
            for my, pts in sorted(years.items())]


# --------------------------------------------------------------------- MCD ---
# Serwer MCD (LMD, Paryz) odpowiada od ~8 s do kilku minut na zapytanie, wiec:
#  * kazda wartosc (Ls, godzina) jest cache'owana osobno (postep nie ginie),
#  * w trakcie zapytania uzytkownika NIE czekamy na serwer: brakujace wartosci
#    dociaga watek w tle, a karta pokazuje obserwacje z adnotacja.
MCD_HOURS = [5, 13, 15]       # okolice minimum (~5 h) i maksimum (13-15 h) dobowego
_bg_lock = threading.Lock()
_bg_running: set[str] = set()


def _mcd_raw_request(var: str, ls: float, hour: float) -> float:
    resp = get(MCD_URL, params={
        "var1": var, "latitude": GALE[0], "longitude": GALE[1],
        "localtime": hour, "ls": ls, "zkey": 3, "hrkey": 1, "dust": 1,
        "var2": "none", "var3": "none", "var4": "none", "var5": "none",
        "zonmean": "off", "format": "ascii",
    }, timeout=60, retries=0)
    m = re.search(r"\.{3,}\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", resp.text)
    if not m:
        raise RuntimeError("MCD: no value in the response")
    return float(m.group(1))


def _mcd_key(var: str, ls: float, hour: float) -> str:
    return f"mars:mcd:v:{var}:{ls}:{hour}"


def _mcd_jobs(var: str) -> list[tuple[float, float]]:
    ls_list = [b * MCD_LS_STEP + LS_BIN / 2 for b in range(360 // MCD_LS_STEP)]
    return [(ls, h) for ls in ls_list for h in MCD_HOURS]


def _mcd_cached(var: str) -> dict[tuple[float, float], float]:
    out = {}
    for ls, h in _mcd_jobs(var):
        if cached_at(_mcd_key(var, ls, h)) is not None:
            v = get_or_fetch(_mcd_key(var, ls, h), lambda: None, ttl_days=3650)
            if v is not None:
                out[(ls, h)] = v
    return out


def mcd_fetch_all(var: str, threads: int = 2) -> int:
    """Dociaga brakujace wartosci modelu (blokujaco). Zwraca liczbe brakow."""
    have = _mcd_cached(var)
    todo = [j for j in _mcd_jobs(var) if j not in have]

    def one(job: tuple[float, float]) -> bool:
        ls, h = job
        try:
            get_or_fetch(_mcd_key(var, ls, h),
                         lambda: _mcd_raw_request(var, ls, h), ttl_days=3650)
            return True
        except Exception:  # noqa: BLE001 - sprobujemy przy nastepnej okazji
            return False

    with cf.ThreadPoolExecutor(threads) as ex:
        ok = list(ex.map(one, todo))
    return ok.count(False)


def mcd_fetch_background(var: str) -> None:
    with _bg_lock:
        if var in _bg_running:
            return
        _bg_running.add(var)

    def run() -> None:
        try:
            mcd_fetch_all(var)
        except RuntimeError:  # zamykanie interpretera (np. skrypt CLI)
            pass
        finally:
            with _bg_lock:
                _bg_running.discard(var)

    threading.Thread(target=run, daemon=True).start()


def mcd_climatology(kind: str = "max_temp", force: bool = False,
                    blocking: bool = True) -> dict[str, Any]:
    """Klimatologia modelu MCD dla Gale: max/min dobowe T (°C) albo srednie p (Pa).

    blocking=False: gdy w cache brakuje wartosci, uruchamia pobieranie w tle
    i zglasza Unsupported (karta pokaze obserwacje bez modelu).
    """
    from sources.regional import Unsupported
    var = "p" if kind == "pressure" else "t"
    if blocking:
        mcd_fetch_all(var)
    table = _mcd_cached(var)
    n_jobs = len(_mcd_jobs(var))
    if len(table) < n_jobs:
        if not blocking:
            mcd_fetch_background(var)
        missing_ls = {ls for ls, h in _mcd_jobs(var) if (ls, h) not in table}
        if not blocking or len(missing_ls) > 2:
            raise Unsupported(
                f"the MCD model is downloading in the background from the LMD server ({len(table)}/{n_jobs} "
                f"values); refresh in a few minutes")
    pts = []
    for ls in sorted({ls for ls, _ in _mcd_jobs(var)}):
        vs = [table[(ls, h)] for h in MCD_HOURS if (ls, h) in table]
        if len(vs) < len(MCD_HOURS):
            continue
        if var == "p":
            v = sum(vs) / len(vs)
        elif kind == "min_temp":
            v = min(vs) - 273.15
        else:
            v = max(vs) - 273.15
        pts.append({"year": ls, "value": round(v, 3)})
    return {"points": pts, "source_url": MCD_URL}
