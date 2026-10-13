"""Alerts (fraud, anomaly, early-warning) endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Alert
from app.schemas import AlertUpdate

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "kind": a.kind,
        "severity": a.severity,
        "subject_type": a.subject_type,
        "subject_id": a.subject_id,
        "title": a.title,
        "message": a.message,
        "reasons": a.reasons or [],
        "score": a.score,
        "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("")
def list_alerts(
    db: Session = Depends(get_db),
    kind: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    subject_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    filters = []
    if kind:
        filters.append(Alert.kind == kind)
    if severity:
        filters.append(Alert.severity == severity)
    if status:
        filters.append(Alert.status == status)
    if subject_id:
        filters.append(Alert.subject_id == str(subject_id))

    total = db.scalar(select(func.count(Alert.id)).where(*filters)) or 0
    rows = list(
        db.scalars(
            select(Alert)
            .where(*filters)
            .order_by(Alert.created_at.desc(), Alert.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    counts = dict(
        db.execute(
            select(Alert.status, func.count(Alert.id)).group_by(Alert.status)
        ).all()
    )
    return {
        "total": total,
        "counts": counts,
        "items": [_dict(a) for a in rows],
    }


@router.get("/{alert_id}")
def alert_detail(alert_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(Alert, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="alert not found")
    return _dict(row)


@router.patch("/{alert_id}")
def update_alert(alert_id: int, payload: AlertUpdate, db: Session = Depends(get_db)) -> dict:
    row = db.get(Alert, alert_id)
    if row is None:
        raise HTTPException(status_code=404, detail="alert not found")
    if payload.status:
        row.status = payload.status
        db.commit()
        db.refresh(row)
    return _dict(row)
