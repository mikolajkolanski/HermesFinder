"""Przetwarzanie tekstu: normalizacja, tokenizacja, synonimy PL/EN."""
from __future__ import annotations

import re
import unicodedata

# Mapa synonimow: rozszerza wektor zapytania o pojecia z katalogu.
# Klucz = normalizowany "chwytak" z tezy; wartosc = dodatkowe tokeny.
SYNONYMS: dict[str, list[str]] = {
    "ocieplenie": ["temperature", "warming", "t2m", "heat"],
    "ocieplenia": ["temperature", "warming", "t2m", "heat"],
    "ociepilo": ["temperature", "warming", "t2m", "heat"],
    "cieplejsze": ["temperature", "warming", "heat"],
    "cieplej": ["temperature", "warming", "heat"],
    "cieplejszy": ["temperature", "warming", "heat"],
    "cieplejsza": ["temperature", "warming", "heat"],
    "grzeje": ["temperature", "warming", "heat"],
    "grzalo": ["temperature", "warming", "heat"],
    "upaly": ["temperature", "heat", "maximum"],
    "upalow": ["temperature", "heat", "maximum"],
    "upał": ["temperature", "heat", "maximum"],
    "rekordy": ["temperature", "warming", "anomaly"],
    "mrozy": ["minimum", "frost", "cold", "temperature"],
    "mrozow": ["minimum", "frost", "cold", "temperature"],
    "mroz": ["minimum", "frost", "cold"],
    "przymrozki": ["minimum", "frost", "cold"],
    "zimy": ["minimum", "cold", "temperature"],
    "zimowe": ["minimum", "cold", "temperature"],
    "chlodne": ["minimum", "cold", "temperature"],
    "chlodniesz": ["minimum", "cold"],
    "ochlodzenie": ["minimum", "cold", "temperature"],
    "deszcze": ["precipitation", "rain", "prectotcorr"],
    "deszczowe": ["precipitation", "rain"],
    "opadow": ["precipitation", "rain"],
    "opady": ["precipitation", "rain"],
    "susza": ["precipitation", "drought", "rain"],
    "susze": ["precipitation", "drought", "rain"],
    "susz": ["precipitation", "drought", "rain"],
    "powodz": ["precipitation", "flood", "rain"],
    "powodzie": ["precipitation", "flood", "rain"],
    "snieg": ["precipitation", "snow", "ice"],
    "sniegu": ["precipitation", "snow", "ice"],
    "wilgotnosc": ["humidity", "moisture"],
    "wilgotnosci": ["humidity", "moisture"],
    "wiatr": ["wind", "ws2m"],
    "wiatru": ["wind", "ws2m"],
    "wiatrowe": ["wind"],
    "wichury": ["wind"],
    "slonce": ["radiation", "sunlight", "solar"],
    "slonca": ["radiation", "sunlight", "solar"],
    "naslonecznienie": ["radiation", "sunlight", "solar"],
    "naslonecznien": ["radiation", "sunlight", "solar"],
    "zachmurzenie": ["radiation", "cloudiness"],
    "promieniowanie": ["radiation", "solar"],
    "promieniowania": ["radiation", "solar"],
    "fotowoltaika": ["radiation", "solar", "sunlight"],
    "co2": ["co2", "carbon", "dioxide", "greenhouse", "ppm", "mauna"],
    "dwutlenek": ["co2", "carbon", "dioxide"],
    "dwutlenku": ["co2", "carbon", "dioxide"],
    "wegla": ["co2", "carbon", "dioxide"],
    "emisje": ["co2", "emissions", "greenhouse"],
    "emisji": ["co2", "emissions", "greenhouse"],
    "cieplarniane": ["co2", "greenhouse", "carbon"],
    "cieplarnianych": ["co2", "greenhouse", "carbon"],
    "poziom": ["sea", "level"],
    "poziomu": ["sea", "level"],
    "morza": ["sea", "level", "ocean"],
    "oceanow": ["sea", "level", "ocean"],
    "podnoszenie": ["sea", "level", "rise"],
    "lody": ["ice", "sea", "arctic"],
    "lodowce": ["ice", "arctic", "sea"],
    "lodow": ["ice", "arctic"],
    "arktyki": ["arctic", "ice", "sea"],
    "arktyczny": ["arctic", "ice", "sea"],
    "arktyczne": ["arctic", "ice"],
    "arktycznego": ["arctic", "ice", "sea"],
    "topnienie": ["ice", "sea", "arctic"],
    "topnienia": ["ice", "sea", "arctic"],
    "topi": ["ice", "arctic", "sea"],
    "biegun": ["arctic", "ice", "polar"],
    "biegunow": ["arctic", "ice", "polar"],
    "grenlandia": ["ice", "arctic"],
    "grenlandii": ["ice", "arctic"],
    "antarktyda": ["ice", "antarctica"],
    "antarktydzie": ["ice", "antarctica"],
    "anomalia": ["anomaly", "global"],
    "anomalie": ["anomaly", "global"],
    "globalne": ["global", "temperature"],
    "globalnego": ["global", "temperature"],
    "globalny": ["global", "temperature"],
    "swiecie": ["global"],
    "swiat": ["global"],
    "planecie": ["global"],
    "polkula": ["nh", "hemisphere"],
    "polkuli": ["nh", "hemisphere"],
    "polnocna": ["nh", "hemisphere"],
    "polkuli polnocnej": ["nh", "hemisphere"],
}


# znaki bez dekompozycji NFD (np. polskie "l") oraz indeksy dolne (CO₂, CH₄)
TRANSLIT = str.maketrans({
    "ł": "l", "ø": "o", "đ": "d", "ð": "d", "å": "a", "æ": "ae", "ß": "ss",
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5",
    "₆": "6", "₇": "7", "₈": "8", "₉": "9",
})


def strip_diacritics(text: str) -> str:
    """Zamienia znaki z diakrytykami na ascii (ą->a, ż->z, ł->l, CO₂->CO2)."""
    nfd = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    return text.translate(TRANSLIT)


def normalize(text: str) -> str:
    """Male litery + bez diakrytykow + pojedyncze spacje."""
    text = strip_diacritics(text.lower())
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def tokenize(text: str) -> list[str]:
    """Tokeny unigramowe z normalizowanego tekstu."""
    return TOKEN_RE.findall(normalize(text))


def prefix_tokens(tokens: list[str], n: int = 5) -> list[str]:
    """Prefiksy dlugosci n - luzny stemmer PL/EN (temperaturze -> tempe)."""
    return [t[:n] for t in tokens if len(t) >= n + 1]


def expand_query_tokens(tokens: list[str]) -> list[str]:
    """Dodaje tokeny z mapy synonimow dla slow wystepujacych w tezie."""
    n = normalize(" ".join(tokens))
    extra: list[str] = []
    for key, additions in SYNONYMS.items():
        k = normalize(key)
        if not k:
            continue
        # dopasowanie slowa lub prefiksu (odmiany: suszy -> susz)
        if re.search(rf"(?:^|\s){re.escape(k)}", n) or any(t.startswith(k[:4]) and k[:4] and len(k) >= 4 for t in tokens):
            extra.extend(additions)
    return extra
