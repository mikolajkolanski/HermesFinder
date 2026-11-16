"""Retriever: dobór top-k zbiorów NASA do tezy (TF-IDF + reguły).

Scoring = cosine(query, doc) + boosty regułowe:
  +0.35 zbiór wspiera regiony, a teza wskazuje konkretny region
  +0.20 zbiór globalny, a teza ma zakres globalny
  +0.25 zbior pokrywa kategorie z metric_hints (dopasowanie hint_terms)
  -0.30 teza wskazuje region, a zbior jest wylacznie globalny i w katalogu
        jest sensowna alternatywa regionalna (stosowane tylko przy remisie)
"""
from __future__ import annotations

import math
from typing import Any

import config
from rag import textproc
from rag.catalog import load_catalog
from rag.indexer import load_index


def _query_vector(thesis: str) -> dict[str, float]:
    """Zapytanie = dokladne tokeny (PL/EN). Nieznane slowa dostaja domyslny
    idf (nic nie trafiaja, ale rownomiernie dyluja norme). Synonimy i prefiksy
    nie sa dodawane: dopasowanie metryki robi liczone boostem hint_terms."""
    idx = load_index()
    idf = idx["idf"]
    toks = textproc.tokenize(thesis)
    default_w = math.log(len(idx["docs"]) + 1) + 1.0
    bag: dict[str, float] = {}
    for t in toks:
        w = idf.get(t)
        bag[t] = bag.get(t, 0.0) + (w if w is not None else default_w)
    norm = math.sqrt(sum(v * v for v in bag.values())) or 1.0
    return {t: v / norm for t, v in bag.items()}


def retrieve(thesis: str, plan: dict[str, Any], top_k: int | None = None,
             exclude: set[str] | None = None) -> list[dict[str, Any]]:
    """Zwraca top-k zbiorow z wynikiem, uzasadnieniem i metadanymi."""
    # limit MAX_TOP_K dotyczy kart; planer moze poprosic o szersza liste kandydatow
    top_k = top_k or config.DEFAULT_TOP_K
    idx = load_index()
    catalog = load_catalog()
    qvec = _query_vector(thesis)
    regions = plan.get("regions") or []
    region_names = ", ".join(r["name"] for r in regions[:3])
    hints = set(plan.get("metric_hints", []))

    scored: list[dict[str, Any]] = []
    for ds_id, doc in idx["docs"].items():
        terms = doc["terms"]
        dnorm = doc["norm"]
        cos = sum(w * qvec[t] for t, w in terms.items() if t in qvec) / dnorm

        reasons: list[str] = []
        boost = 0.0
        meta = doc["meta"]
        if regions and meta.get("supports_regions"):
            boost += 0.35
            reasons.append(f"obsługuje region ({region_names})")
        if plan.get("global_scope") and not meta.get("supports_regions"):
            boost += 0.20
            reasons.append("zbiór globalny, a teza ma zakres globalny")
        # teza sięga wcześniejszych lat niż pokrycie zbioru (np. „od 1880", a
        # POWER od 1981) — kara, chyba że teza regionalna a zbiór regionalny
        # (wtedy klimat lokalny jest cenniejszy niż pełne pokrycie)
        t_info = plan.get("time") or {}
        t_start = int(t_info.get("start") or 0)
        cov_start = int((catalog[ds_id].get("coverage") or {}).get("start") or 0)
        if (t_start and cov_start and not t_info.get("default")
                and t_start < cov_start
                and not (regions and meta.get("supports_regions"))):
            boost -= 0.35
            reasons.append(f"teza sięga {t_start} r., zbiór dopiero od "
                           f"{cov_start} r.")
        hint_terms = {textproc.normalize(h) for h in catalog[ds_id].get("hint_terms", [])}
        hit = hints & hint_terms
        if hit:
            # im wiecej etykiet metryki pasuje, tym silniejszy sygnal
            # (teza o falach upalow: heat+extreme > sam "temperature")
            boost += min(0.15 + 0.10 * (len(hit) - 1), 0.35)
            reasons.append(f"pasuje do metryki: {', '.join(sorted(hit))}")
        if cos > 0.10:
            reasons.append("podobieństwo tekstowe tezy do opisu zbioru")

        scored.append({
            "id": ds_id,
            "score": round(cos + boost, 4),
            "cosine": round(cos, 4),
            "boost": round(boost, 4),
            "reasons": reasons,
            "meta": meta,
        })

    scored.sort(key=lambda d: d["score"], reverse=True)
    if exclude:
        scored = [d for d in scored if d["id"] not in exclude]
    # kara dla globalnych, gdy teza regionalna i istnieje alternatywa
    if regions and len(scored) > top_k:
        rest = scored[top_k:]
        scored = scored[:top_k] + [
            {**d, "score": round(d["score"] - 0.30, 4)} for d in rest
        ]
    return scored[:top_k]
