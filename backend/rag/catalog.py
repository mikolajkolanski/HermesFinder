"""Wczytywanie katalogu zbiorow (catalog/datasets*.json).

Teksty dla uzytkownika sa po angielsku: tytul/opis z pol *_en, a skroty,
jednostki, kraje i okresy odniesienia tlumaczy _localize. Polskie oryginaly
zostaja w polach *_pl (indeks wyszukiwania korzysta z obu jezykow)."""
from __future__ import annotations

import json
import time
from typing import Any

import config

# polskie wartosci z generatora katalogu -> teksty angielskie
_EN: dict[str, str] = {
    # skroty zrodel
    "CSIRO (mareografy+altymetria)": "CSIRO (tide gauges + altimetry)",
    "Climate Watch (GHG łącznie)": "Climate Watch (total GHG)",
    "Eurostat (GHG, UE)": "Eurostat (GHG, EU)",
    "JMA (Japonia)": "JMA (Japan)",
    "MCD ESA/CNES (model)": "MCD ESA/CNES (model)",
    "NASA Curiosity REMS (obserwacje)": "NASA Curiosity REMS (observations)",
    "NASA GISTEMP v4 (półkula N)": "NASA GISTEMP v4 (N hemisphere)",
    "NASA altymetria": "NASA altimetry",
    "NOAA altymetria": "NOAA altimetry",
    "NOAA GML (średnia globalna)": "NOAA GML (global mean)",
    "PSMSL · Brest (Francja)": "PSMSL · Brest (France)",
    "PSMSL · Nowy Jork (Battery)": "PSMSL · New York (Battery)",
    "PSMSL · Sztokholm": "PSMSL · Stockholm",
    "Univ. of Hawaii (mareografy)": "Univ. of Hawaii (tide gauges)",
    # kraje
    "Belgia": "Belgium", "Francja/UE": "France/EU", "Japonia": "Japan",
    "Szwajcaria": "Switzerland", "UE": "EU", "USA/Hiszpania": "USA/Spain",
    "międzynarodowy": "international",
    # organizacje i nazwy zrodel
    "Climate Watch / WRI (opracowanie Our World in Data)": "Climate Watch / WRI (compiled by Our World in Data)",
    "Copernicus ERA5 (opracowanie Our World in Data)": "Copernicus ERA5 (compiled by Our World in Data)",
    "Eurostat (Komisja Europejska)": "Eurostat (European Commission)",
    "JMA (Japońska Agencja Meteorologiczna)": "JMA (Japan Meteorological Agency)",
    "Open-Meteo (dane ECMWF ERA5)": "Open-Meteo (ECMWF ERA5 data)",
    "NASA Vital Signs (dane: NOAA GML, Mauna Loa)": "NASA Vital Signs (data: NOAA GML, Mauna Loa)",
    # jednostki
    "MJ/m²/dzień": "MJ/m²/day", "dni": "days", "godz.": "hours", "liczba plam": "sunspot number",
    "mln km": "million km", "mln km²": "million km²", "mln t CO₂": "Mt CO₂", "mln t CO₂e": "Mt CO₂e",
    "mm (wzgl. 1993)": "mm (vs 1993)", "mm/dzień": "mm/day", "t CO₂/osobę": "t CO₂ per person",
    "°C (anomalia wzgl. 1951–1980)": "°C (anomaly vs 1951–1980)",
    # okresy odniesienia
    "klimatologia sezonowa wg Ls": "seasonal climatology by Ls",
    "wartości bezwzględne": "absolute values", "wartości względne": "relative values",
    "wartości względne (RLR)": "relative values (RLR)", "wartości wzorcowe": "reference values",
    # rozdzielczosc
    "dobowa (sol) -> przedziały Ls 15°": "daily (sol) -> 15° Ls bins",
    "jedna wartość na ciało": "one value per body", "miesięczna": "monthly",
    "miesięczna (domyślnie wrzesień)": "monthly (September by default)", "roczna": "annual",
    "roczna (agregacja z pomiarów satelitarnych)": "annual (aggregated from satellite data)",
    # uwagi
    "plik źródłowy nieaktualizowany od 2024 r.": "source file not updated since 2024",
    "regionalne pliki Berkeley Earth kończą się w 2020 r.": "Berkeley Earth regional files end in 2020",
}


def en(text: Any) -> Any:
    """Angielska wersja tekstu z katalogu (bez zmian, gdy brak tlumaczenia)."""
    return _EN.get(text, text) if isinstance(text, str) else text


def _localize(ds: dict[str, Any]) -> dict[str, Any]:
    if "title_pl" in ds:
        return ds
    ds["title_pl"] = ds.get("title", "")
    ds["description_pl"] = ds.get("description", "")
    ds["title"] = ds.get("title_en") or ds["title_pl"]
    ds["description"] = ds.get("description_en") or ds["description_pl"]
    for key in ("short", "unit", "baseline", "notes"):
        if key in ds:
            ds[key] = en(ds[key])
    prov = ds.get("provider") or {}
    for key in ("org", "country"):
        if key in prov:
            prov[key] = en(prov[key])
    src = ds.get("source") or {}
    if "name" in src:
        src["name"] = en(src["name"])
    cov = ds.get("coverage") or {}
    if "resolution" in cov:
        cov["resolution"] = en(cov["resolution"])
    for var in ds.get("variables") or []:
        if "unit" in var:
            var["unit"] = en(var["unit"])
    return ds

_cache: dict[str, Any] | None = None
_loaded_at: float = 0.0


def load_catalog(force: bool = False) -> dict[str, Any]:
    """Zwraca slownik zbiorow {id: entry}. Wczytuje plik raz i cache'uje."""
    global _cache, _loaded_at
    if _cache is not None and not force and time.time() - _loaded_at < 5.0:
        return _cache
    merged: dict[str, Any] = {}
    for path in config.CATALOG_PATHS:
        if path.exists():
            with open(path, encoding="utf-8") as fh:
                merged.update({k: _localize(v) for k, v in json.load(fh).items()})
    _cache = merged
    _loaded_at = time.time()
    return _cache


def get_dataset(ds_id: str) -> dict[str, Any] | None:
    return load_catalog().get(ds_id)


def dataset_ids() -> list[str]:
    return list(load_catalog().keys())
