"""Central risk configuration — the SINGLE source of truth for thresholds,
categories and normalisation.

React must never redefine these thresholds; it only renders what the API returns.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 0-100 risk bands
# ---------------------------------------------------------------------------
RISK_BANDS: list[tuple[int, int, str, str]] = [
    (0, 30, "Low Risk", "low"),
    (31, 60, "Moderate Risk", "moderate"),
    (61, 80, "High Risk", "high"),
    (81, 100, "Critical Risk", "critical"),
]


def normalize_probability(p: float) -> int:
    """Map a model probability onto the canonical 0-100 risk score."""
    if p != p:  # NaN guard
        raise ValueError("model produced NaN probability")
    return int(round(min(max(float(p), 0.0), 1.0) * 100))


def risk_category(score: float) -> str:
    s = int(round(score))
    for lo, hi, label, _ in RISK_BANDS:
        if lo <= s <= hi:
            return label
    return "Critical Risk" if s > 100 else "Low Risk"


def risk_level(score: float) -> str:
    s = int(round(score))
    for lo, hi, _, level in RISK_BANDS:
        if lo <= s <= hi:
            return level
    return "critical" if s > 100 else "low"


# ---------------------------------------------------------------------------
# Fraud decision language (score vs. activity assessment kept distinct)
# ---------------------------------------------------------------------------
FRAUD_SUSPICIOUS_THRESHOLD = 61   # 61-100 => suspicious
FRAUD_REVIEW_THRESHOLD = 31       # 31-60  => review recommended

# Isolation Forest anomaly band (0-100 anomaly score)
ANOMALY_THRESHOLD = 65

DECISION_SUSPICIOUS = "suspicious"
DECISION_REVIEW = "review_recommended"
DECISION_LOW = "low_suspicion"


def fraud_decision(score: float, is_anomaly: bool = False) -> tuple[str, str]:
    """Return (decision, decision_note).

    A low score is explicitly NOT presented as a legitimacy certificate.
    """
    s = int(round(score))
    if s >= FRAUD_SUSPICIOUS_THRESHOLD or (is_anomaly and s >= FRAUD_REVIEW_THRESHOLD):
        return (
            DECISION_SUSPICIOUS,
            "Model evidence indicates suspicious activity. Treat as unverified until reviewed.",
        )
    if s >= FRAUD_REVIEW_THRESHOLD:
        return (
            DECISION_REVIEW,
            "Signals are mixed — analyst review recommended before accepting this activity.",
        )
    return (
        DECISION_LOW,
        "Low model suspicion. This is NOT a certification that the transaction is "
        "legitimate; it only means little fraud evidence was found in the available features.",
    )


# ---------------------------------------------------------------------------
# Enumerations shared by services + API
# ---------------------------------------------------------------------------
SCAM_CATEGORIES = [
    "phishing",
    "impersonation",
    "fake_refund",
    "investment_scam",
    "mule_account",
    "payment_request_scam",
]

SCAM_LABELS = {
    "phishing": "Phishing",
    "impersonation": "Impersonation",
    "fake_refund": "Fake Refund",
    "investment_scam": "Investment Scam",
    "mule_account": "Mule Account",
    "payment_request_scam": "Payment-Request Scam",
    "none": "Not Classified",
    "unknown": "Unclassified",
}

SPEND_CATEGORIES = [
    "Business",
    "Education",
    "Investment",
    "Essential",
    "Discretionary",
    "Transfer",
]

INTERVENTION_STATUSES = ["Pending", "In Progress", "Completed"]

ALERT_SEVERITIES = ["low", "medium", "high", "critical"]

PREDICTION_OK = "ok"
PREDICTION_FALLBACK = "fallback"
MODEL_XGBOOST = "xgboost"
MODEL_FALLBACK = "fallback"
MODEL_IFOREST = "isolation_forest"
MODEL_RULES = "rule_engine"

MODEL_STATUS_LABELS = {
    "xgboost": "XGBoost",
    "isolation_forest": "Isolation Forest",
    "fallback": "Rule-based fallback",
    "rule_engine": "Rule engine",
}
