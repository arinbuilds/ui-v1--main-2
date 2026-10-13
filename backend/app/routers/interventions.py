"""Interventions — recommendations, status workflow, history."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Alert, Intervention, Transaction, Borrower
from app.schemas import InterventionCreate, InterventionUpdate
from app.services import intervention_service, risk_config as rc

router = APIRouter(prefix="/interventions", tags=["interventions"])


@router.get("")
def list_interventions(
    db: Session = Depends(get_db),
    category: Optional[str] = None,
    status: Optional[str] = None,
    subject_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    rows = intervention_service.list_interventions(
        db, category=category, status=status, subject_id=subject_id
    )[:limit]
    counts = intervention_service.status_counts(db)
    return {
        "total": sum(counts.values()),
        "counts": counts,
        "items": [intervention_service.to_dict(r) for r in rows],
    }


@router.get("/history")
def intervention_history(db: Session = Depends(get_db), limit: int = 100) -> dict:
    return {"events": intervention_service.history_events(db, limit=limit)}


@router.get("/recommendations")
def recommendations_for(
    db: Session = Depends(get_db),
    subject_type: str = Query(..., pattern="^(transaction|borrower)$"),
    subject_id: str = ...,
) -> dict:
    """Suggested interventions for a transaction or borrower (not yet created)."""
    if subject_type == "transaction":
        tx = db.get(Transaction, subject_id)
        if tx is None:
            raise HTTPException(status_code=404, detail="transaction not found")
        analysis = {"score": tx.fraud_score, "anomaly": {"is_anomaly": tx.is_anomaly}}
        recs = intervention_service.recommend_for_fraud(analysis)
    else:
        b = db.get(Borrower, subject_id)
        if b is None:
            raise HTTPException(status_code=404, detail="borrower not found")
        recs = intervention_service.recommend_for_loan(
            {"score": b.repayment_score, "prediction_status": b.repayment_prediction_status},
            warning_level="high" if (b.repayment_score or 0) >= rc.FRAUD_SUSPICIOUS_THRESHOLD else "watch",
        )
    return {"subject_type": subject_type, "subject_id": subject_id, "recommendations": recs}


@router.post("", status_code=201)
def create_intervention(payload: InterventionCreate, db: Session = Depends(get_db)) -> dict:
    row = intervention_service.create(db, payload.model_dump())
    return intervention_service.to_dict(row)


@router.patch("/{intervention_id}")
def update_intervention(
    intervention_id: int, payload: InterventionUpdate, db: Session = Depends(get_db)
) -> dict:
    row = db.get(Intervention, intervention_id)
    if row is None:
        raise HTTPException(status_code=404, detail="intervention not found")
    row = intervention_service.update(db, row, payload.model_dump(exclude_none=True))
    return intervention_service.to_dict(row)
