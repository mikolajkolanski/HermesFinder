"""Cache dyskowy JSON dla danych z API NASA.

Klucz -> sha1 -> data/cache/<hash>.json  {"cached_at": ts, "payload": {...}}.
TTL domyslnie 7 dni; force_refresh pomija cache i odswieza.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Any, Callable

import config


def _path(key: str):
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return config.CACHE_DIR / f"{h}.json"


def get_or_fetch(key: str, fetch_fn: Callable[[], Any],
                 ttl_days: float | None = None,
                 force: bool = False) -> Any:
    """Zwraca dane z cache lub pobiera przez fetch_fn() i cache'uje."""
    ttl = (ttl_days if ttl_days is not None else config.CACHE_TTL_DAYS) * 86400
    path = _path(key)
    if not force and path.exists():
        try:
            with open(path, encoding="utf-8") as fh:
                blob = json.load(fh)
            if time.time() - blob.get("cached_at", 0) < ttl:
                return blob["payload"]
        except Exception:  # noqa: BLE001 - uszkodzony cache = pobierz ponownie
            pass
    payload = fetch_fn()
    # zapis atomowy: karty licza sie rownolegle, czytelnik nie moze trafic na
    # w polowie zapisany plik
    tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"cached_at": time.time(), "payload": payload}, fh,
                  ensure_ascii=False)
    os.replace(tmp, path)
    return payload


def cached_at(key: str) -> float | None:
    """Timestamp zapisu cache dla klucza (None gdy brak)."""
    path = _path(key)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("cached_at")
    except Exception:  # noqa: BLE001
        return None
