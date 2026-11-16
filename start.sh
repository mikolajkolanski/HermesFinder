#!/usr/bin/env bash
# Hermes Finder: FastAPI backend + frontend at http://127.0.0.1:8000
set -e
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
cd backend

if [ ! -d ".venv" ]; then
  echo "[setup] creating the virtual environment backend/.venv ..."
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet -r requirements.txt
else
  ./.venv/bin/python -c "import fastapi, uvicorn, httpx, numpy, scipy" 2>/dev/null || \
    ./.venv/bin/pip install --quiet -r requirements.txt
fi

echo "[start] http://0.0.0.0:7020  (Ctrl+C to stop)"
exec ./.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 7020
