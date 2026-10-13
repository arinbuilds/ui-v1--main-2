#!/usr/bin/env bash
set -e

echo "[riskguard] waiting for database..."
python -m app.wait_for_db

echo "[riskguard] seeding demo data + training models (idempotent)..."
python -m app.seed

echo "[riskguard] starting FastAPI on :${API_PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT:-8000}" --reload
