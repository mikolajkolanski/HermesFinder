"""Zrodla REGIONALNE spoza NASA: Open-Meteo (ERA5/ERA5-Land), OWID, Eurostat,
Berkeley Earth (kraje/kontynenty)."""
from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any

from nasa.cache import get_or_fetch
from sources.http import annual_mean, get, get_json, get_text, to_float


class Unsupported(Exception):
    """Zrodlo nie obsluguje tego regionu / filtra (powod trafia do notatki)."""


# region_id -> kody w poszczegolnych zrodlach (None = brak odpowiednika)
# iso3: OWID, eu: Eurostat geo, berkeley: slug pliku Berkeley Earth
REGION_CODES: dict[str, dict[str, str | None]] = {
    "poland": {"iso3": "POL", "eu": "PL", "berkeley": "poland"},
    "germany": {"iso3": "DEU", "eu": "DE", "berkeley": "germany"},
    "france": {"iso3": "FRA", "eu": "FR", "berkeley": "france"},
    "spain": {"iso3": "ESP", "eu": "ES", "berkeley": "spain"},
    "italy": {"iso3": "ITA", "eu": "IT", "berkeley": "italy"},
    "uk": {"iso3": "GBR", "eu": None, "berkeley": "united-kingdom"},
    "ukraine": {"iso3": "UKR", "eu": None, "berkeley": "ukraine"},
    "belarus": {"iso3": "BLR", "eu": None, "berkeley": "belarus"},
    "czechia": {"iso3": "CZE", "eu": "CZ", "berkeley": "czech-republic"},
    "slovakia": {"iso3": "SVK", "eu": "SK", "berkeley": "slovakia"},
    "lithuania": {"iso3": "LTU", "eu": "LT", "berkeley": "lithuania"},
    "latvia": {"iso3": "LVA", "eu": "LV", "berkeley": "latvia"},
    "estonia": {"iso3": "EST", "eu": "EE", "berkeley": "estonia"},
    "russia": {"iso3": "RUS", "eu": None, "berkeley": "russia"},
    "china": {"iso3": "CHN", "eu": None, "berkeley": "china"},
    "india": {"iso3": "IND", "eu": None, "berkeley": "india"},
    "usa": {"iso3": "USA", "eu": None, "berkeley": "united-states"},
    "brazil": {"iso3": "BRA", "eu": None, "berkeley": "brazil"},
    "australia": {"iso3": "AUS", "eu": None, "berkeley": "australia"},
    "egypt": {"iso3": "EGY", "eu": None, "berkeley": "egypt"},
    "turkey": {"iso3": "TUR", "eu": None, "berkeley": "turkey"},
    "greece": {"iso3": "GRC", "eu": "EL", "berkeley": "greece"},
    "sweden": {"iso3": "SWE", "eu": "SE", "berkeley": "sweden"},
    "norway": {"iso3": "NOR", "eu": None, "berkeley": "norway"},
    "finland": {"iso3": "FIN", "eu": "FI", "berkeley": "finland"},
    "iceland": {"iso3": "ISL", "eu": None, "berkeley": "iceland"},
    "denmark": {"iso3": "DNK", "eu": "DK", "berkeley": "denmark"},
    "netherlands": {"iso3": "NLD", "eu": "NL", "berkeley": "netherlands"},
    "belgium": {"iso3": "BEL", "eu": "BE", "berkeley": "belgium"},
    "austria": {"iso3": "AUT", "eu": "AT", "berkeley": "austria"},
    "hungary": {"iso3": "HUN", "eu": "HU", "berkeley": "hungary"},
    "romania": {"iso3": "ROU", "eu": "RO", "berkeley": "romania"},
    "bulgaria": {"iso3": "BGR", "eu": "BG", "berkeley": "bulgaria"},
    "canada": {"iso3": "CAN", "eu": None, "berkeley": "canada"},
    "japan": {"iso3": "JPN", "eu": None, "berkeley": "japan"},
    "indonesia": {"iso3": "IDN", "eu": None, "berkeley": "indonesia"},
    "greenland": {"iso3": "GRL", "eu": None, "berkeley": "greenland"},
    "europe": {"iso3": None, "eu": "EU27_2020", "berkeley": "europe"},
    "asia": {"iso3": None, "eu": None, "berkeley": "asia"},
    "africa": {"iso3": None, "eu": None, "berkeley": "africa"},
    "north_america": {"iso3": None, "eu": None, "berkeley": "north-america"},
    "south_america": {"iso3": None, "eu": None, "berkeley": "south-america"},
    "antarctica": {"iso3": None, "eu": None, "berkeley": "antarctica"},
    "oceania": {"iso3": None, "eu": None, "berkeley": "oceania"},
    "eu": {"iso3": None, "eu": "EU27_2020", "berkeley": None},
    "switzerland": {"iso3": "CHE", "eu": None, "berkeley": "switzerland"},
    "portugal": {"iso3": "PRT", "eu": "PT", "berkeley": "portugal"},
    "ireland": {"iso3": "IRL", "eu": "IE", "berkeley": "ireland"},
    "croatia": {"iso3": "HRV", "eu": "HR", "berkeley": "croatia"},
    "serbia": {"iso3": "SRB", "eu": None, "berkeley": "serbia"},
    "slovenia": {"iso3": "SVN", "eu": "SI", "berkeley": "slovenia"},
    "moldova": {"iso3": "MDA", "eu": None, "berkeley": "moldova"},
    "mexico": {"iso3": "MEX", "eu": None, "berkeley": "mexico"},
    "argentina": {"iso3": "ARG", "eu": None, "berkeley": "argentina"},
    "chile": {"iso3": "CHL", "eu": None, "berkeley": "chile"},
    "colombia": {"iso3": "COL", "eu": None, "berkeley": "colombia"},
    "peru": {"iso3": "PER", "eu": None, "berkeley": "peru"},
    "south_africa": {"iso3": "ZAF", "eu": None, "berkeley": "south-africa"},
    "nigeria": {"iso3": "NGA", "eu": None, "berkeley": "nigeria"},
    "kenya": {"iso3": "KEN", "eu": None, "berkeley": "kenya"},
    "ethiopia": {"iso3": "ETH", "eu": None, "berkeley": "ethiopia"},
    "morocco": {"iso3": "MAR", "eu": None, "berkeley": "morocco"},
    "algeria": {"iso3": "DZA", "eu": None, "berkeley": "algeria"},
    "saudi_arabia": {"iso3": "SAU", "eu": None, "berkeley": "saudi-arabia"},
    "iran": {"iso3": "IRN", "eu": None, "berkeley": "iran"},
    "israel": {"iso3": "ISR", "eu": None, "berkeley": "israel"},
    "uae": {"iso3": "ARE", "eu": None, "berkeley": "united-arab-emirates"},
    "pakistan": {"iso3": "PAK", "eu": None, "berkeley": "pakistan"},
    "bangladesh": {"iso3": "BGD", "eu": None, "berkeley": "bangladesh"},
    "south_korea": {"iso3": "KOR", "eu": None, "berkeley": "south-korea"},
    "vietnam": {"iso3": "VNM", "eu": None, "berkeley": "vietnam"},
    "thailand": {"iso3": "THA", "eu": None, "berkeley": "thailand"},
    "philippines": {"iso3": "PHL", "eu": None, "berkeley": "philippines"},
    "kazakhstan": {"iso3": "KAZ", "eu": None, "berkeley": "kazakhstan"},
    "new_zealand": {"iso3": "NZL", "eu": None, "berkeley": "new-zealand"},
}

# nazwy agregatow w plikach Our World in Data (wiersze bez kodu ISO)
OWID_NAMES: dict[str, str] = {
    "europe": "Europe", "eu": "European Union (27)", "asia": "Asia", "africa": "Africa",
    "north_america": "North America", "south_america": "South America", "oceania": "Oceania",
}


def codes(region: dict[str, Any] | None) -> dict[str, str | None]:
    """Kody regionu w zrodlach; "owid" = nazwa wiersza OWID (agregaty bez ISO)."""
    if region is None:
        return {"iso3": "OWID_WRL", "eu": None, "berkeley": None, "owid": "World"}
    base = REGION_CODES.get(region["id"], {"iso3": None, "eu": None, "berkeley": None})
    return {**base, "owid": OWID_NAMES.get(region["id"])}


def _last_full_year() -> int:
    return dt.date.today().year - 1


# ------------------------------------------------------------ Open-Meteo -----
OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_START = 1981


OM_VARIABLES = ("temperature_2m_mean", "precipitation_sum")
OM_MODELS = ("era5", "era5_land")


class RateLimited(Unsupported):
    pass


def sample_point(region: dict[str, Any]) -> tuple[float, float]:
    """Punkt reprezentatywny: punkt regionu albo srodek bbox.

    Open-Meteo liczy 45 lat danych dziennych jako ~1200 'wywolan' na punkt
    (limit: 600/min, 5000/h, 10000/dobe), wiec pobieramy JEDEN punkt na
    region - obie zmienne i oba modele w jednym zapytaniu.
    """
    if region.get("type") == "point":
        lat, lon = region["point"]
        return float(lat), float(lon)
    la0, la1, lo0, lo1 = region["bbox"]
    return round((la0 + la1) / 2, 3), round((lo0 + lo1) / 2, 3)


def _aggregate(times: list[str], vals: list[float | None]) -> dict[str, Any]:
    per_month: dict[tuple[int, int], list[float]] = {}
    for t, v in zip(times, vals):
        if v is not None:
            per_month.setdefault((int(t[:4]), int(t[5:7])), []).append(v)
    monthly = [{"year": y, "month": m, "value": round(sum(v) / len(v), 4)}
               for (y, m), v in sorted(per_month.items()) if len(v) >= 25]
    by_year: dict[int, list[float]] = {}
    for r in monthly:
        by_year.setdefault(r["year"], []).append(r["value"])
    annual = [{"year": y, "value": round(sum(v) / 12, 4)}
              for y, v in sorted(by_year.items()) if len(v) == 12]
    return {"annual": annual, "monthly": monthly}


def open_meteo(variable: str, model: str, region: dict[str, Any],
               force: bool = False) -> dict[str, Any]:
    """ERA5 / ERA5-Land (ECMWF/Copernicus) serwowane przez Open-Meteo.

    variable: temperature_2m_mean (°C) | precipitation_sum (mm/dzien, srednia).
    Jedno zapytanie na region: obie zmienne x oba modele, wspolny cache.
    """
    lat, lon = sample_point(region)
    key = f"openmeteo3:{lat:.2f}/{lon:.2f}"
    end = _last_full_year()

    def fetch() -> dict[str, Any]:
        params = {
            "latitude": lat, "longitude": lon,
            "start_date": f"{OPEN_METEO_START}-01-01",
            "end_date": f"{end}-12-31",
            "daily": ",".join(OM_VARIABLES), "models": ",".join(OM_MODELS),
            "timezone": "UTC",
        }
        try:
            data = get_json(OPEN_METEO, params=params, timeout=180)
        except Exception as exc:  # noqa: BLE001
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code == 429:
                raise RateLimited("Open-Meteo request limit reached "
                                  "(try again in an hour; the data will be cached)")
            raise
        daily = data["daily"]
        out: dict[str, Any] = {"point": [lat, lon], "source_url": OPEN_METEO}
        for m in OM_MODELS:
            for var in OM_VARIABLES:
                vals = daily.get(f"{var}_{m}")
                if vals is None and len(OM_MODELS) == 1:
                    vals = daily.get(var)
                if vals is not None:
                    out[f"{m}:{var}"] = _aggregate(daily["time"], vals)
        return out

    data = get_or_fetch(key, fetch, ttl_days=30, force=force)
    series = data.get(f"{model}:{variable}")
    if not series or not series["annual"]:
        raise Unsupported(f"Open-Meteo: no {model} data for this point")
    return {**series, "point": data["point"], "source_url": data["source_url"]}


# ------------------------------------------------------------------ OWID -----
def owid_series(slug: str, iso3: str | None, column: int = 3, scale: float = 1.0,
                force: bool = False, entity: str | None = None) -> dict[str, Any]:
    """Our World in Data (grapher CSV): szereg roczny dla kodu ISO3/OWID_WRL
    albo - dla agregatow bez kodu (Europa, UE, kontynenty) - nazwy wiersza."""
    url = f"https://ourworldindata.org/grapher/{slug}.csv?csvType=full"
    who = iso3 or entity
    if not who:
        raise Unsupported(f"OWID '{slug}': no series for this region")

    def fetch() -> dict[str, Any]:
        annual = []
        reader = csv.reader(io.StringIO(get_text(url, timeout=180)))
        next(reader, None)
        for row in reader:
            if len(row) > column and ((iso3 and row[1] == iso3) or
                                      (not iso3 and entity and row[0] == entity and not row[1])):
                v = to_float(row[column])
                if v is not None and row[2].isdigit():
                    annual.append({"year": int(row[2]), "value": v * scale})
        if not annual:
            raise Unsupported(f"OWID '{slug}': no data for {who}")
        return {"annual": annual, "source_url": url}

    return get_or_fetch(f"owid:{slug}:{who}:{column}", fetch, ttl_days=14,
                        force=force)


# -------------------------------------------------------------- Eurostat -----
def eurostat_ghg(geo: str, force: bool = False) -> dict[str, Any]:
    """Eurostat (Komisja Europejska): emisje GHG bez LULUCF, mln t CO2e."""
    url = ("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/"
           "data/env_air_gge")
    params = {"format": "JSON", "lang": "EN", "geo": geo, "airpol": "GHG",
              "src_crf": "TOTX4_MEMO", "unit": "MIO_T"}

    def fetch() -> dict[str, Any]:
        d = get_json(url, params=params)
        index = d["dimension"]["time"]["category"]["index"]
        values = d.get("value", {})
        annual = []
        for year, pos in index.items():
            v = values.get(str(pos))
            if v is not None and str(year).isdigit():
                annual.append({"year": int(year), "value": float(v)})
        annual.sort(key=lambda r: r["year"])
        if not annual:
            raise Unsupported(f"Eurostat: no data for {geo}")
        return {"annual": annual, "source_url": f"{url}?geo={geo}"}

    return get_or_fetch(f"eurostat:ghg:{geo}", fetch, ttl_days=14,
                        force=force)
