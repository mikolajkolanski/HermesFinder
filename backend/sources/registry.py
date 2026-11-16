"""Rejestr konektorow: katalog (connector + params) -> szereg roczny.

Zwracany kontrakt dla szeregow rocznych:
  {"rows": [{"year", "value"}...], "method_note": str, "months_ignored": bool}
Wyjatek Unsupported = zrodlo nie obsluguje danego regionu/filtra (powod
trafia do notatki karty porownawczej, a nie do bledu 500).
"""
from __future__ import annotations

from typing import Any

from sources import climate, mars, planets, regional
from sources.regional import Unsupported

__all__ = ["Unsupported", "full_series", "seasonal_series", "planet_values", "rebase_offset"]

EXTERNAL_CONNECTORS = {
    "noaa_cag", "hadcrut5", "berkeley_global", "berkeley_region", "jma_global",
    "era5_pulse", "oisst", "gml", "noaa_star", "csiro", "owid_sea_level",
    "psmsl", "silso", "open_meteo", "owid", "owid_temp", "eurostat_ghg",
}
SEASONAL_CONNECTORS = {"mars_rems", "mars_mcd"}
PLANET_CONNECTORS = {"planet_metric"}


def _from_monthly(monthly: list[dict[str, Any]], months: list[int]
                  ) -> list[dict[str, Any]]:
    by_year: dict[int, dict[int, float]] = {}
    for r in monthly:
        if r["month"] in months:
            by_year.setdefault(r["year"], {})[r["month"]] = r["value"]
    return [{"year": y, "value": round(sum(m.values()) / len(m), 4)}
            for y, m in sorted(by_year.items()) if len(m) == len(set(months))]


def _pick(data: dict[str, Any], months: list[int] | None, note: str
          ) -> dict[str, Any]:
    """Wybiera annual albo (przy filtrze miesiecy) agregat z monthly."""
    if months:
        if data.get("monthly"):
            return {"rows": _from_monthly(data["monthly"], months),
                    "method_note": note + " (mean of the selected months)",
                    "months_ignored": False}
        return {"rows": data["annual"],
                "method_note": note + "; no monthly data, "
                                      "annual means shown",
                "months_ignored": True}
    return {"rows": data["annual"], "method_note": note,
            "months_ignored": False}


def full_series(ds: dict[str, Any], region: dict[str, Any] | None,
                months: list[int] | None, force: bool = False) -> dict[str, Any]:
    """Pelny (niefiltrowany po oknie) szereg roczny dla zbioru zewnetrznego."""
    conn = ds["connector"]
    p = ds.get("connector_params", {})
    rname = region["name"] if region else None

    if conn == "noaa_cag":
        d = climate.noaa_cag(p.get("region", "globe"), "tavg",
                             p.get("surface", "land_ocean"), force=force)
        return _pick(d, months, "anomalies vs the 1901–2000 mean (NOAA NCEI)")
    if conn == "hadcrut5":
        return _pick(climate.hadcrut5(force), months,
                     "anomalies vs 1961–1990 (HadCRUT5, ensemble median)")
    if conn == "berkeley_global":
        return _pick(climate.berkeley_global(force), months,
                     "anomalies vs 1951–1980 (Berkeley Earth)")
    if conn == "jma_global":
        return _pick(climate.jma_global(force), months,
                     "anomalies vs 1991–2020 (JMA)")
    if conn == "era5_pulse":
        return _pick(climate.era5_pulse(p["var"], force), months,
                     "anomalies vs 1991–2020 (ERA5, mean of daily values)")
    if conn == "oisst":
        return _pick(climate.oisst_world(force), months,
                     "absolute SST 60°S–60°N (OISST v2.1)")
    if conn == "gml":
        return _pick(climate.noaa_gml_annual(p["gas"], p["scope"], force),
                     months, "annual global means (NOAA GML)")
    if conn == "noaa_star":
        return _pick(climate.noaa_star_sea_level(force), months,
                     "satellite altimetry, annual mean (NOAA LSA)")
    if conn == "csiro":
        return _pick(climate.csiro_sea_level(force), months,
                     "CSIRO reconstruction (Church & White), annual mean")
    if conn == "owid_sea_level":
        return _pick(climate.owid_sea_level(p.get("column", "UHSLC"), force),
                     months, "global tide gauges (UHSLC), mean of quarters")
    if conn == "psmsl":
        return _pick(climate.psmsl_station(p["station_id"], force), months,
                     "annual mean sea level, RLR (PSMSL)")
    if conn == "silso":
        return _pick(climate.silso_sunspots(force), months,
                     "annual mean sunspot number (SILSO SN v2.0)")
    if conn == "open_meteo":
        if region is None:
            raise Unsupported("this source needs a region or a point")
        d = regional.open_meteo(p["variable"], p["model"], region, force)
        pt = d["point"]
        where = ("point" if region.get("type") == "point"
                 else "point at the centre of the area")
        return _pick(d, months, f"{p['model'].upper().replace('_', '-')} reanalysis"
                                f", {where} {pt[0]:.2f}°N {pt[1]:.2f}°E")
    if conn == "berkeley_region":
        slug = regional.codes(region)["berkeley"]
        if not slug:
            raise Unsupported(f"Berkeley Earth has no series for {rname or 'the world'}")
        return _pick(climate.berkeley_region(slug, force), months,
                     "anomalies vs 1951–1980 (Berkeley Earth, land)")
    if conn == "owid_temp":
        iso = regional.codes(region)["iso3"]
        if not iso:
            raise Unsupported(f"no national ERA5 (OWID) series for {rname}")
        d = regional.owid_series(p["slug"], iso, force=force)
        return _pick(d, months, "anomalies vs 1991–2020 (ERA5 via OWID)")
    if conn == "owid":
        iso = regional.codes(region)["iso3"]
        if not iso:
            raise Unsupported(f"OWID has no series for {rname}")
        d = regional.owid_series(p["slug"], iso, p.get("column", 3),
                                 p.get("scale", 1.0), force)
        return _pick(d, months, "national/world data (Our World in Data)")
    if conn == "eurostat_ghg":
        geo = regional.codes(region)["eu"]
        if not geo:
            raise Unsupported(f"Eurostat does not cover {rname or 'the world'} "
                              f"(EU member states and EU-27 only)")
        return _pick(regional.eurostat_ghg(geo, force), months,
                     "CRF inventories excluding LULUCF (Eurostat)")
    raise ValueError(f"Unknown external connector: {conn}")


# ------------------------------------------------------------ rebase ---------
def rebase_offset(rows: list[dict[str, Any]], base: tuple[int, int],
                  min_cover: float = 0.8) -> float | None:
    """Srednia z okresu bazowego (None gdy brak >= min_cover lat bazy)."""
    vals = [r["value"] for r in rows if base[0] <= r["year"] <= base[1]]
    need = (base[1] - base[0] + 1) * min_cover
    return sum(vals) / len(vals) if len(vals) >= need else None


# --------------------------------------------------- Mars / planety ----------
def seasonal_series(ds: dict[str, Any], force: bool = False,
                    blocking: bool = False) -> dict[str, Any]:
    """{"points": klimatologia wg Ls, "per_year": {MY: pts}, ...} (Mars)."""
    conn = ds["connector"]
    p = ds.get("connector_params", {})
    if conn == "mars_rems":
        d = mars.rems_climatology(p["var"], force)
        return {"points": d["points"], "per_year": d["per_year"],
                "mars_years": d["mars_years"],
                "method_note": ("Curiosity REMS observations (Gale crater), mean "
                                f"of full Martian years MY{d['mars_years'][0]}–"
                                f"MY{d['mars_years'][-1]}" if d["mars_years"] else
                                "Curiosity REMS observations")}
    if conn == "mars_mcd":
        d = mars.mcd_climatology(p["kind"], force, blocking=blocking)
        return {"points": d["points"], "per_year": {}, "mars_years": [],
                "method_note": "MCD climate MODEL (Gale crater), "
                               "climatology with the average dust scenario"}
    raise ValueError(f"Unknown seasonal connector: {conn}")


def planet_values(ds: dict[str, Any], body_ids: list[str] | None,
                  force: bool = False) -> list[dict[str, Any]]:
    return planets.metric_values(ds["connector_params"]["metric"], body_ids,
                                 force)
