"""Analiza statystyczna serii czasowych: OLS, srednia kroczaca, opis faktow.

Wazna zasada: zadna funkcja nie zwraca werdyktu "prawda/falsz" wobec tezy.
Opisujemy tylko dane (kierunek trendu, roznice srednich, istotnosc).
"""
from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats as sps


def _fmt(val: float, digits: int = 2) -> str:
    """Liczba z kropka dziesietna (teksty po angielsku)."""
    return f"{val:.{digits}f}"


def ols(years: list[int], values: list[float]) -> dict[str, Any] | None:
    """Regresja liniowa (scipy linregress). Slope w jednostce/rok."""
    if len(years) < 3 or len(years) != len(values):
        return None
    x = np.asarray(years, dtype=float)
    y = np.asarray(values, dtype=float)
    res = sps.linregress(x, y)
    return {
        "slope_per_year": float(res.slope),
        "slope_per_decade": float(res.slope * 10),
        "intercept": float(res.intercept),
        "r2": float(res.rvalue ** 2),
        "p_value": float(res.pvalue),
        "stderr": float(res.stderr) if res.stderr is not None else None,
        "n": len(years),
        "total_change": float(res.slope * (years[-1] - years[0])),
    }


def trend_line(years: list[int], slope: float, intercept: float) -> list[dict[str, Any]]:
    """Punkty linii trendu OLS (koncowe, do rysowania)."""
    if not years:
        return []
    return [{"year": years[0],
             "value": round(slope * years[0] + intercept, 4)},
            {"year": years[-1],
             "value": round(slope * years[-1] + intercept, 4)}]


def rolling_mean(values: list[float], window: int = 5) -> list[float | None]:
    """Srednia kroczaca z kurczacym sie oknem na brzegach."""
    out: list[float | None] = []
    n = len(values)
    for i in range(n):
        lo = max(0, i - window + 1)
        chunk = values[lo:i + 1]
        out.append(round(sum(chunk) / len(chunk), 4))
    return out


def describe_trend(stats: dict[str, Any]) -> str:
    """Opis kierunku trendu DANYCH (nie werdykt wobec tezy)."""
    slope = stats["slope_per_decade"]
    p = stats["p_value"]
    significant = p < 0.05
    if abs(slope) < 1e-6:
        return "the data show a flat trend (no systematic direction)"
    direction = "rising" if slope > 0 else "falling"
    if significant:
        return (f"direction of change in the data: {direction} "
                f"(statistically significant at the 0.05 level)")
    return (f"direction of change in the data: {direction}, "
            f"but the trend is not statistically significant at the 0.05 level")


def fmt_p(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {_fmt(p, 3)}"


def window_stats(values: list[float]) -> dict[str, Any] | None:
    """Statystyki opisowe okna danych."""
    if not values:
        return None
    arr = np.asarray(values, dtype=float)
    return {
        "min": float(arr.min()), "max": float(arr.max()),
        "mean": float(arr.mean()),
    }
