@echo off
REM Hermes Finder: FastAPI backend + frontend at http://127.0.0.1:8000
cd /d "%~dp0backend"

if not exist ".venv" (
  echo [setup] creating the virtual environment backend\.venv ...
  python -m venv .venv
  call .venv\Scripts\pip install --quiet -r requirements.txt
)

echo [start] http://127.0.0.1:8000  (Ctrl+C to stop)
call .venv\Scripts\python -m uvicorn main:app --port 8000
