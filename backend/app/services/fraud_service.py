"""Fraud & transaction risk service.

Pipeline for every transaction:
    features (feature_store) -> XGBoost fraud classifier -> 0-100 score
    features               -> Isolation Forest anomaly detection (separate signal)
    features               -> XGBoost scam-category classifier (suspicious only)
    SHAP                   -> explanation

The API route handlers stay thin: they only call into this service.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Transaction
from app.services import (
    anomaly_service,
    explanation_service,
    model_registry,
    rules,
    scam_classification_service,
)
from app.services.feature_store import FEATURE_NAMES_TX, TransactionFeatureBuilder, build_transaction_matrix
from app.services.risk_config import (
    MODEL_FALLBACK,
    MODEL_XGBOOST,
    PREDICTION_FALLBACK,
    PREDICTION_OK,
    fraud_decision,
    normalize_probability,
    risk_category,
)

logger = logging.getLogger("riskguard.fraud")

_cache_lock = threading.Lock()
_cache: dict | None = None


def invalidate_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


# ---------------------------------------------------------------------------
# data access (the only DB interaction of this service)
# ---------------------------------------------------------------------------
def _tx_to_dict(row: Transaction) -> dict:
    return {
        "id": row.id,
        "sender_account_id": row.sender_account_id,
        "receiver_account_id": row.receiver_account_id,
        "amount": float(row.amount),
        "channel": row.channel,
        "merchant_category": row.merchant_category,
        "purpose": row.purpose,
        "relationship": row.relationship,
        "counterparty_is_new": bool(row.counterparty_is_new),
        "city": row.city,
        "device_id": row.device_id,
        "narrative": row.narrative or "",
        "ts": row.ts,
        # demo stand-in for "previously flagged activity on record"
        "label_is_fraud": bool(row.label_is_fraud),
        "loan_id": row.loan_id,
        "spend_category": row.spend_category,
    }


def _tx_from_payload(payload: dict, ts) -> dict:
    return {
        "id": "PREDICTED",
        "sender_account_id": payload["sender_account_id"],
        "receiver_account_id": payload["receiver_account_id"],
        "amount": float(payload["amount"]),
        "channel": payload["channel"],
        "merchant_category": payload.get("merchant_category", "general"),
        "purpose": payload.get("purpose", "transfer"),
        "relationship": payload.get("relationship", "unknown"),
        "counterparty_is_new": bool(payload.get("counterparty_is_new") or False),
        "city": payload.get("city", "unknown"),
        "device_id": payload.get("device_id", "unknown"),
        "narrative": payload.get("narrative", ""),
        "ts": ts,
        "label_is_fraud": False,
        "loan_id": None,
        "spend_category": None,
    }


def load_dataset(db: Session) -> dict:
    """All transactions (chronological) + the full feature matrix.

    Row i of the matrix only ever used transactions < i (no time leakage).
    Cached because the analysis pass and the detail endpoints share it.
    """
    global _cache
    with _cache_lock:
        rows = db.scalars(
            select(Transaction).order_by(Transaction.ts, Transaction.id)
        ).all()
        if not rows:
            return {"txs": [], "matrix": np.zeros((0, len(FEATURE_NAMES_TX)), dtype=np.float32), "index": {}}
        key = (len(rows), rows[-1].id, str(rows[-1].ts))
        if _cache is not None and _cache.get("key") == key:
            return _cache
        txs = [_tx_to_dict(r) for r in rows]
        labels = [r.label_is_fraud for r in rows]
        matrix = build_transaction_matrix(txs, labels)
        _cache = {
            "key": key,
            "txs": txs,
            "matrix": matrix,
            "index": {t["id"]: i for i, t in enumerate(txs)},
        }
        return _cache


# ---------------------------------------------------------------------------
# model inference + fallback
# ---------------------------------------------------------------------------
def predict_fraud(matrix: np.ndarray) -> dict:
    """Batch fraud probabilities.

    Returns scores (0-100), probabilities (when the model produced them),
    model_used and prediction_status. Never raises because of a model issue.
    """
    matrix = np.atleast_2d(np.asarray(matrix, dtype=np.float32))

    if model_registry.force_fallback():
        logger.warning("[model-fallback] RISKGUARD_FORCE_FALLBACK enabled for fraud scoring")
        return _rule_scores(matrix, MODEL_FALLBACK, PREDICTION_FALLBACK)

    artifact = model_registry.get_artifact("fraud")
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
        logger.exception("[model-fallback] XGBoost fraud inference failed")
        return _rule_scores(matrix, MODEL_FALLBACK, PREDICTION_FALLBACK)


def _rule_scores(matrix: np.ndarray, model_used: str, status: str) -> dict:
    scores = []
    for row in matrix:
        feats = {n: float(row[i]) for i, n in enumerate(FEATURE_NAMES_TX)}
        s, _hits = rules.rule_score_fraud(feats)
        scores.append(float(s))
    return {
        "scores": np.asarray(scores, dtype=float),
        "probabilities": None,
        "model_used": model_used,
        "prediction_status": status,
    }


def _resolve_shap_matrix(artifact: dict, matrix: np.ndarray) -> np.ndarray | None:
    try:
        import shap

        explainer = shap.TreeExplainer(artifact["model"])
        raw = explainer.shap_values(np.asarray(matrix, dtype=np.float32))
        if isinstance(raw, list):
            raw = raw[1] if len(raw) > 1 else raw[0]
        arr = np.asarray(raw, dtype=float)
        if arr.ndim == 3:
            arr = arr[..., 1] if arr.shape[-1] > 1 else arr[..., 0]
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.shape != matrix.shape:
            raise ValueError(f"unexpected SHAP shape {arr.shape} != {matrix.shape}")
        return arr
    except Exception:
        logger.exception("batch SHAP failed — falling back to per-row explanation")
        return None


def explain_row(x_row: np.ndarray, model_used: str) -> dict:
    """Explanation for one row (SHAP when the model is available, rules otherwise)."""
    features = {n: float(x_row[i]) for i, n in enumerate(FEATURE_NAMES_TX)}
    if model_used == MODEL_XGBOOST:
        artifact = model_registry.get_artifact("fraud")
        if artifact is not None:
            result = explanation_service.explain_prediction(
                artifact, x_row, kind="transaction", top_n=8
            )
            return result
    hits = rules.rule_score_fraud(features)[1]
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
def _assemble(
    tx: dict,
    x_row: np.ndarray,
    score: float,
    model_used: str,
    prediction_status: str,
    probabilities: float | None,
    factors: list[dict],
    base_value: float,
    explanation_method: str,
    anomaly: dict,
    scam: dict,
) -> dict:
    category = risk_category(score)
    decision, note = fraud_decision(score, anomaly.get("is_anomaly", False))
    explanation = explanation_service.render_fraud_explanation(factors, int(score), category)

    if model_used == MODEL_XGBOOST and probabilities is not None:
        confidence = rules.band_confidence(float(probabilities))
        confidence_method = "xgboost_probability"
    else:
        confidence = rules.fallback_confidence(score)
        confidence_method = "rule_margin (model unavailable — not a model confidence)"

    return {
        "transaction_id": tx.get("id"),
        "score": int(round(score)),
        "risk_category": category,
        "model_used": model_used,
        "prediction_status": prediction_status,
        "confidence": confidence,
        "confidence_method": confidence_method,
        "explanation": explanation,
        "factors": factors,
        "base_value": base_value,
        "explanation_method": explanation_method,
        "decision": decision,
        "decision_note": note,
        "anomaly": anomaly,
        "scam": scam,
    }


def analyze_at(dataset: dict, idx: int, tx: dict | None = None) -> dict:
    """Full fraud analysis for one row of a prepared dataset."""
    tx = tx or dataset["txs"][idx]
    x_row = dataset["matrix"][idx]
    prediction = predict_fraud(x_row.reshape(1, -1))
    score = float(prediction["scores"][0])
    model_used = prediction["model_used"]
    status = prediction["prediction_status"]
    proba = (
        float(prediction["probabilities"][0])
        if prediction["probabilities"] is not None
        else None
    )
    explained = explain_row(x_row, model_used)
    anomaly = anomaly_service.detect(x_row)
    scam = scam_classification_service.classify(x_row, score)
    return _assemble(
        tx, x_row, score, model_used, status, proba,
        explained["factors"], explained["base_value"], explained["method"],
        anomaly, scam,
    )


def analyze_transaction(db: Session, tx_id: str) -> dict | None:
    """Recompute a fresh, full analysis for a stored transaction."""
    dataset = load_dataset(db)
    idx = dataset["index"].get(tx_id)
    if idx is None:
        return None
    return analyze_at(dataset, idx)


def analyze_payload(db: Session, payload: dict) -> dict:
    """Analyse an externally supplied (normalized) transaction payload."""
    dataset = load_dataset(db)
    base_txs = dataset["txs"]
    last_ts = base_txs[-1]["ts"] if base_txs else None
    ts = payload.get("ts")
    if ts is None:
        ts = (last_ts + dt.timedelta(minutes=1)) if last_ts else dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    new_tx = _tx_from_payload(payload, ts)

    combined = list(base_txs) + [new_tx]
    combined.sort(key=lambda t: (t["ts"], t["sender_account_id"], t["amount"]))
    labels = [t["label_is_fraud"] for t in combined]
    matrix = build_transaction_matrix(combined, labels)
    idx = next(i for i, t in enumerate(combined) if t["id"] == "PREDICTED")
    prepared = {"txs": combined, "matrix": matrix, "index": {}}
    return analyze_at(prepared, idx, tx=new_tx)


def score_all(db: Session) -> list[dict]:
    """Batch analysis for the seed pass — model inference and SHAP are
    vectorized, so 6k transactions score in seconds."""
    dataset = load_dataset(db)
    matrix = dataset["matrix"]
    if matrix.shape[0] == 0:
        return []

    prediction = predict_fraud(matrix)
    scores = prediction["scores"]
    model_used = prediction["model_used"]
    status = prediction["prediction_status"]
    probas = prediction["probabilities"]

    # SHAP for every row in one pass (falls back to rules on failure)
    shap_values = None
    if model_used == MODEL_XGBOOST:
        artifact = model_registry.get_artifact("fraud")
        if artifact is not None:
            shap_values = _resolve_shap_matrix(artifact, matrix)

    anomalies = anomaly_service.detect_matrix(matrix)[1]

    results: list[dict] = []
    for i, tx in enumerate(dataset["txs"]):
        x_row = matrix[i]
        if shap_values is not None:
            factors = explanation_service.top_factors(
                shap_values[i], x_row, FEATURE_NAMES_TX, kind="transaction", top_n=8
            )
            method = "shap"
            base_value = 0.0
        else:
            explained = explain_row(x_row, model_used)
            factors, method, base_value = (
                explained["factors"], explained["method"], explained["base_value"],
            )
        scam = scam_classification_service.classify(x_row, float(scores[i]))
        results.append(
            _assemble(
                tx, x_row, float(scores[i]), model_used, status,
                float(probas[i]) if probas is not None else None,
                factors, base_value, method, anomalies[i], scam,
            )
        )
    return results
