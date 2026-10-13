"""Scam-category classification.

Primary model: XGBoost multiclass (same model family required by the spec).
Fallback: deterministic rule heuristics, explicitly flagged as fallback.
"""
from __future__ import annotations

import logging

import numpy as np

from app.services import model_registry, rules
from app.services.feature_store import (
    CHANNELS,
    FEATURE_NAMES_TX,
    MERCHANT_CATEGORIES,
    PURPOSES,
    RELATIONSHIPS,
)
from app.services.risk_config import (
    MODEL_FALLBACK,
    MODEL_XGBOOST,
    PREDICTION_FALLBACK,
    PREDICTION_OK,
    SCAM_CATEGORIES,
    SCAM_LABELS,
)

logger = logging.getLogger("riskguard.scam")

SCAM_EXPLANATIONS = {
    "phishing": (
        "Payment to a first-time payee following an urgency/verification prompt, "
        "typically at an unusual hour and from a new device — consistent with phishing."
    ),
    "impersonation": (
        "Large, urgent transfer to a claimed family/friend contact that does not match "
        "the sender's usual pattern — consistent with impersonation of a known person."
    ),
    "fake_refund": (
        "Outbound 'fee' or 'verification' payment linked to a refund narrative with an "
        "unfamiliar counterparty — consistent with a fake-refund scam."
    ),
    "investment_scam": (
        "Large round-sum transfer to an investment/wealth counterparty promising returns, "
        "outside the sender's normal value band — consistent with an investment scam."
    ),
    "mule_account": (
        "Counterparty aggregates inflows from many unrelated senders and moves funds on "
        "quickly, including round-trip flows — consistent with mule-account activity."
    ),
    "payment_request_scam": (
        "Repeated small collect requests paid to a first-time payee in a short window — "
        "consistent with a payment-request scam."
    ),
    "none": "Fraud evidence was insufficient — no scam category assigned.",
    "unknown": "Model could not assign a scam category with usable confidence.",
}


def _feature_dict(x_row: np.ndarray) -> dict[str, float]:
    return {name: float(x_row[i]) for i, name in enumerate(FEATURE_NAMES_TX)}


def _rule_classify(features: dict[str, float]) -> tuple[str, float, str]:
    """Deterministic heuristics used only when the XGBoost scam model is missing."""
    def code(name, vocab):
        v = features.get(name, -1)
        return vocab[int(v)] if 0 <= int(v) < len(vocab) else ""

    merchant = code("merchant_code", MERCHANT_CATEGORIES)
    purpose = code("purpose_code", PURPOSES)
    relationship = code("relationship_code", RELATIONSHIPS)
    new_cp = features.get("counterparty_is_new", 0) >= 0.5
    night = features.get("is_night", 0) >= 0.5
    geo = features.get("geo_deviation", 0) >= 0.5
    device = features.get("device_change", 0) >= 0.5
    fan_in = features.get("receiver_unique_senders", 0) >= 4
    amount = np.expm1(features.get("log_amount", 0.0))
    amount_ratio = features.get("amount_ratio_mean", 1.0)

    if fan_in or features.get("receiver_in_tx_count", 0) >= 6:
        return "mule_account", 0.78, ""
    if purpose == "investment" or merchant in ("crypto_exchange", "gambling"):
        return "investment_scam", 0.74, ""
    if purpose == "refund" and amount_ratio > 1.4:
        return "fake_refund", 0.7, ""
    if amount < 2500 and new_cp and purpose == "transfer":
        return "payment_request_scam", 0.68, ""
    if relationship == "family" and (night or geo) and amount_ratio > 1.5:
        return "impersonation", 0.72, ""
    if new_cp and (night or device) and relationship in ("unknown", ""):
        return "phishing", 0.71, ""
    return "unknown", 0.5, ""


def classify(x_row: np.ndarray, fraud_score: float) -> dict:
    """Classify a *suspicious* transaction into a scam category."""
    features = _feature_dict(x_row)

    if fraud_score < 31:
        return {
            "scam_category": "none",
            "confidence": 0.0,
            "model_used": MODEL_XGBOOST,
            "prediction_status": PREDICTION_OK,
            "label": SCAM_LABELS["none"],
            "explanation": SCAM_EXPLANATIONS["none"],
        }

    artifact = None
    if not model_registry.force_fallback():
        artifact = model_registry.get_artifact("scam")

    if artifact is None:
        category, confidence, _ = _rule_classify(features)
        logger.warning("[model-fallback] scam classifier unavailable — rule heuristics used")
        return {
            "scam_category": category,
            "confidence": round(float(confidence), 3),
            "model_used": MODEL_FALLBACK,
            "prediction_status": PREDICTION_FALLBACK,
            "label": SCAM_LABELS.get(category, category),
            "explanation": SCAM_EXPLANATIONS.get(category, "")
            + " (Rule-based classification — XGBoost scam model unavailable.)",
        }

    try:
        model = artifact["model"]
        classes = artifact.get("classes") or list(SCAM_CATEGORIES)
        proba = model.predict_proba(np.asarray(x_row, dtype=np.float32).reshape(1, -1))[0]
        idx = int(np.argmax(proba))
        confidence = float(proba[idx])
        category = classes[idx] if idx < len(classes) else "unknown"
        if confidence != confidence:
            raise ValueError("NaN scam probability")
    except Exception:
        logger.exception("[model-fallback] scam model inference failed")
        category, confidence, _ = _rule_classify(features)
        return {
            "scam_category": category,
            "confidence": round(float(confidence), 3),
            "model_used": MODEL_FALLBACK,
            "prediction_status": PREDICTION_FALLBACK,
            "label": SCAM_LABELS.get(category, category),
            "explanation": SCAM_EXPLANATIONS.get(category, "")
            + " (Rule-based classification — XGBoost scam model inference failed.)",
        }

    if confidence < 0.40:
        category_final = "unknown"
        explanation = SCAM_EXPLANATIONS["unknown"]
    else:
        category_final = category
        explanation = SCAM_EXPLANATIONS.get(category, "")

    return {
        "scam_category": category_final,
        "confidence": round(confidence, 3),
        "model_used": MODEL_XGBOOST,
        "prediction_status": PREDICTION_OK,
        "label": SCAM_LABELS.get(category_final, category_final),
        "explanation": explanation,
    }
