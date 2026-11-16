"""Budowanie indeksu TF-IDF po katalogu zbiorow NASA.

Indeks zapisywany do data/index.json - dokladnie jak planowano:
  {
    "built_at": ISO timestamp,
    "n_docs": 12,
    "idf": {term: idf},
    "docs": {ds_id: {"terms": {term: waga_tf-idf}, "norm": ||v||, "meta": {...}}}
  }

Wagi liczone na dokumencie zlozonym z: tytul PL/EN, opis PL/EN, slowa kluczowe
PL/EN, hint_terms, nazwy zmiennych, kategoria + id zbioru. Zbudowany wazony:
slowa kluczowe x4, tytul x3, hint_terms x3, opis x1.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import config
from rag import textproc
from rag.catalog import load_catalog

TITLE_WEIGHT = 3.0
KEYWORD_WEIGHT = 4.0
HINT_WEIGHT = 3.0
DESC_WEIGHT = 1.0

# Bump przy zmianie logiki indeksowania/tokenizera - wymusza rebuild index.json
INDEX_VERSION = 6


def _catalog_sha1() -> str:
    """Odcisk katalogu - zmiana keywords/parametrow wymusza rebuild indeksu."""
    import hashlib
    h = hashlib.sha1()
    try:
        for path in config.CATALOG_PATHS:
            if path.exists():
                h.update(path.read_bytes())
    except OSError:
        return ""
    return h.hexdigest()


def _doc_terms(ds: dict[str, Any], ds_id: str) -> Counter[str]:
    """Buduje wazona torbe tokenow dla jednego zbioru."""
    bag: Counter[str] = Counter()

    def add(text: str, weight: float) -> None:
        # dokladne tokeny bez prefiksow: query ma wlasny fallback prefiksu
        # dla slow nieznanych, a podwojne liczenie (t + t[:5]) zalewalo
        # cosine duplikatami tego samego konceptu (tempe+temperature)
        for t in textproc.tokenize(text):
            bag[t] += weight

    add(ds.get("title_pl", ""), TITLE_WEIGHT)
    add(ds.get("title_en", ""), TITLE_WEIGHT)
    add(" ".join(ds.get("keywords_pl", [])), KEYWORD_WEIGHT)
    add(" ".join(ds.get("keywords_en", [])), KEYWORD_WEIGHT)
    # hint_terms NIE wchodza do torby dokumentu: sa metrycznymi etykietami
    # kategorii (PL/EN), uzywanymi tylko do reguly boost w retrieverze.
    # W torbie zalewaly cosine ogolnikowymi trafieniami (temperature/heat...)
    # i zabieraly glos charakterystycznym slowom kluczowym (zimy, fale upalow).
    add(ds.get("description_pl", ""), DESC_WEIGHT)
    add(ds.get("description_en", ""), DESC_WEIGHT)
    add(ds.get("category", ""), HINT_WEIGHT)
    add(ds_id.replace("_", " "), KEYWORD_WEIGHT)
    for var in ds.get("variables", []):
        add(var.get("id", ""), KEYWORD_WEIGHT)
        add(var.get("desc", ""), DESC_WEIGHT)
    return bag


def build_index(force: bool = False) -> dict[str, Any]:
    """Buduje indeks TF-IDF i zapisuje go do index.json."""
    catalog = load_catalog()
    docs_terms = {ds_id: _doc_terms(ds, ds_id) for ds_id, ds in catalog.items()}

    # IDF: ile dokumentow zawiera term (z uwzglednieniem prefiksow)
    df: Counter[str] = Counter()
    for bag in docs_terms.values():
        df.update(bag.keys())
    n_docs = len(docs_terms)
    idf = {t: math.log((n_docs + 1) / (c + 1)) + 1.0 for t, c in df.items()}

    docs: dict[str, dict[str, Any]] = {}
    for ds_id, bag in docs_terms.items():
        tfidf = {t: round(w * idf[t], 5) for t, w in bag.items()}
        norm = math.sqrt(sum(v * v for v in tfidf.values())) or 1.0
        meta = {
            "title": catalog[ds_id].get("title", ""),
            "category": catalog[ds_id].get("category", ""),
            "supports_regions": catalog[ds_id].get("supports_regions", False),
            "unit": catalog[ds_id].get("unit", ""),
        }
        docs[ds_id] = {"terms": tfidf, "norm": round(norm, 5), "meta": meta}

    index = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "n_docs": n_docs,
        "n_terms": len(idf),
        "index_version": INDEX_VERSION,
        "catalog_sha1": _catalog_sha1(),
        "idf": {t: round(v, 5) for t, v in idf.items()},
        "docs": docs,
    }

    config.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.INDEX_PATH, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)
    return index


def _read_index() -> dict[str, Any] | None:
    """Czyta index.json (None gdy brak/uszkodzony)."""
    if not config.INDEX_PATH.exists():
        return None
    try:
        with open(config.INDEX_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return None


def _is_fresh(idx: dict[str, Any] | None) -> bool:
    """Czy indeks odpowiada katalogowi, tokenizatorowi i wersji logiki."""
    return bool(
        idx
        and idx.get("n_docs") == len(load_catalog())
        and idx.get("catalog_sha1") == _catalog_sha1()
        and idx.get("index_version") == INDEX_VERSION
    )


def load_index() -> dict[str, Any]:
    """Wczytuje index.json, automatycznie przebudowujac gdy nie swiezy."""
    idx = _read_index()
    if _is_fresh(idx):
        return idx
    return build_index()


def index_is_fresh() -> bool:
    """Czy indeks odpowiada aktualnej wersji katalogu i tokenizera."""
    return _is_fresh(_read_index())


if __name__ == "__main__":
    idx = build_index()
    print(f"Indeks zapisany: {config.INDEX_PATH}")
    print(f"  dokumenty: {idx['n_docs']}, terminy: {idx['n_terms']}")
