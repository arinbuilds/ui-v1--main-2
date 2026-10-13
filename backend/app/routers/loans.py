"""Loan endpoints — listing, detail, transaction-level loan usage analysis."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account, Borrower, Loan, Repayment, Transaction
from app.services import risk_config as rc

router = APIRouter(prefix="/loans", tags=["loans"])


@router.get("")
def list_loans(
    db: Session = Depends(get_db),
    borrower_id: Optional[str] = None,
    status: Optional[str] = None,
    purpose: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    stmt = select(Loan)
    if borrower_id:
        stmt = stmt.where(Loan.borrower_id == borrower_id)
    if status:
        stmt = stmt.where(Loan.status == status)
    if purpose:
        stmt = stmt.where(Loan.purpose == purpose)
    rows = list(db.scalars(stmt.order_by(Loan.disbursed_at.desc()).limit(limit)).all())

    names = {b.id: b.name for b in db.scalars(select(Borrower)).all()}
    overdue: dict[str, int] = {}
    for lid, cnt in db.execute(
        select(Repayment.loan_id, func.count(Repayment.id)).where(
            Repayment.status.in_(["missed", "late", "partial"])
        ).group_by(Repayment.loan_id)
    ).all():
        overdue[lid] = cnt

    return {
        "total": len(rows),
        "items": [
            {
                "id": l.id,
                "borrower_id": l.borrower_id,
                "borrower_name": names.get(l.borrower_id, l.borrower_id),
                "principal": l.principal,
                "outstanding_amount": l.outstanding_amount,
                "purpose": l.purpose,
                "interest_rate": l.interest_rate,
                "term_months": l.term_months,
                "monthly_emi": l.monthly_emi,
                "disbursed_at": l.disbursed_at.isoformat(),
                "status": l.status,
                "problem_repayments": overdue.get(l.id, 0),
            }
            for l in rows
        ],
    }


@router.get("/{loan_id}")
def loan_detail(loan_id: str, db: Session = Depends(get_db)) -> dict:
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="loan not found")
    reps = list(
        db.scalars(
            select(Repayment).where(Repayment.loan_id == loan_id).order_by(Repayment.due_date)
        ).all()
    )
    return {
        "id": loan.id,
        "borrower_id": loan.borrower_id,
        "principal": loan.principal,
        "outstanding_amount": loan.outstanding_amount,
        "purpose": loan.purpose,
        "interest_rate": loan.interest_rate,
        "term_months": loan.term_months,
        "monthly_emi": loan.monthly_emi,
        "disbursed_at": loan.disbursed_at.isoformat(),
        "status": loan.status,
        "repayments": [
            {
                "id": r.id,
                "due_date": r.due_date.isoformat(),
                "paid_date": r.paid_date.isoformat() if r.paid_date else None,
                "amount": r.amount,
                "paid_amount": r.paid_amount,
                "status": r.status,
            }
            for r in reps
        ],
        "stats": {
            "settled": sum(1 for r in reps if r.status == "paid"),
            "late": sum(1 for r in reps if r.status == "late"),
            "missed": sum(1 for r in reps if r.status == "missed"),
            "partial": sum(1 for r in reps if r.status == "partial"),
            "upcoming": sum(1 for r in reps if r.status == "upcoming"),
        },
    }


@router.get("/{loan_id}/usage")
def loan_usage(loan_id: str, db: Session = Depends(get_db), limit: int = 100) -> dict:
    """Transaction-level loan usage analysis.

    Tracks money around the loan events: disbursement -> subsequent spending
    (classified into broad categories) -> repayment.
    """
    loan = db.get(Loan, loan_id)
    if loan is None:
        raise HTTPException(status_code=404, detail="loan not found")

    borrower = db.get(Borrower, loan.borrower_id)
    account_id = borrower.account_id if borrower else None

    txs = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.loan_id == loan_id)
            .order_by(Transaction.ts)
        ).all()
    )
    names = {a.id: a.name for a in db.scalars(select(Account)).all()}

    disbursements = [t for t in txs if t.spend_category is None and t.purpose == "transfer" and t.amount >= loan.principal * 0.9]
    emi_txs = [t for t in txs if t.purpose == "loan_repayment"]
    spending = [t for t in txs if t.spend_category]

    buckets: dict[str, dict] = {}
    for t in spending:
        b = buckets.setdefault(
            t.spend_category, {"category": t.spend_category, "amount": 0.0, "count": 0}
        )
        b["amount"] += t.amount
        b["count"] += 1
    total_spend = sum(b["amount"] for b in buckets.values()) or 1.0
    breakdown = sorted(
        (
            {**b, "amount": round(b["amount"], 2), "share": round(b["amount"] / total_spend, 4)}
            for b in buckets.values()
        ),
        key=lambda x: x["amount"],
        reverse=True,
    )

    return {
        "loan_id": loan_id,
        "principal": loan.principal,
        "disbursed_at": loan.disbursed_at.isoformat(),
        "intended_use": loan.intended_use,
        "flow": {
            "disbursed_amount": round(sum(t.amount for t in disbursements), 2),
            "spent_amount": round(sum(t.amount for t in spending), 2),
            "repaid_amount": round(sum(t.amount for t in emi_txs), 2),
        },
        "spend_breakdown": breakdown,
        "transactions": [
            {
                "id": t.id,
                "ts": t.ts.isoformat(),
                "amount": t.amount,
                "direction": "out" if t.sender_account_id == account_id else "in",
                "counterparty": names.get(
                    t.receiver_account_id
                    if t.sender_account_id == account_id
                    else t.sender_account_id,
                    "?",
                ),
                "spend_category": t.spend_category,
                "purpose": t.purpose,
                "merchant_category": t.merchant_category,
                "channel": t.channel,
                "fraud_score": t.fraud_score,
                "is_anomaly": t.is_anomaly,
            }
            for t in txs[:limit]
        ],
        "category_labels": rc.SPEND_CATEGORIES,
        "note": "Spending categories are an ANALYTICAL classification of where the loan "
        "money went. A category by itself does not indicate risk or misuse.",
    }
