"""Transaction endpoints — listing, detail and fresh fraud-risk prediction."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account, Transaction
from app.schemas import FraudAnalysis
from app.services import fraud_service, risk_config as rc

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _account_names(db: Session) -> dict[str, str]:
    return {a.id: a.name for a in db.scalars(select(Account)).all()}


def _item(row: Transaction, names: dict[str, str]) -> dict:
    return {
        "id": row.id,
        "ts": row.ts.isoformat(),
        "amount": row.amount,
        "channel": row.channel,
        "merchant_category": row.merchant_category,
        "purpose": row.purpose,
        "relationship": row.relationship,
        "city": row.city,
        "narrative": row.narrative,
        "counterparty_is_new": row.counterparty_is_new,
        "loan_id": row.loan_id,
        "spend_category": row.spend_category,
        "sender": {"id": row.sender_account_id, "name": names.get(row.sender_account_id, row.sender_account_id)},
        "receiver": {"id": row.receiver_account_id, "name": names.get(row.receiver_account_id, row.receiver_account_id)},
        "fraud_score": row.fraud_score,
        "risk_category": row.fraud_risk_category,
        "model_used": row.fraud_model_used,
        "prediction_status": row.fraud_prediction_status,
        "confidence": row.fraud_confidence,
        "decision": row.fraud_decision,
        "explanation": row.fraud_explanation,
        "anomaly": {
            "anomaly_score": row.anomaly_score,
            "is_anomaly": row.is_anomaly,
            "explanation": row.anomaly_explanation,
        },
        "scam": {
            "scam_category": row.scam_category,
            "label": rc.SCAM_LABELS.get(row.scam_category or "", row.scam_category),
            "confidence": row.scam_confidence,
            "model_used": row.scam_model_used,
            "explanation": row.scam_explanation,
        },
        "is_fraud_label": row.label_is_fraud,  # demo ground truth (synthetic dataset)
    }


@router.get("")
def list_transactions(
    db: Session = Depends(get_db),
    q: Optional[str] = Query(None, description="search id, narrative, merchant, account"),
    channel: Optional[str] = None,
    risk_category: Optional[str] = None,
    decision: Optional[str] = None,
    scam_category: Optional[str] = None,
    anomaly: Optional[bool] = None,
    model_used: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    account_id: Optional[str] = None,
    sort: str = Query("score", pattern="^(score|time|amount)$"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    filters = []
    if q:
        like = f"%{q.strip()}%"
        filters.append(
            or_(
                Transaction.id.ilike(like),
                Transaction.narrative.ilike(like),
                Transaction.merchant_category.ilike(like),
                Transaction.sender_account_id.ilike(like),
                Transaction.receiver_account_id.ilike(like),
                Transaction.city.ilike(like),
            )
        )
    if channel:
        filters.append(Transaction.channel == channel)
    if risk_category:
        filters.append(Transaction.fraud_risk_category == risk_category)
    if decision:
        filters.append(Transaction.fraud_decision == decision)
    if scam_category:
        filters.append(Transaction.scam_category == scam_category)
    if anomaly is not None:
        filters.append(Transaction.is_anomaly.is_(anomaly))
    if model_used:
        filters.append(Transaction.fraud_model_used == model_used)
    if min_score is not None:
        filters.append(Transaction.fraud_score >= min_score)
    if max_score is not None:
        filters.append(Transaction.fraud_score <= max_score)
    if account_id:
        filters.append(
            or_(
                Transaction.sender_account_id == account_id,
                Transaction.receiver_account_id == account_id,
            )
        )

    total = db.scalar(select(func.count(Transaction.id)).where(*filters)) or 0
    order = {
        "score": (Transaction.fraud_score.desc(), Transaction.ts.desc()),
        "time": (Transaction.ts.desc(),),
        "amount": (Transaction.amount.desc(),),
    }[sort]
    rows = list(
        db.scalars(
            select(Transaction)
            .where(*filters)
            .order_by(*order)
            .limit(limit)
            .offset(offset)
        ).all()
    )
    names = _account_names(db)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_item(r, names) for r in rows],
    }


@router.get("/{tx_id}")
def transaction_detail(tx_id: str, db: Session = Depends(get_db)) -> dict:
    row = db.get(Transaction, tx_id)
    if row is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    names = _account_names(db)
    payload = _item(row, names)
    payload["dataset_label"] = {
        # synthetic demo ground truth — shown for validation of the model output
        "is_fraud": row.label_is_fraud,
        "scam_category": row.label_scam_category,
        "note": "Ground truth exists only because the demo dataset is synthetic.",
    }
    return payload


@router.get("/{tx_id}/risk", response_model=FraudAnalysis)
def transaction_risk(tx_id: str, db: Session = Depends(get_db)) -> dict:
    """Fresh fraud-risk prediction (recomputed live by the ML layer)."""
    analysis = fraud_service.analyze_transaction(db, tx_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    return analysis
