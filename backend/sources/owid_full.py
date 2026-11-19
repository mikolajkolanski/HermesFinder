"""Pelne pliki danych Our World in Data: energia (Ember, Energy Institute) i CO2/GHG
(Global Carbon Project, Jones et al.).

Jeden plik CSV = dziesiatki zmiennych (prad z wegla, z OZE, emisje z wegla...).
Plik jest pobierany raz, z tabeli zostaja tylko kolumny uzywane w katalogu
(connector "owid_csv") i wiersze krajow (kod ISO3) oraz najwazniejszych agregatow
(swiat, kontynenty, UE). Wynik trafia do cache dyskowego (14 dni) i do pamieci
procesu, wiec kolejne zapytania nie parsuja CSV ponownie.
"""
from __future__ import annotations

import csv
import io
import threading
import time
from typing import Any

from nasa.cache import get_or_fetch
from sources.http import get_text, to_float
from sources.regional import Unsupported, codes

FILES: dict[str, list[str]] = {
    "energy": ["https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv",
               "https://owid-public.owid.io/data/energy/owid-energy-data.csv"],
    "co2": ["https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv",
            "https://owid-public.owid.io/data/co2/owid-co2-data.csv"],
}
# agregaty bez kodu ISO, ktore zostawiamy (reszta: "(EI)", "(Ember)", grupy dochodowe...)
AGGREGATES = {"World", "Europe", "European Union (27)", "Asia", "Africa", "North America",
              "South America", "Oceania", "High-income countries", "Low-income countries"}

_memo: dict[str, tuple[float, dict[str, Any]]] = {}
_lock = threading.Lock()
MEMO_TTL = 6 * 3600


def _columns_for(file: str) -> list[str]:
    from rag.catalog import load_catalog
    cols = {d["connector_params"]["column"] for d in load_catalog().values()
            if d.get("connector") == "owid_csv" and d["connector_params"].get("file") == file}
    return sorted(cols)


def parse_csv(text: str, columns: list[str]) -> dict[str, Any]:
    """CSV OWID -> {"columns": {kolumna: {klucz: [[rok, wartosc], ...]}}}.
    Klucz = kod ISO3 albo nazwa agregatu."""
    reader = csv.DictReader(io.StringIO(text))
    out: dict[str, dict[str, list[list[float]]]] = {c: {} for c in columns}
    for row in reader:
        iso = (row.get("iso_code") or "").strip()
        name = (row.get("country") or "").strip()
        key = iso if iso and not iso.startswith("OWID_") else (name if name in AGGREGATES else None)
        year = (row.get("year") or "").strip()
        if not key or not year.isdigit():
            continue
        for c in columns:
            v = to_float(row.get(c) or "")
            if v is not None:
                out[c].setdefault(key, []).append([int(year), v])
    return {"columns": out}


def table(file: str, force: bool = False) -> dict[str, Any]:
    columns = _columns_for(file)
    key = f"owidfull:{file}:" + ",".join(columns)
    now = time.time()
    with _lock:
        hit = _memo.get(key)
        if hit and not force and now - hit[0] < MEMO_TTL:
            return hit[1]

    def fetch() -> dict[str, Any]:
        last: Exception | None = None
        for url in FILES[file]:
            try:
                data = parse_csv(get_text(url, timeout=180), columns)
                data["source_url"] = url
                return data
            except Exception as exc:  # noqa: BLE001 - nastepne lustro
                last = exc
        raise last or RuntimeError(f"OWID {file}: unavailable")

    data = get_or_fetch(key, fetch, ttl_days=14, force=force)
    with _lock:
        _memo[key] = (now, data)
    return data


def series(file: str, column: str, region: dict[str, Any] | None,
           force: bool = False) -> dict[str, Any]:
    """Szereg roczny kolumny dla regionu (None = swiat)."""
    c = codes(region)
    keys = [k for k in (c.get("iso3"), c.get("owid")) if k and not str(k).startswith("OWID_")]
    if region is None:
        keys = ["World"]
    if not keys:
        name = region["name"] if region else "the world"
        raise Unsupported(f"Our World in Data has no national series for {name}")
    data = table(file, force)
    col = data["columns"].get(column) or {}
    for k in keys:
        rows = col.get(k)
        if rows:
            return {"annual": [{"year": int(y), "value": float(v)} for y, v in sorted(rows)],
                    "source_url": data.get("source_url")}
    name = region["name"] if region else "the world"
    raise Unsupported(f"Our World in Data: no '{column}' data for {name}")
