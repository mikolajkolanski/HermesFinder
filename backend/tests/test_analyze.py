"""Pelny przebieg analyze() bez sieci: atrapa danych + atrapa odpowiedzi modelu.

Sprawdza scenariusze z produkcji:
  * porownanie dwoch miejsc ("Chiny emituja wiecej CO2 niz Europa"),
  * wiele miejsc naraz ("temperatura w Polsce vs w 5 sasiadach") + mapa kilku krajow,
  * teza zlozona -> kilka kart (OZE i wegiel),
  * czesc tezy bez danych -> komunikat "missing" od modelu,
  * teza bez sensu -> brak kart, no_data.
Uruchom: cd backend && python -m pytest tests -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from analysis import pipeline  # noqa: E402
from nasa import power  # noqa: E402
from rag import llm  # noqa: E402


def _fake_series(ds, region, window, months, force):
    rid = (region or {}).get("id") or "world"
    base = sum(ord(c) for c in rid + ds["connector"]) % 50 + 10
    pts = [{"year": y, "value": round(base + 0.1 * (y - window[0]), 3)}
           for y in range(max(window[0], 1990), window[1] + 1)]
    return {"points": pts, "method_note": "fake", "months_ignored": False}


def _fake_grid(parameter, start, end, bbox, months=None, force=False):
    lats = [bbox[1] - i * 0.5 for i in range(int((bbox[1] - bbox[0]) / 0.5) + 1)]
    lons = [bbox[2] + j * 0.625 for j in range(int((bbox[3] - bbox[2]) / 0.625) + 1)]
    years = list(range(max(start, 1981), end + 1))
    frames = [[round(10 - 0.3 * la + 0.02 * (y - 2000), 2) for la in lats for _ in lons] for y in years]
    return {"lats": lats, "lons": lons, "years": years, "frames": frames,
            "annual": [{"year": y, "value": 1.0 + y / 1000} for y in years],
            "method": "area_mean", "n_points": len(lats) * len(lons), "step": [0.5, 0.625],
            "bbox_used": bbox, "parameter": parameter}


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(pipeline, "_series_for", _fake_series)
    monkeypatch.setattr(power, "fetch_regional_grid", _fake_grid)
    monkeypatch.setattr(pipeline.nasa_power, "fetch_regional_grid", _fake_grid)
    # compare.py korzysta z pipeline._series_for przez leniwy import
    return monkeypatch


def _with_llm(monkeypatch, answer: dict):
    monkeypatch.setattr(llm, "llm_info", lambda: {"provider": "gemini", "model": "fake", "available": True})
    monkeypatch.setattr(llm, "_call_gemini", lambda prompt: json.dumps(answer))


def _good(res):
    return [c for c in res["cards"] if not c.get("error")]


def test_two_places_compare_sources_becomes_one_chart(env):
    _with_llm(env, {"summary": "CO2 emissions of China and Europe.", "queries": [{
        "dataset_id": "owid_co2_emissions", "dataset_ids": ["owid_co2_emissions", "owid_ghg_total"],
        "region_ids": ["china", "europe"], "start_year": 1990, "end_year": 2024,
        "chart_type": "compare_sources", "title": "CO2 emissions: China vs Europe"}]})
    res = pipeline.analyze("Chiny emitują więcej CO2 do atmosfery niż Europa")
    cards = _good(res)
    assert len(cards) == 1
    c = cards[0]
    assert c["type"] == "multi_line" and [s["label"] for s in c["series"]] == ["China", "Europe"]
    assert any("last year with data for all" in f for f in c["facts"])
    assert any("×" in f for f in c["facts"])  # iloraz najwiekszy / najmniejszy


def test_many_places_and_multi_country_heatmap(env):
    regs = ["poland", "germany", "czechia", "slovakia", "ukraine", "lithuania"]
    _with_llm(env, {"queries": [
        {"dataset_id": "power_t2m", "region_ids": regs, "start_year": 2000, "end_year": 2024,
         "chart_type": "multi_line", "title": "Air temperature: Poland and 5 neighbours"},
        {"dataset_id": "power_t2m", "region_ids": regs, "start_year": 2000, "end_year": 2024,
         "chart_type": "region_bars"},
        {"dataset_id": "openmeteo_era5_t2m", "region_ids": regs, "start_year": 2000, "end_year": 2024,
         "chart_type": "heatmap"},
    ]})
    res = pipeline.analyze("temperatura w polsce vs w 5 jej sąsiadach")
    cards = _good(res)
    types = [c["type"] for c in cards]
    assert types == ["multi_line", "bars", "heatmap"], types
    assert len(cards[0]["series"]) == 6
    assert len(cards[1]["values"]) == 6 and cards[1]["region_bars"]
    hm = cards[2]
    assert hm["dataset_id"] == "power_t2m"  # mapa zawsze z siatki POWER
    assert len(hm["regions"]) == 6 and hm["regions"][0]["iso_n"] == ["616"]
    assert hm["bbox"][0] <= 44.3 and hm["bbox"][3] >= 40.2  # obwiednia wszystkich krajow
    assert len(hm["grid"]["frames"]) == len(hm["grid"]["years"])


def test_compound_claim_gets_every_part(env):
    _with_llm(env, {"queries": [
        {"dataset_id": "owid_elec_renewables", "region_ids": ["germany", "poland"],
         "start_year": 2000, "end_year": 2024, "chart_type": "multi_line"},
        {"dataset_id": "owid_elec_coal", "region_ids": ["germany", "poland"],
         "start_year": 2000, "end_year": 2024, "chart_type": "multi_line"},
        {"chart_type": "multi_series", "dataset_id": "owid_elec_coal", "start_year": 2000, "end_year": 2024,
         "series": [{"dataset_id": "owid_elec_coal", "region_id": "poland"},
                    {"dataset_id": "owid_elec_renewables", "region_id": "poland"}]},
    ]})
    res = pipeline.analyze("Niemcy produkują więcej prądu z OZE niż Polska, "
                           "ale mniej prądu z elektrowni węglowych")
    cards = _good(res)
    assert [c["topic"] for c in cards] == ["electricity_renewables", "electricity_coal", "electricity_coal"]
    assert len(cards[2]["series"]) == 2  # dwie wielkosci dla Polski na jednym wykresie


def test_partial_missing_data_message(env):
    msg = "Brak danych dla emisji CO₂ z hodowli krów — katalog nie zawiera emisji z rolnictwa."
    _with_llm(env, {"queries": [
        {"dataset_id": "owid_co2_emissions", "region_ids": ["china"], "start_year": 1990,
         "end_year": 2024, "chart_type": "line"}],
        "missing": [{"subject": "CO2 from cows", "message": msg}]})
    res = pipeline.analyze("porównanie produkcji co2 przez chiny i krowy", {"language": "pl"})
    assert _good(res) and res["missing"][0]["message"] == msg
    assert res["no_data"] is False


def test_nonsense_with_llm_no_data(env):
    _with_llm(env, {"queries": [], "no_data": True,
                    "missing": [{"subject": "", "message": "Brak dostępnych danych dla tej tezy."}]})
    res = pipeline.analyze("asdkjh qwe zxc lorem ipsum")
    assert res["cards"] == [] and res["no_data"] is True
    assert res["missing"]


def test_nonsense_without_llm_no_data(env):
    res = pipeline.analyze("asdkjh qwe zxc lorem ipsum", {"disable_llm": True})
    assert res["cards"] == [] and res["no_data"] is True


def test_llm_prompt_mentions_language(env):
    p = llm._build_prompt("test", {"regions": []}, None, "pl")
    assert json.loads(p)["message_language"] == "Polish"
    assert "region_bars" in llm.SYSTEM_PROMPT and "missing" in llm.SYSTEM_PROMPT
