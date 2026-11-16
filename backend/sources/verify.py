"""Weryfikacja wszystkich zbiorow z katalogu (dostepnosc + poprawnosc danych).

Uruchomienie (z katalogu backend/):
    python -m sources.verify            # raport w konsoli + data/verification_report.json
    python -m sources.verify --force    # z pominieciem cache (swieze pobranie)

Testy na zbior:
  * dostepnosc: zrodlo odpowiada i parser zwraca dane,
  * liczba punktow >= sanity.min_points,
  * lata rosnace, bez duplikatow, wartosci skonczone,
  * wartosci w fizycznie wiarygodnym zakresie (sanity.min/max),
  * aktualnosc: ostatni rok nie starszy niz 2 lata (chyba ze katalog deklaruje
    koniec pokrycia),
Testy krzyzowe w ramach tematu (ten sam "topic", rozni dostawcy):
  * po sprowadzeniu do wspolnej linii odniesienia: korelacja Pearsona i RMSE
    dla wspolnych lat - niezalezne zrodla tego samego zjawiska musza sie
    zgadzac (inaczej blad parsera, zla kolumna, zla jednostka).
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import math
import sys
from typing import Any

import config
from analysis import compare
from rag.catalog import load_catalog
from regions import region_by_id, region_dict
from sources import registry

# temat -> (min. korelacja, maks. RMSE) dla testu zgodnosci miedzy zrodlami
CROSS_THRESHOLDS: dict[str, tuple[float, float]] = {
    "global_temperature": (0.95, 0.12),
    "ocean_temperature": (0.90, 0.15),
    "sea_level": (0.95, 8.0),
    "co2": (0.99, 2.5),
    "regional_temperature": (0.90, 0.45),
    "regional_precipitation": (0.60, 0.5),
    "mars_max_temp": (0.60, 15.0),
    "mars_min_temp": (0.60, 15.0),
    "mars_pressure": (0.80, 60.0),
}
# tematy, w ktorych zrodla mierza rozne zakresy (CO2 vs wszystkie GHG) albo
# rozne miejsca (mareografy) - korelacja tylko informacyjnie
INFO_ONLY_TOPICS = {"emissions", "tide_gauge_sea_level"}
TEST_REGION = "poland"
# --mcd: czekaj na model MCD (wolny serwer, do kilkunastu minut)
BLOCKING_MCD = "--mcd" in sys.argv


def _region_for(ds: dict[str, Any]) -> dict[str, Any] | None:
    if ds.get("region_scope") in ("any", "country", "eu", "country_or_world") \
            or ds.get("supports_regions"):
        return region_dict(region_by_id(TEST_REGION))
    return None


def _load(ds_id: str, ds: dict[str, Any], force: bool) -> dict[str, Any]:
    from analysis import pipeline as pl
    kind = ds.get("series_kind", "annual")
    if kind == "planet_metric":
        vals = registry.planet_values(ds, None, force)
        return {"kind": kind, "points": [{"year": i, "value": v["value"]}
                                         for i, v in enumerate(vals)],
                "labels": [v["name"] for v in vals]}
    if kind == "seasonal_ls":
        r = registry.seasonal_series(ds, force, blocking=BLOCKING_MCD)
        return {"kind": kind, "points": r["points"],
                "mars_years": r.get("mars_years")}
    region = _region_for(ds)
    cur = dt.date.today().year
    window = pl._clamp_window(ds, 1700, cur)
    r = pl._series_for(ds, region, window, None, force)
    return {"kind": kind, "points": r["points"], "region": region["name"] if region else None,
            "note": r["method_note"]}


def _check(ds_id: str, ds: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
    san = ds.get("sanity") or {}
    pts = data["points"]
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, level: str = "error") -> None:
        checks.append({"check": name, "ok": ok, "detail": detail,
                       "level": "ok" if ok else level})

    n_min = int(san.get("min_points", 10))
    add("number of points", len(pts) >= n_min, f"{len(pts)} (min. {n_min})")
    vals = [p["value"] for p in pts]
    add("finite values", all(isinstance(v, (int, float)) and math.isfinite(v)
                                  for v in vals), "no NaN/inf")
    xs = [p["year"] for p in pts]
    add("increasing axis, no duplicates", all(b > a for a, b in zip(xs, xs[1:])),
        f"{xs[0]}–{xs[-1]}" if xs else "empty")
    if vals and ("min" in san or "max" in san):
        lo, hi = san.get("min", -math.inf), san.get("max", math.inf)
        bad = [p for p in pts if not lo <= p["value"] <= hi]
        add("plausible range", not bad,
            f"min {min(vals):.3g}, max {max(vals):.3g} (allowed {lo}…{hi})"
            + (f"; out of range: {[(b['year'], b['value']) for b in bad[:3]]}" if bad else ""))
    if data["kind"] == "annual" and xs:
        cur = dt.date.today().year
        end = (ds.get("coverage") or {}).get("end")
        need = (int(end) - 1) if end else cur - 2
        add("up to date", xs[-1] >= need,
            f"last year {xs[-1]} (required ≥ {need})", level="warning")
        missing = (xs[-1] - xs[0] + 1) - len(set(xs))
        add("continuity", missing <= max(2, 0.05 * len(xs)),
            f"missing years: {missing}", level="warning")
    return checks


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    sa = math.sqrt(sum((x - ma) ** 2 for x in a))
    sb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if sa == 0 or sb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def _cross(topic: str, members: dict[str, dict[str, Any]], cat: dict[str, Any]
           ) -> dict[str, Any]:
    seasonal = all(m["kind"] == "seasonal_ls" for m in members.values())
    series = {i: {p["year"]: p["value"] for p in m["points"]} for i, m in members.items()}
    baseline = None
    if not seasonal:
        kinds = {cat[i].get("kind") for i in members}
        if "anomaly" in kinds or topic in ("regional_temperature",):
            years = {i: set(s) for i, s in series.items()}
            baseline, _ = compare.choose_baseline(
                years, compare.TOPIC_BASELINE.get(topic, compare.DEFAULT_BASELINE))
            if baseline:
                for i, s in series.items():
                    off = registry.rebase_offset(
                        [{"year": y, "value": v} for y, v in s.items()], baseline)
                    if off is not None:
                        series[i] = {y: v - off for y, v in s.items()}
    ref = next(iter(series))
    thr = CROSS_THRESHOLDS.get(topic)
    pairs = []
    for other in list(series)[1:]:
        common = sorted(set(series[ref]) & set(series[other]))
        a = [series[ref][y] for y in common]
        b = [series[other][y] for y in common]
        r = _pearson(a, b)
        rmse = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)) if a else None
        ok = None
        if thr and r is not None and topic not in INFO_ONLY_TOPICS and len(common) >= 10:
            ok = r >= thr[0] and rmse <= thr[1]
        pairs.append({"a": ref, "b": other, "n_common": len(common),
                      "r": round(r, 3) if r is not None else None,
                      "rmse": round(rmse, 3) if rmse is not None else None,
                      "ok": ok})
    return {"topic": topic, "baseline": list(baseline) if baseline else None,
            "threshold": thr, "info_only": topic in INFO_ONLY_TOPICS, "pairs": pairs}


def run(force: bool = False) -> dict[str, Any]:
    cat = load_catalog()
    results: dict[str, dict[str, Any]] = {}

    def job(item: tuple[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        ds_id, ds = item
        try:
            data = _load(ds_id, ds, force)
        except Exception as exc:  # noqa: BLE001
            return ds_id, {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                           "checks": [], "data": None}
        checks = _check(ds_id, ds, data)
        return ds_id, {"ok": all(c["level"] != "error" for c in checks),
                       "warnings": [c for c in checks if c["level"] == "warning"],
                       "checks": checks, "data": data}

    # Open-Meteo ma limit minutowy - jego zbiory sekwencyjnie, reszta rownolegle
    om = [(k, v) for k, v in cat.items() if v["connector"] == "open_meteo"]
    rest = [(k, v) for k, v in cat.items() if v["connector"] != "open_meteo"]
    with cf.ThreadPoolExecutor(8) as ex:
        for ds_id, res in ex.map(job, rest):
            results[ds_id] = res
    for item in om:
        ds_id, res = job(item)
        results[ds_id] = res

    by_topic: dict[str, dict[str, dict[str, Any]]] = {}
    for ds_id, res in results.items():
        if res.get("data") and res["ok"] and cat[ds_id].get("series_kind") != "planet_metric":
            by_topic.setdefault(cat[ds_id].get("topic") or ds_id, {})[ds_id] = res["data"]
    cross = [_cross(t, m, cat) for t, m in by_topic.items() if len(m) >= 2]

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_datasets": len(cat),
        "n_ok": sum(1 for r in results.values() if r["ok"]),
        "datasets": {
            k: {"ok": r["ok"], "error": r.get("error"),
                "provider": (cat[k].get("provider") or {}).get("org"),
                "title": cat[k]["title"],
                "n_points": len(r["data"]["points"]) if r.get("data") else 0,
                "range": ([r["data"]["points"][0]["year"], r["data"]["points"][-1]["year"]]
                          if r.get("data") and r["data"]["points"] else None),
                "test_region": (r.get("data") or {}).get("region"),
                "checks": r["checks"]}
            for k, r in results.items()},
        "cross_checks": cross,
    }
    out = config.DATA_DIR / "verification_report.json"
    try:
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        out = config.CACHE_DIR / "verification_report.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    report["_path"] = str(out)
    return report


def load_report() -> dict[str, Any] | None:
    for p in (config.DATA_DIR / "verification_report.json",
              config.CACHE_DIR / "verification_report.json"):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return None
    return None


def _print(report: dict[str, Any]) -> None:
    print(f"\nDatasets: {report['n_ok']}/{report['n_datasets']} OK\n")
    for k, d in report["datasets"].items():
        mark = "OK  " if d["ok"] else "FAIL"
        warn = [c for c in d["checks"] if c["level"] == "warning"]
        rng = f"{d['range'][0]}–{d['range'][1]}" if d["range"] else ""
        extra = d["error"] or "; ".join(f"{c['check']}: {c['detail']}" for c in d["checks"]
                                        if c["level"] == "error")
        print(f"{mark} {k:28} n={d['n_points']:<4} {rng:11} {d['provider'] or '':38.38} {extra}")
        for c in warn:
            print(f"       ⚠ {c['check']}: {c['detail']}")
    print("\nAgreement between sources (same topic):")
    for c in report["cross_checks"]:
        base = f"baseline {c['baseline'][0]}–{c['baseline'][1]}" if c["baseline"] else "no rebase"
        print(f"  {c['topic']} ({base}{', for information' if c['info_only'] else ''})")
        for p in c["pairs"]:
            st = {True: "OK  ", False: "FAIL", None: "info"}[p["ok"]]
            print(f"    {st} {p['a']} vs {p['b']}: r={p['r']} RMSE={p['rmse']} (n={p['n_common']})")


if __name__ == "__main__":
    rep = run(force="--force" in sys.argv)
    _print(rep)
    print(f"\nReport: {rep['_path']}")
    failed = [k for k, d in rep["datasets"].items() if not d["ok"]] + \
        [f"{c['topic']}:{p['b']}" for c in rep["cross_checks"] for p in c["pairs"] if p["ok"] is False]
    sys.exit(1 if failed else 0)
