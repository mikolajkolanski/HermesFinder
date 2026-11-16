"""Konfiguracja backendu climate-verifier."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR
CATALOG_PATH = BASE_DIR / "catalog" / "datasets.json"
# Katalog = NASA + zbiory zewnetrzne (ESA/Copernicus, NOAA, Met Office, firmy...)
CATALOG_PATHS = [CATALOG_PATH, BASE_DIR / "catalog" / "datasets_external.json"]

# ---- katalogi robocze (cache danych NASA, indeks RAG) -------------------
# Kolejnosc wyboru: zmienna srodowiskowa (CV_CACHE_DIR / CV_INDEX_PATH /
# CV_DATA_DIR) -> katalog domyslny obok kodu -> ~/.local/state/
# climate-verifier -> /tmp. Awaryjne przekierowanie jest niezbedne w
# pakiecie Nix (flake.nix): kod lezy w read-only /nix/store, wiec katalog
# data/ obok kodu nie nadaje sie na cache. Wrapper flake.nix ustawia
# zmienne srodowiskowe, ale backend radzi sobie tez bez nich (dowolny
# launcher, brak HOME itp.).


def _state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "climate-verifier"


def _writable(path: Path) -> bool:
    """Probe realnego zapisu: mkdir z exist_ok=True na istniejacym katalogu
    read-only nie rzucilby wyjatku, wiec probujemy zapis pliku probnego."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".cv-write-probe"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _redirect_notice(old: Path, new: Path, what: str) -> None:
    print(f"[config] {what} '{old}' nie jest zapisywalny "
          f"(np. read-only /nix/store) — przekierowano na '{new}'")


DATA_DIR = Path(os.environ.get("CV_DATA_DIR") or BASE_DIR / "data")

_cache_default = DATA_DIR / "cache"
_cache_env = os.environ.get("CV_CACHE_DIR")
CACHE_DIR = Path(_cache_env) if _cache_env else _cache_default
if not _writable(CACHE_DIR):
    _redirect_notice(CACHE_DIR, _state_dir() / "cache", "katalog cache")
    CACHE_DIR = _state_dir() / "cache"
    _writable(CACHE_DIR)

_index_default = DATA_DIR / "index.json"
_index_env = os.environ.get("CV_INDEX_PATH")
INDEX_PATH = Path(_index_env) if _index_env else _index_default
if not _writable(INDEX_PATH.parent):
    _redirect_notice(INDEX_PATH.parent, _state_dir() / "index.json", "indeks RAG")
    INDEX_PATH = _state_dir() / "index.json"
    _writable(INDEX_PATH.parent)

# Cache dla danych z API NASA (dni)
CACHE_TTL_DAYS = float(os.environ.get("CV_CACHE_TTL_DAYS", "7"))

# Ile zbiorow maksymalnie pokazujemy w jednej analizie
DEFAULT_TOP_K = 3
MAX_TOP_K = 5

# Domyslne okno czasowe (lata wstecz), gdy teza nie okresla okresu
DEFAULT_YEARS_BACK = 25

# Lata graniczne (uzywane tez gdy teza wspomnia o latach przed zakryciem danych)
MIN_YEAR = 1880          # GISTEMP od 1880
POWER_START_YEAR = 1981  # POWER od 1981-01-01

# Limit punktow siatki POWER: powyzej tego progu bbox-a probkujemy
# punktami, aby odpowiedz API nie byla gigantyczna
POWER_REGIONAL_MAX_POINTS = 600
POWER_SAMPLE_POINTS = 9

# Timeouty sieci
HTTP_TIMEOUT = 120.0

# --------------------------------------------------------------- LLM planner --
# Priorytet wyboru dostawcy: LLM_PROVIDER (gemini|openai|openrouter) lub
# automatycznie pierwszy dostepny klucz. Bez klucza dziala fallback TF-IDF.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "").strip().lower()
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "30"))       # na 1 model
LLM_TOTAL_BUDGET = float(os.environ.get("LLM_TOTAL_BUDGET", "60"))  # cala lista modeli

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")
# modele zapasowe, gdy glowny jest przeciazony (503) lub niedostepny (404)
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_FALLBACK_MODELS",
    "gemini-3.5-flash-lite,gemini-flash-lite-latest,gemini-3.1-flash-lite,"
    "gemini-3.8-flash"
).split(",") if m.strip()]

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")

# Rozgrzewanie cache wolnych zrodel (Mars MCD, REMS) w tle przy starcie
WARM_CACHE = os.environ.get("CV_WARM_CACHE", "1") != "0"

# Maksymalna liczba kart wykresow w jednej analizie
MAX_CARDS = 4

# Cache HTTP (user-agent wymagany przez niektore hosty)
USER_AGENT = "climate-verifier/1.0 (educational research tool)"

DISCLAIMER = (
    "Hermes Finder only provides data from source datasets (NASA, ESA/Copernicus, NOAA "
    "and other organisations) and a statistical description of it "
    "(trend, differences of means, ranges). It does not judge whether a claim is true: "
    "the interpretation and the decision are yours."
)
