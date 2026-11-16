"""FastAPI backend climate-verifier.

Uruchamianie (z katalogu backend/):
    uvicorn main:app --reload --port 8000

Endpointy:
    GET  /               -> frontend (statyczny, katalog ../frontend)
    GET  /api/health     -> status
    GET  /api/catalog    -> katalog zbiorow NASA (widoczny indeks)
    POST /api/analyze    -> {"thesis": "...", "options": {...}}
"""
from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import datetime as dt

from pydantic import BaseModel, Field, model_validator

import config
from analysis.pipeline import analyze
from rag import indexer
from rag.catalog import load_catalog

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(
    title="Hermes Finder API",
    description="Picks datasets (NASA, ESA/Copernicus, NOAA, Met Office, "
                "JMA, universities, non-profits, companies) for a claim about the climate "
                "of Earth or other planets and returns charts and statistics. "
                "It does not judge whether the claim is true.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeOptions(BaseModel):
    top_k: int = Field(default=3, ge=1, le=5)
    # lata obserwacji: 1850 (najstarsze serie) .. biezacy rok
    start_year: Optional[int] = Field(default=None, ge=1850)
    end_year: Optional[int] = Field(default=None, ge=1850)
    region_id: Optional[str] = None
    force_refresh: bool = False
    disable_llm: bool = False
    # kontekst zrodla tezy (np. tytul artykulu) - tylko do uzupelnienia
    # brakujacego miejsca/okresu, nigdy jako osobna teza
    context: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _check_years(self) -> "AnalyzeOptions":
        year_now = dt.date.today().year
        for name in ("start_year", "end_year"):
            v = getattr(self, name)
            if v is not None and v > year_now:
                raise ValueError(f"{name} must be between 1850 and {year_now}")
        if (self.start_year is not None and self.end_year is not None
                and self.start_year > self.end_year):
            raise ValueError("start_year must not be later than end_year")
        return self


class AnalyzeRequest(BaseModel):
    thesis: str = Field(min_length=4, max_length=600,
                        description="Teza o zmianie klimatu (PL/EN)")
    options: AnalyzeOptions = AnalyzeOptions()


@app.on_event("startup")
def build_index_on_startup() -> None:
    """Indeks RAG (index.json) powstaje raz przy starcie, jesli nie jest swiezy."""
    if not indexer.index_is_fresh():
        idx = indexer.build_index()
        print(f"[index] zbudowano indeks: {idx['n_docs']} dokumentow, "
              f"{idx['n_terms']} terminow")
    if config.WARM_CACHE:
        import threading
        threading.Thread(target=_warm_slow_sources, daemon=True).start()


def _warm_slow_sources() -> None:
    """W tle pobiera wolne zrodla (model MCD ~1 min, REMS, duze pliki ERA5),
    zeby pierwsze zapytanie uzytkownika nie czekalo. Bledy sa ignorowane."""
    from sources import climate, mars
    jobs = [lambda: mars.rems_climatology("max_temp"),
            lambda: climate.era5_pulse("2t_global"),
            lambda: mars.mcd_fetch_all("t"),
            lambda: mars.mcd_fetch_all("p")]
    for job in jobs:
        try:
            job()
        except Exception as exc:  # noqa: BLE001
            print(f"[warm] pominieto: {exc}")


@app.get("/api/health")
def health() -> dict[str, Any]:
    from rag.llm import llm_info
    info = llm_info()
    return {
        "status": "ok",
        "index_fresh": indexer.index_is_fresh(),
        "llm": {"available": info["available"],
                "provider": info["provider"], "model": info["model"]},
        "datasets": len(load_catalog()),
        "cache_ttl_days": config.CACHE_TTL_DAYS,
    }


@app.get("/api/catalog")
def catalog() -> dict[str, Any]:
    from sources.verify import load_report
    cat = load_catalog()
    report = (load_report() or {}).get("datasets", {})
    return {
        "count": len(cat),
        "datasets": [
            {
                "id": ds_id,
                "title": ds["title"],
                "description": ds["description"],
                "unit": ds["unit"],
                "category": ds.get("category"),
                "supports_regions": ds.get("supports_regions", False),
                "coverage": ds.get("coverage"),
                "source": ds.get("source"),
                "provider": ds.get("provider"),
                "topic": ds.get("topic"),
                "body": ds.get("body", "earth"),
                "data_type": ds.get("data_type"),
                "verified": (report.get(ds_id) or {}).get("ok"),
            }
            for ds_id, ds in cat.items()
        ],
        "providers": sorted({(ds.get("provider") or {}).get("org", "")
                             for ds in cat.values()} - {""}),
    }


@app.get("/api/stripes")
def stripes() -> dict[str, Any]:
    """Roczne anomalie NASA GISTEMP do paskow ocieplenia w naglowku strony."""
    from nasa import vitals
    rows = vitals.gistemp("global")["annual"]
    return {"source": "NASA GISTEMP v4", "baseline": "1951–1980",
            "years": [r["year"] for r in rows],
            "values": [r["value"] for r in rows]}


@app.get("/api/verification")
def verification() -> dict[str, Any]:
    """Ostatni raport weryfikacji zbiorow (python -m sources.verify)."""
    from sources.verify import load_report
    rep = load_report()
    if not rep:
        raise HTTPException(status_code=404,
                            detail="no report yet; run: python -m sources.verify")
    return rep


@app.post("/api/analyze")
def analyze_endpoint(req: AnalyzeRequest) -> JSONResponse:
    try:
        result = analyze(req.thesis, req.options.model_dump())
        return JSONResponse(content=result)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        raise HTTPException(status_code=500,
                            detail=f"analysis error: {exc}") from exc


# Frontend statyczny (ostatni, aby nie przysłaniać /api)
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True),
              name="frontend")
else:
    @app.get("/")
    def no_frontend() -> dict[str, str]:
        return {"message": "frontend not found; run uvicorn from the backend/ directory"}
