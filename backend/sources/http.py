"""Wspolne helpery HTTP dla zewnetrznych zrodel (poza NASA)."""
from __future__ import annotations

import time
from typing import Any

import httpx

import config


def get(url: str, *, params: dict[str, Any] | None = None,
        timeout: float | None = None, retries: int = 2) -> httpx.Response:
    """GET z ponawianiem (5xx / sieć) i User-Agentem aplikacji."""
    last: Exception | None = None
    for attempt in range(retries + 2):
        try:
            resp = httpx.get(url, params=params,
                             timeout=timeout or config.HTTP_TIMEOUT,
                             headers={"User-Agent": config.USER_AGENT},
                             follow_redirects=True)
            if resp.status_code == 429 and attempt == 0 and \
                    "minut" in resp.text.lower():
                # limit minutowy: jedna proba po odczekaniu; godzinowy/dobowy
                # -> natychmiast blad (zrodlo zostanie pominiete z powodem)
                wait = float(resp.headers.get("retry-after") or 30)
                time.sleep(min(wait + 2, 65))
                continue
            if resp.status_code >= 500 and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last = exc
            if isinstance(exc, httpx.HTTPStatusError) and \
                    exc.response.status_code < 500:
                raise
            time.sleep(1.5 * (attempt + 1))
    assert last is not None
    raise last


def get_text(url: str, **kw: Any) -> str:
    return get(url, **kw).text


def get_json(url: str, **kw: Any) -> Any:
    return get(url, **kw).json()


def to_float(raw: str) -> float | None:
    """'+0.34' / '-.18' / 'NaN' / '***' -> float albo None."""
    raw = raw.strip()
    if raw in ("", "NaN", "nan", "NA", "***", "****", "--", "-999", "-99999"):
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    return v if v == v else None


def annual_mean(rows: list[tuple[int, float]], min_count: int = 1
                ) -> list[dict[str, Any]]:
    """[(rok, wartosc), ...] -> srednie roczne (z minimalna liczba probek)."""
    by_year: dict[int, list[float]] = {}
    for y, v in rows:
        by_year.setdefault(y, []).append(v)
    return [{"year": y, "value": round(sum(vs) / len(vs), 4)}
            for y, vs in sorted(by_year.items()) if len(vs) >= min_count]
