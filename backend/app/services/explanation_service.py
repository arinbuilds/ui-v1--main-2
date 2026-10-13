"""Explainable AI service — SHAP calculations + plain-language rendering.

SHAP runs HERE (Services/ML layer), never in React.
"""
from __future__ import annotations

import logging

import numpy as np

from app.services import model_registry

logger = logging.getLogger("riskguard.explain")

# ---------------------------------------------------------------------------
# Human readable feature labels
# ---------------------------------------------------------------------------
FEATURE_LABELS_TX: dict[str, str] = {
    "log_amount": "Transaction amount",
    "amount_ratio_mean": "Amount vs sender's usual value",
    "amount_ratio_p90": "Amount vs sender's 90th percentile",
    "amount_zscore": "Amount deviation (z-score)",
    "hour_of_day": "Time of day",
    "is_night": "Unusual hour (night)",
    "is_weekend": "Weekend transaction",
    "channel_code": "Payment channel",
    "merchant_code": "Merchant category",
    "purpose_code": "Stated purpose",
    "relationship_code": "Sender–receiver relationship",
    "counterparty_is_new": "First-time counterparty",
    "geo_deviation": "Geographic deviation",
    "device_change": "New device / behavioural change",
    "tx_count_24h": "Sender velocity (24h)",
    "tx_count_7d": "Sender velocity (7d)",
    "amount_sum_7d_log": "Sender volume (7d)",
    "hours_since_last": "Hours since previous transaction",
    "avg_interval_hours": "Usual gap between transactions",
    "log_user_mean_amount": "Sender's average amount",
    "counterparty_tx_count": "Prior dealings with counterparty",
    "counterparty_prior_fraud_rate": "Prior suspicious activity (counterparty)",
    "receiver_unique_senders": "Unique senders to counterparty",
    "receiver_in_tx_count": "Counterparty incoming transactions",
    "receiver_fraud_rate": "Prior suspicious activity (receiver)",
    "receiver_in_amount_7d_log": "Counterparty inflow (7d)",
    "is_round_amount": "Round amount",
    "amount_over_receiver_avg": "Amount vs counterparty average",
}

FEATURE_LABELS_BORROWER: dict[str, str] = {
    "log_outstanding": "Outstanding loan amount",
    "monthly_emi": "Monthly repayment obligation",
    "emi_to_income": "EMI-to-income ratio",
    "loan_to_income": "Loan-to-income ratio",
    "on_time_ratio": "On-time repayment history",
    "missed_payments": "Missed payments",
    "late_payments": "Late payments",
    "partial_payments": "Partial repayments",
    "recent_delinquency_30d": "Recent delinquency (30d)",
    "log_income": "Monthly income",
    "income_trend": "Income change",
    "income_volatility": "Income stability",
    "employment_years": "Employment tenure (years)",
    "employment_stable": "Employment stability",
    "existing_debt": "Existing debt",
    "debt_to_income": "Debt-to-income ratio",
    "credit_utilization": "Credit utilisation",
    "spending_trend": "Spending change",
    "spending_to_income": "Spending-to-income ratio",
    "active_loans": "Active loans",
    "avg_utilisation_pct": "Loan utilisation",
    "months_since_disbursement": "Months since disbursement",
}

_MONEY_HINTS = ("outstanding", "income", "debt", "emi", "amount")
_RATIO_HINTS = (
    "ratio", "utilization", "utilisation", "trend", "volatility",
    "rate", "share", "to_income",
)
_YES_NO = {
    "is_night", "is_weekend", "counterparty_is_new", "geo_deviation",
    "device_change", "is_round_amount", "employment_stable",
    "recent_delinquency_30d",
}


def format_feature_value(name: str, value: float) -> str:
    v = float(value)
    if name in _YES_NO:
        return "yes" if v >= 0.5 else "no"
    if name == "hour_of_day":
        h = int(v) % 24
        return f"{h:02d}:{int(round((v - int(v)) * 60)):02d}"
    if name == "channel_code":
        from app.services.feature_store import CHANNELS

        return CHANNELS[int(v)] if 0 <= int(v) < len(CHANNELS) else "unknown"
    if name == "merchant_code":
        from app.services.feature_store import MERCHANT_CATEGORIES

        return MERCHANT_CATEGORIES[int(v)] if 0 <= int(v) < len(MERCHANT_CATEGORIES) else "unknown"
    if name == "purpose_code":
        from app.services.feature_store import PURPOSES

        return PURPOSES[int(v)] if 0 <= int(v) < len(PURPOSES) else "unknown"
    if name == "relationship_code":
        from app.services.feature_store import RELATIONSHIPS

        return RELATIONSHIPS[int(v)] if 0 <= int(v) < len(RELATIONSHIPS) else "unknown"
    if name == "amount_zscore":
        return f"{v:+.1f}σ"
    if name in {"tx_count_24h", "tx_count_7d", "counterparty_tx_count",
                "receiver_unique_senders", "receiver_in_tx_count",
                "missed_payments", "late_payments", "partial_payments",
                "active_loans", "employment_years"}:
        return f"{v:.0f}"
    if "trend" in name or name.endswith("_rate") or name in _RATIO_HINTS:
        return f"{v * 100:+.0f}%" if abs(v) <= 5 else f"{v:.2f}"
    if any(h in name for h in _MONEY_HINTS) and "log_" not in name:
        if abs(v) >= 1000:
            return f"{v:,.0f}"
    if name.startswith("log_"):
        return f"₹{np.expm1(v):,.0f}"
    return f"{v:.2f}"


def _labels(kind: str) -> dict[str, str]:
    return FEATURE_LABELS_BORROWER if kind == "borrower" else FEATURE_LABELS_TX


# ---------------------------------------------------------------------------
# SHAP
# ---------------------------------------------------------------------------
def _resolve_vector(raw, n_features: int, class_index: int = 1) -> np.ndarray:
    if isinstance(raw, list):
        raw = raw[class_index] if len(raw) > class_index else raw[0]
    arr = np.asarray(raw, dtype=float)
    if arr.ndim == 2:
        arr = arr[0] if arr.shape[0] == 1 else arr.mean(axis=0)
    if arr.ndim != 1 or arr.size != n_features:
        arr = arr.reshape(-1)
        if arr.size != n_features:
            raise ValueError(f"unexpected SHAP output shape: {arr.size} != {n_features}")
    return arr


def _resolve_base(explainer, class_index: int = 1) -> float:
    ev = np.asarray(explainer.expected_value, dtype=float)
    if ev.ndim == 0:
        return float(ev)
    flat = ev.reshape(-1)
    return float(flat[min(class_index, flat.size - 1)])


def shap_contributions(
    artifact: dict, x_row: np.ndarray, class_index: int = 1
) -> tuple[np.ndarray, float]:
    """Compute SHAP contributions for one row. Raises on failure — callers
    decide whether to fall back."""
    import shap

    names = artifact.get("feature_names") or [f"f{i}" for i in range(x_row.size)]
    explainer = shap.TreeExplainer(artifact["model"])
    raw = explainer.shap_values(np.asarray(x_row, dtype=np.float32).reshape(1, -1))
    values = _resolve_vector(raw, len(names), class_index=class_index)
    base = _resolve_base(explainer, class_index=class_index)
    return values, base


def top_factors(
    contributions: np.ndarray,
    x_row: np.ndarray,
    feature_names: list[str],
    kind: str = "transaction",
    top_n: int = 8,
) -> list[dict]:
    labels = _labels(kind)
    factors = []
    for i, name in enumerate(feature_names):
        c = float(contributions[i])
        factors.append(
            {
                "feature": name,
                "label": labels.get(name, name.replace("_", " ")),
                "value": format_feature_value(name, float(x_row[i])),
                "contribution": round(c, 4),
                "direction": "increase" if c >= 0 else "decrease",
            }
        )
    factors.sort(key=lambda f: abs(f["contribution"]), reverse=True)
    return factors[:top_n]


def explain_prediction(
    artifact: dict,
    x_row: np.ndarray,
    kind: str = "transaction",
    top_n: int = 8,
) -> dict:
    """SHAP explanation with a deterministic rule-based safety net.

    Returns {"method": "shap"|"rule", "factors": [...], "base_value": float}
    """
    names = artifact.get("feature_names") or [f"f{i}" for i in range(x_row.size)]
    try:
        values, base = shap_contributions(artifact, x_row)
        return {
            "method": "shap",
            "factors": top_factors(values, x_row, names, kind=kind, top_n=top_n),
            "base_value": round(float(base), 4),
        }
    except Exception:
        logger.exception("SHAP explanation failed — using rule-based attribution")
        from app.services import rules

        contribs = rules.rule_attributions(
            dict(zip(names, [float(v) for v in x_row])), kind=kind
        )
        arr = np.asarray([contribs.get(n, 0.0) for n in names], dtype=float)
        return {
            "method": "rule",
            "factors": top_factors(arr, x_row, names, kind=kind, top_n=top_n),
            "base_value": 0.0,
        }


# ---------------------------------------------------------------------------
# Plain-language rendering (non-technical users)
# ---------------------------------------------------------------------------
def _phrase_tx(factor: dict) -> str:
    label = factor["label"].lower()
    value = factor["value"]
    return f"{label} ({value})"


def _phrase_borrower(factor: dict) -> str:
    name, value = factor["feature"], factor["value"]
    mapping = {
        "income_trend": "income declined" if value.startswith("-") else "income changed",
        "spending_trend": "spending increased" if value.startswith("+") else "spending changed",
        "missed_payments": "recent repayments were missed",
        "late_payments": "recent repayments were delayed",
        "partial_payments": "repayments were only partially made",
        "emi_to_income": "EMIs take up a large share of income",
        "loan_to_income": "loan burden is high relative to income",
        "debt_to_income": "existing debt increased relative to income",
        "credit_utilization": "credit cards are close to their limit",
        "on_time_ratio": "on-time repayment history weakened",
        "employment_stable": "employment is unstable",
        "income_volatility": "income is volatile",
        "spending_to_income": "spending grew relative to income",
        "recent_delinquency_30d": "a repayment slipped in the last 30 days",
        "existing_debt": "existing debt grew",
        "outstanding_amount": "outstanding loan balance is high",
        "avg_utilisation_pct": "loan utilisation is high",
    }
    return mapping.get(name, f"{factor['label'].lower()} ({value})")


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def render_fraud_explanation(factors: list[dict], score: int, category: str) -> str:
    increases = [f for f in factors if f["direction"] == "increase"][:3]
    decreases = [f for f in factors if f["direction"] == "decrease"][:2]
    parts = [f"Fraud risk score {score}/100 ({category})."]
    if increases:
        parts.append(
            "Driven by " + _join([_phrase_tx(f) for f in increases]) + "."
        )
    if decreases:
        parts.append(
            "Partially offset by " + _join([_phrase_tx(f) for f in decreases]) + "."
        )
    if not increases and not decreases:
        parts.append("No single dominant signal was found.")
    return " ".join(parts)


def render_repayment_explanation(factors: list[dict], score: int, category: str) -> str:
    increases = [f for f in factors if f["direction"] == "increase"][:3]
    decreases = [f for f in factors if f["direction"] == "decrease"][:2]
    parts = [f"Repayment risk score {score}/100 ({category})."]
    if increases:
        parts.append(
            "Repayment risk increased primarily because "
            + _join([_phrase_borrower(f) for f in increases]) + "."
        )
    if decreases:
        parts.append(
            "It was held down by " + _join([_phrase_borrower(f) for f in decreases]) + "."
        )
    return " ".join(parts)
