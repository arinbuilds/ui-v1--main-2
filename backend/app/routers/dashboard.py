"""Dashboard aggregation endpoint (all computation happens in the service layer)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db)) -> dict:
    return dashboard_service.summary(db)
