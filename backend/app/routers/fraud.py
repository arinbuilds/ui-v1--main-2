"""Fraud-prediction endpoints for externally supplied transactions."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import FraudAnalysis, FraudPredictRequest
from app.services import fraud_service
from app.services import risk_config as rc

router = APIRouter(prefix="/fraud", tags=["fraud"])


@router.post("/predict", response_model=FraudAnalysis)
def predict_fraud(payload: FraudPredictRequest, db: Session = Depends(get_db)) -> dict:
    """Score a normalized transaction from any channel (UPI, wallet, card,
    digital banking). All ML inference happens in the services layer."""
    return fraud_service.analyze_payload(db, payload.model_dump())


@router.get("/scam-categories")
def scam_categories() -> dict:
    return {
        "categories": [
            {"key": k, "label": rc.SCAM_LABELS[k]} for k in rc.SCAM_CATEGORIES
        ],
        "note": "Categories are produced by the XGBoost multiclass scam classifier.",
    }


@router.get("/thresholds")
def thresholds() -> dict:
    """Central thresholds (single source of truth published to the UI)."""
    return {
        "risk_bands": [
            {"from": lo, "to": hi, "label": label, "level": level}
            for lo, hi, label, level in rc.RISK_BANDS
        ],
        "fraud_suspicious_threshold": rc.FRAUD_SUSPICIOUS_THRESHOLD,
        "fraud_review_threshold": rc.FRAUD_REVIEW_THRESHOLD,
        "anomaly_threshold": rc.ANOMALY_THRESHOLD,
        "decisions": {
            "suspicious": rc.DECISION_SUSPICIOUS,
            "review": rc.DECISION_REVIEW,
            "low": rc.DECISION_LOW,
        },
    }
