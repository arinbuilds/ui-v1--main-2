"""Early financial-stress detection (loan side).

Detects *changes* in a borrower's behaviour before a repayment problem turns
into a major delinquency, and always explains WHY the warning was raised.
"""
from __future__ import annotations

import numpy as np

# (code, label, base severity, predicate, message template)
def _trend(values: list[float]) -> float:
    if len(values) < 6:
        return 0.0
    head = float(np.mean(values[:3]))
    tail = float(np.mean(values[-3:]))
    if abs(head) < 1e-6:
        return 0.0
    return float(np.clip((tail - head) / abs(head), -3, 3))


def evaluate(borrower: dict, loans: list[dict], repayments: list[dict]) -> list[dict]:
    """Return the list of early-warning signals for one borrower."""
    signals: list[dict] = []

    income_hist = [float(v) for v in (borrower.get("income_history") or [])]
    spend_hist = [float(v) for v in (borrower.get("spending_history") or [])]
    income_trend = _trend(income_hist)
    spend_trend = _trend(spend_hist)
    income = max(float(borrower.get("monthly_income") or 0), 1.0)

    # 1. declining income
    if income_trend <= -0.05:
        signals.append(
            {
                "code": "declining_income",
                "label": "Declining income",
                "severity": "high" if income_trend <= -0.15 else "medium",
                "message": (
                    f"Average income of the last 3 months is {abs(income_trend) * 100:.0f}% "
                    f"below the first 3 months of the observed window."
                ),
                "evidence": {"income_trend": round(income_trend, 4)},
            }
        )

    # 2. increasing expenditure
    if spend_trend >= 0.10:
        signals.append(
            {
                "code": "rising_spending",
                "label": "Increasing expenditure",
                "severity": "high" if spend_trend >= 0.25 else "medium",
                "message": (
                    f"Monthly spending is up {spend_trend * 100:.0f}% over the observation "
                    f"window while income is {'falling' if income_trend < 0 else 'flat'}."
                ),
                "evidence": {"spending_trend": round(spend_trend, 4)},
            }
        )

    # 3. spending above income (cash-flow deficit)
    spending = float(borrower.get("monthly_spending") or 0.0)
    if spending > income:
        signals.append(
            {
                "code": "cashflow_deficit",
                "label": "Spending exceeds income",
                "severity": "high",
                "message": (
                    f"Monthly spending (₹{spending:,.0f}) exceeds monthly income "
                    f"(₹{income:,.0f}) — the borrower is financing the gap."
                ),
                "evidence": {"spending_to_income": round(spending / income, 3)},
            }
        )

    # 4. rising debt / credit dependence
    utilisation = float(borrower.get("credit_utilization") or 0.0)
    if utilisation >= 0.8:
        signals.append(
            {
                "code": "high_credit_utilisation",
                "label": "Heavy credit dependence",
                "severity": "high",
                "message": f"Credit utilisation is at {utilisation * 100:.0f}% of the assigned limit.",
                "evidence": {"credit_utilization": round(utilisation, 4)},
            }
        )
    elif utilisation >= 0.6:
        signals.append(
            {
                "code": "rising_credit_use",
                "label": "Rising credit dependence",
                "severity": "medium",
                "message": f"Credit utilisation has risen to {utilisation * 100:.0f}%.",
                "evidence": {"credit_utilization": round(utilisation, 4)},
            }
        )

    dti = float(borrower.get("total_existing_debt") or 0.0) / (income * 12)
    if dti > 0.6:
        signals.append(
            {
                "code": "high_debt_burden",
                "label": "Increasing debt",
                "severity": "medium",
                "message": f"Existing debt equals {dti * 100:.0f}% of annual income.",
                "evidence": {"debt_to_income": round(dti, 4)},
            }
        )

    # 5/6. late + partial repayments
    recent = [
        r
        for r in repayments
        if r.get("due_date") is not None and r.get("status") in {"late", "missed", "partial"}
    ]
    late = [r for r in recent if r["status"] == "late"]
    missed = [r for r in recent if r["status"] == "missed"]
    partial = [r for r in recent if r["status"] == "partial"]

    if late:
        signals.append(
            {
                "code": "late_repayments",
                "label": "Late repayments",
                "severity": "medium" if len(late) == 1 else "high",
                "message": f"{len(late)} repayment(s) were settled after the due date.",
                "evidence": {"late_payments": len(late)},
            }
        )
    if missed:
        signals.append(
            {
                "code": "missed_repayments",
                "label": "Missed repayments",
                "severity": "critical" if len(missed) >= 2 else "high",
                "message": f"{len(missed)} repayment(s) were missed entirely.",
                "evidence": {"missed_payments": len(missed)},
            }
        )
    if partial:
        signals.append(
            {
                "code": "partial_repayments",
                "label": "Partial repayments",
                "severity": "medium",
                "message": (
                    f"{len(partial)} repayment(s) were only partially settled — a common "
                    "early sign of liquidity stress."
                ),
                "evidence": {"partial_payments": len(partial)},
            }
        )

    # 7. significant deviation from historical behaviour
    if len(spend_hist) >= 6:
        history = spend_hist[:-1]
        mu, sigma = float(np.mean(history)), float(np.std(history)) or 1.0
        z = (spend_hist[-1] - mu) / sigma
        if z >= 1.5:
            signals.append(
                {
                    "code": "behaviour_deviation",
                    "label": "Behavioural deviation",
                    "severity": "medium",
                    "message": (
                        f"Latest-month spending is {z:.1f}σ above this borrower's own "
                        "historical pattern."
                    ),
                    "evidence": {"spending_z": round(float(z), 3)},
                }
            )

    # 8. employment instability
    if not borrower.get("employment_stable", True):
        signals.append(
            {
                "code": "employment_instability",
                "label": "Employment instability",
                "severity": "medium",
                "message": "Employment status is flagged as unstable in the profile.",
                "evidence": {"employment_years": borrower.get("employment_years")},
            }
        )

    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    signals.sort(key=lambda s: order.get(s["severity"], 0), reverse=True)
    return signals


def warning_level(signals: list[dict]) -> str:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    if not signals:
        return "none"
    top = max(order.get(s["severity"], 0) for s in signals)
    if top >= 3:
        return "critical"
    if top == 2 or len(signals) >= 4:
        return "high"
    if top == 1 or len(signals) >= 2:
        return "watch"
    return "low"


def summary(signals: list[dict]) -> str:
    if not signals:
        return "No early-warning indicators detected — behaviour is within this borrower's normal pattern."
    labels = [s["label"].lower() for s in signals[:4]]
    text = ", ".join(labels[:-1]) + (" and " + labels[-1] if len(labels) > 1 else labels[0])
    return (
        f"Early warning raised because of {text}. "
        "These are leading indicators — they do not by themselves mean the loan will default."
    )
