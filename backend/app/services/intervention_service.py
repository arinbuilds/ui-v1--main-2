"""Intervention engine.

Given a detected risk (fraud side or loan side) it recommends concrete
interventions, tracks status (Pending / In Progress / Completed) and keeps a
full history of every change.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Intervention
from app.services import risk_config as rc

# ---------------------------------------------------------------------------
# recommendation rules
# ---------------------------------------------------------------------------
FRAUD_ACTIONS = {
    "critical": [
        ("Temporarily restrict suspicious transaction", "Block/hold the transaction pending analyst confirmation."),
        ("Flag transaction for review", "Add to the fraud queue with the attached SHAP/rule explanation."),
        ("Trace money flow", "Follow the funds through connected accounts in the money-flow graph."),
        ("Investigate connected accounts", "Review counterparties sharing flows with this account."),
    ],
    "high": [
        ("Flag transaction for review", "Queue for analyst review with contextual explanation."),
        ("Warn the customer", "Send an out-of-band confirmation prompt to the sender."),
        ("Investigate connected accounts", "Review counterparties sharing flows with this account."),
    ],
    "medium": [
        ("Warn the customer", "Ask the customer to confirm intent before settling."),
        ("Monitor account behaviour", "Raise anomaly sensitivity for this account for 7 days."),
    ],
    "low": [
        ("Monitor account behaviour", "Continue observation; no customer-facing action required."),
    ],
}

LOAN_ACTIONS = {
    "critical": [
        ("Contact borrower", "Direct outreach from the collections/relationship manager."),
        ("Offer review of repayment terms", "Assess affordability before the next due date."),
        ("Consider restructuring options", "Evaluate step-down EMI / tenure extension."),
    ],
    "high": [
        ("Contact borrower", "Proactive call before the next instalment due date."),
        ("Schedule follow-up", "Book a follow-up after the next repayment attempt."),
        ("Send repayment reminder", "Automated reminder 3 days before due date."),
    ],
    "moderate": [
        ("Send repayment reminder", "Automated reminder before the due date."),
        ("Schedule follow-up", "Check in if the next instalment is not paid on time."),
    ],
    "watch": [
        ("Send repayment reminder", "Gentle reminder and offer of part-payment support."),
    ],
}


def recommend_for_fraud(analysis: dict) -> list[dict]:
    level = rc.risk_level(analysis.get("score", 0))
    actions = FRAUD_ACTIONS.get(level, FRAUD_ACTIONS["medium"])
    recs = [
        {"action": a, "description": d, "priority": level if level != "low" else "low"}
        for a, d in actions
    ]
    anomaly = analysis.get("anomaly") or {}
    if anomaly.get("is_anomaly") and level in {"low", "medium"}:
        recs.append(
            {
                "action": "Investigate behavioural anomaly",
                "description": "Isolation Forest flagged unusual behaviour — review before closing.",
                "priority": "medium",
            }
        )
    return recs


def recommend_for_loan(analysis: dict, warning_level: str = "none") -> list[dict]:
    level = rc.risk_level(analysis.get("score", 0))
    key = {"critical": "critical", "high": "high", "moderate": "moderate", "low": "watch"}[level]
    if warning_level in {"critical", "high"} and key in {"watch", "moderate"}:
        key = "high"
    actions = LOAN_ACTIONS.get(key, LOAN_ACTIONS["moderate"])
    recs = [{"action": a, "description": d, "priority": key} for a, d in actions]
    if analysis.get("prediction_status") == rc.PREDICTION_FALLBACK:
        recs.append(
            {
                "action": "Re-verify score once the model is healthy",
                "description": "This score came from the rule-based fallback — confirm with the XGBoost model before actioning.",
                "priority": "medium",
            }
        )
    return recs


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------
def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def to_dict(row: Intervention) -> dict:
    return {
        "id": row.id,
        "category": row.category,
        "action": row.action,
        "title": row.title,
        "description": row.description,
        "priority": row.priority,
        "subject_type": row.subject_type,
        "subject_id": row.subject_id,
        "status": row.status,
        "outcome": row.outcome,
        "history": row.history or [],
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def create(
    db: Session,
    payload: dict,
    status: str = "Pending",
    auto: bool = False,
) -> Intervention:
    now = _utcnow()
    row = Intervention(
        category=payload["category"],
        action=payload["action"],
        title=payload.get("title") or payload["action"],
        description=payload.get("description", ""),
        priority=payload.get("priority", "medium"),
        subject_type=payload.get("subject_type", "transaction"),
        subject_id=str(payload.get("subject_id", "")),
        status=status,
        history=[
            {
                "at": now.isoformat(timespec="seconds") + "Z",
                "event": "created",
                "to": status,
                "note": "Recommended automatically by the intervention engine."
                if auto
                else "Created manually by analyst.",
            }
        ],
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update(db: Session, row: Intervention, payload: dict) -> Intervention:
    now = _utcnow()
    history = list(row.history or [])
    changes = []
    if payload.get("status") and payload["status"] != row.status:
        changes.append({"event": "status_change", "from": row.status, "to": payload["status"]})
        row.status = payload["status"]
    if payload.get("outcome") is not None:
        row.outcome = payload["outcome"]
        changes.append({"event": "outcome_recorded", "to": payload["outcome"]})
    for change in changes:
        change["at"] = now.isoformat(timespec="seconds") + "Z"
        change["note"] = payload.get("note") or ""
        history.append(change)
    row.history = history
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def list_interventions(
    db: Session,
    category: str | None = None,
    status: str | None = None,
    subject_id: str | None = None,
) -> list[Intervention]:
    stmt = select(Intervention).order_by(Intervention.updated_at.desc())
    if category:
        stmt = stmt.where(Intervention.category == category)
    if status:
        stmt = stmt.where(Intervention.status == status)
    if subject_id:
        stmt = stmt.where(Intervention.subject_id == str(subject_id))
    return list(db.scalars(stmt).all())


def history_events(db: Session, limit: int = 100) -> list[dict]:
    events: list[dict] = []
    for row in db.scalars(select(Intervention)).all():
        for h in row.history or []:
            events.append(
                {
                    "intervention_id": row.id,
                    "action": row.action,
                    "category": row.category,
                    "subject_id": row.subject_id,
                    **h,
                }
            )
    events.sort(key=lambda e: e.get("at", ""), reverse=True)
    return events[:limit]


def status_counts(db: Session) -> dict:
    counts = {s: 0 for s in rc.INTERVENTION_STATUSES}
    for row in db.scalars(select(Intervention.status)).all():
        counts[row] = counts.get(row, 0) + 1
    return counts
