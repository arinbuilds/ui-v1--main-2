"""Behavioural / transaction anomaly detection — Isolation Forest ONLY.

Role separation (strict):
    XGBoost          -> fraud classification
    XGBoost          -> repayment-risk prediction
    Isolation Forest -> transaction & behavioural anomaly detection

An anomaly is NOT automatically fraud: the anomaly output is only an input
signal to the wider fraud pipeline (and a separate panel in the UI).
"""
from __future__ import annotations

import logging

import numpy as np

from app.services import model_registry, rules
from app.services.feature_store import FEATURE_NAMES_TX
from app.services.risk_config import (
    ANOMALY_THRESHOLD,
    MODEL_FALLBACK,
    MODEL_IFOREST,
    MODEL_RULES,
    PREDICTION_FALLBACK,
    PREDICTION_OK,
)

logger = logging.getLogger("riskguard.anomaly")


def _feature_dict(x_row: np.ndarray) -> dict[str, float]:
    return {name: float(x_row[i]) for i, name in enumerate(FEATURE_NAMES_TX)}


def _build_result(score: float, drivers: list[str], model_used: str, status: str) -> dict:
    """Shared result assembler (keeps single-row and batch paths identical)."""
    score = float(np.clip(float(score), 0.0, 100.0))
    is_anomaly = score >= ANOMALY_THRESHOLD
    signal_text = "signals: " + ", ".join(drivers) if drivers else "no single behavioural signal dominated"
    if model_used == MODEL_FALLBACK:
        return {
            "anomaly_score": round(score, 1),
            "is_anomaly": is_anomaly,
            "model_used": MODEL_FALLBACK,
            "prediction_status": PREDICTION_FALLBACK,
            "drivers": drivers,
            "explanation": (
                "Isolation Forest unavailable — this anomaly score comes from the deterministic "
                f"rule engine ({signal_text}). Anomaly detection is separate from fraud "
                "classification: unusual behaviour alone does not prove fraud."
            ),
        }
    return {
        "anomaly_score": round(score, 1),
        "is_anomaly": is_anomaly,
        "model_used": MODEL_IFOREST,
        "prediction_status": PREDICTION_OK,
        "drivers": drivers,
        "explanation": (
            f"Isolation Forest anomaly score {round(score)}/100 against the user's normal "
            f"behaviour ({signal_text}). "
            + (
                "Behaviour deviates from this user's baseline."
                if is_anomaly
                else "Behaviour stays close to this user's baseline."
            )
            + " Anomaly ≠ fraud: unusual behaviour is an investigation signal, not a verdict."
        ),
    }


def detect(x_row: np.ndarray) -> dict:
    """Return the anomaly result for one transaction feature vector."""
    features = _feature_dict(x_row)

    artifact = None
    if not model_registry.force_fallback():
        artifact = model_registry.get_artifact("anomaly")

    if artifact is None:
        # ---- deterministic fallback (clearly flagged, never hidden) -------
        score, drivers = rules.anomaly_rules(features)
        logger.warning(
            "[model-fallback] Isolation Forest unavailable — rule-based anomaly score used"
        )
        return _build_result(score, drivers, MODEL_FALLBACK, PREDICTION_FALLBACK)

    # ---- Isolation Forest path -------------------------------------------
    try:
        model = artifact["model"]
        raw = float(model.decision_function(np.asarray(x_row, dtype=np.float32).reshape(1, -1))[0])
        hi = float(artifact.get("normal_anchor", 1.0))
        lo = float(artifact.get("anomaly_anchor", -1.0))
        span = (hi - lo) or 1.0
        score = float(np.clip((hi - raw) / span * 100.0, 0.0, 100.0))
        if score != score:
            raise ValueError("NaN anomaly score")
    except Exception:
        logger.exception("[model-fallback] Isolation Forest inference failed")
        score, drivers = rules.anomaly_rules(features)
        return _build_result(score, drivers, MODEL_FALLBACK, PREDICTION_FALLBACK)

    _rule_score, drivers = rules.anomaly_rules(features)
    return _build_result(score, drivers, MODEL_IFOREST, PREDICTION_OK)


def detect_matrix(matrix: np.ndarray) -> tuple[np.ndarray, list[dict]]:
    """Batch anomaly scoring (used by the seed analysis pass)."""
    results: list[dict] = []
    artifact = None if model_registry.force_fallback() else model_registry.get_artifact("anomaly")

    if artifact is None:
        for row in matrix:
            results.append(detect(row))
        return np.asarray([r["anomaly_score"] for r in results], dtype=float), results

    model = artifact["model"]
    hi = float(artifact.get("normal_anchor", 1.0))
    lo = float(artifact.get("anomaly_anchor", -1.0))
    span = (hi - lo) or 1.0
    raw = model.decision_function(np.asarray(matrix, dtype=np.float32))
    scores = np.clip((hi - raw) / span * 100.0, 0.0, 100.0)
    for i, row in enumerate(matrix):
        _rule_score, drivers = rules.anomaly_rules(_feature_dict(row))
        results.append(
            _build_result(float(scores[i]), drivers, MODEL_IFOREST, PREDICTION_OK)
        )
    return scores, results
