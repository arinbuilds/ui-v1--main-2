"""System / health endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.services import model_registry

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    models = model_registry.status()
    all_loaded = all(m["loaded"] for m in models.values())
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "database": db_status,
        "models": models,
        "model_summary": {
            "all_loaded": all_loaded,
            "forced_fallback": settings.force_fallback,
            "fallback_in_use": settings.force_fallback or not all_loaded,
        },
    }
