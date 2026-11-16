"""Generator katalogu: catalog/datasets_external.json + metadane dostawcow w datasets.json.

Uruchom: python catalog/generate_catalog.py  (potem: python -m sources.verify)
"""
import json
from pathlib import Path

CAT = Path(__file__).resolve().parent

# ---- dostawcy -------------------------------------------------------------
P = {
    "nasa": {"org": "NASA", "country": "USA", "type": "agency"},
    "noaa": {"org": "NOAA", "country": "USA", "type": "agency"},
    "metoffice": {"org": "Met Office Hadley Centre / UEA CRU", "country": "UK", "type": "agency"},
    "berkeley": {"org": "Berkeley Earth", "country": "USA", "type": "nonprofit"},
    "jma": {"org": "JMA (Japońska Agencja Meteorologiczna)", "country": "Japonia", "type": "agency"},
    "copernicus": {"org": "Copernicus C3S / ECMWF (UE, ESA)", "country": "UE", "type": "intergovernmental"},
    "umaine": {"org": "Climate Reanalyzer, University of Maine", "country": "USA", "type": "academic"},
    "csiro": {"org": "CSIRO", "country": "Australia", "type": "agency"},
    "uhslc": {"org": "University of Hawaii Sea Level Center", "country": "USA", "type": "academic"},
    "psmsl": {"org": "PSMSL / National Oceanography Centre", "country": "UK", "type": "agency"},
    "silso": {"org": "SILSO, Royal Observatory of Belgium", "country": "Belgia", "type": "agency"},
    "openmeteo": {"org": "Open-Meteo (dane ECMWF ERA5)", "country": "Szwajcaria", "type": "private"},
    "owid": {"org": "Our World in Data", "country": "UK", "type": "nonprofit"},
    "gcp": {"org": "Global Carbon Project (via OWID)", "country": "międzynarodowy", "type": "academic"},
    "ember": {"org": "Ember (via OWID)", "country": "UK", "type": "nonprofit"},
    "eurostat": {"org": "Eurostat (Komisja Europejska)", "country": "UE", "type": "intergovernmental"},
    "cab": {"org": "NASA/JPL + CAB-INTA (Curiosity REMS)", "country": "USA/Hiszpania", "type": "agency"},
    "mcd": {"org": "LMD / CNES / Open Univ. / IAA / ESA (Mars Climate Database)", "country": "Francja/UE", "type": "intergovernmental"},
    "nsidc": {"org": "NSIDC (NOAA/NASA DAAC)", "country": "USA", "type": "agency"},
}

KEYS_PL_TEMP = ["temperatura", "temperatury", "temperaturze", "ocieplenie", "ocieplenia",
                "cieplej", "średnia temperatura", "anomalia temperatury", "anomalie"]
KEYS_EN_TEMP = ["temperature", "warming", "anomaly", "temperature anomaly", "global warming"]

ds: dict[str, dict] = {}


def add(id_, *, title, title_en, desc, desc_en, kw_pl, kw_en, hints, unit, connector,
        params, regions, start, end=None, category, source, provider, topic, body="earth",
        kind="absolute", baseline=None, series_kind="annual", sanity=None, resolution="roczna",
        region_scope="global", var_desc=None, notes=None):
    ds[id_] = {
        "title": title, "title_en": title_en, "description": desc, "description_en": desc_en,
        "keywords_pl": kw_pl, "keywords_en": kw_en, "hint_terms": hints,
        "variables": [{"id": id_, "unit": unit, "desc": var_desc or title}],
        "unit": unit, "connector": connector, "connector_params": params,
        "supports_regions": regions,
        "coverage": {"start": start, "end": end, "resolution": resolution},
        "category": category, "source": source, "provider": provider, "topic": topic,
        "body": body, "kind": kind, "baseline": baseline, "series_kind": series_kind,
        "region_scope": region_scope, "sanity": sanity or {}, "notes": notes,
    }


def src(name, url, dataset_url=None):
    return {"name": name, "url": url, "dataset_url": dataset_url or url}


# ============================================================ temperatura globalna
GT = dict(topic="global_temperature", category="temperature", kind="anomaly",
          unit="°C", hints=["global temperature", "temperature", "warming"],
          kw_pl=KEYS_PL_TEMP + ["globalna temperatura", "globalne ocieplenie", "temperatura ziemi"],
          kw_en=KEYS_EN_TEMP + ["global mean temperature", "global surface temperature"],
          regions=False, params={})

add("noaa_global_temp", title="Globalna anomalia temperatury (NOAA NOAAGlobalTemp)",
    title_en="Global land+ocean temperature anomaly (NOAA NOAAGlobalTemp)",
    desc="Roczne odchylenia temperatury powierzchni lądów i oceanów od średniej 1901–2000, "
         "NOAA NCEI (NOAAGlobalTemp).",
    desc_en="Annual global land+ocean surface temperature departures from the 1901–2000 mean (NOAA NCEI).",
    connector="noaa_cag", baseline="1901–2000", start=1850,
    provider=P["noaa"], source=src("NOAA NCEI — Climate at a Glance / NOAAGlobalTemp",
        "https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/global/time-series"),
    sanity={"min": -1.0, "max": 2.2, "min_points": 150}, **{**GT, "params": {"region": "globe", "surface": "land_ocean"}})

add("hadcrut5", title="Globalna anomalia temperatury (Met Office HadCRUT5)",
    title_en="Global temperature anomaly (Met Office HadCRUT5)",
    desc="Roczne anomalie globalnej temperatury względem 1961–1990 z brytyjskiego Met Office "
         "Hadley Centre i University of East Anglia (HadCRUT5, ensemble).",
    desc_en="Annual global surface temperature anomalies vs 1961–1990 (Met Office Hadley Centre & UEA CRU).",
    connector="hadcrut5", baseline="1961–1990", start=1850,
    provider=P["metoffice"], source=src("Met Office Hadley Centre HadCRUT5",
        "https://www.metoffice.gov.uk/hadobs/hadcrut5/"),
    sanity={"min": -1.0, "max": 2.2, "min_points": 150}, **GT)

add("berkeley_global", title="Globalna anomalia temperatury (Berkeley Earth)",
    title_en="Global land+ocean temperature anomaly (Berkeley Earth)",
    desc="Roczne anomalie temperatury lądów i oceanów względem 1951–1980, niezależna analiza "
         "organizacji non-profit Berkeley Earth (50 tys. stacji + obserwacje oceaniczne).",
    desc_en="Annual global land+ocean anomalies vs 1951–1980 from the independent non-profit Berkeley Earth.",
    connector="berkeley_global", baseline="1951–1980", start=1850,
    provider=P["berkeley"], source=src("Berkeley Earth — Global Temperature Report",
        "https://berkeleyearth.org/data/"),
    sanity={"min": -1.0, "max": 2.2, "min_points": 150}, **GT)

add("jma_global", title="Globalna anomalia temperatury (JMA)",
    title_en="Global temperature anomaly (Japan Meteorological Agency)",
    desc="Roczne anomalie globalnej temperatury względem 1991–2020, Japońska Agencja Meteorologiczna "
         "(analiza COBE-SST + stacje lądowe).",
    desc_en="Annual global surface temperature anomalies vs 1991–2020 (JMA).",
    connector="jma_global", baseline="1991–2020", start=1891,
    provider=P["jma"], source=src("Japan Meteorological Agency — Global Surface Temperature Anomalies",
        "https://www.data.jma.go.jp/cpd/longfcst/en/tcc/"),
    sanity={"min": -1.0, "max": 1.5, "min_points": 100}, **GT)

add("era5_global_temp", title="Globalna temperatura powietrza (Copernicus ERA5)",
    title_en="Global 2 m air temperature (Copernicus ERA5)",
    desc="Roczne średnie dobowych anomalii temperatury powietrza 2 m z reanalizy ERA5 "
         "(Copernicus Climate Change Service, ECMWF), baza 1991–2020, od 1940.",
    desc_en="Annual mean of daily ERA5 2 m air temperature anomalies vs 1991–2020 (Copernicus C3S / ECMWF).",
    connector="era5_pulse", baseline="1991–2020", start=1940,
    provider=P["copernicus"], source=src("Copernicus Climate Pulse (ERA5)",
        "https://pulse.climate.copernicus.eu/",
        "https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels"),
    sanity={"min": -1.0, "max": 1.5, "min_points": 70},
    **{**GT, "params": {"var": "2t_global"}, "kw_pl": GT["kw_pl"] + ["copernicus", "era5", "esa"],
       "kw_en": GT["kw_en"] + ["copernicus", "era5", "ecmwf", "esa"]})

# ============================================================ temperatura oceanu
SST = dict(topic="ocean_temperature", category="ocean", kind="anomaly", unit="°C",
           hints=["ocean temperature", "temperature"], regions=False,
           kw_pl=["temperatura oceanu", "temperatura wody", "temperatura morza", "oceany", "ocean",
                  "temperatura powierzchni oceanu", "morza", "ocieplenie oceanów", "wody"],
           kw_en=["sea surface temperature", "sst", "ocean temperature", "ocean warming"])

add("noaa_ocean_temp", title="Anomalia temperatury oceanów (NOAA ERSST)",
    title_en="Global ocean temperature anomaly (NOAA ERSST)",
    desc="Roczne odchylenia temperatury powierzchni oceanów od średniej 1901–2000 (NOAA NCEI).",
    desc_en="Annual global ocean surface temperature departures vs 1901–2000 (NOAA NCEI).",
    connector="noaa_cag", baseline="1901–2000", start=1850,
    provider=P["noaa"], source=src("NOAA NCEI — Climate at a Glance (ocean)",
        "https://www.ncei.noaa.gov/access/monitoring/climate-at-a-glance/global/time-series"),
    sanity={"min": -1.0, "max": 1.6, "min_points": 150}, **{**SST, "params": {"region": "globe", "surface": "ocean"}})

add("oisst_sst", title="Temperatura powierzchni oceanu 60°S–60°N (NOAA OISST)",
    title_en="Sea surface temperature 60S–60N (NOAA OISST via Climate Reanalyzer)",
    desc="Średnia roczna temperatura powierzchni oceanu 60°S–60°N z satelitarnej analizy NOAA OISST v2.1, "
         "udostępniana przez Climate Reanalyzer (University of Maine).",
    desc_en="Annual mean SST (60S–60N) from NOAA OISST v2.1 served by Climate Reanalyzer (Univ. of Maine).",
    connector="oisst", baseline="wartości bezwzględne", start=1982,
    provider=P["umaine"], source=src("Climate Reanalyzer (Univ. of Maine) — OISST v2.1",
        "https://climatereanalyzer.org/clim/sst_daily/"),
    sanity={"min": 19.0, "max": 22.5, "min_points": 35}, **{**SST, "params": {}})

add("era5_sst", title="Temperatura powierzchni oceanu 60°S–60°N (Copernicus ERA5)",
    title_en="Sea surface temperature 60S–60N (Copernicus ERA5)",
    desc="Roczne średnie dobowych anomalii SST 60°S–60°N z reanalizy ERA5 (Copernicus C3S / ECMWF), baza 1991–2020.",
    desc_en="Annual mean of daily ERA5 SST anomalies 60S–60N vs 1991–2020 (Copernicus C3S / ECMWF).",
    connector="era5_pulse", baseline="1991–2020", start=1979,
    provider=P["copernicus"], source=src("Copernicus Climate Pulse (ERA5 SST)",
        "https://pulse.climate.copernicus.eu/"),
    sanity={"min": -0.7, "max": 1.0, "min_points": 40},
    **{**SST, "params": {"var": "sst_60S-60N"}, "kw_pl": SST["kw_pl"] + ["copernicus", "esa"],
       "kw_en": SST["kw_en"] + ["copernicus", "ecmwf", "esa"]})

# ============================================================ gazy cieplarniane
GAS = dict(category="greenhouse", regions=False)
add("noaa_co2_global", title="Globalne stężenie CO₂ (NOAA GML)", title_en="Global mean atmospheric CO2 (NOAA GML)",
    desc="Roczna średnia globalna stężenia CO₂ w atmosferze z sieci stacji NOAA GML (ppm).",
    desc_en="Annual global mean marine-surface atmospheric CO2 from the NOAA GML network.",
    kw_pl=["co2", "dwutlenek węgla", "dwutlenku węgla", "stężenie co2", "gazy cieplarniane", "globalne stężenie co2"],
    kw_en=["co2", "carbon dioxide", "atmospheric co2", "global mean co2", "greenhouse gases"],
    hints=["co2", "greenhouse"], unit="ppm", connector="gml", params={"gas": "co2", "scope": "gl"},
    start=1979, provider=P["noaa"], topic="co2", kind="absolute",
    source=src("NOAA GML — Global Monitoring Laboratory", "https://gml.noaa.gov/ccgg/trends/",
               "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_annmean_gl.csv"),
    sanity={"min": 330, "max": 450, "min_points": 40}, **GAS)
add("noaa_ch4_global", title="Globalne stężenie metanu CH₄ (NOAA GML)", title_en="Global mean atmospheric methane (NOAA GML)",
    desc="Roczna średnia globalna stężenia metanu w atmosferze (ppb), NOAA GML.",
    desc_en="Annual global mean atmospheric methane (ppb), NOAA GML.",
    kw_pl=["metan", "metanu", "ch4", "gazy cieplarniane", "gazów cieplarnianych", "krowy", "bagna"],
    kw_en=["methane", "ch4", "greenhouse gases"], hints=["methane", "greenhouse"], unit="ppb",
    connector="gml", params={"gas": "ch4", "scope": "gl"}, start=1984, provider=P["noaa"], topic="methane",
    kind="absolute", source=src("NOAA GML — Methane", "https://gml.noaa.gov/ccgg/trends_ch4/",
                                "https://gml.noaa.gov/webdata/ccgg/trends/ch4/ch4_annmean_gl.csv"),
    sanity={"min": 1600, "max": 2100, "min_points": 35}, **GAS)
add("noaa_n2o_global", title="Globalne stężenie N₂O (NOAA GML)", title_en="Global mean atmospheric nitrous oxide (NOAA GML)",
    desc="Roczna średnia globalna stężenia podtlenku azotu w atmosferze (ppb), NOAA GML.",
    desc_en="Annual global mean atmospheric nitrous oxide (ppb), NOAA GML.",
    kw_pl=["podtlenek azotu", "podtlenku azotu", "n2o", "gazy cieplarniane", "nawozy"],
    kw_en=["nitrous oxide", "n2o", "greenhouse gases"], hints=["n2o", "greenhouse"], unit="ppb",
    connector="gml", params={"gas": "n2o", "scope": "gl"}, start=2001, provider=P["noaa"], topic="n2o",
    kind="absolute", source=src("NOAA GML — Nitrous oxide", "https://gml.noaa.gov/ccgg/trends_n2o/",
                                "https://gml.noaa.gov/webdata/ccgg/trends/n2o/n2o_annmean_gl.csv"),
    sanity={"min": 310, "max": 345, "min_points": 20}, **GAS)

# ============================================================ poziom morza
SL = dict(topic="sea_level", category="sea_level", unit="mm", kind="anomaly", regions=False,
          hints=["sea level"],
          kw_pl=["poziom morza", "poziomu morza", "podnoszenie się oceanów", "poziom oceanów", "wzrost poziomu morza"],
          kw_en=["sea level", "sea level rise", "global mean sea level", "gmsl"])
add("noaa_star_sea_level", title="Globalny poziom morza — altymetria (NOAA STAR)",
    title_en="Global mean sea level — satellite altimetry (NOAA LSA)",
    desc="Średnia roczna globalnego poziomu morza z altymetrii satelitarnej TOPEX/Poseidon–Jason–Sentinel-6 "
         "(NOAA Laboratory for Satellite Altimetry), mm.",
    desc_en="Annual GMSL from TOPEX/Poseidon, Jason-1/2/3 and Sentinel-6 altimetry (NOAA LSA).",
    connector="noaa_star", baseline="wartości względne", start=1993, provider=P["noaa"],
    source=src("NOAA Laboratory for Satellite Altimetry", "https://www.star.nesdis.noaa.gov/socd/lsa/SeaLevelRise/"),
    sanity={"min": -40, "max": 160, "min_points": 25}, params={}, **SL)
add("csiro_sea_level", title="Globalny poziom morza — rekonstrukcja (CSIRO)",
    title_en="Global mean sea level — reconstruction (CSIRO, Church & White)",
    desc="Rekonstrukcja globalnego poziomu morza z mareografów i altymetrii (Church & White 2011, "
         "aktualizacja CSIRO 2015), mm, 1880–2013.",
    desc_en="Tide-gauge + altimetry GMSL reconstruction, 1880–2013 (CSIRO, Church & White).",
    connector="csiro", baseline="wartości względne", start=1880, end=2013, provider=P["csiro"],
    source=src("CSIRO — Sea level data", "https://www.cmar.csiro.au/sealevel/sl_data_cmar.html"),
    sanity={"min": -230, "max": 100, "min_points": 120}, params={}, **SL)
add("uhslc_sea_level", title="Globalny poziom morza — mareografy (Univ. of Hawaii)",
    title_en="Global mean sea level — tide gauges (University of Hawaii Sea Level Center)",
    desc="Globalny poziom morza z sieci mareografów (UHSLC; dane z Our World in Data), mm.",
    desc_en="GMSL from the global tide-gauge network (UHSLC, via Our World in Data).",
    connector="owid_sea_level", baseline="wartości względne", start=1880, provider=P["uhslc"],
    source=src("University of Hawaii Sea Level Center", "https://uhslc.soest.hawaii.edu/",
               "https://ourworldindata.org/grapher/sea-level"),
    sanity={"min": -250, "max": 120, "min_points": 80}, params={"column": "UHSLC"}, **SL)

GAUGES = [(1, "Brest (Francja)", 1807), (64, "Gdańsk Nowy Port", 1886), (2, "Świnoujście", 1811),
          (78, "Sztokholm", 1889), (202, "Newlyn (UK)", 1916), (12, "Nowy Jork (Battery)", 1856),
          (155, "Honolulu", 1905), (196, "Sydney", 1886)]
for sid, name, start in GAUGES:
    add(f"psmsl_{sid}", title=f"Poziom morza — mareograf {name} (PSMSL)",
        title_en=f"Relative sea level — tide gauge {name} (PSMSL)",
        desc=f"Roczny względny poziom morza z mareografu {name} (PSMSL, National Oceanography Centre UK), mm RLR.",
        desc_en=f"Annual relative sea level at the {name} tide gauge (PSMSL RLR), mm.",
        kw_pl=["mareograf", "poziom morza", "poziomu morza", name.split()[0].lower(), "bałtyk", "wybrzeże"],
        kw_en=["tide gauge", "sea level", name.split()[0].lower()], hints=["sea level"], unit="mm",
        connector="psmsl", params={"station_id": sid}, regions=False, start=start,
        provider=P["psmsl"], topic="tide_gauge_sea_level", category="sea_level", kind="anomaly",
        baseline="wartości względne (RLR)",
        source=src("Permanent Service for Mean Sea Level (PSMSL)", "https://psmsl.org/",
                   f"https://psmsl.org/data/obtaining/stations/{sid}.php"),
        sanity={"min": 5500, "max": 8000, "min_points": 50} if False else {"min_points": 50})

# ============================================================ lod / slonce
add("arctic_ice_south", title="Zasięg lodu morskiego Antarktyki (wrzesień)", title_en="Antarctic sea ice extent (September)",
    desc="Zasięg lodu morskiego wokół Antarktydy we wrześniu (Sea Ice Index, NSIDC), mln km².",
    desc_en="September Antarctic sea ice extent (NSIDC Sea Ice Index), million km².",
    kw_pl=["antarktyka", "antarktydy", "lód antarktyczny", "lód południowy", "biegun południowy", "lody antarktyki"],
    kw_en=["antarctic sea ice", "south pole ice", "antarctica"], hints=["sea ice", "antarctic"],
    unit="mln km²", connector="arctic_ice", params={"pole": "south", "month": 9}, regions=False, start=1979,
    provider=P["nsidc"], topic="antarctic_sea_ice", category="sea_ice", kind="absolute",
    source=src("NSIDC Sea Ice Index", "https://nsidc.org/data/seaice_index/",
               "https://noaadata.apps.nsidc.org/NOAA/G02135/south/monthly/data/"),
    sanity={"min": 14.0, "max": 21.0, "min_points": 35})
add("sunspots_silso", title="Liczba plam słonecznych (SILSO)", title_en="Annual sunspot number (SILSO)",
    desc="Roczna średnia liczba plam słonecznych (SN v2.0), Royal Observatory of Belgium — wskaźnik aktywności Słońca.",
    desc_en="Annual mean total sunspot number v2.0 (SILSO, Royal Observatory of Belgium).",
    kw_pl=["plamy słoneczne", "plam słonecznych", "aktywność słońca", "słońce", "cykl słoneczny", "słoneczna"],
    kw_en=["sunspots", "solar activity", "solar cycle", "sun"], hints=["sunspots", "solar activity"],
    unit="liczba plam", connector="silso", params={}, regions=False, start=1700, provider=P["silso"],
    topic="solar_activity", category="sun", body="sun", kind="absolute",
    source=src("SILSO — Sunspot Index and Long-term Solar Observations", "https://www.sidc.be/SILSO/"),
    sanity={"min": 0, "max": 300, "min_points": 250})

# ============================================================ regionalne: temperatura
RT = dict(topic="regional_temperature", category="temperature", unit="°C", hints=["temperature", "warming"],
          kw_pl=KEYS_PL_TEMP, kw_en=KEYS_EN_TEMP)
add("openmeteo_era5_t2m", title="Temperatura powietrza 2 m — ERA5 (Open-Meteo)",
    title_en="Air temperature 2 m — ERA5 reanalysis (Open-Meteo)",
    desc="Średnia temperatura powietrza 2 m z reanalizy ECMWF ERA5 (Copernicus) dla dowolnego punktu/obszaru, "
         "udostępniana przez Open-Meteo; od 1981.",
    desc_en="2 m air temperature from ECMWF ERA5 reanalysis for any point/area, served by Open-Meteo.",
    connector="open_meteo", params={"variable": "temperature_2m_mean", "model": "era5"}, regions=True,
    start=1981, provider=P["openmeteo"], kind="absolute", region_scope="any",
    source=src("Open-Meteo Historical Weather API (ECMWF ERA5)", "https://open-meteo.com/en/docs/historical-weather-api"),
    sanity={"min": -15, "max": 30, "min_points": 35, "max_gap": 1}, **{**RT,
    "kw_pl": RT["kw_pl"] + ["era5", "copernicus", "esa", "ecmwf"], "kw_en": RT["kw_en"] + ["era5", "copernicus", "ecmwf", "esa"]})
add("openmeteo_era5land_t2m", title="Temperatura powietrza 2 m — ERA5-Land (Open-Meteo)",
    title_en="Air temperature 2 m — ERA5-Land (Open-Meteo)",
    desc="Średnia temperatura powietrza 2 m z modelu lądowego ERA5-Land (ECMWF/Copernicus, 9 km) przez Open-Meteo.",
    desc_en="2 m air temperature from ECMWF ERA5-Land (9 km land reanalysis) via Open-Meteo.",
    connector="open_meteo", params={"variable": "temperature_2m_mean", "model": "era5_land"}, regions=True,
    start=1981, provider=P["openmeteo"], kind="absolute", region_scope="any",
    source=src("Open-Meteo Historical Weather API (ERA5-Land)", "https://open-meteo.com/en/docs/historical-weather-api"),
    sanity={"min": -15, "max": 30, "min_points": 35}, **{**RT,
    "kw_pl": RT["kw_pl"] + ["era5-land", "copernicus", "esa"], "kw_en": RT["kw_en"] + ["era5-land", "copernicus", "ecmwf", "esa"]})
add("berkeley_region_temp", title="Anomalia temperatury kraju/kontynentu — Berkeley Earth",
    title_en="Country/continent land temperature anomaly — Berkeley Earth",
    desc="Roczne anomalie temperatury lądu dla kraju lub kontynentu względem 1951–1980 (Berkeley Earth, "
         "niezależna analiza stacji naziemnych).",
    desc_en="Annual land temperature anomalies for a country or continent vs 1951–1980 (Berkeley Earth).",
    connector="berkeley_region", params={}, regions=True, start=1850, provider=P["berkeley"], kind="anomaly",
    baseline="1951–1980", region_scope="country",
    source=src("Berkeley Earth — Regional temperature", "https://berkeleyearth.org/data/"),
    sanity={"min": -4, "max": 6, "min_points": 100}, **RT)
add("owid_era5_temp_anomaly", title="Anomalia temperatury kraju — ERA5 (Copernicus via OWID)",
    title_en="Country temperature anomaly — ERA5 (Copernicus via Our World in Data)",
    desc="Roczna anomalia temperatury przy powierzchni dla kraju względem 1991–2020 (reanaliza ERA5, "
         "Copernicus C3S) w opracowaniu Our World in Data; od 1940.",
    desc_en="Annual country-level near-surface temperature anomaly vs 1991–2020 (Copernicus ERA5 via OWID).",
    connector="owid_temp", params={"slug": "annual-temperature-anomalies"}, regions=True, start=1940,
    provider={**P["owid"], "org": "Copernicus ERA5 (opracowanie Our World in Data)"}, kind="anomaly",
    baseline="1991–2020", region_scope="country",
    source=src("Our World in Data / Copernicus C3S", "https://ourworldindata.org/grapher/annual-temperature-anomalies"),
    sanity={"min": -4, "max": 5, "min_points": 70}, **{**RT,
    "kw_pl": RT["kw_pl"] + ["copernicus", "esa"], "kw_en": RT["kw_en"] + ["copernicus", "esa"]})

# ============================================================ regionalne: opady
RP = dict(topic="regional_precipitation", category="precipitation", unit="mm/dzień",
          hints=["precipitation", "rain"],
          kw_pl=["opady", "opadów", "deszcz", "susza", "susze", "powódź", "powodzie", "deszczowe"],
          kw_en=["precipitation", "rain", "drought", "rainfall"])
add("openmeteo_era5_prec", title="Opady — ERA5 (Open-Meteo)", title_en="Precipitation — ERA5 (Open-Meteo)",
    desc="Średni dobowy opad (mm/dzień) z reanalizy ECMWF ERA5 przez Open-Meteo; od 1981.",
    desc_en="Mean daily precipitation (mm/day) from ECMWF ERA5 via Open-Meteo.",
    connector="open_meteo", params={"variable": "precipitation_sum", "model": "era5"}, regions=True,
    start=1981, provider=P["openmeteo"], kind="absolute", region_scope="any",
    source=src("Open-Meteo Historical Weather API (ECMWF ERA5)", "https://open-meteo.com/en/docs/historical-weather-api"),
    sanity={"min": 0, "max": 15, "min_points": 35}, **RP)
# ERA5-Land przez Open-Meteo nie udostepnia opadow dobowych (sprawdzone) - brak zbioru

# ============================================================ emisje
EM = dict(topic="emissions", category="greenhouse", hints=["co2", "greenhouse", "emissions"],
          kw_pl=["emisje", "emisji", "emisje co2", "emisje gazów cieplarnianych", "gazy cieplarniane", "spalanie paliw", "emituje"],
          kw_en=["emissions", "co2 emissions", "greenhouse gas emissions", "carbon emissions"],
          regions=True, region_scope="country_or_world", kind="absolute")
add("owid_co2_emissions", title="Emisje CO₂ ze spalania paliw (Global Carbon Project)",
    title_en="Annual CO2 emissions (Global Carbon Project)", unit="mln t CO₂",
    desc="Roczne emisje CO₂ ze spalania paliw kopalnych i przemysłu (Global Carbon Project, via Our World in Data) dla kraju lub świata.",
    desc_en="Annual fossil CO2 emissions (Global Carbon Project via OWID) for a country or the world.",
    connector="owid", params={"slug": "annual-co2-emissions-per-country", "column": 3, "scale": 1e-6}, start=1950,
    provider=P["gcp"], source=src("Global Carbon Project / Our World in Data",
        "https://ourworldindata.org/co2-emissions", "https://ourworldindata.org/grapher/annual-co2-emissions-per-country"),
    sanity={"min": 0, "max": 15000, "min_points": 60}, **EM)
add("owid_ghg_total", title="Emisje wszystkich gazów cieplarnianych (Climate Watch via OWID)",
    title_en="Total greenhouse gas emissions incl. land use (Climate Watch via OWID)", unit="mln t CO₂e",
    desc="Roczne emisje wszystkich gazów cieplarnianych z użytkowaniem gruntów (CO₂e), Climate Watch / Our World in Data.",
    desc_en="Annual total GHG emissions incl. land use (CO2e), Climate Watch via OWID.",
    connector="owid", params={"slug": "total-ghg-emissions", "column": 3, "scale": 1e-6}, start=1850,
    provider={**P["owid"], "org": "Climate Watch / WRI (opracowanie Our World in Data)"},
    source=src("Climate Watch / Our World in Data", "https://ourworldindata.org/greenhouse-gas-emissions",
               "https://ourworldindata.org/grapher/total-ghg-emissions"),
    sanity={"min": -500, "max": 70000, "min_points": 25}, **EM)
add("eurostat_ghg", title="Emisje gazów cieplarnianych (Eurostat)", title_en="Greenhouse gas emissions (Eurostat)",
    unit="mln t CO₂e",
    desc="Roczne emisje gazów cieplarnianych bez LULUCF dla krajów UE i UE-27 (Eurostat, inwentaryzacje krajowe CRF).",
    desc_en="Annual GHG emissions excl. LULUCF for EU member states and the EU-27 (Eurostat).",
    connector="eurostat_ghg", params={}, start=1990, provider=P["eurostat"],
    source=src("Eurostat — env_air_gge", "https://ec.europa.eu/eurostat/databrowser/view/env_air_gge/",
               "https://ec.europa.eu/eurostat/databrowser/view/env_air_gge/"),
    sanity={"min": 1, "max": 5500, "min_points": 25}, **{**EM, "region_scope": "eu"})
add("owid_co2_per_capita", title="Emisje CO₂ na mieszkańca (Global Carbon Project)",
    title_en="CO2 emissions per capita (Global Carbon Project)", unit="t CO₂/osobę",
    desc="Roczne emisje CO₂ na mieszkańca (Global Carbon Project via Our World in Data).",
    desc_en="Annual CO2 emissions per capita (GCP via OWID).",
    connector="owid", params={"slug": "co-emissions-per-capita", "column": 3, "scale": 1.0}, start=1950,
    provider=P["gcp"], source=src("Global Carbon Project / Our World in Data",
        "https://ourworldindata.org/co2-emissions", "https://ourworldindata.org/grapher/co-emissions-per-capita"),
    sanity={"min": 0, "max": 40, "min_points": 60}, **{**EM, "topic": "emissions_per_capita"})
add("owid_renewables_share", title="Udział OZE w produkcji energii elektrycznej (Ember)",
    title_en="Renewables share of electricity (Ember via OWID)", unit="%",
    desc="Udział odnawialnych źródeł energii w produkcji energii elektrycznej (Ember, via Our World in Data).",
    desc_en="Share of electricity from renewables (Ember via OWID).",
    connector="owid", params={"slug": "share-electricity-renewables", "column": 3, "scale": 1.0}, start=2000,
    provider=P["ember"], source=src("Ember / Our World in Data", "https://ourworldindata.org/renewable-energy",
        "https://ourworldindata.org/grapher/share-electricity-renewables"),
    sanity={"min": 0, "max": 100, "min_points": 15},
    **{**EM, "topic": "renewables", "kw_pl": ["odnawialne", "oze", "energia odnawialna", "wiatr", "słońce", "fotowoltaika", "energetyka"],
       "kw_en": ["renewables", "renewable energy", "electricity mix", "wind", "solar"], "hints": ["renewables", "energy"],
       "category": "energy"})

# ============================================================ MARS
MARS_KW_PL = ["mars", "marsa", "marsie", "marsem", "marsjański", "marsjańska", "marsjańskie", "czerwona planeta",
              "pogoda na marsie", "klimat marsa", "curiosity", "łazik", "krater gale"]
MARS_KW_EN = ["mars", "martian", "red planet", "curiosity rover", "gale crater", "rems", "mars weather"]


def mars(id_, title, title_en, desc, unit, connector, params, provider, source, topic, san, extra_kw_pl=(), extra_kw_en=(),
         desc_en=None):
    add(id_, title=title, title_en=title_en, desc=desc, desc_en=desc_en or desc,
        kw_pl=MARS_KW_PL + list(extra_kw_pl), kw_en=MARS_KW_EN + list(extra_kw_en),
        hints=["mars", "planets"], unit=unit, connector=connector, params=params, regions=False, start=2012,
        provider=provider, topic=topic, category="planetary", body="mars", kind="absolute",
        series_kind="seasonal_ls", baseline="klimatologia sezonowa wg Ls",
        resolution="dobowa (sol) -> przedziały Ls 15°", source=source, sanity=san)


REMS_SRC = src("NASA Curiosity REMS (CAB-INTA / NASA-JPL)", "https://mars.nasa.gov/msl/mission/weather/",
               "https://mars.nasa.gov/rss/api/?feed=weather&category=msl&feedtype=json")
MCD_SRC = src("Mars Climate Database (LMD/CNES/Open University/IAA/ESA)", "http://www-mars.lmd.jussieu.fr/mcd_python/",
              "http://www-mars.lmd.jussieu.fr/mars/access.html")
for var, label, label_en, unit, rems_san, mcd_san, kw in [
    ("max_temp", "dzienne maksimum temperatury powietrza", "daily maximum air temperature", "°C",
     {"min": -60, "max": 40}, {"min": -80, "max": 40}, ["maksimum", "ciepło", "temperatura w dzień"]),
    ("min_temp", "dzienne minimum temperatury powietrza", "daily minimum air temperature", "°C",
     {"min": -120, "max": 0}, {"min": -140, "max": 0}, ["minimum", "mróz", "noc", "temperatura w nocy"]),
    ("pressure", "ciśnienie atmosferyczne", "atmospheric pressure", "Pa",
     {"min": 600, "max": 1000}, {"min": 500, "max": 1100}, ["ciśnienie", "atmosfera", "atmosfery"])]:
    mars(f"mars_rems_{var}", f"Mars: {label} — Curiosity REMS (NASA)", f"Mars: {label_en} — Curiosity REMS (NASA/CAB)",
         f"{label.capitalize()} na Marsie w kraterze Gale mierzone przez stację REMS łazika Curiosity, "
         f"średnie wg Ls z pełnych lat marsjańskich (od 2012).",
         unit, "mars_rems", {"var": var}, P["cab"], REMS_SRC, f"mars_{var}", {**rems_san, "min_points": 20},
         kw, ["temperature", "pressure"] if var == "pressure" else ["temperature"],
         desc_en=f"{label_en.capitalize()} on Mars in Gale crater measured by the REMS station on the "
                 f"Curiosity rover, averaged by Ls over full Martian years (since 2012).")
    if var != "pressure":
        mars(f"mars_mcd_{var}", f"Mars: {label} — model MCD (ESA/CNES/LMD)",
             f"Mars: {label_en} — Mars Climate Database (ESA/CNES)",
             f"Modelowana klimatologia ({label}) dla krateru Gale z Mars Climate Database "
             f"(LMD, CNES, Open University, IAA, ESA) — MODEL, nie obserwacja.",
             unit, "mars_mcd", {"kind": var}, P["mcd"], MCD_SRC, f"mars_{var}", {**mcd_san, "min_points": 10},
             kw + ["model", "esa", "mcd"], ["model", "esa", "mcd", "temperature"],
             desc_en=f"Modelled climatology ({label_en}) for Gale crater from the Mars Climate Database "
                     f"(LMD, CNES, Open University, IAA, ESA). A MODEL, not an observation.")
    else:
        mars("mars_mcd_pressure", "Mars: ciśnienie atmosferyczne — model MCD (ESA/CNES/LMD)",
             "Mars: atmospheric pressure — Mars Climate Database (ESA/CNES)",
             "Modelowana klimatologia ciśnienia dla krateru Gale z Mars Climate Database (LMD, CNES, Open Univ., IAA, ESA) — MODEL.",
             "Pa", "mars_mcd", {"kind": "pressure"}, P["mcd"], MCD_SRC, "mars_pressure", {**mcd_san, "min_points": 10},
             kw + ["model", "esa", "mcd"], ["model", "esa", "mcd", "pressure"],
             desc_en="Modelled pressure climatology for Gale crater from the Mars Climate Database "
                     "(LMD, CNES, Open Univ., IAA, ESA). A MODEL.")
for var, label, label_en, rng in [
        ("max_gts_temp", "dzienne maksimum temperatury gruntu", "daily maximum ground temperature", {"min": -40, "max": 60}),
        ("min_gts_temp", "dzienne minimum temperatury gruntu", "daily minimum ground temperature", {"min": -120, "max": 0})]:
    mars(f"mars_rems_{var}", f"Mars: {label} — Curiosity REMS (NASA)", f"Mars: {label_en} — Curiosity REMS",
         f"{label.capitalize()} na Marsie (krater Gale, REMS/Curiosity), średnie wg Ls z pełnych lat marsjańskich.",
         "°C", "mars_rems", {"var": var}, P["cab"], REMS_SRC, f"mars_{var}", {**rng, "min_points": 20},
         ["grunt", "gruntu", "powierzchnia"], ["ground temperature", "surface temperature"],
         desc_en=f"{label_en.capitalize()} on Mars (Gale crater, REMS/Curiosity), averaged by Ls over full Martian years.")

# ============================================================ PLANETY
PL_KW_PL = ["planety", "planet", "planetach", "układ słoneczny", "układzie słonecznym", "wenus", "wenusie", "merkury",
            "jowisz", "jowiszu", "saturn", "saturnie", "uran", "neptun", "pluton", "księżyc", "księżycu", "mars", "marsie",
            "ziemia", "ziemi", "porównanie planet"]
PL_KW_EN = ["planets", "solar system", "venus", "mercury", "jupiter", "saturn", "uranus", "neptune", "pluto", "moon", "mars", "earth"]
for key, title, title_en, unit, extra_pl, extra_en in [
    ("mean_temp", "Średnia temperatura planet", "Mean temperature of the planets", "°C", ["temperatura", "temperatura na planetach", "gorąco", "zimno", "ciepło"],
     ["temperature", "hottest planet", "coldest planet"]),
    ("gravity", "Grawitacja na planetach", "Surface gravity of the planets", "m/s²", ["grawitacja", "przyciąganie", "ciężar"], ["gravity"]),
    ("distance_sun", "Odległość planet od Słońca", "Distance of the planets from the Sun", "mln km", ["odległość", "od słońca"], ["distance from sun"]),
    ("day_length", "Długość doby na planetach", "Length of day on the planets", "godz.", ["doba", "dzień", "długość dnia"], ["length of day"]),
    ("surface_pressure", "Ciśnienie przy powierzchni planet", "Surface pressure of the planets", "bar", ["ciśnienie", "atmosfera"], ["pressure", "atmosphere"]),
    ("orbital_period", "Okres obiegu planet wokół Słońca", "Orbital period of the planets", "dni", ["rok", "okres obiegu"], ["orbital period", "year length"]),
    ("diameter", "Średnica planet", "Diameter of the planets", "km", ["średnica", "rozmiar", "wielkość"], ["diameter", "size"]),
]:
    add(f"planet_{key}", title=f"{title} (NASA Planetary Fact Sheet)", title_en=f"{title_en} (NASA Planetary Fact Sheet)",
        desc=f"{title} — porównanie ciał Układu Słonecznego wg NASA NSSDCA Planetary Fact Sheet.",
        desc_en=f"{title_en} — comparison across Solar System bodies from the NASA NSSDCA Planetary Fact Sheet.",
        kw_pl=PL_KW_PL + extra_pl, kw_en=PL_KW_EN + extra_en, hints=["planets", "mars"], unit=unit,
        connector="planet_metric", params={"metric": key}, regions=False, start=1960, provider=P["nasa"],
        topic=f"planet_{key}", category="planetary", body="solar_system", kind="absolute", series_kind="planet_metric",
        baseline="wartości wzorcowe", resolution="jedna wartość na ciało",
        source=src("NASA NSSDCA Planetary Fact Sheet", "https://nssdc.gsfc.nasa.gov/planetary/factsheet/"),
        sanity={"min_points": 5})

# ---------- krotkie etykiety + znacznik modelu ----------
SHORT = {
    "noaa_global_temp": "NOAA NOAAGlobalTemp", "hadcrut5": "Met Office HadCRUT5", "berkeley_global": "Berkeley Earth",
    "jma_global": "JMA (Japonia)", "era5_global_temp": "Copernicus ERA5", "noaa_ocean_temp": "NOAA ERSST",
    "oisst_sst": "NOAA OISST (UMaine)", "era5_sst": "Copernicus ERA5", "noaa_co2_global": "NOAA GML (średnia globalna)",
    "noaa_ch4_global": "NOAA GML", "noaa_n2o_global": "NOAA GML", "noaa_star_sea_level": "NOAA altymetria",
    "csiro_sea_level": "CSIRO (mareografy+altymetria)", "uhslc_sea_level": "Univ. of Hawaii (mareografy)",
    "openmeteo_era5_t2m": "ECMWF ERA5 (Open-Meteo)", "openmeteo_era5land_t2m": "ECMWF ERA5-Land (Open-Meteo)",
    "berkeley_region_temp": "Berkeley Earth", "owid_era5_temp_anomaly": "Copernicus ERA5 (OWID)",
    "openmeteo_era5_prec": "ECMWF ERA5 (Open-Meteo)",
    "owid_co2_emissions": "Global Carbon Project (CO₂)", "owid_ghg_total": "Climate Watch (GHG łącznie)",
    "eurostat_ghg": "Eurostat (GHG, UE)", "owid_co2_per_capita": "Global Carbon Project",
    "owid_renewables_share": "Ember", "arctic_ice_south": "NSIDC", "sunspots_silso": "SILSO",
    "mars_rems_max_temp": "NASA Curiosity REMS (obserwacje)", "mars_rems_min_temp": "NASA Curiosity REMS (obserwacje)",
    "mars_rems_pressure": "NASA Curiosity REMS (obserwacje)", "mars_mcd_max_temp": "MCD ESA/CNES (model)",
    "mars_mcd_min_temp": "MCD ESA/CNES (model)", "mars_mcd_pressure": "MCD ESA/CNES (model)",
    "mars_rems_max_gts_temp": "NASA Curiosity REMS (obserwacje)", "mars_rems_min_gts_temp": "NASA Curiosity REMS (obserwacje)",
}
for k, v in SHORT.items():
    ds[k]["short"] = v
for sid, name, _ in GAUGES:
    ds[f"psmsl_{sid}"]["short"] = f"PSMSL · {name}"
def dtype(k):
    if k.startswith("mars_mcd"):
        return "model"
    if k.startswith(("openmeteo", "era5", "owid_era5", "power")):
        return "reanalysis"
    if k.startswith("planet_"):
        return "reference"
    if k in ("owid_co2_emissions", "owid_ghg_total", "eurostat_ghg", "owid_co2_per_capita", "owid_renewables_share"):
        return "inventory"
    if k in ("berkeley_global", "berkeley_region_temp", "hadcrut5", "noaa_global_temp", "jma_global", "noaa_ocean_temp", "gistemp_global", "gistemp_nh"):
        return "analysis"
    return "observation"


for k in ds:
    ds[k]["data_type"] = dtype(k)
    ds[k]["is_model"] = ds[k]["data_type"] == "model"

# ---------- pokrycie zgodne z faktycznymi danymi (z weryfikacji) ----------
COV = {"uhslc_sea_level": (1970, 2020), "psmsl_64": (1951, 1999), "psmsl_2": (1811, 1999),
       "berkeley_region_temp": (1850, 2020), "oisst_sst": (1982, 2023), "era5_sst": (1979, 2023),
       "psmsl_196": (1915, None)}
for k, (a, b) in COV.items():
    ds[k]["coverage"]["start"], ds[k]["coverage"]["end"] = a, b
ds["uhslc_sea_level"]["sanity"]["min_points"] = 40
ds["psmsl_64"]["sanity"]["min_points"] = 40
ds["oisst_sst"]["notes"] = ds["era5_sst"]["notes"] = "plik źródłowy nieaktualizowany od 2024 r."
ds["berkeley_region_temp"]["notes"] = "regionalne pliki Berkeley Earth kończą się w 2020 r."

# ---------- zapis ----------
(CAT / "datasets_external.json").write_text(json.dumps(ds, ensure_ascii=False, indent=1), encoding="utf-8")

# ---------- metadane dla zbiorow NASA ----------
nasa = json.loads((CAT / "datasets.json").read_text(encoding="utf-8"))
tmap = {"power_t2m": ("regional_temperature", "absolute"), "power_t2m_max": ("regional_tmax", "absolute"),
        "power_t2m_min": ("regional_tmin", "absolute"), "power_prec": ("regional_precipitation", "absolute"),
        "power_rh": ("regional_humidity", "absolute"), "power_wind": ("regional_wind", "absolute"),
        "power_radiation": ("regional_radiation", "absolute"),
        "gistemp_global": ("global_temperature", "anomaly"), "gistemp_nh": ("nh_temperature", "anomaly"),
        "co2": ("co2", "absolute"), "sea_level": ("sea_level", "anomaly"), "arctic_ice": ("arctic_sea_ice", "absolute")}
for k, d in nasa.items():
    topic, kind = tmap.get(k, (k, "absolute"))
    d["provider"] = P["nasa"] if not k == "co2" else {"org": "NOAA GML (via NASA Vital Signs)", "country": "USA", "type": "agency"}
    d["topic"], d["kind"], d["body"] = topic, kind, "earth"
    d["series_kind"] = "annual"
    d.setdefault("region_scope", "any" if d.get("supports_regions") else "global")
    d["baseline"] = {"gistemp_global": "1951–1980", "gistemp_nh": "1951–1980"}.get(k)
    d["short"] = {"power_t2m": "NASA POWER (MERRA-2)", "power_prec": "NASA POWER (MERRA-2)", "gistemp_global": "NASA GISTEMP v4",
                  "gistemp_nh": "NASA GISTEMP v4 (półkula N)", "co2": "NOAA/NASA Mauna Loa", "sea_level": "NASA altymetria",
                  "arctic_ice": "NSIDC (NASA DAAC)"}.get(k, "NASA POWER (MERRA-2)" if k.startswith("power") else "NASA")
    d["data_type"] = dtype(k)
    d["is_model"] = False
    d["sanity"] = {"power_t2m": {"min": -15, "max": 30}, "gistemp_global": {"min": -1.0, "max": 1.8},
                   "gistemp_nh": {"min": -1.5, "max": 2.5}, "co2": {"min": 310, "max": 450},
                   "sea_level": {"min": -20, "max": 160}, "arctic_ice": {"min": 2.5, "max": 9.0}}.get(k, {})
nasa["co2"]["topic"] = "co2"
(CAT / "datasets.json").write_text(json.dumps(nasa, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(ds), "zbiorow zewnetrznych;", len(nasa), "NASA")
