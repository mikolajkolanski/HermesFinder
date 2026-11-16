"""Slownik regionow geograficznych (bez zewnetrznego geokodera).

Kazdy region: lista wariantow nazw (PL z odmianami + EN), typ (country/point/
bbox) i wspolrzedne. Dopasowanie po normalizacji tekstu (bez polskich znakow).
"""
from __future__ import annotations

from typing import Any

# bbox = [lat_min, lat_max, lon_min, lon_max] (POWER regional)
# point = (lat, lon) (POWER point)
REGIONS: list[dict[str, Any]] = [
    # ---- Polska ----
    {
        "id": "poland", "name": "Polska", "type": "bbox",
        "bbox": [49.0, 54.9, 14.1, 24.15],
        "aliases": ["polska", "polsce", "polski", "polsce", "poland", "rp",
                    "na polski", "w polsce", "poludniowa polska", "polen", "pologne", "polonia"],
    },
    # ---- miasta PL (punkt) ----
    {"id": "warsaw", "name": "Warszawa", "type": "point", "point": [52.23, 21.01],
     "aliases": ["warszawa", "warszawie", "warszawy", "warsaw"]},
    {"id": "krakow", "name": "Kraków", "type": "point", "point": [50.06, 19.94],
     "aliases": ["krakow", "krakowie", "krakowa", "kraków", "cracow"]},
    {"id": "gdansk", "name": "Gdańsk", "type": "point", "point": [54.35, 18.65],
     "aliases": ["gdansk", "gdansku", "gdanska", "gdańsk", "gdansk", "danzig"]},
    {"id": "wroclaw", "name": "Wrocław", "type": "point", "point": [51.11, 17.03],
     "aliases": ["wroclaw", "wroclawie", "wroclawa", "wrocław", "breslau"]},
    {"id": "poznan", "name": "Poznań", "type": "point", "point": [52.41, 16.93],
     "aliases": ["poznan", "poznanie", "poznania", "poznań"]},
    {"id": "lodz", "name": "Łódź", "type": "point", "point": [51.76, 19.46],
     "aliases": ["lodz", "lodzi", "lodzi", "łódź"]},
    {"id": "katowice", "name": "Katowice", "type": "point", "point": [50.26, 19.02],
     "aliases": ["katowice", "katowicach", "katowic"]},
    {"id": "lublin", "name": "Lublin", "type": "point", "point": [51.25, 22.57],
     "aliases": ["lublin", "lublinie", "lublina"]},
    {"id": "szczecin", "name": "Szczecin", "type": "point", "point": [53.43, 14.55],
     "aliases": ["szczecin", "szczecinie", "szczecina"]},
    {"id": "bydgoszcz", "name": "Bydgoszcz", "type": "point", "point": [53.12, 18.01],
     "aliases": ["bydgoszcz", "bydgoszczy"]},
    {"id": "bialystok", "name": "Białystok", "type": "point", "point": [53.13, 23.16],
     "aliases": ["bialystok", "białystok", "bialymstoku"]},
    {"id": "rzeszow", "name": "Rzeszów", "type": "point", "point": [50.04, 21.99],
     "aliases": ["rzeszow", "rzeszowie", "rzeszowa", "rzeszów"]},
    {"id": "olsztyn", "name": "Olsztyn", "type": "point", "point": [53.78, 20.48],
     "aliases": ["olsztyn", "olsztynie"]},
    {"id": "zakopane", "name": "Zakopane", "type": "point", "point": [49.30, 19.95],
     "aliases": ["zakopane", "zakopanem", "tatry", "tatrach"]},
    # ---- wojewodztwa (bbox przyblizony) ----
    {"id": "mazowieckie", "name": "województwo mazowieckie", "type": "bbox",
     "bbox": [51.1, 53.7, 18.8, 22.8],
     "aliases": ["mazowieckie", "mazowszu", "mazowsze", "mazowsza",
                 "mazowszanskim", "mazowszanskie"]},
    {"id": "malopolskie", "name": "województwo małopolskie", "type": "bbox",
     "bbox": [49.4, 50.6, 18.9, 21.3],
     "aliases": ["malopolskie", "małopolskie", "malopolsce", "małopolsce",
                 "malopolska", "małopolska", "malopolska", "malopolsku"]},
    {"id": "wielkopolskie", "name": "województwo wielkopolskie", "type": "bbox",
     "bbox": [51.3, 53.5, 15.8, 18.9],
     "aliases": ["wielkopolskie", "wielkopolsce", "wielkopolska"]},
    {"id": "slaskie", "name": "województwo śląskie", "type": "bbox",
     "bbox": [49.5, 51.2, 18.1, 19.9],
     "aliases": ["slaskie", "śląskie", "slasku", "śląsku"]},
    {"id": "dolnoslaskie", "name": "województwo dolnośląskie", "type": "bbox",
     "bbox": [50.2, 51.7, 15.0, 17.9],
     "aliases": ["dolnoslaskie", "dolnośląskie", "dolnym slasku", "dolnym śląsku"]},
    {"id": "pomorskie", "name": "województwo pomorskie", "type": "bbox",
     "bbox": [53.5, 54.8, 16.5, 19.6],
     "aliases": ["pomorskie", "pomorskiem", "pomorzu"]},
    {"id": "zachodniopomorskie", "name": "województwo zachodniopomorskie", "type": "bbox",
     "bbox": [52.9, 54.6, 13.9, 17.0],
     "aliases": ["zachodniopomorskie", "zachodniopomorskiem"]},
    {"id": "lubelskie", "name": "województwo lubelskie", "type": "bbox",
     "bbox": [50.2, 51.7, 20.9, 24.1],
     "aliases": ["lubelskie", "lubelskiem"]},
    {"id": "podkarpackie", "name": "województwo podkarpackie", "type": "bbox",
     "bbox": [49.2, 50.9, 20.6, 23.0],
     "aliases": ["podkarpackie", "podkarpackiem"]},
    {"id": "kujawskopomorskie", "name": "województwo kujawsko-pomorskie", "type": "bbox",
     "bbox": [52.3, 53.8, 16.7, 19.7],
     "aliases": ["kujawsko-pomorskie", "kujawskopomorskie", "kujawsko pomorskie"]},
    {"id": "podlaskie", "name": "województwo podlaskie", "type": "bbox",
     "bbox": [52.6, 54.5, 20.9, 23.9],
     "aliases": ["podlaskie", "podlaskiem"]},
    {"id": "warminskomazurskie", "name": "województwo warmińsko-mazurskie", "type": "bbox",
     "bbox": [53.2, 54.7, 18.9, 22.9],
     "aliases": ["warminsko-mazurskie", "warmińsko-mazurskie", "warminskomazurskie"]},
    {"id": "lodzkie", "name": "województwo łódzkie", "type": "bbox",
     "bbox": [50.8, 52.4, 18.1, 20.3],
     "aliases": ["lodzkie", "łódzkie"]},
    {"id": "swietokrzyskie", "name": "województwo świętokrzyskie", "type": "bbox",
     "bbox": [50.3, 51.4, 19.6, 21.5],
     "aliases": ["swietokrzyskie", "świętokrzyskie"]},
    {"id": "lubuskie", "name": "województwo lubuskie", "type": "bbox",
     "bbox": [51.4, 53.0, 14.6, 16.9],
     "aliases": ["lubuskie", "lubuskim"]},
    {"id": "opolskie", "name": "województwo opolskie", "type": "bbox",
     "bbox": [50.1, 51.2, 17.0, 18.9],
     "aliases": ["opolskie", "opolskiem"]},
    # ---- kraje ----
    {"id": "germany", "name": "Niemcy", "type": "bbox", "bbox": [47.3, 55.0, 5.9, 15.0],
     "aliases": ["niemcy", "niemczech", "niemcami", "niemiec", "germany",
                 "niemieckiej", "niemieckim", "niemieckie", "deutschland", "allemagne", "alemania", "germania", "duitsland"]},
    {"id": "france", "name": "Francja", "type": "bbox", "bbox": [41.4, 51.1, -5.1, 9.6],
     "aliases": ["francja", "francji", "francji", "france", "frankreich", "francia", "frança"]},
    {"id": "spain", "name": "Hiszpania", "type": "bbox", "bbox": [36.0, 43.8, -9.3, 3.3],
     "aliases": ["hiszpania", "hiszpanii", "spain", "españa", "espana", "espagne", "spanien", "spagna", "peninsula iberica", "península ibérica", "peninsula", "península"]},
    {"id": "italy", "name": "Włochy", "type": "bbox", "bbox": [36.7, 47.1, 6.6, 18.5],
     "aliases": ["wlochy", "włochy", "wloszech", "włoszech", "italy", "italii", "italia", "italie", "italien"]},
    {"id": "uk", "name": "Wielka Brytania", "type": "bbox", "bbox": [49.9, 60.9, -8.6, 1.8],
     "aliases": ["wielkiej brytanii", "wielka brytania", "uk", "anglii", "anglia", "uk", "united kingdom", "großbritannien", "royaume-uni", "reino unido", "regno unito"]},
    {"id": "ukraine", "name": "Ukraina", "type": "bbox", "bbox": [44.3, 52.4, 22.1, 40.2],
     "aliases": ["ukraina", "ukrainie", "ukraine"]},
    {"id": "belarus", "name": "Białoruś", "type": "bbox", "bbox": [51.3, 56.2, 23.2, 32.8],
     "aliases": ["bialorus", "białoruś", "bialorusi", "białorusi"]},
    {"id": "czechia", "name": "Czechy", "type": "bbox", "bbox": [48.6, 51.1, 12.0, 18.9],
     "aliases": ["czechy", "czech", "czechach", "czechia"]},
    {"id": "slovakia", "name": "Słowacja", "type": "bbox", "bbox": [47.7, 49.6, 16.8, 22.6],
     "aliases": ["slowacja", "słowacja", "slowacji", "słowacji"]},
    {"id": "lithuania", "name": "Litwa", "type": "bbox", "bbox": [53.9, 56.5, 20.9, 26.8],
     "aliases": ["litwa", "litwie", "lithuania"]},
    {"id": "latvia", "name": "Łotwa", "type": "bbox", "bbox": [55.7, 58.1, 20.9, 28.2],
     "aliases": ["lotwa", "łotwa", "lotwie", "łotwie"]},
    {"id": "estonia", "name": "Estonia", "type": "bbox", "bbox": [57.5, 59.7, 21.8, 28.2],
     "aliases": ["estonia", "estonii"]},
    {"id": "russia", "name": "Rosja", "type": "bbox", "bbox": [41.2, 77.7, 27.0, 180.0],
     "aliases": ["rosja", "rosji", "russia"]},
    {"id": "china", "name": "Chiny", "type": "bbox", "bbox": [18.1, 53.6, 73.7, 135.0],
     "aliases": ["chiny", "chinach", "chin", "china"]},
    {"id": "india", "name": "Indie", "type": "bbox", "bbox": [6.7, 35.5, 68.1, 97.4],
     "aliases": ["indie", "indiach", "india"]},
    {"id": "usa", "name": "USA", "type": "bbox", "bbox": [24.5, 49.4, -125.0, -66.9],
     "aliases": ["usa", "stanach zjednoczonych", "stany zjednoczone", "ameryce",
                 "ameryka", "united states", "usa"]},
    {"id": "brazil", "name": "Brazylia", "type": "bbox", "bbox": [-33.7, 5.3, -73.9, -32.4],
     "aliases": ["brazylia", "brazylii", "brazil"]},
    {"id": "australia", "name": "Australia", "type": "bbox", "bbox": [-43.6, -10.7, 113.2, 153.6],
     "aliases": ["australia", "australii"]},
    {"id": "egypt", "name": "Egipt", "type": "bbox", "bbox": [22.0, 31.7, 25.0, 34.9],
     "aliases": ["egipt", "egipcie", "egypt"]},
    {"id": "turkey", "name": "Turcja", "type": "bbox", "bbox": [35.8, 42.1, 25.7, 44.8],
     "aliases": ["turcja", "turcji", "turkey"]},
    {"id": "greece", "name": "Grecja", "type": "bbox", "bbox": [34.8, 41.7, 19.4, 28.2],
     "aliases": ["grecja", "grecji", "greece"]},
    {"id": "sweden", "name": "Szwecja", "type": "bbox", "bbox": [55.3, 69.1, 11.0, 24.2],
     "aliases": ["szwecja", "szwecji", "sweden"]},
    {"id": "norway", "name": "Norwegia", "type": "bbox", "bbox": [57.9, 71.2, 4.6, 31.0],
     "aliases": ["norwegia", "norwegii", "norway"]},
    {"id": "finland", "name": "Finlandia", "type": "bbox", "bbox": [59.7, 70.1, 20.5, 31.6],
     "aliases": ["finlandia", "finlandii", "finland"]},
    {"id": "iceland", "name": "Islandia", "type": "bbox", "bbox": [63.4, 66.6, -24.6, -13.5],
     "aliases": ["islandia", "islandii", "iceland"]},
    {"id": "denmark", "name": "Dania", "type": "bbox", "bbox": [54.6, 57.8, 8.1, 12.8],
     "aliases": ["dania", "danii", "denmark"]},
    {"id": "netherlands", "name": "Holandia", "type": "bbox", "bbox": [50.8, 53.6, 3.4, 7.2],
     "aliases": ["holandia", "holandii", "netherlands"]},
    {"id": "belgium", "name": "Belgia", "type": "bbox", "bbox": [49.5, 51.5, 2.5, 6.4],
     "aliases": ["belgia", "belgii", "belgium"]},
    {"id": "austria", "name": "Austria", "type": "bbox", "bbox": [46.4, 49.0, 9.5, 17.2],
     "aliases": ["austria", "austrii", "austria"]},
    {"id": "hungary", "name": "Węgry", "type": "bbox", "bbox": [45.7, 48.6, 16.1, 22.2],
     "aliases": ["wegry", "węgry", "wegrze", "węgrzech", "hungary"]},
    {"id": "romania", "name": "Rumunia", "type": "bbox", "bbox": [43.6, 48.3, 20.3, 29.7],
     "aliases": ["rumunia", "rumunii", "romania"]},
    {"id": "bulgaria", "name": "Bułgaria", "type": "bbox", "bbox": [41.2, 44.2, 22.4, 28.6],
     "aliases": ["bulgaria", "bułgaria", "bulgarii", "bułgarii"]},
    {"id": "canada", "name": "Kanada", "type": "bbox", "bbox": [41.7, 83.1, -141.0, -52.6],
     "aliases": ["kanada", "kanadzie", "canada"]},
    {"id": "japan", "name": "Japonia", "type": "bbox", "bbox": [30.0, 45.6, 129.4, 145.8],
     "aliases": ["japonia", "japonii", "japan"]},
    {"id": "indonesia", "name": "Indonezja", "type": "bbox", "bbox": [-11.0, 6.1, 94.8, 141.0],
     "aliases": ["indonezja", "indonezji", "indonesia"]},
    {"id": "sahara", "name": "Sahara", "type": "bbox", "bbox": [16.0, 30.0, -17.0, 33.0],
     "aliases": ["sahara", "saharze", "sahary"]},
    # ---- kontynenty / wielkie obszary ----
    {"id": "europe", "name": "Europa", "type": "bbox", "bbox": [35.0, 71.0, -10.0, 40.0],
     "aliases": ["europa", "europie", "europy", "europe"]},
    {"id": "asia", "name": "Azja", "type": "bbox", "bbox": [0.0, 77.0, 40.0, 180.0],
     "aliases": ["azja", "azji", "azjii", "asia"]},
    {"id": "africa", "name": "Afryka", "type": "bbox", "bbox": [-35.0, 37.0, -17.0, 51.0],
     "aliases": ["afryka", "afryce", "afryki", "africa"]},
    {"id": "north_america", "name": "Ameryka Północna", "type": "bbox",
     "bbox": [7.0, 83.0, -168.0, -52.0],
     "aliases": ["ameryce polnocnej", "ameryka polnocna", "ameryki polnocnej",
                 "north america"]},
    {"id": "south_america", "name": "Ameryka Południowa", "type": "bbox",
     "bbox": [-56.0, 12.6, -81.8, -34.7],
     "aliases": ["ameryce poludniowej", "ameryka poludniowa", "ameryki poludniowej",
                 "south america"]},
    {"id": "antarctica", "name": "Antarktyda", "type": "bbox", "bbox": [-90.0, -60.0, -180.0, 180.0],
     "aliases": ["antarktyda", "antarktydzie", "antarktyki", "antarktyka", "antarctica", "antarktis", "antarctique", "antartide", "antártida", "antartida"]},
    {"id": "arctic", "name": "Arktyka", "type": "bbox", "bbox": [66.5, 90.0, -180.0, 180.0],
     "aliases": ["arktyka", "arktyce", "arktyki", "arctic", "arktis", "arctique", "artico", "ártico"]},
    {"id": "oceania", "name": "Oceania", "type": "bbox", "bbox": [-50.0, 20.0, 110.0, 180.0],
     "aliases": ["oceania", "oceanii"]},
    # ---- oceany ----
    {"id": "atlantic", "name": "Ocean Atlantycki", "type": "bbox", "bbox": [-60.0, 66.0, -70.0, 20.0],
     "aliases": ["atlantyckim", "atlantycki", "atlantycka", "atlantic"]},
    {"id": "pacific", "name": "Ocean Spokojny", "type": "bbox", "bbox": [-55.0, 62.0, 130.0, -70.0],
     "aliases": ["spokojnym", "spokojny", "pacyfiku", "pacyficzny", "pacyficznym", "pacific"]},
    {"id": "indian_ocean", "name": "Ocean Indyjski", "type": "bbox", "bbox": [-50.0, 25.0, 20.0, 120.0],
     "aliases": ["indyjskim", "indyjski", "indian"]},
    {"id": "arctic_ocean", "name": "Ocean Arktyczny", "type": "bbox", "bbox": [66.0, 90.0, -180.0, 180.0],
     "aliases": ["arktycznym", "arktyczny", "arctic ocean"]},
    {"id": "mediterranean", "name": "Morze Śródziemne", "type": "bbox", "bbox": [30.0, 46.0, -6.0, 36.0],
     "aliases": ["srodziemnym", "śródziemnym", "srodziemne", "śródziemne", "mediterranean",
                 "mari italiani", "mare mediterraneo", "mediterraneo", "mittelmeer",
                 "mediterranee", "méditerranée", "mediterraneo"]},
    {"id": "baltic", "name": "Morze Bałtyckie", "type": "bbox", "bbox": [53.5, 66.0, 10.0, 30.5],
     "aliases": ["baltyckim", "bałtyckim", "baltyk", "bałtyk", "baltyku", "bałtyku",
                 "baltic", "baltyckie", "baltycka", "morzu baltyckim", "ostsee",
                 "baltique", "baltico", "báltico", "mar baltico"]},
    # ---- regiony czesto cytowane w mediach (lodowce, lasy, pustynie) ----
    {"id": "greenland", "name": "Grenlandia", "type": "bbox",
     "bbox": [59.8, 83.6, -73.0, -12.0],
     "aliases": ["grenlandia", "grenlandii", "grenlandii", "greenland",
                 "grenlandzki", "grenlandii"]},
    {"id": "alps", "name": "Alpy", "type": "bbox", "bbox": [43.5, 48.5, 5.5, 16.5],
     "aliases": ["alpy", "alpach", "alpach", "alp", "alps", "alpejski",
                 "alpejskich"]},
    {"id": "himalaya", "name": "Himalaje", "type": "bbox",
     "bbox": [26.5, 36.5, 72.0, 95.0],
     "aliases": ["himalaje", "himalajach", "himalajach", "himalajow", "himalaya",
                 "himalayas"]},
    {"id": "amazonia", "name": "Amazonia", "type": "bbox",
     "bbox": [-10.0, 5.5, -74.0, -48.0],
     "aliases": ["amazonia", "amazonii", "amazonii", "amazon", "amazonką",
                 "amazonia"]},
    {"id": "siberia", "name": "Syberia", "type": "bbox",
     "bbox": [50.0, 73.5, 60.0, 145.0],
     "aliases": ["syberia", "syberii", "syberii", "siberia", "syberyjski",
                 "syberyjskich"]},
    {"id": "california", "name": "Kalifornia", "type": "bbox",
     "bbox": [32.5, 42.0, -124.5, -114.0],
     "aliases": ["kalifornia", "kalifornii", "kalifornii", "california"]},
]

# Nazwy wyswietlane uzytkownikowi (po angielsku). Polska nazwa zostaje w name_pl
# i w aliasach, wiec rozpoznawanie polskich tez dziala jak wczesniej.
NAMES_EN: dict[str, str] = {
    "poland": "Poland", "warsaw": "Warsaw", "krakow": "Kraków", "gdansk": "Gdańsk",
    "wroclaw": "Wrocław", "poznan": "Poznań", "lodz": "Łódź",
    "mazowieckie": "Masovian Voivodeship", "malopolskie": "Lesser Poland Voivodeship",
    "wielkopolskie": "Greater Poland Voivodeship", "slaskie": "Silesian Voivodeship",
    "dolnoslaskie": "Lower Silesian Voivodeship", "pomorskie": "Pomeranian Voivodeship",
    "zachodniopomorskie": "West Pomeranian Voivodeship", "lubelskie": "Lublin Voivodeship",
    "podkarpackie": "Subcarpathian Voivodeship", "kujawskopomorskie": "Kuyavian-Pomeranian Voivodeship",
    "podlaskie": "Podlaskie Voivodeship", "warminskomazurskie": "Warmian-Masurian Voivodeship",
    "lodzkie": "Łódź Voivodeship", "swietokrzyskie": "Holy Cross Voivodeship",
    "lubuskie": "Lubusz Voivodeship", "opolskie": "Opole Voivodeship",
    "germany": "Germany", "france": "France", "spain": "Spain", "italy": "Italy",
    "uk": "United Kingdom", "ukraine": "Ukraine", "belarus": "Belarus", "czechia": "Czechia",
    "slovakia": "Slovakia", "lithuania": "Lithuania", "latvia": "Latvia", "russia": "Russia",
    "china": "China", "india": "India", "brazil": "Brazil", "egypt": "Egypt", "turkey": "Turkey",
    "greece": "Greece", "sweden": "Sweden", "norway": "Norway", "finland": "Finland",
    "iceland": "Iceland", "denmark": "Denmark", "netherlands": "Netherlands", "belgium": "Belgium",
    "hungary": "Hungary", "romania": "Romania", "bulgaria": "Bulgaria", "canada": "Canada",
    "japan": "Japan", "indonesia": "Indonesia", "europe": "Europe", "asia": "Asia",
    "africa": "Africa", "north_america": "North America", "south_america": "South America",
    "antarctica": "Antarctica", "arctic": "Arctic", "atlantic": "Atlantic Ocean",
    "pacific": "Pacific Ocean", "indian_ocean": "Indian Ocean", "arctic_ocean": "Arctic Ocean",
    "mediterranean": "Mediterranean Sea", "baltic": "Baltic Sea", "greenland": "Greenland",
    "alps": "Alps", "himalaya": "Himalayas", "siberia": "Siberia", "california": "California",
}
for _reg in REGIONS:
    _reg.setdefault("name_pl", _reg["name"])
    _reg["name"] = NAMES_EN.get(_reg["id"], _reg["name"])
    for _n in (_reg["name"], _reg["name_pl"]):
        if _n.lower() not in _reg["aliases"]:
            _reg["aliases"].append(_n.lower())

# Swiat / globalne - traktowane specjalnie (brak regionu, wskazowka dla retrievera)
GLOBAL_ALIASES = [
    "swiecie", "swiat", "świecie", "świat", "globalne", "globalny", "globalnie",
    "global", "planecie", "planeta", "planet", "ziemi", "ziemia", "earth",
    "world", "worldwide", "na swiecie", "calego swiata", "na globie", "globie",
]


def _norm(text: str) -> str:
    """Normalizacja: male litery + ascii (diakrytyki, l->l, cyfry indeksowe)."""
    import unicodedata
    from rag.textproc import TRANSLIT
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.translate(TRANSLIT)


def find_region(text: str) -> dict[str, Any] | None:
    """Znajduje pierwszy region w tekscie (najdluzsze dopasowanie, fleksja ok)."""
    n = _norm(text)
    matches: list[tuple[int, int, dict[str, Any]]] = []
    for reg in REGIONS:
        for alias in reg["aliases"]:
            a = _norm(alias)
            idx = _find_alias(n, a)
            if idx is not None:
                matches.append((len(a), idx, reg))
    if not matches:
        return None
    matches.sort(key=lambda m: (-m[0], m[1]))
    return matches[0][2]


def is_global_mentioned(text: str) -> bool:
    n = _norm(text)
    return any(_norm(a) in n for a in GLOBAL_ALIASES)


def _find_alias(n: str, a: str) -> int | None:
    """Indeks dopasowania aliasu z fleksja (alias + do 4 znakow koncowki)."""
    idx = n.find(a)
    if idx < 0:
        return None
    before_ok = idx == 0 or not n[idx - 1].isalnum()
    if not before_ok:
        return None
    rest = n[idx + len(a):]
    if rest and rest[0].isalnum():
        # dopuszczamy polska fleksje: "mazowsze" + "m" (mazowszem),
        # ale tylko gdy alias dlugi (>=5) i koniecka krotka (<=4 znaki)
        ext = 0
        for ch in rest:
            if ch.isalnum():
                ext += 1
            else:
                break
        if ext <= 4 and len(a) >= 5:
            return idx
        return None
    return idx


def region_by_id(region_id: str) -> dict[str, Any] | None:
    """Zwraca region o podanym id (lub None)."""
    for reg in REGIONS:
        if reg["id"] == region_id:
            return reg
    return None


def region_dict(reg: dict[str, Any]) -> dict[str, Any]:
    """Region w formacie przekazywanym do kart (id/name/type/bbox|point)."""
    out: dict[str, Any] = {"id": reg["id"], "name": reg["name"], "type": reg["type"]}
    if reg["type"] == "bbox":
        out["bbox"] = reg["bbox"]
    else:
        out["point"] = reg["point"]
    return out


def extract_regions_all(text: str, limit: int = 4) -> list[dict[str, Any]]:
    """Wszystkie rozne regiony wystepujace w tekscie, w kolejnosci wystapien
    (dluzszy alias wygrywa w ramach jednego regionu; bez duplikatow)."""
    n = _norm(text)
    hits: list[tuple[int, int, dict[str, Any]]] = []
    for reg in REGIONS:
        best: tuple[int, int] | None = None
        for alias in reg["aliases"]:
            a = _norm(alias)
            idx = _find_alias(n, a)
            if idx is not None and (best is None or len(a) > best[0]):
                best = (len(a), idx)
        if best:
            hits.append((best[0], best[1], reg))
    # kolejnosc w tezy (dluzsze aliasy rozwiazywaja kolizje w tym samym miejscu)
    hits.sort(key=lambda h: (h[1], -h[0]))
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for _, _, reg in hits:
        if reg["id"] in seen:
            continue
        seen.add(reg["id"])
        out.append(region_dict(reg))
        if len(out) >= limit:
            break
    return out


def regions_for_llm() -> list[dict[str, Any]]:
    """Kompaktowa lista regionow dla promptu LLM (id, name, type, bbox)."""
    return [
        {
            "id": reg["id"], "name": reg["name"], "type": reg["type"],
            **({"bbox": reg["bbox"]} if reg["type"] == "bbox"
               else {"point": reg["point"]}),
        }
        for reg in REGIONS
    ]
