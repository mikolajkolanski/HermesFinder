# Tezy klimatyczne z polskich mediów — korpus testowy

Tezy zebrane z popularnych polskich mediów i portali informacyjnych
(IMGW-PIB — „KLIMAT POLSKI"/raporty suszowe, Nauka w Polsce — PAN,
Klimada 2.0, Deutsche Welle PL, portale pogodowe i prasowe). Dla każdej tezy:
**oczekiwany wykres** (typ karty), zbiór NASA i parametry. Te same tezy są
automatycznym testem plannera (`scripts/test_theses.py`) — każda po
wklejeniu w aplikację ma wygenerować dokładnie ten zestaw kart.

## 1. Temperatury i rekordy

| # | Teza (wklej do aplikacji) | Źródło | Oczekiwane wykresy |
| --- | --- | --- | --- |
| 1 | Średnia roczna temperatura w Polsce stale rośnie | IMGW: KLIMAT POLSKI 2024 (2024 najcieplejszy, 10,7°C) | line · POWER T2M · Polska |
| 2 | Temperatura w Polsce rośnie od lat 70. | IMGW/naukawpolsce: rekordy po latach ocieplenia | line · POWER T2M · Polska, okno od 1970 |
| 3 | Globalna anomalia temperatury rośnie od 1880 roku | naukawpolsce: anomalia 2024 vs era przedprzemysłowa | line · GISTEMP global, od 1880 |
| 4 | Półkula północna ociepla się szybciej niż reszta świata | GISTEMP (porównanie półkul) | 2 karty line · GISTEMP global + północna |
| 5 | Temperatura wzrosła od czasów rewolucji przemysłowej | naukawpolsce/DW: era przedprzemysłowa | line · GISTEMP global, od 1880 |
| 22 | Temperatura w Alpach rośnie szybciej niż globalna | media o lodowcach alpejskich | line · POWER T2M · Alpy |

## 2. Lody, morza, CO₂

| # | Teza | Źródło | Oczekiwane wykresy |
| --- | --- | --- | --- |
| 6 | Poziom morza podnosi się w wyniku topnienia lądolodów Grenlandii | DW/naukawpolsce: 11 bln ton lodu od lat 70. | line · poziom morza (altymetria) |
| 7 | Zasięg lodu morskiego w Arktyce maleje we wrześniu | relacje z sezonu roztopów | line · NSIDC lód arktyczny (IX) |
| 8 | Poziom oceanów rośnie coraz szybciej: 1993-2003 oraz 2015-2025 | media: „rośnie 2× szybciej niż w ubiegłym wieku" | period_compare · poziom morza, 2 okresy |
| 9 | Stężenie dwutlenku węgla w atmosferze pobiło wszelkie rekordy | media: rekordowe CO₂ | line · Mauna Loa CO₂ |
| 10 | Wraz ze wzrostem CO₂ rośnie globalna temperatura | media klimatyczne (korelacja) | 2 karty line · CO₂ + GISTEMP global |

## 3. Polska lokalnie — opady, upały, zimy, wiatr

| # | Teza | Źródło | Oczekiwane wykresy |
| --- | --- | --- | --- |
| 11 | Wielka susza w Polsce — opady atmosferyczne maleją | IMGW: „Wielka susza nie ustępuje" | line · POWER opady · Polska |
| 12 | Fale upałów stają się częstsze: latem w Polsce coraz cieplejsze dni | media: „Fale upałów coraz częstsze" | line · POWER T2M max · Polska, lato |
| 13 | Miejskie wyspy ciepła: Warszawa jest cieplejsza niż okolice Mazowsza | media: „Miejskie wyspy ciepła na mapie" | multi_line · POWER T2M · Warszawa + Mazowsze |
| 14 | Zimy w Polsce stają się cieplejsze | Klimada 2.0: „Jak zmienia się zima?" | line · POWER T2M (lub T2M min) · Polska, zima |
| 15 | Dni ze śniegiem ubywa — zimowe opady w Polsce coraz rzadsze | media: „Liczba dni ze śniegiem spada" | line · POWER opady · Polska, zima |
| 16 | Ciepły marzec w Polsce: wiosna zaczyna się coraz wcześniej | media: „Polacy dostrzegają zmiany, ciepły marzec" | line · POWER T2M · Polska, marzec |
| 17 | Wichury i silny wiatr stają się częstsze w Polsce | media: „Ekstremalne zjawiska staną się normą?" | line · POWER wiatr · Polska |
| 18 | Bałtyk się ociepla | Rzeczpospolita i inne: „Bałtyk cierpi" | line · POWER T2M · Morze Bałtyckie |
| 19 | Nasłonecznienie w Polsce rośnie — dobrodziejstwo dla fotowoltaiki | branżowe: fotowoltaika a nasłonecznienie | line · POWER promieniowanie · Polska |
| 25 | Rekordowy styczeń: zimowe miesiące w Polsce cieplejsze | media: styczeń rekordowy pod względem temperatury | line · POWER T2M · Polska, styczeń |

## 4. Porównania okresów, regionów i przestrzeń

| # | Teza | Źródło | Oczekiwane wykresy |
| --- | --- | --- | --- |
| 20 | Jak zmieniła się średnia temperatura w Polsce: 1961-1990 oraz 1991-2020 | IMGW: normy klimatologiczne | period_compare · POWER T2M · Polska, 2 okresy |
| 21 | Różnica temperatur między Niemcami a Polską | media porównujące kraje | difference · POWER T2M · DE − PL |
| 23 | Rozkład przestrzenny temperatury na Mazowszu | media: mapa ciepła miasta/regionu | line + heatmap · POWER T2M · Mazowsze |
| 24 | Deszcze w Amazonii stają się nieregularne — opady maleją | media o Amazonii i suszach | line · POWER opady · Amazonia |

## Zasady „wszystkie potrzebne, ale nie za dużo"

- maksymalnie **4 karty** na tezę (limit `MAX_CARDS`; zwykle 1–3),
- jedna teza = jeden główny zbiór (karta pierwsza) + ewentualnie kontekst
  (drugi zbiór) lub mapa cieplna dla regionów bbox,
- tezy okresowe → jedna karta `period_compare` zamiast wielu liniowych,
- LLM (Gemini/OpenAI/OpenRouter) planuje tak samo, ale zawsze walidowany —
  fallback bez klucza daje identyczne typy kart dzięki powyższym regułom.
