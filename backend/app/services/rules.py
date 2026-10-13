"""Deterministic rule engines.

Two purposes:
  1. model FALLBACK scoring when an XGBoost artifact is unavailable
     (clearly flagged as model_used="fallback" / prediction_status="fallback")
  2. human-readable signal attribution (which concrete signals fired)

Rules are intentionally simple and transparent — they are not a model and are
never presented as one.
"""
from __future__ import annotations

import numpy as np

from app.services import risk_config as rc

# ---------------------------------------------------------------------------
# Fraud fallback scoring (0-100)
# ---------------------------------------------------------------------------
_FRAUD_RULES: list[tuple[str, str, float, callable]] = [
    ("counterparty_is_new", "First-time counterparty", 11.0, lambda v: v >= 0.5),
    ("is_night", "Unusual hour (night)", 8.0, lambda v: v >= 0.5),
    ("geo_deviation", "Geographic deviation", 10.0, lambda v: v >= 0.5),
    ("device_change", "New device / behavioural change", 11.0, lambda v: v >= 0.5),
    ("amount_ratio_p90", "Amount far above sender's normal range", 15.0, lambda v: v >= 3.0),
    ("amount_ratio_p90", "Amount above sender's normal range", 7.0, lambda v: 1.6 <= v < 3.0),
    ("amount_zscore", "Extreme amount deviation", 8.0, lambda v: v >= 2.5),
    ("tx_count_24h", "Unusual transaction frequency (24h)", 12.0, lambda v: v >= 4),
    ("tx_count_7d", "Elevated weekly velocity", 6.0, lambda v: v >= 12),
    ("counterparty_prior_fraud_rate", "Counterparty previously flagged", 16.0, lambda v: v > 0.3),
    ("receiver_fraud_rate", "Receiver previously flagged", 12.0, lambda v: v > 0.2),
    ("receiver_unique_senders", "Fan-in pattern (many senders)", 8.0, lambda v: v >= 4),
    ("merchant_code", "High-risk merchant category", 8.0, lambda v: v in (10.0, 11.0)),
    ("is_round_amount", "Round amount with elevated value", 7.0, lambda v: v >= 0.5),
    ("hours_since_last", "Rapid repeat of activity", 5.0, lambda v: 0 <= v < 1),
    ("purpose_code", "Investment/transfer purpose", 6.0, lambda v: v in (5.0, 1.0)),
]


def rule_score_fraud(features: dict[str, float]) -> tuple[int, list[dict]]:
    """Deterministic rule-based fraud score (fallback only)."""
    score = 0.0
    hits: list[dict] = []
    for name, label, weight, predicate in _FRAUD_RULES:
        value = features.get(name)
        if value is None:
            continue
        try:
            fired = bool(predicate(float(value)))
        except (TypeError, ValueError):
            fired = False
        if fired:
            score += weight
            hits.append({"feature": name, "label": label, "weight": weight})
    # cross-rule: round amount only counts against a materially large transfer
    if features.get("amount_ratio_mean", 0) < 2:
        score -= 7.0
    final = int(round(min(max(score, 0.0), 100.0)))
    return final, hits


# ---------------------------------------------------------------------------
# Repayment fallback scoring (0-100)
# ---------------------------------------------------------------------------
_REPAY_RULES: list[tuple[str, str, float, callable]] = [
    ("missed_payments", "Missed repayments", 15.0, lambda v: v >= 2),
    ("missed_payments", "One missed repayment", 7.0, lambda v: v == 1),
    ("late_payments", "Repeated late repayments", 9.0, lambda v: v >= 2),
    ("partial_payments", "Partial repayments", 7.0, lambda v: v >= 2),
    ("on_time_ratio", "Weak on-time history (<60%)", 18.0, lambda v: v < 0.6),
    ("on_time_ratio", "Softening on-time history (<85%)", 9.0, lambda v: v < 0.85),
    ("recent_delinquency_30d", "Delinquency in last 30 days", 11.0, lambda v: v >= 0.5),
    ("emi_to_income", "EMIs exceed 60% of income", 17.0, lambda v: v > 0.6),
    ("emi_to_income", "EMIs exceed 40% of income", 9.0, lambda v: v > 0.4),
    ("income_trend", "Income declining sharply", 14.0, lambda v: v < -0.1),
    ("income_trend", "Income declining", 7.0, lambda v: v < -0.03),
    ("spending_trend", "Spending rising quickly", 8.0, lambda v: v > 0.15),
    ("credit_utilization", "Credit utilisation above 80%", 12.0, lambda v: v > 0.8),
    ("credit_utilization", "Credit utilisation above 50%", 6.0, lambda v: v > 0.5),
    ("debt_to_income", "Debt-to-income above 60%", 10.0, lambda v: v > 0.6),
    ("loan_to_income", "Loan-to-income above 1.5", 8.0, lambda v: v > 1.5),
    ("employment_stable", "Unstable employment", 6.0, lambda v: v < 0.5),
    ("employment_years", "Short employment tenure", 5.0, lambda v: v < 1.0),
    ("spending_to_income", "Spending above income", 9.0, lambda v: v > 1.0),
]


def rule_score_repayment(features: dict[str, float]) -> tuple[int, list[dict]]:
    """Deterministic rule-based repayment score (fallback only)."""
    score = 0.0
    hits: list[dict] = []
    for name, label, weight, predicate in _REPAY_RULES:
        value = features.get(name)
        if value is None:
            continue
        try:
            fired = bool(predicate(float(value)))
        except (TypeError, ValueError):
            fired = False
        if fired:
            score += weight
            hits.append({"feature": name, "label": label, "weight": weight})
    final = int(round(min(max(score, 0.0), 100.0)))
    return final, hits


def rule_attributions(features: dict[str, float], kind: str = "transaction") -> dict[str, float]:
    """Per-feature signed contributions used when SHAP is unavailable."""
    rules = _FRAUD_RULES if kind != "borrower" else _REPAY_RULES
    out: dict[str, float] = {}
    for name, _label, weight, predicate in rules:
        value = features.get(name)
        if value is None:
            continue
        try:
            if bool(predicate(float(value))):
                out[name] = out.get(name, 0.0) + weight
        except (TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# Anomaly rules — used as driver attribution AND as the anomaly fallback
# ---------------------------------------------------------------------------
_ANOMALY_RULES: list[tuple[str, str, float, callable]] = [
    ("amount_zscore", "Unusual transaction amount", 18.0, lambda v: v >= 2.0),
    ("amount_ratio_p90", "Amount above the user's normal band", 14.0, lambda v: v >= 2.5),
    ("is_night", "Unusual transaction timing", 12.0, lambda v: v >= 0.5),
    ("hours_since_last", "Abnormal gap since last activity", 8.0, lambda v: 0 <= v < 0.5),
    ("tx_count_24h", "Unusual transaction frequency", 16.0, lambda v: v >= 5),
    ("counterparty_is_new", "New counterparty", 14.0, lambda v: v >= 0.5),
    ("geo_deviation", "Geographic deviation", 13.0, lambda v: v >= 0.5),
    ("device_change", "Device / behavioural change", 13.0, lambda v: v >= 0.5),
    ("receiver_unique_senders", "Counterparty receives from many senders", 10.0, lambda v: v >= 5),
    ("amount_over_receiver_avg", "Amount unusual for this counterparty", 9.0, lambda v: v >= 6.0),
]


def anomaly_rules(features: dict[str, float]) -> tuple[int, list[str]]:
    """Deterministic anomaly signal aggregation (also the fallback scorer)."""
    score = 0.0
    drivers: list[str] = []
    for _name, label, weight, predicate in _ANOMALY_RULES:
        # amount-based signals double up; apply half weight once both fire
        value = features.get(_name)
        if value is None:
            continue
        try:
            fired = bool(predicate(float(value)))
        except (TypeError, ValueError):
            fired = False
        if fired:
            score += weight
            drivers.append(label)
    if (
        features.get("amount_zscore", 0) >= 2.0
        and features.get("amount_ratio_p90", 0) >= 2.5
    ):
        score -= 8.0  # one underlying amount deviation, not two
    return int(round(min(max(score, 0.0), 100.0))), drivers


def fallback_confidence(score: float) -> float:
    """Deterministic rule-margin confidence (never presented as model confidence)."""
    return round(min(0.55 + abs(float(score) - 50.0) / 150.0, 0.95), 3)


def clip_score(value: float) -> int:
    return int(round(min(max(float(value), 0.0), 100.0)))


def band_confidence(probability: float) -> float:
    """Confidence of the predicted class for a binary probability."""
    p = float(np.clip(probability, 0.0, 1.0))
    return round(max(p, 1.0 - p), 3)
