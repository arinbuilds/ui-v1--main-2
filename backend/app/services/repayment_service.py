"""Loan repayment-risk service — a completely separate pipeline from fraud.

    features (feature_store) -> XGBoost repayment model -> 0-100 score
    SHAP                     -> per-borrower explanation

The repayment score is never merged with the fraud score.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Borrower, Loan, Repayment, Transaction
from app.services import explanation_service, model_registry, rules
from app.services.feature_store import FEATURE_NAMES_BORROWER, build_repayment_features
from app.services.risk_config import (
    MODEL_FALLBACK,
    MODEL_XGBOOST,
    PREDICTION_FALLBACK,
    PREDICTION_OK,
    normalize_probability,
    risk_category,
)

logger = logging.getLogger("riskguard.repayment")

_cache_lock = threading.Lock()
_cache: dict | None = None


def invalidate_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


# ---------------------------------------------------------------------------
# context loading
# ---------------------------------------------------------------------------
def reference_time(db: Session) -> dt.datetime:
    """Stable 'now' for the demo dataset (latest transaction timestamp)."""
    latest = db.scalar(select(func.max(Transaction.ts)))
    return latest or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def load_context(db: Session, borrower_id: str) -> dict | None:
    borrower = db.get(Borrower, borrower_id)
    if borrower is None:
        return None
    loans = [
        _loan_dict(l)
        for l in db.scalars(select(Loan).where(Loan.borrower_id == borrower_id)).all()
    ]
    loan_ids = [l["id"] for l in loans]
    reps = []
    if loan_ids:
        reps = [
            _repayment_dict(r)
            for r in db.scalars(
                select(Repayment).where(Repayment.loan_id.in_(loan_ids)).order_by(Repayment.due_date)
            ).all()
        ]
    return {
        "borrower": _borrower_dict(borrower),
        "loans": loans,
        "repayments": reps,
        "now": reference_time(db),
    }


def _borrower_dict(b: Borrower) -> dict:
    return {
        "id": b.id,
        "account_id": b.account_id,
        "name": b.name,
        "city": b.city,
        "employer": b.employer,
        "occupation": b.occupation,
        "employment_years": b.employment_years,
        "employment_stable": b.employment_stable,
        "monthly_income": b.monthly_income,
        "monthly_spending": b.monthly_spending,
        "total_existing_debt": b.total_existing_debt,
        "credit_limit": b.credit_limit,
        "credit_utilization": b.credit_utilization,
        "income_history": b.income_history or [],
        "spending_history": b.spending_history or [],
        "repayment_score": b.repayment_score,
        "repayment_category": b.repayment_category,
        "repayment_model_used": b.repayment_model_used,
        "repayment_prediction_status": b.repayment_prediction_status,
        "repayment_confidence": b.repayment_confidence,
    }


def _loan_dict(l: Loan) -> dict:
    return {
        "id": l.id,
        "borrower_id": l.borrower_id,
        "principal": l.principal,
        "outstanding_amount": l.outstanding_amount,
        "purpose": l.purpose,
        "intended_use": l.intended_use,
        "interest_rate": l.interest_rate,
        "term_months": l.term_months,
        "monthly_emi": l.monthly_emi,
        "disbursed_at": l.disbursed_at,
        "status": l.status,
    }


def _repayment_dict(r: Repayment) -> dict:
    return {
        "id": r.id,
        "loan_id": r.loan_id,
        "due_date": r.due_date,
        "paid_date": r.paid_date,
        "amount": r.amount,
        "paid_amount": r.paid_amount,
        "status": r.status,
    }


# ---------------------------------------------------------------------------
# inference + fallback
# ---------------------------------------------------------------------------
def _feature_dict(vector: np.ndarray) -> dict[str, float]:
    return {name: float(vector[i]) for i, name in enumerate(FEATURE_NAMES_BORROWER)}


def predict_repayment(matrix: np.ndarray) -> dict:
    matrix = np.atleast_2d(np.asarray(matrix, dtype=np.float32))

    if model_registry.force_fallback():
        logger.warning("[model-fallback] RISKGUARD_FORCE_FALLBACK enabled for repayment scoring")
        return _rule_scores(matrix, MODEL_FALLBACK, PREDICTION_FALLBACK)

    artifact = model_registry.get_artifact("repayment")
    if artifact is None:
        return _rule_scores(matrix, MODEL_FALLBACK, PREDICTION_FALLBACK)

    try:
        proba = artifact["model"].predict_proba(matrix)[:, 1]
        if not np.all(np.isfinite(proba)):
            raise ValueError("model produced non-finite probabilities")
        scores = np.asarray([normalize_probability(p) for p in proba], dtype=float)
        return {
            "scores": scores,
            "probabilities": proba,
            "model_used": MODEL_XGBOOST,
            "prediction_status": PREDICTION_OK,
        }
    except Exception:
        logger.exception("[model-fallback] XGBoost repayment inference failed")
        return _rule_scores(matrix, MODEL_FALLBACK, PREDICTION_FALLBACK)


def _rule_scores(matrix: np.ndarray, model_used: str, status: str) -> dict:
    scores = []
    for row in matrix:
        s, _hits = rules.rule_score_repayment(_feature_dict(row))
        scores.append(float(s))
    return {
        "scores": np.asarray(scores, dtype=float),
        "probabilities": None,
        "model_used": model_used,
        "prediction_status": status,
    }


def explain(vector: np.ndarray, model_used: str) -> dict:
    if model_used == MODEL_XGBOOST:
        artifact = model_registry.get_artifact("repayment")
        if artifact is not None:
            return explanation_service.explain_prediction(
                artifact, vector, kind="borrower", top_n=8
            )
    features = _feature_dict(vector)
    hits = rules.rule_score_repayment(features)[1]
    factors = [
        {
            "feature": h["feature"],
            "label": h["label"],
            "value": explanation_service.format_feature_value(h["feature"], features.get(h["feature"], 0.0)),
            "contribution": round(float(h["weight"]), 4),
            "direction": "increase",
        }
        for h in hits
    ]
    factors.sort(key=lambda f: f["contribution"], reverse=True)
    return {"method": "rule", "factors": factors[:8], "base_value": 0.0}


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def _assemble(ctx: dict, vector: np.ndarray, prediction: dict, explained: dict, idx: int = 0) -> dict:
    borrower = ctx["borrower"]
    score = float(prediction["scores"][idx])
    model_used = prediction["model_used"]
    status = prediction["prediction_status"]
    proba = (
        float(prediction["probabilities"][idx])
        if prediction["probabilities"] is not None
        else None
    )
    category = risk_category(score)
    factors = explained["factors"]
    explanation = explanation_service.render_repayment_explanation(
        factors, int(score), category
    )

    if model_used == MODEL_XGBOOST and proba is not None:
        confidence = rules.band_confidence(proba)
        confidence_method = "xgboost_probability"
    else:
        confidence = rules.fallback_confidence(score)
        confidence_method = "rule_margin (model unavailable — not a model confidence)"

    return {
        "borrower_id": borrower["id"],
        "borrower_name": borrower["name"],
        "loan_ids": [l["id"] for l in ctx["loans"]],
        "score": int(round(score)),
        "risk_category": category,
        "model_used": model_used,
        "prediction_status": status,
        "confidence": confidence,
        "confidence_method": confidence_method,
        "explanation": explanation,
        "factors": factors,
        "base_value": explained["base_value"],
        "explanation_method": explained["method"],
        "indicators": _indicators(ctx, vector),
    }


def _indicators(ctx: dict, vector: np.ndarray) -> dict:
    f = _feature_dict(vector)
    return {
        "outstanding": float(np.expm1(f.get("log_outstanding", 0.0))),
        "monthly_emi": round(f.get("monthly_emi", 0.0), 2),
        "emi_to_income": round(f.get("emi_to_income", 0.0), 3),
        "loan_to_income": round(f.get("loan_to_income", 0.0), 3),
        "on_time_ratio": round(f.get("on_time_ratio", 1.0), 3),
        "missed_payments": int(f.get("missed_payments", 0)),
        "late_payments": int(f.get("late_payments", 0)),
        "partial_payments": int(f.get("partial_payments", 0)),
        "income_trend": round(f.get("income_trend", 0.0), 4),
        "spending_trend": round(f.get("spending_trend", 0.0), 4),
        "credit_utilization": round(f.get("credit_utilization", 0.0), 4),
        "debt_to_income": round(f.get("debt_to_income", 0.0), 4),
        "employment_years": round(f.get("employment_years", 0.0), 1),
        "employment_stable": bool(f.get("employment_stable", 1.0) >= 0.5),
        "recent_delinquency_30d": bool(f.get("recent_delinquency_30d", 0.0) >= 0.5),
        "monthly_income": ctx["borrower"]["monthly_income"],
        "monthly_spending": ctx["borrower"]["monthly_spending"],
    }


def score_borrower(db: Session, borrower_id: str) -> dict | None:
    """Fresh, on-demand repayment-risk prediction for one borrower."""
    ctx = load_context(db, borrower_id)
    if ctx is None:
        return None
    vector = build_repayment_features(
        ctx["borrower"], ctx["loans"], ctx["repayments"], now=ctx["now"]
    )
    prediction = predict_repayment(vector.reshape(1, -1))
    explained = explain(vector, prediction["model_used"])
    return _assemble(ctx, vector, prediction, explained)


def shap_explanation(db: Session, borrower_id: str) -> dict | None:
    """SHAP explanation payload for the UI (recomputed live in the ML layer)."""
    ctx = load_context(db, borrower_id)
    if ctx is None:
        return None
    vector = build_repayment_features(
        ctx["borrower"], ctx["loans"], ctx["repayments"], now=ctx["now"]
    )
    prediction = predict_repayment(vector.reshape(1, -1))
    explained = explain(vector, prediction["model_used"])
    analysis = _assemble(ctx, vector, prediction, explained)

    increasing = [f for f in explained["factors"] if f["direction"] == "increase"]
    decreasing = [f for f in explained["factors"] if f["direction"] == "decrease"]
    chart = [
        {
            "feature": f["feature"],
            "label": f["label"],
            "value": f["value"],
            "contribution": f["contribution"],
            "direction": f["direction"],
        }
        for f in sorted(explained["factors"], key=lambda f: f["contribution"])
    ]
    return {
        "borrower_id": borrower_id,
        "score": analysis["score"],
        "risk_category": analysis["risk_category"],
        "model_used": analysis["model_used"],
        "prediction_status": analysis["prediction_status"],
        "explanation_method": explained["method"],
        "base_value": explained["base_value"],
        "contributions": explained["factors"],
        "increasing": increasing,
        "decreasing": decreasing,
        "summary": analysis["explanation"],
        "chart": chart,
        "note": (
            "SHAP values explain the model's output for THIS borrower; they are not "
            "causal statements."
            if explained["method"] == "shap"
            else "SHAP unavailable — contributions attributed by deterministic rules."
        ),
    }


def score_all(db: Session) -> dict[str, dict]:
    """Batch scoring (seed pass)."""
    borrowers = db.scalars(select(Borrower)).all()
    if not borrowers:
        return {}
    now = reference_time(db)
    contexts: list[dict] = []
    vectors: list[np.ndarray] = []
    for b in borrowers:
        ctx = load_context(db, b.id)
        if ctx is None:
            continue
        ctx["now"] = now
        contexts.append(ctx)
        vectors.append(
            build_repayment_features(ctx["borrower"], ctx["loans"], ctx["repayments"], now=now)
        )
    if not vectors:
        return {}
    matrix = np.vstack(vectors)
    prediction = predict_repayment(matrix)

    shap_values = None
    if prediction["model_used"] == MODEL_XGBOOST:
        artifact = model_registry.get_artifact("repayment")
        if artifact is not None:
            try:
                from app.services.fraud_service import _resolve_shap_matrix

                shap_values = _resolve_shap_matrix(artifact, matrix)
            except Exception:
                logger.exception("batch SHAP for repayment failed")

    out: dict[str, dict] = {}
    for i, ctx in enumerate(contexts):
        if shap_values is not None:
            factors = explanation_service.top_factors(
                shap_values[i], matrix[i], FEATURE_NAMES_BORROWER,
                kind="borrower", top_n=8,
            )
            explained = {"factors": factors, "base_value": 0.0, "method": "shap"}
        else:
            explained = explain(matrix[i], prediction["model_used"])
        out[ctx["borrower"]["id"]] = _assemble(ctx, matrix[i], prediction, explained, idx=i)
    return out
